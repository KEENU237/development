"""
NSE F&O Trading System — Live Terminal Dashboard
Excel sheet jaisa view terminal mein
"""

import os
import sys
import time
import logging
from datetime import datetime

# Path fix karo
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import (
    KITE_API_KEY, KITE_API_SECRET,
    UOA_CONFIG, RISK
)
from core.kite_manager import KiteManager
from core.uoa_scanner import UOAScanner
from core.pcr_tracker import PCRTracker
from strategies.basket_builder import BasketOrderBuilder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/system.log"),
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def print_header(expiry: str):
    now = datetime.now().strftime("%d %b %Y  %H:%M:%S")
    print("=" * 65)
    print(f"  NSE F&O TRADING SYSTEM  ◆  {now}")
    print(f"  Expiry: {expiry}  |  Zerodha Kite Connect")
    print("=" * 65)


def print_market_overview(kite: KiteManager):
    symbols = ["NSE:NIFTY 50", "NSE:NIFTY BANK", "NSE:INDIA VIX"]
    prices = kite.get_ltp(symbols)
    print("\n  ▸ MARKET OVERVIEW")
    print(f"  {'SYMBOL':<15} {'LTP':>10}")
    print(f"  {'─'*25}")
    for sym, price in prices.items():
        label = sym.replace("NSE:", "")
        print(f"  {label:<15} {price:>10,.2f}")


def print_uoa_alerts(scanner: UOAScanner, expiry: str):
    print("\n  ▸ UNUSUAL OPTIONS ACTIVITY — LIVE ALERTS")
    print(f"  {'TIME':<10} {'SYMBOL':<12} {'TYPE':<5} {'STRIKE':<8} {'VOLUME':<10} {'MULT':<8} {'SENTIMENT'}")
    print(f"  {'─'*65}")

    alerts = scanner.scan(expiry)
    if not alerts:
        print("  No unusual activity detected")
        return

    for alert in scanner.get_top_alerts(10):
        fire = " 🔥" if alert.is_fire else ""
        mult_str = f"{alert.mult:.1f}x{fire}"
        print(
            f"  {alert.time:<10} {alert.symbol:<12} {alert.opt_type:<5} "
            f"{int(alert.strike):<8} {alert.volume:>8,}  {mult_str:<10} {alert.sentiment}"
        )


def print_pcr(tracker: PCRTracker, expiry: str):
    print("\n  ▸ PCR READINGS")
    print(f"  {'SYMBOL':<12} {'PCR':<8} {'ZONE':<15} {'SIGNAL':<15} {'STRATEGY'}")
    print(f"  {'─'*70}")

    for symbol in ["NIFTY", "BANKNIFTY"]:
        reading = tracker.get_pcr(symbol, expiry)
        if reading:
            print(
                f"  {reading.symbol:<12} {reading.pcr:<8.2f} "
                f"{reading.zone:<15} {reading.signal:<15} {reading.strategy}"
            )


def print_oi_chain(tracker: PCRTracker, symbol: str, expiry: str):
    chain = tracker.get_oi_chain(symbol, expiry, strikes_around_atm=6)
    if not chain:
        return

    print(f"\n  ▸ {symbol} OI CHAIN (ATM ±6 strikes)")
    print(f"  {'CE OI':>10}  {'CE CHG':>8}  {'CE LTP':>8}  {'STRIKE':>7}  {'PE LTP':>8}  {'PE CHG':>8}  {'PE OI':>10}  {'PCR':>5}")
    print(f"  {'─'*80}")

    for row in chain:
        print(
            f"  {row.ce_oi:>10,}  "
            f"{row.ce_oi_chg:>+8,}  "
            f"{row.ce_ltp:>8.1f}  "
            f"{int(row.strike):>7}  "
            f"{row.pe_ltp:>8.1f}  "
            f"{row.pe_oi_chg:>+8,}  "
            f"{row.pe_oi:>10,}  "
            f"{row.pcr:>5.2f}"
        )


def basket_order_menu(builder: BasketOrderBuilder, expiry: str):
    """Interactive basket order builder"""
    print("\n  ▸ BASKET ORDER BUILDER")
    print("  1. Bull Call Spread (Nifty)")
    print("  2. Bear Put Spread  (BankNifty)")
    print("  3. Iron Condor      (Nifty)")
    print("  0. Back")
    print()

    choice = input("  Strategy choose karo (0-3): ").strip()

    order = None
    if choice == "1":
        order = builder.build_bull_call_spread("NIFTY", expiry, lot_size=75)
    elif choice == "2":
        order = builder.build_bear_put_spread("BANKNIFTY", expiry, lot_size=30)
    elif choice == "3":
        order = builder.build_iron_condor("NIFTY", expiry, lot_size=75)
    elif choice == "0":
        return

    if not order:
        print("\n  Order build nahi hua — logs check karo")
        return

    print(order.summary())

    confirm = input("  Execute karna hai? (y/N): ").strip().lower()
    if confirm == "y":
        order_ids = builder.execute_basket(order)
        print(f"\n  {len(order_ids)} legs placed successfully")
        for oid in order_ids:
            print(f"  Order ID: {oid}")
    else:
        print("  Cancelled")


def main():
    # ── Setup ─────────────────────────────────────────────────────────────────
    os.makedirs("logs", exist_ok=True)
    os.makedirs("data", exist_ok=True)

    if KITE_API_KEY == "your_api_key_here":
        print("\n  ⚠️  config/settings.py mein KITE_API_KEY set karo!\n")
        sys.exit(1)

    kite    = KiteManager(KITE_API_KEY, KITE_API_SECRET)
    scanner = UOAScanner(kite, UOA_CONFIG)
    tracker = PCRTracker(kite)
    builder = BasketOrderBuilder(kite)

    # Default expiry (nearest Thursday)
    expiry = input("\nExpiry date (YYYY-MM-DD format, e.g. 2024-03-28): ").strip()

    # ── Main Loop ─────────────────────────────────────────────────────────────
    while True:
        clear()
        print_header(expiry)
        print_market_overview(kite)
        print_uoa_alerts(scanner, expiry)
        print_pcr(tracker, expiry)
        print_oi_chain(tracker, "NIFTY", expiry)

        print("\n" + "─" * 65)
        print("  [R] Refresh  |  [B] Basket Orders  |  [Q] Quit")
        print("─" * 65)

        try:
            cmd = input("  Command: ").strip().upper()
        except KeyboardInterrupt:
            print("\n\n  Exiting...")
            break

        if cmd == "Q":
            break
        elif cmd == "B":
            basket_order_menu(builder, expiry)
            input("\n  Enter dabao...")
        elif cmd == "R" or cmd == "":
            continue  # Refresh
        else:
            # Auto-refresh every 60 seconds
            print(f"\n  {UOA_CONFIG['scan_interval_seconds']}s baad refresh hoga...")
            time.sleep(UOA_CONFIG["scan_interval_seconds"])


if __name__ == "__main__":
    main()
