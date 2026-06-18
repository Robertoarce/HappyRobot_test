"""TCP adapter for the HappyRobot Legacy TMS.

Protocol (per spec): one request per connection, single ``\r\n``-terminated
line of ``|``-delimited ``KEY:VALUE`` pairs, ASCII, max frame 4096 bytes.
Success responses are zero or more record lines followed by ``END``.
Errors are a single ``ERR|CODE:<code>|MSG:<msg>`` line.

The non-production server injects faults (timeouts, truncated responses,
malformed frames, delayed close). Faults are not signaled — we detect them
from the wire and retry with backoff. Semantic errors (UNKNOWN_LOAD,
ALREADY_BOOKED, ...) are never retried.
"""

from __future__ import annotations

import logging
import socket
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

MAX_FRAME = 4096
TERMINATOR = b"\r\n"

# Server-reported codes that indicate a transient server-side problem.
RETRYABLE_ERR_CODES = {"SERVER_ERROR", "MALFORMED"}


class TmsError(Exception):
    """Base error for the TMS adapter."""


class TmsTransportError(TmsError):
    """Timeout, truncated or malformed response — retryable."""


class TmsCommandError(TmsError):
    """Semantic error returned by the server — not retryable."""

    def __init__(self, code: str, msg: str):
        super().__init__(f"{code}: {msg}")
        self.code = code
        self.msg = msg


class TmsUnavailableError(TmsError):
    """All retries exhausted."""


@dataclass
class TmsClient:
    host: str
    port: int
    auth_token: str
    timeout: float = 5.0
    max_retries: int = 3
    backoff_base: float = 0.5
    records_last_call: list[dict[str, str]] = field(default_factory=list, repr=False)

    # ---------------------------------------------------------------- public

    def debug_echo(self, msg: str = "ping") -> dict[str, str]:
        records = self._request_with_retries("DEBUG_ECHO", MSG=msg)
        return records[0] if records else {}

    def load_query(self, **filters: str) -> list[dict[str, str]]:
        clean = {k.upper(): str(v) for k, v in filters.items() if v not in (None, "")}
        if not clean:
            raise ValueError("LOAD_QUERY requires at least one filter")
        return self._request_with_retries("LOAD_QUERY", **clean)

    def load_get(self, load_id: str) -> dict[str, str]:
        records = self._request_with_retries("LOAD_GET", LOAD_ID=load_id)
        if not records:
            raise TmsTransportError("LOAD_GET returned no record before END")
        return records[0]

    def load_book(self, load_id: str, mc_num: str, agreed_rate: int) -> dict[str, str]:
        records = self._request_with_retries(
            "LOAD_BOOK", LOAD_ID=load_id, MC_NUM=mc_num, AGREED_RATE=str(agreed_rate)
        )
        if not records:
            raise TmsTransportError("LOAD_BOOK returned no record before END")
        return records[0]

    # -------------------------------------------------------------- internals

    def _request_with_retries(self, cmd: str, **fields: str) -> list[dict[str, str]]:
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return self._request_once(cmd, **fields)
            except TmsCommandError as exc:
                if exc.code in RETRYABLE_ERR_CODES:
                    last_exc = exc
                else:
                    raise
            except (TmsTransportError, OSError) as exc:
                last_exc = exc
            wait = self.backoff_base * (2 ** (attempt - 1))
            logger.warning(
                "TMS %s attempt %d/%d failed (%s); retrying in %.1fs",
                cmd, attempt, self.max_retries, last_exc, wait,
            )
            if attempt < self.max_retries:
                time.sleep(wait)
        raise TmsUnavailableError(
            f"TMS {cmd} failed after {self.max_retries} attempts: {last_exc}"
        )

    def _request_once(self, cmd: str, **fields: str) -> list[dict[str, str]]:
        line = self._encode(cmd, fields)
        raw = self._roundtrip(line)
        return self._parse_response(raw)

    def _encode(self, cmd: str, fields: dict[str, str]) -> bytes:
        parts = [f"CMD:{cmd}", f"AUTH:{self.auth_token}"]
        for key, value in fields.items():
            value = str(value)
            if "|" in value or "\r" in value or "\n" in value:
                raise ValueError(f"illegal characters in field {key}")
            parts.append(f"{key}:{value}")
        frame = ("|".join(parts)).encode("ascii") + TERMINATOR
        if len(frame) > MAX_FRAME:
            raise ValueError("request exceeds maximum frame size")
        return frame

    def _roundtrip(self, frame: bytes) -> bytes:
        """One connection per request, per spec. Read until END/ERR is seen —
        the server may legitimately hold the connection open after a complete
        response (delayed-termination fault), so we never wait for close."""
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
            sock.sendall(frame)
            buf = b""
            while True:
                if self._is_complete(buf):
                    return buf
                if len(buf) > MAX_FRAME * 64:
                    raise TmsTransportError("response exceeds sane size; aborting")
                try:
                    chunk = sock.recv(4096)
                except socket.timeout as exc:
                    raise TmsTransportError("timed out waiting for response") from exc
                if not chunk:
                    # Server closed without END — truncated/partial response.
                    if self._is_complete(buf):
                        return buf
                    raise TmsTransportError("connection closed before END terminator")
                buf += chunk

    @staticmethod
    def _is_complete(buf: bytes) -> bool:
        if buf.startswith(b"ERR|") and buf.endswith(TERMINATOR):
            return True
        return buf.endswith(b"END" + TERMINATOR) or (b"\r\nEND\r\n" in buf)

    def _parse_response(self, raw: bytes) -> list[dict[str, str]]:
        try:
            text = raw.decode("ascii")
        except UnicodeDecodeError as exc:
            raise TmsTransportError("non-ASCII bytes in response") from exc

        lines = text.split("\r\n")
        records: list[dict[str, str]] = []
        terminated = False
        for line in lines:
            if line == "":
                continue
            if line == "END":
                terminated = True
                break
            if line.startswith("ERR|"):
                err = self._parse_pairs(line[len("ERR|"):], strict=False)
                raise TmsCommandError(err.get("CODE", "UNKNOWN"), err.get("MSG", ""))
            records.append(self._parse_pairs(line, strict=True))
        if not terminated:
            raise TmsTransportError("response missing END terminator")
        self.records_last_call = records
        return records

    @staticmethod
    def _parse_pairs(line: str, strict: bool) -> dict[str, str]:
        pairs: dict[str, str] = {}
        for token in line.split("|"):
            key, sep, value = token.partition(":")
            if not sep:
                # Bare marker tokens exist (e.g. the leading ECHO in
                # DEBUG_ECHO responses); record them with an empty value.
                if token and token.isalpha() and token.isupper():
                    pairs[token] = ""
                    continue
                if strict:
                    raise TmsTransportError(f"malformed token in record line: {token!r}")
                continue
            if not key or not key.isupper():
                if strict:
                    raise TmsTransportError(f"malformed token in record line: {token!r}")
                continue
            # Fixed-width values are right-padded with spaces.
            pairs[key] = value.rstrip()
        if strict and not pairs:
            raise TmsTransportError("empty record line")
        return pairs
