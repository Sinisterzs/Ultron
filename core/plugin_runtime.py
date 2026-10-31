"""
core/plugin_runtime.py — Generic minimal plugin runtime contract and host bridge.

Provides lifecycle management (initialization, execution context, cancellation,
graceful shutdown) and delimited host interaction (consent requests, logging,
speech requests, configuration) without tight coupling to Qt UI internals or main session.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class ConsentRequest:
    action: str              # e.g. "capture_screen", "send_vision_to_model"
    title: str               # Human-readable title
    detail: str              # Explanatory description
    target: str = ""         # e.g. "screen", "monitor_1", "region"
    destination: str = ""    # e.g. "models/gemini-2.5-flash"
    timeout_s: float = 30.0  # Timeout for user approval


class HostContext:
    """Delimited services exposed by the host to a plugin runtime."""

    def __init__(self,
                 notify: Optional[Callable[[str], None]] = None,
                 log: Optional[Callable[[str], None]] = None,
                 say: Optional[Callable[[str], None]] = None,
                 consent_callback: Optional[Callable[[ConsentRequest], bool]] = None,
                 get_config_fn: Optional[Callable[[str, Any], Any]] = None,
                 save_config_fn: Optional[Callable[[str, Any], None]] = None):
        self._notify = notify or (lambda _: None)
        self._log = log or (lambda _: None)
        self._say = say or (lambda _: None)
        self._consent = consent_callback
        self._get_config = get_config_fn or (lambda _k, d=None: d)
        self._save_config = save_config_fn or (lambda _k, _v: None)

    def notify(self, message: str) -> None:
        """Post a user-facing notification (e.g. Activity Log)."""
        try:
            self._notify(message)
        except Exception:
            pass

    def log(self, message: str) -> None:
        """Post an internal transcript / log message."""
        try:
            self._log(message)
        except Exception:
            pass

    def plugin_say(self, instruction: str) -> None:
        """Request the assistant to speak an instruction during execution."""
        try:
            self._say(instruction)
        except Exception:
            pass

    def request_consent(self, request: ConsentRequest) -> bool:
        """Ask the human user for explicit consent. False if denied or no handler."""
        if self._consent is None:
            return False
        try:
            return bool(self._consent(request))
        except Exception:
            return False

    def get_config(self, key: str, default: Any = None) -> Any:
        return self._get_config(key, default)

    def save_config(self, key: str, value: Any) -> None:
        self._save_config(key, value)


class PluginRuntime:
    """Base class for stateful plugin runtimes with lifecycle management."""

    def __init__(self, name: str, context: Optional[HostContext] = None):
        self.name = name
        self.context = context or HostContext()
        self._is_running = True
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    def cancel_all(self) -> None:
        """Cancel any in-flight background operations."""
        pass

    def shutdown(self) -> None:
        """Gracefully release resources and terminate operations (idempotent)."""
        with self._lock:
            if not self._is_running:
                return
            self._is_running = False
        self.cancel_all()
