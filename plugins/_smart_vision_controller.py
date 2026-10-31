"""
plugins/_smart_vision_controller.py — Central state machine and orchestrator for Smart Vision.

Enforces:
1. Mutual exclusion: only one active vision operation at a time.
2. Two-stage explicit consent: separate capture approval and transmission approval.
3. Three duration tiers: 'once', 'session', 'always'.
4. Ephemeral in-memory capture artifact retention with short TTL.
5. Immediate cancellation, revocation, and resource cleanup on abort, timeout, or shutdown.
6. Sanitized logging (no pixels, base64, or sensitive extracted text).
7. Integration with PluginRuntime lifecycle.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Optional

from core.outcome import failed, started
from core.plugin_runtime import HostContext, PluginRuntime
from plugins._smart_vision_analyzer import SmartVisionAnalyzer
from plugins._smart_vision_capture import CaptureArtifact, ScreenCapturer
from plugins._smart_vision_permissions import PermissionManager, get_shared_permission_manager
from ui_vision import VisionConsentBridge, VisionState, get_vision_bridge


class SmartVisionController(PluginRuntime):
    """Orchestrates capture, permissions, UI consent, and analysis."""

    def __init__(self, context: Optional[HostContext] = None,
                 bridge: Optional[VisionConsentBridge] = None,
                 permissions: Optional[PermissionManager] = None,
                 capture_ttl_s: float = 60.0):
        super().__init__(name="smart_vision", context=context)
        self.bridge = bridge or get_vision_bridge()
        self.permissions = permissions or get_shared_permission_manager()
        self.capturer = ScreenCapturer()
        self.analyzer = SmartVisionAnalyzer()
        self.capture_ttl_s = capture_ttl_s

        self._active_lock = threading.Lock()
        self._is_busy = False
        self._last_op_time = 0.0
        self._cooldown_s = 2.0

        self._current_cancel_event = threading.Event()
        self._last_capture: Optional[CaptureArtifact] = None
        self._last_capture_time = 0.0

        # Register cancellation callback on bridge
        self.bridge.set_handlers(cancel_handler=self.cancel)

    def is_busy(self) -> bool:
        with self._active_lock:
            return self._is_busy

    def get_state(self) -> VisionState:
        return self.bridge.state

    def cancel(self, reason: str = "cancelled") -> None:
        """Cancel active operation immediately and release resources."""
        self._current_cancel_event.set()
        self.permissions.revoke_all(clear_persistent=False)
        self._cleanup_capture()
        self.bridge.set_state(VisionState.CANCELLED, reason)
        self.context.log(f"[SmartVision] 🛑 Operation cancelled: {reason}")

    def revoke_permissions(self, clear_persistent: bool = True) -> None:
        """Revoke all permissions immediately, invalidate in-flight work, and optionally wipe saved config."""
        self.cancel("permissions_revoked")
        self.permissions.revoke_all(clear_persistent=clear_persistent)
        self.context.log(f"[SmartVision] 🛡️ Permissions revoked (persistent={clear_persistent})")

    def cancel_all(self) -> None:
        self.cancel("system_cancel_all")

    def shutdown(self) -> None:
        """Plugin shutdown: cancel all work, cleanup memory, set state to OFF."""
        super().shutdown()
        self.cancel("plugin_shutdown")
        self.bridge.set_state(VisionState.OFF, "Plugin stopped")

    def _cleanup_capture(self) -> None:
        """Drop references to image bytes to allow immediate GC."""
        self._last_capture = None
        self._last_capture_time = 0.0

    def get_last_capture(self) -> Optional[CaptureArtifact]:
        """Return cached capture only if still within TTL."""
        if self._last_capture is not None:
            if (time.monotonic() - self._last_capture_time) <= self.capture_ttl_s:
                return self._last_capture
            self._cleanup_capture()
        return None

    def execute_vision_request(self, question: str, target: str = "screen",
                               region: Optional[str] = None,
                               destination: Optional[str] = None,
                               deadline_s: float = 30.0) -> str:
        """Full pipeline: consent check -> capture -> consent check -> analysis -> outcome."""
        now = time.monotonic()
        with self._active_lock:
            if not self.is_running:
                return failed("smart_vision", "Smart Vision plugin is disabled or stopped.")
            if self._is_busy:
                return failed("smart_vision", "Another visual analysis is currently in progress.")
            if (now - self._last_op_time) < self._cooldown_s:
                return failed("smart_vision", "Cooldown active. Please wait a moment before requesting another capture.")
            self._is_busy = True
            self._current_cancel_event.clear()

        start_time = time.monotonic()
        dest = (destination or "gemini-2.5-flash").strip()
        self.context.log(f"[SmartVision] 🔍 Starting request: target='{target}', dest='{dest}'")

        try:
            # ─────────────────────────────────────────────────────────────────
            # Stage 1: Local Capture Authorization
            # ─────────────────────────────────────────────────────────────────
            if self._current_cancel_event.is_set():
                return failed("smart_vision", "Operation cancelled before capture.")

            self.context.log(f"[SmartVision] 🛡️ Checking capture consent for target '{target}'...")
            capture_choice = self.bridge.request_capture_consent(target=target, timeout_s=15.0, source="screen")
            if not capture_choice or self._current_cancel_event.is_set():
                self.bridge.set_state(VisionState.CANCELLED, "Capture consent denied")
                self.context.log("[SmartVision] ❌ Capture consent denied or timed out.")
                return failed("smart_vision", "Screen capture authorization was denied or timed out by the user.")

            capture_grant = self.permissions.create_capture_grant(source="screen", target=target, ttl_s=self.capture_ttl_s)
            if not self.permissions.validate_capture_grant(capture_grant, source="screen", target=target):
                return failed("smart_vision", "Internal permission validation failed for capture.")

            # ─────────────────────────────────────────────────────────────────
            # Stage 2: In-Memory Capture
            # ─────────────────────────────────────────────────────────────────
            if self._current_cancel_event.is_set():
                return failed("smart_vision", "Operation cancelled before screen grab.")

            self.bridge.set_state(VisionState.CAPTURING, f"Grabbing {target}")
            try:
                artifact = self.capturer.capture(target=target, region=region)
            except Exception as e:
                self.bridge.set_state(VisionState.ERROR, str(e))
                self.context.log(f"[SmartVision] ⚠️ Capture error: {e}")
                return failed("smart_vision", f"Screen capture failed: {e}")

            if self._current_cancel_event.is_set():
                self._cleanup_capture()
                return failed("smart_vision", "Operation cancelled during screen grab.")

            self._last_capture = artifact
            self._last_capture_time = time.monotonic()
            self.context.log(
                f"[SmartVision] 📸 Captured {artifact.width}x{artifact.height} ({artifact.size_bytes():,} bytes, SHA: {artifact.sha256[:8]}...)"
            )

            # ─────────────────────────────────────────────────────────────────
            # Stage 3: Remote Transmission Authorization
            # ─────────────────────────────────────────────────────────────────
            if self._current_cancel_event.is_set():
                self._cleanup_capture()
                return failed("smart_vision", "Operation cancelled before transmission.")

            self.context.log(f"[SmartVision] 🛡️ Checking send consent for destination '{dest}'...")
            send_choice = self.bridge.request_send_consent(
                target=target,
                destination=dest,
                preview_artifact=artifact,
                timeout_s=20.0,
                capture_id=artifact.id,
                sha256=artifact.sha256,
            )
            if not send_choice or self._current_cancel_event.is_set():
                self.bridge.set_state(VisionState.CANCELLED, "Send consent denied")
                self.context.log("[SmartVision] ❌ Transmission consent denied or timed out.")
                self._cleanup_capture()
                return failed(
                    "smart_vision",
                    f"Authorization to transmit screen capture to '{dest}' was denied or timed out."
                )

            send_grant = self.permissions.create_send_grant(
                capture_id=artifact.id,
                sha256=artifact.sha256,
                destination=dest,
                ttl_s=self.capture_ttl_s,
            )
            if not self.permissions.validate_send_grant(send_grant, artifact.id, artifact.sha256, dest):
                self._cleanup_capture()
                return failed("smart_vision", "Internal permission validation failed for transmission.")

            # ─────────────────────────────────────────────────────────────────
            # Stage 4: Visual Analysis via Authorized Model
            # ─────────────────────────────────────────────────────────────────
            if self._current_cancel_event.is_set():
                self._cleanup_capture()
                return failed("smart_vision", "Operation cancelled before analysis.")

            self.bridge.set_state(VisionState.ANALYZING, f"Analyzing with {dest}")
            time_spent = time.monotonic() - start_time
            remaining_deadline = max(5.0, deadline_s - time_spent)

            outcome_str = self.analyzer.analyze(
                artifact=artifact,
                question=question,
                destination=dest,
                deadline_s=remaining_deadline,
            )

            if self._current_cancel_event.is_set():
                self._cleanup_capture()
                return failed("smart_vision", "Analysis cancelled while waiting for model.")

            self.bridge.set_state(VisionState.OFF, "Analysis complete")
            duration = time.monotonic() - start_time
            self.context.log(f"[SmartVision] ✅ Completed analysis in {duration:.2f}s")
            return outcome_str

        finally:
            with self._active_lock:
                self._is_busy = False
                self._last_op_time = time.monotonic()
            self.permissions.prune_expired()
