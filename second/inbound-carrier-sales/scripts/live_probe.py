"""Ad-hoc live probe against the real Legacy TMS. Run: python -m scripts.live_probe"""

import sys

from app.config import get_settings
from app.tms_client import TmsClient, TmsCommandError, TmsError

s = get_settings()
client = TmsClient(
    host=s.tms_host,
    port=s.tms_port,
    auth_token=s.tms_auth_token,
    timeout=s.tms_timeout_seconds,
    max_retries=s.tms_max_retries,
)

print(f"== Connecting to {s.tms_host}:{s.tms_port} ==")

print("\n[1] DEBUG_ECHO")
try:
    print("   ->", client.debug_echo("probe"))
except TmsError as e:
    print("   FAILED:", repr(e))
    sys.exit(1)

print("\n[2] LOAD_QUERY ORIG_STATE=GA DEST_STATE=TX EQTYPE=DRY_VAN MAX_RESULTS=5")
try:
    rows = client.load_query(ORIG_STATE="GA", DEST_STATE="TX", EQTYPE="DRY_VAN", MAX_RESULTS="5")
    print(f"   -> {len(rows)} record(s)")
    for r in rows:
        print("   ", r)
except TmsError as e:
    print("   FAILED:", repr(e))
    rows = []

print("\n[3] LOAD_GET on first result (if any)")
if rows:
    lid = rows[0].get("LOAD_ID")
    try:
        rec = client.load_get(lid)
        print(f"   -> {lid}")
        for k, v in rec.items():
            print(f"       {k}: {v}")
        print("   MAX_BUY present on this token:", "MAX_BUY" in rec)
    except TmsError as e:
        print("   FAILED:", repr(e))
else:
    print("   (skipped, no rows)")
