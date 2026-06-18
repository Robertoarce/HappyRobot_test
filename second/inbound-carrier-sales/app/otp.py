"""In-memory OTP store.

The middleware generates the code and the HappyRobot workflow sends it by SMS.
The code is returned only to the workflow's SMS node — it must never be wired
into the voice agent's context, so the agent cannot be talked into reading it
back (social-engineering resistance is a hard requirement).
"""

from __future__ import annotations

import secrets
import time
from dataclasses import dataclass


@dataclass
class _OtpEntry:
    code: str
    expires_at: float
    attempts_left: int


class OtpStore:
    def __init__(self, ttl_seconds: int = 300, max_attempts: int = 3):
        self.ttl = ttl_seconds
        self.max_attempts = max_attempts
        self._entries: dict[str, _OtpEntry] = {}

    def issue(self, session_id: str) -> str:
        code = f"{secrets.randbelow(1_000_000):06d}"
        self._entries[session_id] = _OtpEntry(
            code=code,
            expires_at=time.monotonic() + self.ttl,
            attempts_left=self.max_attempts,
        )
        return code

    def verify(self, session_id: str, code: str) -> dict:
        entry = self._entries.get(session_id)
        if entry is None:
            return {"verified": False, "reason": "no_otp_issued"}
        if time.monotonic() > entry.expires_at:
            del self._entries[session_id]
            return {"verified": False, "reason": "expired"}
        if entry.attempts_left <= 0:
            return {"verified": False, "reason": "too_many_attempts"}
        entry.attempts_left -= 1
        if secrets.compare_digest(entry.code, code.strip()):
            del self._entries[session_id]
            return {"verified": True, "reason": None}
        reason = "incorrect" if entry.attempts_left > 0 else "too_many_attempts"
        return {"verified": False, "reason": reason, "attempts_left": entry.attempts_left}
