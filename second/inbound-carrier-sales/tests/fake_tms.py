"""Local stand-in for the Legacy TMS, including the documented fault modes:
timeout, partial response, malformed response, delayed termination."""

from __future__ import annotations

import socket
import threading
import time

TOKEN = "test-token"

LOAD_LINE = (
    "LOAD_ID:LD0000045821|ORIG_CITY:Atlanta              |ORIG_STATE:GA|ORIG_ZIP:30303|"
    "DEST_CITY:Dallas               |DEST_STATE:TX|DEST_ZIP:75201|PICKUP_DT:20260512080000|"
    "DELIVERY_DT:20260513170000|EQTYPE:DRY_VAN |RATE:0002150|WEIGHT:0042000|"
    "COMMODITY:PALLETIZED CONSUMER GOODS         |PIECES:000026|MILES:000785|"
    "DIMS:48X40 STD GMA PALLETS    |NOTES:Drop trailer at destination.            |"
    "STATUS:OPEN   |MAX_BUY:0001950"
)


class FakeTms:
    """Each accepted connection consumes the next scripted behavior.
    Behaviors: ok, ok_delayed_close, timeout, partial, malformed, err:<CODE>."""

    def __init__(self):
        self.behaviors: list[str] = []
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(8)
        self.port = self._sock.getsockname()[1]
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self.requests: list[str] = []

    def start(self):
        self._thread.start()
        return self

    def stop(self):
        self._stop.set()
        try:
            socket.create_connection(("127.0.0.1", self.port), timeout=1).close()
        except OSError:
            pass
        self._sock.close()

    def _serve(self):
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            if self._stop.is_set():
                conn.close()
                return
            behavior = self.behaviors.pop(0) if self.behaviors else "ok"
            threading.Thread(
                target=self._handle, args=(conn, behavior), daemon=True
            ).start()

    def _handle(self, conn: socket.socket, behavior: str):
        try:
            conn.settimeout(5)
            data = b""
            while not data.endswith(b"\r\n"):
                chunk = conn.recv(4096)
                if not chunk:
                    return
                data += chunk
            request = data.decode("ascii").strip()
            self.requests.append(request)
            fields = dict(
                token.partition(":")[::2] for token in request.split("|")
            )

            if behavior == "timeout":
                time.sleep(8)  # longer than client timeout; no response
                return
            if fields.get("AUTH") != TOKEN:
                conn.sendall(b"ERR|CODE:AUTH_FAILED|MSG:invalid or missing auth token\r\n")
                return
            if behavior.startswith("err:"):
                code = behavior.split(":", 1)[1]
                conn.sendall(f"ERR|CODE:{code}|MSG:scripted error\r\n".encode())
                return
            if behavior == "partial":
                conn.sendall(LOAD_LINE[:80].encode())  # truncated, no END
                return
            if behavior == "malformed":
                conn.sendall(b"%%%not|a::valid||record\r\nEND\r\n")
                return

            body = self._respond(fields)
            conn.sendall(body)
            if behavior == "ok_delayed_close":
                time.sleep(2)  # complete response, connection held open
        finally:
            conn.close()

    @staticmethod
    def _respond(fields: dict[str, str]) -> bytes:
        cmd = fields.get("CMD")
        if cmd == "DEBUG_ECHO":
            n = len(fields)
            return f"ECHO|AUTH:OK|FIELDS_PARSED:{n}|MSG:{fields.get('MSG', '')}\r\nEND\r\n".encode()
        if cmd == "LOAD_QUERY":
            if len(fields) <= 2:
                return b"ERR|CODE:MISSING_FIELD|MSG:at least one filter required\r\n"
            if fields.get("ORIG_STATE") == "ZZ":
                return b"END\r\n"
            return (LOAD_LINE + "\r\nEND\r\n").encode()
        if cmd == "LOAD_GET":
            if fields.get("LOAD_ID") != "LD0000045821":
                return b"ERR|CODE:UNKNOWN_LOAD|MSG:load not found\r\n"
            return (LOAD_LINE + "\r\nEND\r\n").encode()
        if cmd == "LOAD_BOOK":
            if not {"LOAD_ID", "MC_NUM", "AGREED_RATE"} <= set(fields):
                return b"ERR|CODE:MISSING_FIELD|MSG:missing required field\r\n"
            if int(fields["AGREED_RATE"]) <= 0:
                return b"ERR|CODE:INVALID_RATE|MSG:rate rejected\r\n"
            return (
                b"LOAD_ID:LD0000045821|BOOKING_REF:BR00000000091277|"
                b"STATUS:BOOKED |TIMESTAMP:20260504193122\r\nEND\r\n"
            )
        return b"ERR|CODE:UNKNOWN_CMD|MSG:unknown command\r\n"
