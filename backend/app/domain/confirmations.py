"""One-time, session-local confirmation records for consequential actions."""

from __future__ import annotations

import secrets
import time
from copy import deepcopy
from threading import RLock
from typing import Any, Callable


class PendingActionStore:
    """Bind a single pending action to a target, details, and the next user turn."""

    def __init__(
        self,
        ttl_seconds: int = 300,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._ttl_seconds = ttl_seconds
        self._clock = clock
        self._pending: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    @property
    def ttl_seconds(self) -> int:
        return self._ttl_seconds

    def create(
        self,
        *,
        action: str,
        target: dict[str, Any],
        details: dict[str, Any],
        user_turn: int,
    ) -> dict[str, Any]:
        """Replace any previous pending action and return the new record."""
        now = self._clock()
        record = {
            "confirmation_id": secrets.token_urlsafe(18),
            "action": action,
            "target": deepcopy(target),
            "details": deepcopy(details),
            "user_turn": user_turn,
            "created_at": now,
            "expires_at": now + self._ttl_seconds,
        }
        with self._lock:
            self._pending.clear()
            self._pending[record["confirmation_id"]] = record
        return deepcopy(record)

    def invalidate(self) -> None:
        """Clear pending consent when the customer starts a different mutation."""
        with self._lock:
            self._pending.clear()

    def consume(
        self,
        *,
        confirmation_id: str,
        action: str,
        target: dict[str, Any],
        details: dict[str, Any],
        user_turn: int,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Consume a matching record only on the immediately following user turn."""
        now = self._clock()
        with self._lock:
            record = self._pending.get(confirmation_id)
            if record is None:
                return None, "CONFIRMATION_INVALID"
            if now >= record["expires_at"]:
                del self._pending[confirmation_id]
                return None, "CONFIRMATION_EXPIRED"
            if record["action"] != action or record["target"] != target:
                del self._pending[confirmation_id]
                return None, "CONFIRMATION_MISMATCH"
            if record["details"] != details:
                del self._pending[confirmation_id]
                return None, "CONFIRMATION_CHANGED"
            if user_turn <= record["user_turn"]:
                return None, "CONFIRMATION_NOT_READY"
            if user_turn != record["user_turn"] + 1:
                del self._pending[confirmation_id]
                return None, "CONFIRMATION_STALE"
            del self._pending[confirmation_id]
            return deepcopy(record), None

    def __len__(self) -> int:
        now = self._clock()
        with self._lock:
            expired = [key for key, value in self._pending.items() if now >= value["expires_at"]]
            for key in expired:
                del self._pending[key]
            return len(self._pending)
