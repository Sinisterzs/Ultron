"""
plugins/_smart_vision_permissions.py — Ephemeral and persistent permission manager for Smart Vision.

Enforces:
1. Three explicit duration tiers: 'once' (ephemeral), 'session' (in-memory), and 'always' (persistent).
2. Strict separation between local capture authorization and remote transmission authorization.
3. Persistent permissions saved to config without storing any images or image hashes.
4. Exact binding of transmission authorization to capture scope and destination model.
5. Invalidation and immediate revocation of in-flight operations.
6. Scope or provider changes require re-authorization.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from typing import Optional

try:
    from memory.config_manager import (
        add_persistent_capture_scope,
        add_persistent_send_destination,
        clear_vision_persistent_permissions,
        get_vision_permissions,
    )
except ImportError:
    # Safe fallback for isolated test environments
    def get_vision_permissions() -> dict:
        return {"capture_scopes": [], "send_destinations": []}

    def add_persistent_capture_scope(scope: str) -> None:
        pass

    def add_persistent_send_destination(dest: str) -> None:
        pass

    def clear_vision_persistent_permissions() -> None:
        pass


def format_capture_scope(source: str, target: str) -> str:
    """Standardize capture scope format: '{source}:{target}' (e.g. 'screen:screen', 'camera:camera')."""
    s = (source or "screen").strip().lower()
    t = (target or "screen").strip().lower()
    return f"{s}:{t}"


@dataclass
class CaptureGrant:
    grant_id: str
    source: str
    target: str
    created_at: float
    ttl_s: float = 60.0
    revoked: bool = False

    def is_valid(self, now: Optional[float] = None) -> bool:
        if self.revoked:
            return False
        current = now if now is not None else time.monotonic()
        return (current - self.created_at) <= self.ttl_s


@dataclass
class SendGrant:
    grant_id: str
    capture_id: str
    sha256: str
    destination: str
    created_at: float
    ttl_s: float = 60.0
    revoked: bool = False

    def is_valid(self, now: Optional[float] = None) -> bool:
        if self.revoked:
            return False
        current = now if now is not None else time.monotonic()
        return (current - self.created_at) <= self.ttl_s


class PermissionManager:
    """Thread-safe manager for ephemeral and persistent Smart Vision permissions."""

    def __init__(self, default_ttl_s: float = 60.0):
        self._default_ttl_s = default_ttl_s
        self._capture_grants: dict[str, CaptureGrant] = {}
        self._send_grants: dict[str, SendGrant] = {}
        self._session_capture_scopes: set[str] = set()
        self._session_send_destinations: set[str] = set()
        self._lock = threading.RLock()

    # ── Permission Checking (Session / Persistent) ──────────────────────────

    def has_capture_permission(self, source: str = "screen", target: str = "screen") -> bool:
        """Check whether capture for the given scope has been granted for this session or permanently."""
        scope = format_capture_scope(source, target)
        wildcard = f"{(source or 'screen').strip().lower()}:all"
        with self._lock:
            if scope in self._session_capture_scopes or wildcard in self._session_capture_scopes:
                return True

            try:
                stored = get_vision_permissions()
                persistent_scopes = set(stored.get("capture_scopes", []))
                if scope in persistent_scopes or wildcard in persistent_scopes:
                    self._session_capture_scopes.add(scope)
                    return True
            except Exception:
                pass
            return False

    def has_send_permission(self, destination: str) -> bool:
        """Check whether transmission to the destination model has been granted for this session or permanently."""
        dest = (destination or "").strip()
        if not dest:
            return False
        with self._lock:
            if dest in self._session_send_destinations:
                return True

            try:
                stored = get_vision_permissions()
                persistent_dests = set(stored.get("send_destinations", []))
                if dest in persistent_dests:
                    self._session_send_destinations.add(dest)
                    return True
            except Exception:
                pass
            return False

    # ── Recording Grants with Duration Tier ──────────────────────────────────

    def record_capture_permission(self, source: str = "screen", target: str = "screen",
                                  choice: str = "once") -> Optional[CaptureGrant]:
        """Record authorization according to duration choice ('once', 'session', 'always').
        Returns CaptureGrant or None if choice is invalid/cancelled.
        """
        c = (choice or "").strip().lower()
        if c not in ("once", "session", "always"):
            return None

        scope = format_capture_scope(source, target)
        with self._lock:
            if c in ("session", "always"):
                self._session_capture_scopes.add(scope)
            if c == "always":
                try:
                    add_persistent_capture_scope(scope)
                except Exception:
                    pass

        return self.create_capture_grant(source=source, target=target)

    def record_send_permission(self, capture_id: str, sha256: str, destination: str,
                               choice: str = "once") -> Optional[SendGrant]:
        """Record transmission authorization according to duration choice ('once', 'session', 'always').
        Returns SendGrant or None if choice is invalid/cancelled.
        """
        c = (choice or "").strip().lower()
        if c not in ("once", "session", "always"):
            return None

        dest = (destination or "").strip()
        with self._lock:
            if c in ("session", "always"):
                self._session_send_destinations.add(dest)
            if c == "always":
                try:
                    add_persistent_send_destination(dest)
                except Exception:
                    pass

        return self.create_send_grant(capture_id=capture_id, sha256=sha256, destination=dest)

    # ── Ephemeral Grant Creation & Validation ────────────────────────────────

    def create_capture_grant(self, source: str, target: str, ttl_s: Optional[float] = None) -> CaptureGrant:
        """Issue an ephemeral grant to perform local screen capture."""
        ttl = ttl_s if ttl_s is not None else self._default_ttl_s
        grant = CaptureGrant(
            grant_id=str(uuid.uuid4()),
            source=source,
            target=target,
            created_at=time.monotonic(),
            ttl_s=ttl,
            revoked=False,
        )
        with self._lock:
            self._capture_grants[grant.grant_id] = grant
        return grant

    def validate_capture_grant(self, grant: Optional[CaptureGrant], source: str, target: str) -> bool:
        """Validate that a capture grant exists, is not revoked, has not expired, and matches source/target."""
        if not isinstance(grant, CaptureGrant):
            return False
        with self._lock:
            stored = self._capture_grants.get(grant.grant_id)
            if stored is None or stored is not grant:
                return False
            if not stored.is_valid():
                return False
            if stored.source != source:
                return False
            if stored.target != target and stored.target != "all":
                return False
            return True

    def create_send_grant(self, capture_id: str, sha256: str, destination: str,
                          ttl_s: Optional[float] = None) -> SendGrant:
        """Issue an ephemeral grant to transmit a specific capture to a specific destination."""
        ttl = ttl_s if ttl_s is not None else self._default_ttl_s
        grant = SendGrant(
            grant_id=str(uuid.uuid4()),
            capture_id=capture_id,
            sha256=sha256,
            destination=destination,
            created_at=time.monotonic(),
            ttl_s=ttl,
            revoked=False,
        )
        with self._lock:
            self._send_grants[grant.grant_id] = grant
        return grant

    def validate_send_grant(self, grant: Optional[SendGrant], capture_id: str, sha256: str,
                            destination: str) -> bool:
        """Validate that a transmission grant is valid, matches capture ID, sha256, and destination."""
        if not isinstance(grant, SendGrant):
            return False
        with self._lock:
            stored = self._send_grants.get(grant.grant_id)
            if stored is None or stored is not grant:
                return False
            if not stored.is_valid():
                return False
            if stored.capture_id != capture_id:
                return False
            if stored.sha256 != sha256:
                return False
            if stored.destination != destination:
                return False
            return True

    def is_destination_authorized(self, destination: str, capture_id: str) -> bool:
        """Check if any active, valid grant exists for the destination and capture_id."""
        with self._lock:
            now = time.monotonic()
            for g in self._send_grants.values():
                if g.capture_id == capture_id and g.destination == destination and g.is_valid(now):
                    return True
        return False

    # ── Revocation ───────────────────────────────────────────────────────────

    def revoke_grant(self, grant_id: str) -> None:
        """Revoke a specific ephemeral grant."""
        with self._lock:
            if grant_id in self._capture_grants:
                self._capture_grants[grant_id].revoked = True
            if grant_id in self._send_grants:
                self._send_grants[grant_id].revoked = True

    def revoke_session(self) -> None:
        """Revoke all active in-flight grants and in-memory session permissions."""
        with self._lock:
            for cg in self._capture_grants.values():
                cg.revoked = True
            for sg in self._send_grants.values():
                sg.revoked = True
            self._session_capture_scopes.clear()
            self._session_send_destinations.clear()

    def revoke_persistent(self) -> None:
        """Revoke all persistent permissions and clear in-memory cache."""
        with self._lock:
            self.revoke_session()
            try:
                clear_vision_persistent_permissions()
            except Exception:
                pass

    def revoke_all(self, clear_persistent: bool = False) -> None:
        """Revoke in-flight grants and session permissions.
        If clear_persistent is True, also clears stored configuration.
        """
        with self._lock:
            self.revoke_session()
            if clear_persistent:
                try:
                    clear_vision_persistent_permissions()
                except Exception:
                    pass

    def prune_expired(self) -> None:
        """Remove expired grants from memory."""
        with self._lock:
            now = time.monotonic()
            self._capture_grants = {
                gid: g for gid, g in self._capture_grants.items() if g.is_valid(now)
            }
            self._send_grants = {
                gid: g for gid, g in self._send_grants.items() if g.is_valid(now)
            }


# ── Global Singleton Instance ───────────────────────────────────────────────

_SHARED_PM: Optional[PermissionManager] = None
_SHARED_PM_LOCK = threading.Lock()


def get_shared_permission_manager() -> PermissionManager:
    """Return the application-wide PermissionManager singleton."""
    global _SHARED_PM
    with _SHARED_PM_LOCK:
        if _SHARED_PM is None:
            _SHARED_PM = PermissionManager()
        return _SHARED_PM
