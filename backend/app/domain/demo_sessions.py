"""Ephemeral named demo identities authorized by opaque session credentials."""

from __future__ import annotations

import hashlib
import secrets
import time
import uuid
from copy import deepcopy
from contextlib import contextmanager
from threading import RLock
from typing import Any, Callable, Iterator


class DemoSessionStore:
    """Process-local account/mock context store with sliding inactivity expiry.

    Only a SHA-256 digest of each high-entropy credential is retained. The
    session data itself is JSON-compatible and is intentionally in memory, so
    a server restart clears all temporary identities.
    """

    def __init__(
        self,
        idle_timeout_seconds: int = 30 * 60,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if idle_timeout_seconds <= 0:
            raise ValueError("idle_timeout_seconds must be positive")
        self._idle_timeout_seconds = idle_timeout_seconds
        self._clock = clock
        self._sessions: dict[str, dict[str, Any]] = {}
        self._lock = RLock()

    @staticmethod
    def _digest(credential: str) -> str:
        return hashlib.sha256(credential.encode("utf-8")).hexdigest()

    def _remove_expired(self, now: float) -> None:
        expired = [
            digest
            for digest, session in self._sessions.items()
            if now - session["last_activity"] >= self._idle_timeout_seconds
        ]
        for digest in expired:
            del self._sessions[digest]

    def create(self, display_name: str) -> tuple[str, dict[str, Any]]:
        """Create an identity and return its credential exactly once."""
        return self._create_session(mode="account", display_name=display_name)

    def create_mock_context(self) -> tuple[str, dict[str, Any]]:
        """Create an anonymous Mock DB context session, not an account identity."""
        return self._create_session(mode="mock_db", display_name=None)

    def _create_session(
        self, *, mode: str, display_name: str | None
    ) -> tuple[str, dict[str, Any]]:
        credential = secrets.token_urlsafe(32)
        now = self._clock()
        session = {
            "identity_id": uuid.uuid4().hex,
            "mode": mode,
            "display_name": display_name,
            "created_at": now,
            "last_activity": now,
            "conversation_context": {},
            "orders": [],
            "carts": [],
        }
        with self._lock:
            self._remove_expired(now)
            self._sessions[self._digest(credential)] = session
        return credential, deepcopy(session)

    def authorize(
        self, credential: str, *, expected_mode: str | None = None
    ) -> dict[str, Any] | None:
        """Validate and refresh a credential without exposing it in state."""
        if not isinstance(credential, str) or not credential:
            return None
        now = self._clock()
        digest = self._digest(credential)
        with self._lock:
            self._remove_expired(now)
            session = self._sessions.get(digest)
            if session is None or (expected_mode and session["mode"] != expected_mode):
                return None
            session["last_activity"] = now
            return deepcopy(session)

    @contextmanager
    def account_transaction(self, credential: str) -> Iterator[dict[str, Any] | None]:
        """Serialize one account operation and its state writeback in-process.

        The store lock is re-entrant so callers can authorize and replace state
        while the transaction is held. Do not await while using this context.
        """
        self._lock.acquire()
        try:
            yield self.authorize(credential, expected_mode="account")
        finally:
            self._lock.release()

    def list_account_orders(self, credential: str) -> list[dict[str, Any]] | None:
        """Return only orders owned by the authorized temporary account."""
        session = self.authorize(credential, expected_mode="account")
        if session is None:
            return None
        return deepcopy(session["orders"])

    def replace_account_orders(self, credential: str, orders: list[dict[str, Any]]) -> bool:
        """Persist temporary order state only on the credential's account identity."""
        if not isinstance(orders, list) or not all(isinstance(order, dict) for order in orders):
            return False
        now = self._clock()
        digest = self._digest(credential) if isinstance(credential, str) and credential else None
        if digest is None:
            return False
        with self._lock:
            self._remove_expired(now)
            session = self._sessions.get(digest)
            if session is None or session["mode"] != "account":
                return False
            session["orders"] = deepcopy(orders)
            session["last_activity"] = now
            return True

    def replace_account_carts(self, credential: str, carts: list[dict[str, Any]]) -> bool:
        """Persist temporary cart state only on the credential's account identity."""
        if not isinstance(carts, list) or not all(isinstance(cart, dict) for cart in carts):
            return False
        now = self._clock()
        digest = self._digest(credential) if isinstance(credential, str) and credential else None
        if digest is None:
            return False
        with self._lock:
            self._remove_expired(now)
            session = self._sessions.get(digest)
            if session is None or session["mode"] != "account":
                return False
            session["carts"] = deepcopy(carts)
            session["last_activity"] = now
            return True

    def update_context(
        self, credential: str, *, expected_mode: str, context: dict[str, Any]
    ) -> bool:
        """Replace structured continuity state for the matching temporary session."""
        if not isinstance(context, dict):
            return False
        now = self._clock()
        digest = self._digest(credential) if isinstance(credential, str) and credential else None
        if digest is None:
            return False
        with self._lock:
            self._remove_expired(now)
            session = self._sessions.get(digest)
            if session is None or session["mode"] != expected_mode:
                return False
            session["conversation_context"] = deepcopy(context)
            session["last_activity"] = now
            return True

    def purge_expired(self) -> int:
        """Remove expired sessions and return the number removed."""
        with self._lock:
            before = len(self._sessions)
            self._remove_expired(self._clock())
            return before - len(self._sessions)

    def __len__(self) -> int:
        with self._lock:
            self._remove_expired(self._clock())
            return len(self._sessions)
