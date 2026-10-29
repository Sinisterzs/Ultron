from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict

class WhatsAppDriver(ABC):
    """Abstract interface defining the strict contract for all WhatsApp drivers
    (Desktop UIA and Web Playwright), ensuring unified outcome structures,
    deadlines, draft protection, and deduplication guardrails.
    """

    @abstractmethod
    def detect(self) -> bool:
        """Return True if the target WhatsApp client/session is running and accessible."""
        pass

    @abstractmethod
    def search_recipient(self, target: str) -> str:
        """Search and select the target contact or group.
        Returns an outcome string (e.g. outcome.done or outcome.failed).
        """
        pass

    @abstractmethod
    def verify_conversation(self, expected_target: str) -> bool:
        """Verify that the currently active chat header strictly matches expected_target."""
        pass

    @abstractmethod
    def prepare_message(self, text: str) -> str:
        """Prepare the composer with the message text without sending.
        Preserves existing drafts and guards against whitespace-only anomalies.
        """
        pass

    @abstractmethod
    def send_and_verify(self, timeout: float = 10.0) -> str:
        """Execute send action and wait for delivery/sent verification.
        Returns outcome.done, outcome.unverified, or outcome.failed.
        """
        pass
