"""
Market Utilities — NSE F&O specific helpers
Lot sizes, strike rounding, cost breakdown, expiry detection, market hours
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ─── LOT SIZES (SEBI-mandated, as of 2025-26) ────────────────────────────────
LOT_SIZES: dict = {
    "NIFTY":        75,
    "BANKNIFTY":    30,
    "FINNIFTY":     40,
    "MIDCPNIFTY":   75,
    "SENSEX":       10,
    "BANKEX":       15,
    # Stock F&O
    "RELIANCE":     250,
    "TCS":          150,
    "INFY":         400,
    "ICICIBANK":    700,
    "SBIN":        1500,
    "HDFC":         300,
    "HDFCBANK":     550,
    "AXISBANK":     625,
    "LT":           150,
    "BAJFINANCE":   125,
    "WIPRO":       1500,
    "KOTAKBANK":    400,
    "TECHM":        600,
    "ASIANPAINT":   200,
    "HINDUNILVR":   300,
    "MARUTI":        50,
    "TATAMOTORS":  1425,
    "ADANIENT":    275,
    "ONGC":        1925,
    "NTPC":        2250,
    "POWERGRID":   2700,
}

# ─── STRIKE STEP SIZES ───────────────────────────────────────────────────────
STRIKE_STEPS: dict = {
    "NIFTY":       50,
    "BANKNIFTY":  100,
    "FINNIFTY":    50,
    "MIDCPNIFTY":  25,
    "SENSEX":     100,
}

# ─── NSE F&O TRANSACTION COST CONSTANTS (Zerodha, 2025) ──────────────────────
_BROKERAGE        = 20.00      # ₹20 flat per executed order
_STT_SELL_PCT     = 0.000500   # 0.05% on SELL side (on premium)
_EXCHANGE_CHG_PCT = 0.000530   # 0.053% on turnover (NSE options)
_SEBI_CHG_PCT     = 0.000001   # ₹10 per crore  ≈ 0.000001
_GST_PCT          = 0.180000   # 18% GST on brokerage + exchange + SEBI
_STAMP_DUTY_PCT   = 0.000030   # 0.003% on BUY side

# ─── MARKET HOURS (IST) ──────────────────────────────────────────────────────
_OPEN_H,  _OPEN_M  = 9,  15
_CLOSE_H, _CLOSE_M = 15, 30


# ═══════════════════════════════════════════════════════════════════════════════
# LOT & STRIKE HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def get_lot_size(symbol: str) -> int:
    """SEBI lot size for the symbol (returns 1 if unknown)."""
    return LOT_SIZES.get(symbol.upper(), 1)


def round_to_strike(price: float, symbol: str) -> float:
    """Round price to the nearest valid strike for the given symbol."""
    step = STRIKE_STEPS.get(symbol.upper(), 50)
    return round(price / step) * step


# ═══════════════════════════════════════════════════════════════════════════════
# EXPIRY DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

def get_nearest_expiry(symbol: str = "NIFTY", kite=None) -> date:
    """
    Returns the nearest weekly expiry for the symbol.

    If kite is provided: fetches real expiries from NFO instruments
    (handles holidays where expiry shifts by 1 day).
    Otherwise falls back to weekday calculation.
    """
    today = date.today()

    # ── Live fetch from Kite (most accurate) ──────────────────────────────────
    if kite is not None:
        try:
            instruments = kite.instruments("NFO")
            expiries = sorted(set(
                i["expiry"] for i in instruments
                if i["name"] == symbol.upper()
                and i["instrument_type"] in ("CE", "PE")
                and i["expiry"] >= today
            ))
            if expiries:
                # Return soonest expiry that is today or in future
                for exp in expiries:
                    exp_date = exp if isinstance(exp, date) else date.fromisoformat(str(exp)[:10])
                    now = datetime.now()
                    # If expiry is today but market closed, skip to next
                    if exp_date == today:
                        if now.hour > _CLOSE_H or (now.hour == _CLOSE_H and now.minute >= _CLOSE_M):
                            continue
                    return exp_date
        except Exception as e:
            logger.warning(f"Live expiry fetch failed for {symbol}: {e}")

    # ── Weekday fallback (no kite available) ──────────────────────────────────
    expiry_weekday = {
        "NIFTY":     0,   # Monday
        "BANKNIFTY": 2,   # Wednesday
        "FINNIFTY":  1,   # Tuesday
    }.get(symbol.upper(), 0)

    days_ahead = (expiry_weekday - today.weekday()) % 7
    if days_ahead == 0:
        now = datetime.now()
        if now.hour > _CLOSE_H or (now.hour == _CLOSE_H and now.minute >= _CLOSE_M):
            days_ahead = 7
    return today + timedelta(days=days_ahead)


def get_monthly_expiry(month_offset: int = 0) -> date:
    """Last Thursday of the month at [month_offset] months from today."""
    today = date.today()
    year  = today.year
    month = today.month + month_offset
    while month > 12:
        month -= 12
        year  += 1
    # Find last day of that month
    first_next = date(year + (month // 12), (month % 12) + 1, 1) if month < 12 \
        else date(year + 1, 1, 1)
    last = first_next - timedelta(days=1)
    # Walk back to last Thursday
    while last.weekday() != 3:
        last -= timedelta(days=1)
    return last


def days_to_expiry(expiry_str: str) -> int:
    """Calendar days remaining to expiry (0 on expiry day)."""
    try:
        return max((date.fromisoformat(expiry_str) - date.today()).days, 0)
    except Exception:
        return 0


# ═══════════════════════════════════════════════════════════════════════════════
# MARKET STATUS
# ═══════════════════════════════════════════════════════════════════════════════

def is_market_open() -> bool:
    """True if NSE is in continuous trading session right now."""
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = (now.hour, now.minute)
    return (_OPEN_H, _OPEN_M) <= t < (_CLOSE_H, _CLOSE_M)


def get_market_status() -> str:
    """Returns 'OPEN', 'PRE-OPEN', 'CLOSED', or 'WEEKEND'."""
    now = datetime.now()
    if now.weekday() >= 5:
        return "WEEKEND"
    h, m = now.hour, now.minute
    if (h, m) < (9, 0):
        return "CLOSED"
    elif (h, m) < (_OPEN_H, _OPEN_M):
        return "PRE-OPEN"
    elif (h, m) < (_CLOSE_H, _CLOSE_M):
        return "OPEN"
    else:
        return "CLOSED"


# ═══════════════════════════════════════════════════════════════════════════════
# TRANSACTION COST CALCULATOR
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_order_cost(
    premium_per_unit: float,
    qty: int,
    action: str,
) -> dict:
    """
    Full NSE F&O transaction cost breakdown for one order leg.

    Parameters
    ----------
    premium_per_unit : Option LTP (premium per share)
    qty              : Total quantity = lots × lot_size
    action           : 'BUY' or 'SELL'

    Returns
    -------
    dict with keys: turnover, brokerage, stt, exchange, sebi, gst,
                    stamp_duty, total_cost
    """
    turnover  = premium_per_unit * qty
    brokerage = _BROKERAGE
    stt       = turnover * _STT_SELL_PCT    if action.upper() == "SELL" else 0.0
    exchange  = turnover * _EXCHANGE_CHG_PCT
    sebi      = turnover * _SEBI_CHG_PCT
    gst       = (brokerage + exchange + sebi) * _GST_PCT
    stamp     = turnover * _STAMP_DUTY_PCT   if action.upper() == "BUY"  else 0.0
    total     = brokerage + stt + exchange + sebi + gst + stamp

    return {
        "turnover":   round(turnover,  2),
        "brokerage":  round(brokerage, 2),
        "stt":        round(stt,       2),
        "exchange":   round(exchange,  4),
        "sebi":       round(sebi,      4),
        "gst":        round(gst,       2),
        "stamp_duty": round(stamp,     2),
        "total_cost": round(total,     2),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# DISPLAY HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def format_number(n: float) -> str:
    """Compact Indian-style number formatting (K / L / Cr)."""
    if abs(n) >= 1_00_00_000:
        return f"{n / 1_00_00_000:.1f}Cr"
    elif abs(n) >= 1_00_000:
        return f"{n / 1_00_000:.1f}L"
    elif abs(n) >= 1_000:
        return f"{n / 1_000:.1f}K"
    return f"{int(n)}"


def format_inr(amount: float) -> str:
    """Format rupee amount with sign and commas."""
    sign = "+" if amount >= 0 else ""
    return f"₹{sign}{amount:,.0f}"
