"""Probe the FMCSA QCMobile API to validate the webKey. Run: python -m scripts.fmcsa_probe"""

import asyncio
import json

import httpx

from app.config import get_settings
from app.fmcsa import FmcsaClient

s = get_settings()
print("webKey set:", bool(s.fmcsa_web_key), "len:", len(s.fmcsa_web_key))

# A few real, well-known active carriers to exercise the lookup.
TEST_MCS = ["133655", "44110", "872144"]


async def main():
    # 1) Raw call so we can see auth status independent of MC validity.
    url = f"{s.fmcsa_base_url}/carriers/docket-number/{TEST_MCS[0]}"
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(url, params={"webKey": s.fmcsa_web_key})
    print(f"\n[RAW] GET {url} -> HTTP {r.status_code}")
    body = r.text[:600]
    print("body:", body)

    # 2) Through our client wrapper.
    client = FmcsaClient(s.fmcsa_base_url, s.fmcsa_web_key)
    for mc in TEST_MCS:
        try:
            res = await client.verify_mc(mc)
            print(f"\n[verify_mc {mc}] -> {json.dumps(res)}")
        except Exception as e:
            print(f"\n[verify_mc {mc}] ERROR {type(e).__name__}: {e}")


asyncio.run(main())
