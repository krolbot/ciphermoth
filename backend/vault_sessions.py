"""
Unlocked vault sessions, held in the memory of the one process that serves the
vault.

A session maps an opaque bearer token to the vault key derived at unlock, so
clients never hold the key. Only a SHA-256 digest of each token is kept, as the
lookup key. Sessions end when they sit idle longer than the configured
inactivity timeout, after an absolute lifetime, when they are locked, when the
master password changes, and when the process exits. Nothing is ever written to
disk.

Server mode keeps one session per client (browser tab or CLI command), bounded
by ``max_sessions``: when full, expired sessions are dropped first and then the
least recently used one. A desktop core uses ``max_sessions=1``: unlocking
replaces the previous session and the shell, not the renderer, holds the token.

Limits: Python cannot reliably erase a secret from memory. Locking drops every
reference to the key, but copies made by ``str``, ``base64`` and
``cryptography`` stay in freed memory until it is reused. Sessions protect the
key from clients and from storage, not from someone who can read the process's
memory.
"""

import hashlib
import re
import secrets
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import NamedTuple

from errors import SessionRequired

TOKEN_BYTES = 32
ACTIVITY_GRACE_MS = 60_000
MAX_LIFETIME_MS = 12 * 60 * 60 * 1000
DEFAULT_MAX_SESSIONS = 32

_TOKEN = re.compile(r"[A-Za-z0-9_-]{43}", re.ASCII)
_ENDED = "Your session expired or was locked. Unlock the vault again."


class Instant(NamedTuple):
    monotonic: float
    wall: float

    def ms_since(self, earlier: "Instant") -> float:
        """
        The larger of the two clocks' elapsed times. The monotonic clock stops
        while the machine sleeps on macOS and Linux, and the wall clock can be
        set back, so each one covers the other's blind spot.
        """
        return 1000 * max(self.monotonic - earlier.monotonic, self.wall - earlier.wall)


def system_clock() -> Instant:
    return Instant(time.monotonic(), time.time())


def idle_timeout_for(inactivity_ms: int) -> int:
    return inactivity_ms + ACTIVITY_GRACE_MS


def _digest(token: str) -> bytes:
    return hashlib.sha256(token.encode("ascii")).digest()


@dataclass(slots=True)
class _Session:
    key: str = field(repr=False)
    created: Instant
    last_used: Instant


@dataclass(frozen=True, slots=True)
class SessionInfo:
    idle_timeout_ms: int
    expires_in_ms: int


class VaultSessions:
    def __init__(
        self,
        *,
        idle_timeout_ms: int,
        max_lifetime_ms: int = MAX_LIFETIME_MS,
        max_sessions: int = DEFAULT_MAX_SESSIONS,
        clock: Callable[[], Instant] = system_clock,
    ) -> None:
        if max_sessions < 1:
            raise ValueError("max_sessions must be at least 1")
        self._idle_timeout_ms = idle_timeout_ms
        self._max_lifetime_ms = max_lifetime_ms
        self._max_sessions = max_sessions
        self._clock = clock
        self._sessions: OrderedDict[bytes, _Session] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def idle_timeout_ms(self) -> int:
        return self._idle_timeout_ms

    def set_idle_timeout(self, idle_timeout_ms: int) -> None:
        with self._lock:
            self._idle_timeout_ms = idle_timeout_ms

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)

    def open(self, key: str) -> str:
        token = secrets.token_urlsafe(TOKEN_BYTES)
        now = self._clock()
        with self._lock:
            self._drop_expired(now)
            while len(self._sessions) >= self._max_sessions:
                self._sessions.popitem(last=False)
            self._sessions[_digest(token)] = _Session(
                key=key, created=now, last_used=now
            )
        return token

    def resolve(self, token: str | None) -> str:
        """Return the vault key of a live session and mark it as just used."""
        with self._lock:
            digest, session = self._live(token)
            session.last_used = self._clock()
            self._sessions.move_to_end(digest)
            return session.key

    def info(self, token: str | None) -> SessionInfo:
        with self._lock:
            _, session = self._live(token)
            return SessionInfo(
                idle_timeout_ms=self._idle_timeout_ms,
                expires_in_ms=int(self._remaining_ms(session, self._clock())),
            )

    def revoke(self, token: str | None) -> bool:
        if token is None or not _TOKEN.fullmatch(token):
            return False
        with self._lock:
            return self._sessions.pop(_digest(token), None) is not None

    def revoke_all(self) -> int:
        with self._lock:
            count = len(self._sessions)
            self._sessions.clear()
            return count

    def drop_expired(self) -> int:
        with self._lock:
            return self._drop_expired(self._clock())

    def _live(self, token: str | None) -> tuple[bytes, _Session]:
        if token is None or not _TOKEN.fullmatch(token):
            raise SessionRequired(_ENDED)
        digest = _digest(token)
        session = self._sessions.get(digest)
        if session is None:
            raise SessionRequired(_ENDED)
        if self._remaining_ms(session, self._clock()) <= 0:
            del self._sessions[digest]
            raise SessionRequired(_ENDED)
        return digest, session

    def _remaining_ms(self, session: _Session, now: Instant) -> float:
        return min(
            self._idle_timeout_ms - now.ms_since(session.last_used),
            self._max_lifetime_ms - now.ms_since(session.created),
        )

    def _drop_expired(self, now: Instant) -> int:
        expired = [
            digest
            for digest, session in self._sessions.items()
            if self._remaining_ms(session, now) <= 0
        ]
        for digest in expired:
            del self._sessions[digest]
        return len(expired)
