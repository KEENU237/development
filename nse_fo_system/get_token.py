"""
Run this script every morning before market opens to get a fresh Kite token.
Usage: python get_token.py
"""
import sys
import os
import pickle
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import KITE_API_KEY, KITE_API_SECRET
from kiteconnect import KiteConnect

kite = KiteConnect(api_key=KITE_API_KEY)

print("\n" + "="*55)
print("  ZERODHA KITE — Daily Token Generator")
print("="*55)
print("\nStep 1: Open this URL in your browser:\n")
print(kite.login_url())
print("\nStep 2: Log in with your Zerodha credentials.")
print("Step 3: After login, you will be redirected to a URL like:")
print("        http://127.0.0.1/?request_token=XXXXXXXX&status=success")
print("        Copy ONLY the request_token value (the long string).\n")
print("="*55)

raw = input("Paste request_token here and press Enter: ").strip()
# Auto-strip quotes and spaces in case they were accidentally included
request_token = raw.strip("'\"` ")
print(f"\n  Using token: {request_token}")
print(f"  Token length: {len(request_token)} characters")
if len(request_token) < 10:
    print("  WARNING: Token looks too short — make sure you copied the full value!")

try:
    session = kite.generate_session(request_token, api_secret=KITE_API_SECRET)
    access_token = session["access_token"]
    kite.set_access_token(access_token)

    # Save token
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    os.makedirs(data_dir, exist_ok=True)
    token_file = os.path.join(data_dir, "kite_token.pkl")
    with open(token_file, "wb") as f:
        pickle.dump({"date": date.today().isoformat(), "access_token": access_token}, f)

    # Verify
    profile = kite.profile()
    print("\n" + "="*55)
    print(f"  LOGIN SUCCESSFUL!")
    print(f"  Name:   {profile['user_name']}")
    print(f"  Email:  {profile['email']}")
    print(f"  Token valid for: {date.today().isoformat()}")
    print("="*55)
    print("\nYou can now run:  python main.py\n")

except Exception as e:
    print(f"\n  ERROR: {e}")
    print("\n  Common causes:")
    print("  1. Token already used — each request_token works ONLY ONCE")
    print("  2. Token expired  — they expire within 2 minutes of generation")
    print("  3. Wrong value    — must be the part AFTER 'request_token=' and BEFORE '&'")
    print("\n  SOLUTION: Go back to browser, open the login URL again, log in FRESH,")
    print("  and immediately paste the new request_token here within 60 seconds.\n")
