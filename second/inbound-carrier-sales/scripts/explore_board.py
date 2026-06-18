"""Sweep the board to discover what loads/lanes exist. Run: python -m scripts.explore_board"""

from collections import Counter

from app.config import get_settings
from app.tms_client import TmsClient, TmsError

s = get_settings()
client = TmsClient(
    host=s.tms_host, port=s.tms_port, auth_token=s.tms_auth_token,
    timeout=s.tms_timeout_seconds, max_retries=s.tms_max_retries,
)

STATES = ["GA", "TX", "FL", "CA", "IL", "NJ", "NC", "OH", "PA", "TN", "AZ", "WA", "CO", "NY", "MI"]
EQUIP = ["DRY_VAN", "REEFER", "FLATBED"]

found = {}
eq_counter = Counter()
state_counter = Counter()

for st in STATES:
    for eq in EQUIP:
        try:
            rows = client.load_query(ORIG_STATE=st, EQTYPE=eq, MAX_RESULTS="10")
        except TmsError as e:
            print(f"  {st}/{eq}: ERROR {e}")
            continue
        if rows:
            eq_counter[eq] += len(rows)
            state_counter[st] += len(rows)
            for r in rows:
                found[r.get("LOAD_ID")] = r
            print(f"  ORIG {st} / {eq}: {len(rows)} -> "
                  f"{[ (r.get('ORIG_CITY'), r.get('DEST_STATE'), r.get('RATE')) for r in rows ]}")

print(f"\nUnique loads discovered: {len(found)}")
print("By equipment:", dict(eq_counter))
print("By origin state:", dict(state_counter))

if found:
    first = next(iter(found.values()))
    lid = first["LOAD_ID"]
    print(f"\nLOAD_GET sample on {lid}:")
    rec = client.load_get(lid)
    for k, v in rec.items():
        print(f"   {k}: {v}")
    print("MAX_BUY present on this token:", "MAX_BUY" in rec)
