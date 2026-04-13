"""Debug script — check why OI chain is empty."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import KITE_API_KEY, KITE_API_SECRET
from core.kite_manager import KiteManager

print("Connecting to Kite...")
km = KiteManager(KITE_API_KEY, KITE_API_SECRET)
kite = km.kite

# Step 1: Check what expiries exist for NIFTY in NFO
print("\nFetching NFO instruments (this takes 10-15 seconds)...")
instruments = kite.instruments("NFO")
nifty_instr = [i for i in instruments if i["name"] == "NIFTY" and i["instrument_type"] in ("CE","PE")]

# Get unique expiries
expiries = sorted(set(str(i["expiry"]) for i in nifty_instr))
print(f"\nNIFTY available expiries ({len(expiries)} total):")
for e in expiries[:10]:
    count = sum(1 for i in nifty_instr if str(i["expiry"]) == e)
    print(f"  {e}  ({count} strikes)")

# Step 2: Try the expiry the dashboard is using
test_expiry = "2026-04-02"
chain = [i for i in nifty_instr if str(i["expiry"]) == test_expiry]
print(f"\nChain for {test_expiry}: {len(chain)} instruments")

# Step 3: Try with [:10] slicing (in case expiry has time component)
chain2 = [i for i in nifty_instr if str(i["expiry"])[:10] == test_expiry[:10]]
print(f"Chain with [:10] match: {len(chain2)} instruments")

# Step 4: Show raw expiry format from Kite
if nifty_instr:
    sample = nifty_instr[0]
    print(f"\nRaw expiry value: {repr(sample['expiry'])}")
    print(f"Type: {type(sample['expiry'])}")
    print(f"str(): '{str(sample['expiry'])}'")

# Step 5: Test quote fetch on a couple of instruments
if chain2:
    sample_instruments = [f"NFO:{i['tradingsymbol']}" for i in chain2[:3]]
    print(f"\nFetching quotes for: {sample_instruments}")
    try:
        quotes = kite.quote(sample_instruments)
        for k, v in quotes.items():
            print(f"  {k}: LTP={v.get('last_price')} OI={v.get('oi')}")
    except Exception as e:
        print(f"  Quote fetch error: {e}")

print("\nDone.")
