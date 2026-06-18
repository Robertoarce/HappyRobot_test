"""FMCSA QCMobile API client — carrier authority verification by MC number.

Lookup is by docket number (the MC number). The carrier is eligible when it
exists and reports active authority / allowed to operate.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class FmcsaClient:
    def __init__(self, base_url: str, web_key: str, timeout: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.web_key = web_key
        self.timeout = timeout

    async def verify_mc(self, mc_number: str) -> dict[str, Any]:
        url = f"{self.base_url}/carriers/docket-number/{mc_number}"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url, params={"webKey": self.web_key})
        if resp.status_code == 404:
            return {"eligible": False, "reason": "MC number not found"}
        resp.raise_for_status()
        payload = resp.json()

        content = payload.get("content") or []
        if not content:
            return {"eligible": False, "reason": "MC number not found"}

        # The API returns a list of matches; take the first carrier entry.
        entry = content[0] if isinstance(content, list) else content
        carrier = entry.get("carrier") or {}

        allowed = str(carrier.get("allowedToOperate", "")).upper() == "Y"
        status_code = str(carrier.get("statusCode", "")).upper()
        out_of_service = carrier.get("oosDate") not in (None, "", "null")

        eligible = allowed and status_code == "A" and not out_of_service
        reason = None
        if not eligible:
            if out_of_service:
                reason = "Carrier is out of service"
            elif not allowed:
                reason = "Carrier not allowed to operate"
            else:
                reason = f"Authority status is not active (status={status_code or 'unknown'})"

        return {
            "eligible": eligible,
            "reason": reason,
            "carrier_name": carrier.get("legalName") or carrier.get("dbaName"),
            "dot_number": carrier.get("dotNumber"),
        }
