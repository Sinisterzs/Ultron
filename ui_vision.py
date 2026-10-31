"""
ui_vision.py — UI bridge, consent coordinator, and state notifications for Smart Vision.

Coordinates human consent for:
1. Screen capture authorization (local).
2. Remote transmission authorization (model/destination).

Provides non-blocking state updates and cancellation hooks without altering
VOID OS or crystal designs.
"""
from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Any, Callable, Optional


class VisionState(str, Enum):
    OFF = "OFF"
    AWAITING_CAPTURE = "AWAITING_CAPTURE"
    CAPTURING = "CAPTURING"
    AWAITING_SEND = "AWAITING_SEND"
    ANALYZING = "ANALYZING"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


class VisionConsentBridge:
    """Thread-safe bridge between Smart Vision controller and UI/user."""

    def __init__(self, pm: Optional[Any] = None):
        self._pm = pm
        self._state = VisionState.OFF
        self._state_listeners: list[Callable[[VisionState, str], None]] = []
        self._capture_consent_handler: Optional[Callable[[str, float], Any]] = None
        self._send_consent_handler: Optional[Callable[[str, str, Any, float], Any]] = None
        self._cancel_handler: Optional[Callable[[str], None]] = None
        self._lock = threading.Lock()

    def _get_pm(self):
        if self._pm is not None:
            return self._pm
        from plugins._smart_vision_permissions import get_shared_permission_manager
        return get_shared_permission_manager()

    @property
    def state(self) -> VisionState:
        with self._lock:
            return self._state

    def set_state(self, new_state: VisionState, detail: str = "") -> None:
        with self._lock:
            self._state = new_state
            listeners = list(self._state_listeners)
        for listener in listeners:
            try:
                listener(new_state, detail)
            except Exception:
                pass

    def add_state_listener(self, listener: Callable[[VisionState, str], None]) -> None:
        with self._lock:
            if listener not in self._state_listeners:
                self._state_listeners.append(listener)

    def remove_state_listener(self, listener: Callable[[VisionState, str], None]) -> None:
        with self._lock:
            if listener in self._state_listeners:
                self._state_listeners.remove(listener)

    def set_handlers(self,
                     capture_handler: Optional[Callable[[str, float], Any]] = None,
                     send_handler: Optional[Callable[[str, str, Any, float], Any]] = None,
                     cancel_handler: Optional[Callable[[str], None]] = None) -> None:
        """Register UI or test handlers for consent and cancellation."""
        with self._lock:
            if capture_handler is not None:
                self._capture_consent_handler = capture_handler
            if send_handler is not None:
                self._send_consent_handler = send_handler
            if cancel_handler is not None:
                self._cancel_handler = cancel_handler

    def request_capture_consent(self, target: str, timeout_s: float = 30.0,
                                source: str = "screen") -> str:
        """Request explicit human authorization to capture the screen/camera.
        Returns duration choice ('once', 'session', 'always') or '' if denied/cancelled.
        """
        pm = self._get_pm()
        if pm.has_capture_permission(source=source, target=target):
            return "session"

        self.set_state(VisionState.AWAITING_CAPTURE, f"Target: {target}")
        handler = self._capture_consent_handler
        if handler is None:
            # Default safe policy: when unconfigured, do not capture without explicit consent handler
            self.set_state(VisionState.CANCELLED, "No consent handler registered")
            return ""

        try:
            raw = handler(target, timeout_s)
            if raw is True:
                choice = "once"
            elif isinstance(raw, str) and raw.strip().lower() in ("once", "session", "always"):
                choice = raw.strip().lower()
            else:
                choice = ""

            if not choice:
                self.set_state(VisionState.CANCELLED, "Capture consent denied")
                return ""

            pm.record_capture_permission(source=source, target=target, choice=choice)
            return choice
        except Exception:
            self.set_state(VisionState.CANCELLED, "Consent request error")
            return ""

    def request_send_consent(self, target: str, destination: str, preview_artifact: Any = None,
                             timeout_s: float = 30.0, capture_id: str = "capture",
                             sha256: str = "") -> str:
        """Request explicit human authorization to transmit image to destination model.
        Returns duration choice ('once', 'session', 'always') or '' if denied/cancelled.
        """
        pm = self._get_pm()
        if pm.has_send_permission(destination):
            return "session"

        self.set_state(VisionState.AWAITING_SEND, f"Destination: {destination}")
        handler = self._send_consent_handler
        if handler is None:
            # Default safe policy: when unconfigured, do not transmit without explicit consent handler
            self.set_state(VisionState.CANCELLED, "No consent handler registered")
            return ""

        try:
            raw = handler(target, destination, preview_artifact, timeout_s)
            if raw is True:
                choice = "once"
            elif isinstance(raw, str) and raw.strip().lower() in ("once", "session", "always"):
                choice = raw.strip().lower()
            else:
                choice = ""

            if not choice:
                self.set_state(VisionState.CANCELLED, "Transmission consent denied")
                return ""

            pm.record_send_permission(capture_id=capture_id, sha256=sha256, destination=destination, choice=choice)
            return choice
        except Exception:
            self.set_state(VisionState.CANCELLED, "Consent request error")
            return ""

    def request_cancel(self, reason: str = "user_requested") -> None:
        """Trigger cancellation from UI (e.g. Stop button)."""
        handler = self._cancel_handler
        if handler is not None:
            try:
                handler(reason)
            except Exception:
                pass
        self.set_state(VisionState.CANCELLED, reason)


# Global singleton bridge instance
_BRIDGE: Optional[VisionConsentBridge] = None
_BRIDGE_LOCK = threading.Lock()


def get_vision_bridge() -> VisionConsentBridge:
    global _BRIDGE
    with _BRIDGE_LOCK:
        if _BRIDGE is None:
            _BRIDGE = VisionConsentBridge()
        return _BRIDGE


def bind_ui(ui_player) -> None:
    """Wire the VisionConsentBridge to the HUD user interface."""
    bridge = get_vision_bridge()
    if ui_player is None or not hasattr(ui_player, "request_vision_consent"):
        return
    bridge.set_handlers(
        capture_handler=lambda target, timeout: ui_player.request_vision_consent(
            "AUTORIZAÇÃO: CAPTURA VISUAL",
            f"Permitir que o ULTRON capture ({target}) para análise?",
            timeout_s=timeout
        ),
        send_handler=lambda target, dest, preview, timeout: ui_player.request_vision_consent(
            "AUTORIZAÇÃO: TRANSMISSÃO AO MODELO",
            f"Autorizar envio da imagem de {target} para análise pelo modelo '{dest}'?",
            timeout_s=timeout
        ),
    )

    # Visible capture indicator via HUD log
    def _vision_state_logger(state: VisionState, detail: str):
        try:
            if not hasattr(ui_player, "write_log"):
                return
            if state == VisionState.CAPTURING:
                ui_player.write_log(f"👁 [VISÃO] Captura autorizada — gravando quadro ({detail})...")
            elif state == VisionState.ANALYZING:
                ui_player.write_log(f"👁 [VISÃO] Transmissão autorizada — analisando com IA ({detail})...")
            elif state == VisionState.CANCELLED:
                ui_player.write_log(f"🛑 [VISÃO] Operação cancelada: {detail}")
        except Exception:
            pass

    bridge.add_state_listener(_vision_state_logger)
