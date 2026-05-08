"""
Intraday Stock Scanner — IFS v4.0
==================================
7-pillar score + 6 filters + market regime detection

Pillars:
  P1 VWAP alignment          : ±2
  P2 ORB breakout (2-candle) : ±3
  P3 Volume directional      : ±3
  P4 PDH/PDL breakout        : ±3
  P5 First candle bias       : ±1
  P6 Nifty alignment bonus   : ±1
  P7 Relative Strength/Nifty : ±2
  Max: ±15  Buy zone: ≥9  Sell zone: ≤-7

Hard filters (cause FILTERED status):
  1. Gap > 1.5%              → FILTERED
  2. Symbol in skip list     → FILTERED

Soft filters (score adjustment / warning only):
  3. ORB invalid range       → p2 = 0  (stock still scored)
  4. VIX > 22                → BUY score zeroed
  5. Nifty strong opposite   → score downgraded
  6. Sector index opposite   → score downgraded
  7. Market Regime CHOPPY    → banner warning
"""

import time
import logging
from datetime import datetime, date, timedelta

import pandas as pd
import streamlit as st

logger = logging.getLogger(__name__)

# ── Universe ──────────────────────────────────────────────────────────────────
SCAN_UNIVERSE = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY",
    "HINDUNILVR", "ITC", "SBIN", "BHARTIARTL", "KOTAKBANK",
    "LT", "AXISBANK", "ASIANPAINT", "MARUTI", "TITAN",
    "SUNPHARMA", "WIPRO", "ULTRACEMCO", "TECHM", "HCLTECH",
    "BAJFINANCE", "POWERGRID", "NTPC", "ONGC", "TATAMOTORS",
    "TATASTEEL", "ADANIENT", "ADANIPORTS", "COALINDIA", "BAJAJFINSV",
    "DIVISLAB", "DRREDDY", "EICHERMOT", "GRASIM", "HEROMOTOCO",
    "HINDALCO", "INDUSINDBK", "JSWSTEEL", "BRITANNIA", "CIPLA",
    "APOLLOHOSP", "BPCL", "TATACONSUM", "SBILIFE", "HDFCLIFE",
    "PIDILITIND", "SIEMENS", "SHRIRAMFIN", "TRENT", "ZOMATO",
    "DMART", "HAVELLS", "BERGEPAINT", "TORNTPHARM", "LUPIN",
    "MUTHOOTFIN", "CHOLAFIN", "BANKBARODA", "PNB", "FEDERALBNK",
    "IDFCFIRSTB", "PERSISTENT", "MPHASIS", "LTIM", "COFORGE",
    "TATAPOWER", "GODREJCP", "DABUR", "MARICO", "COLPAL",
    "IRCTC", "CONCOR", "AARTIIND", "UPL", "CHAMBLFERT",
    "NMDC", "SAIL", "RECLTD", "PFC", "CANBK",
    "UNIONBANK", "AUBANK", "BANDHANBNK", "RBLBANK",
    "KPITTECH", "NHPC", "ADANIGREEN", "TORNTPOWER", "EMAMILTD",
    "PIIND", "COROMANDEL", "INDIGO",
]

# ── Sector map ────────────────────────────────────────────────────────────────
# Stock → which sector index to check
_SECTOR_STOCKS = {
    "NIFTY BANK": [
        "HDFCBANK", "ICICIBANK", "KOTAKBANK", "AXISBANK", "SBIN",
        "BANKBARODA", "INDUSINDBK", "FEDERALBNK", "IDFCFIRSTB",
        "BANDHANBNK", "RBLBANK", "AUBANK", "CANBK", "UNIONBANK", "PNB",
    ],
    "NIFTY IT": [
        "TCS", "INFY", "WIPRO", "HCLTECH", "TECHM",
        "PERSISTENT", "MPHASIS", "LTIM", "COFORGE", "KPITTECH",
    ],
    "NIFTY PHARMA": [
        "SUNPHARMA", "DIVISLAB", "DRREDDY", "CIPLA", "TORNTPHARM", "LUPIN",
        "APOLLOHOSP",
    ],
    "NIFTY AUTO": [
        "MARUTI", "TATAMOTORS", "EICHERMOT", "HEROMOTOCO",
    ],
    "NIFTY FMCG": [
        "HINDUNILVR", "ITC", "BRITANNIA", "TATACONSUM", "GODREJCP",
        "DABUR", "MARICO", "COLPAL", "EMAMILTD",
        "ZOMATO", "TRENT", "DMART",
    ],
    "NIFTY METAL": [
        "TATASTEEL", "HINDALCO", "JSWSTEEL", "NMDC", "SAIL",
    ],
    "NIFTY ENERGY": [
        "ONGC", "BPCL", "COALINDIA", "TATAPOWER", "NHPC",
        "ADANIGREEN", "TORNTPOWER",
    ],
    "NIFTY INFRA": [
        "LT", "SIEMENS", "POWERGRID", "NTPC", "RECLTD", "PFC",
        "ADANIENT", "ADANIPORTS", "CONCOR", "IRCTC",
        "ULTRACEMCO", "GRASIM",
    ],
    "NIFTY FIN SERVICE": [
        "BAJFINANCE", "BAJAJFINSV", "SBILIFE", "HDFCLIFE",
        "MUTHOOTFIN", "CHOLAFIN", "SHRIRAMFIN",
    ],
    "NIFTY CONSR DURBL": [
        "TITAN", "HAVELLS", "ASIANPAINT", "BERGEPAINT", "PIDILITIND",
    ],
    "NIFTY OIL AND GAS": [
        "RELIANCE",
    ],
}
# Reverse: symbol → sector index name
STOCK_SECTOR = {
    sym: idx
    for idx, syms in _SECTOR_STOCKS.items()
    for sym in syms
}

# Thresholds
VIX_LIMIT  = 22.0
GAP_LIMIT  = 1.5
ORB_MIN    = 0.3
ORB_MAX    = 1.5
BUY_ZONE   = 9    # ±15 max → 9 = 60% threshold (was 8/±13 = 62%)
SELL_ZONE  = -7   # symmetric tightening

_SIG_COLOR = {
    "STRONG BUY":  "#00c853",
    "BUY":         "#43a047",
    "WAIT":        "#9e9e9e",
    "SELL":        "#e53935",
    "STRONG SELL": "#b71c1c",
    "FILTERED":    "#ff6f00",
}


# ══════════════════════════════════════════════════════════════════════════════
# MATH
# ══════════════════════════════════════════════════════════════════════════════

def _vwap(df):
    tp = (df["high"] + df["low"] + df["close"]) / 3
    return (tp * df["volume"]).cumsum() / df["volume"].cumsum()

def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()

def _slope(s, n=3):
    return float(s.iloc[-1] - s.iloc[-n]) if len(s) >= n + 1 else 0.0


# ══════════════════════════════════════════════════════════════════════════════
# DATA
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=1800, show_spinner=False)
def _load_tokens(_kite):
    """Equity + sector index tokens. Cache 30 min."""
    try:
        instr = pd.DataFrame(_kite.instruments("NSE"))
        eq    = instr[instr["instrument_type"] == "EQ"]
        idx   = instr[instr["instrument_type"] == "INDEX"]

        tokens = {}

        # Equity tokens
        for sym in SCAN_UNIVERSE:
            row = eq[eq["tradingsymbol"] == sym]
            if not row.empty:
                tokens[sym] = int(row.iloc[0]["instrument_token"])

        # Nifty 50 index
        nifty_row = idx[idx["tradingsymbol"] == "NIFTY 50"]
        tokens["__NIFTY__"] = (
            int(nifty_row.iloc[0]["instrument_token"])
            if not nifty_row.empty else 256265
        )

        # Sector indices
        for sec_name in _SECTOR_STOCKS:
            row = idx[idx["tradingsymbol"] == sec_name]
            if not row.empty:
                tokens[f"__SEC__{sec_name}"] = int(row.iloc[0]["instrument_token"])

        return tokens
    except Exception as e:
        logger.error(f"Token load: {e}")
        return {}


def _fetch(kite, token, from_dt, to_dt):
    """5-min OHLCV → DataFrame or None."""
    try:
        raw = kite.historical_data(token, from_dt, to_dt, "5minute")
        if not raw:
            return None
        df = pd.DataFrame(raw)
        df.columns = ["date", "open", "high", "low", "close", "volume"]
        df["date"] = pd.to_datetime(df["date"])
        return df
    except Exception:
        return None


def _trend_from_df(df):
    """Compute BULLISH/BEARISH/NEUTRAL from 5-min DataFrame."""
    if df is None or len(df) < 4:
        return {"dir": "NEUTRAL", "score": 0, "price": 0, "vwap": 0, "open": 0}

    df = df.copy()
    df["vwap"] = _vwap(df)
    df["ema9"] = _ema(df["close"], 9)
    open_px = float(df["open"].iloc[0])
    price   = float(df["close"].iloc[-1])
    vwap    = float(df["vwap"].iloc[-1])
    ema9    = float(df["ema9"].iloc[-1])

    bull = sum([
        price > vwap,
        _slope(df["vwap"]) > 0,
        price > ema9,
        _slope(df["ema9"]) > 0,
    ])

    if   bull >= 3: d, s = "BULLISH",  1
    elif bull <= 1: d, s = "BEARISH", -1
    else:           d, s = "NEUTRAL",  0

    return {"dir": d, "score": s,
            "price": round(price, 2), "vwap": round(vwap, 2),
            "open":  round(open_px, 2)}


def _market_regime(df):
    """
    Nifty ke pehle 30 min (6 candles of 5-min) se market regime detect karo.
    Returns: dict with regime, move_pct, range_pct
    """
    if df is None or len(df) < 4:
        return {"regime": "UNKNOWN", "move_pct": 0.0, "range_pct": 0.0}

    first_30  = df.head(6)
    open_px   = float(first_30.iloc[0]["open"])
    close_30  = float(first_30.iloc[-1]["close"])
    high_30   = float(first_30["high"].max())
    low_30    = float(first_30["low"].min())

    move_pct  = round((close_30 - open_px) / open_px * 100, 2)
    range_pct = round((high_30  - low_30)  / open_px * 100, 2)

    if range_pct < 0.3:
        regime = "CHOPPY"
    elif move_pct >= 0.5:
        regime = "TRENDING_BULL"
    elif move_pct <= -0.5:
        regime = "TRENDING_BEAR"
    else:
        regime = "NEUTRAL"

    return {"regime": regime, "move_pct": move_pct, "range_pct": range_pct}


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_trends(_kite, tokens_json, today_str):
    """
    Fetch Nifty + all sector index trends in one cached call.
    Returns dict: key → trend dict.
    Cache refreshes every 5 min.
    """
    import json
    tokens = json.loads(tokens_json)
    today  = date.today()
    from_dt = datetime(today.year, today.month, today.day, 9, 15)
    to_dt   = datetime.now()

    trends = {}

    # Nifty
    nifty_tok = tokens.get("__NIFTY__", 256265)
    df = _fetch(_kite, nifty_tok, from_dt, to_dt)
    trends["__NIFTY__"]  = _trend_from_df(df)
    trends["__REGIME__"] = _market_regime(df)

    # Sectors
    for key, tok in tokens.items():
        if key.startswith("__SEC__"):
            df = _fetch(_kite, tok, from_dt, to_dt)
            trends[key] = _trend_from_df(df)

    return trends


def _vix(kite):
    try:
        return float(kite.ltp(["NSE:INDIA VIX"])["NSE:INDIA VIX"]["last_price"])
    except Exception:
        return 0.0


def _prev_trading_day():
    d = date.today() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def _trading_days_ago(n):
    """n trading days pehle ka date return karo (weekends skip)."""
    d = date.today()
    count = 0
    while count < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            count += 1
    return d


# ══════════════════════════════════════════════════════════════════════════════
# IFS v4 SCORE
# ══════════════════════════════════════════════════════════════════════════════

def _ifs(today_df, prev_df, symbol, nifty, sector_trend, vix_val, skip_list,
         hist_df=None):
    """
    IFS v4 — 6 pillars + 7 filters + PDH/PDL + directional volume.
    hist_df: last 5 trading days data (volume baseline ke liye).
    Returns scored dict or None.
    """
    if today_df is None or len(today_df) < 4:
        return None

    # ── Filter 0: Result date / manual skip ───────────────────────────────────
    if symbol.upper() in skip_list:
        return {
            "symbol": symbol, "score": 0, "signal": "FILTERED", "dir": "NEUTRAL",
            "price": 0, "vwap": 0, "entry": 0, "stop": 0, "target": 0,
            "vol_ratio": 0, "gap_pct": 0, "orb_h": 0, "orb_l": 0, "orb_rng": 0,
            "pdh": 0, "pdl": 0, "rs_alpha": 0, "adr": 0, "adr_consumed": 0,
            "filters": ["Result date / manual skip"],
            "p1": 0, "p2": 0, "p3": 0, "p4": 0, "p5": 0, "p6": 0, "p7": 0,
        }

    df = today_df.copy().reset_index(drop=True)
    df["vwap"] = _vwap(df)

    price    = float(df["close"].iloc[-1])
    open_px  = float(df["open"].iloc[0])
    vwap_val = float(df["vwap"].iloc[-1])
    cur_vol  = float(df["volume"].iloc[-1])

    # Volume baseline — 5-day average if available, else previous day, else today
    if hist_df is not None and len(hist_df) >= 20:
        avg_vol = float(hist_df["volume"].mean())
    elif prev_df is not None and len(prev_df) >= 20:
        avg_vol = float(prev_df["volume"].mean())
    else:
        avg_vol = float(df["volume"].mean())
    vol_ratio = cur_vol / avg_vol if avg_vol > 0 else 0

    # ADR — Average Daily Range (last 5 days)
    if hist_df is not None and len(hist_df) > 0:
        daily = hist_df.groupby(hist_df["date"].dt.date).agg(
            h=("high", "max"), l=("low", "min")
        )
        adr = round(float(((daily["h"] - daily["l"]) / daily["l"] * 100).mean()), 2)
    else:
        adr = 0.0
    today_high    = float(df["high"].max())
    today_low     = float(df["low"].min())
    today_range   = (today_high - today_low) / today_low * 100 if today_low > 0 else 0
    adr_consumed  = round(today_range / adr * 100, 1) if adr > 0 else 0.0

    # Gap
    if prev_df is not None and len(prev_df) > 0:
        prev_close = float(prev_df["close"].iloc[-1])
        gap_pct    = (open_px - prev_close) / prev_close * 100
    else:
        gap_pct = 0.0

    # PDH / PDL — Previous Day High and Low
    if prev_df is not None and len(prev_df) > 0:
        pdh = float(prev_df["high"].max())
        pdl = float(prev_df["low"].min())
    else:
        pdh = pdl = 0.0

    # ORB
    orb      = df.head(3)
    orb_high = float(orb["high"].max())
    orb_low  = float(orb["low"].min())
    orb_rng  = (orb_high - orb_low) / orb_low * 100

    # ── Hard filters (FILTERED status) ───────────────────────────────────────
    filters = []       # display warnings shown in expander
    hard_filter = False  # True = stock completely FILTERED (only gap triggers)

    if abs(gap_pct) > GAP_LIMIT:
        hard_filter = True
        filters.append(f"Gap {gap_pct:+.1f}% > ±{GAP_LIMIT}%")

    # ORB range — soft: just zeroes p2, stock is still scored on other pillars
    orb_invalid = False
    if len(df) > 3 and not (ORB_MIN <= orb_rng <= ORB_MAX):
        orb_invalid = True
        filters.append(
            f"ORB {'tight' if orb_rng < ORB_MIN else 'wide'} ({orb_rng:.2f}%) — P2 skipped"
        )

    # ── P1 VWAP ───────────────────────────────────────────────────────────────
    if   price > vwap_val and _slope(df["vwap"]) > 0: p1 =  2
    elif price < vwap_val and _slope(df["vwap"]) < 0: p1 = -2
    else:                                               p1 =  0

    # ── P2 ORB — 2-candle confirmation ───────────────────────────────────────
    # v3: Require 2 consecutive candle closes above/below ORB for full +3/-3
    # Single candle = +2/-2 (partial confidence)
    if len(df) <= 3 or orb_invalid:
        p2 = 0
    else:
        post_orb = df.iloc[3:]
        if len(post_orb) >= 2:
            last2_close = post_orb["close"].tail(2).values
            if (last2_close > orb_high).all():
                p2 = 3   # 2-candle confirmed bullish breakout
            elif last2_close[-1] > orb_high:
                p2 = 2   # Single candle — partial confidence
            elif (last2_close < orb_low).all():
                p2 = -3  # 2-candle confirmed breakdown
            elif last2_close[-1] < orb_low:
                p2 = -2  # Single candle breakdown
            else:
                p2 = 0
        elif len(post_orb) == 1:
            c = float(post_orb.iloc[-1]["close"])
            if   c > orb_high: p2 =  2
            elif c < orb_low:  p2 = -2
            else:               p2 =  0
        else:
            p2 = 0

    # ── P3 Volume (directional) ───────────────────────────────────────────────
    # Magnitude: kitna unusual volume hai
    if   vol_ratio >= 3.0: p3_mag = 3
    elif vol_ratio >= 2.0: p3_mag = 2
    elif vol_ratio >= 1.5: p3_mag = 1
    else:                  p3_mag = 0
    # Direction: last candle bullish ya bearish
    last_c = df.iloc[-1]
    p3_dir = 1 if last_c["close"] >= last_c["open"] else -1
    p3 = p3_mag * p3_dir

    # ── P4 PDH/PDL Breakout ───────────────────────────────────────────────────
    if pdh <= 0 or pdl <= 0:
        p4 = 0                                        # prev data nahi hai
    elif price > pdh:
        p4 =  3 if vol_ratio >= 1.5 else  1           # PDH breakout
    elif price < pdl:
        p4 = -3 if vol_ratio >= 1.5 else -1           # PDL breakdown
    elif price >= pdh * (1 - 0.002):
        p4 =  1                                        # PDH ke 0.2% ke andar — testing
    elif price <= pdl * (1 + 0.002):
        p4 = -1                                        # PDL ke 0.2% ke andar — testing
    else:
        p4 =  0                                        # Range ke andar

    # ── P5 First candle ───────────────────────────────────────────────────────
    fc  = df.iloc[0]
    rng = fc["high"] - fc["low"]
    if rng > 0:
        pos = (fc["close"] - fc["low"]) / rng
        if   fc["close"] > fc["open"] and pos > 0.6: p5 =  1
        elif fc["close"] < fc["open"] and pos < 0.4: p5 = -1
        else:                                          p5 =  0
    else:
        p5 = 0

    # ── P6 Nifty alignment ────────────────────────────────────────────────────
    p6 = nifty.get("score", 0)

    # ── P7 Relative Strength vs Nifty ────────────────────────────────────────
    nifty_open = nifty.get("open", 0)
    if nifty_open > 0 and open_px > 0:
        stock_chg  = (price   - open_px)    / open_px    * 100
        nifty_chg  = (nifty["price"] - nifty_open) / nifty_open * 100
        rs_alpha   = round(stock_chg - nifty_chg, 2)   # outperformance vs Nifty
        if   rs_alpha >=  0.5: p7 =  2
        elif rs_alpha >=  0.2: p7 =  1
        elif rs_alpha <= -0.5: p7 = -2
        elif rs_alpha <= -0.2: p7 = -1
        else:                  p7 =  0
    else:
        rs_alpha = 0.0
        p7       = 0

    score = p1 + p2 + p3 + p4 + p5 + p6 + p7

    # ── Post-score filters ────────────────────────────────────────────────────

    # VIX
    if vix_val > VIX_LIMIT and score > 0:
        filters.append(f"VIX {vix_val:.1f} > {VIX_LIMIT} — buys blocked")
        score = 0

    # Nifty opposite
    if nifty["dir"] == "BEARISH" and score >= BUY_ZONE:
        filters.append("Nifty bearish — buy downgraded")
        score = BUY_ZONE - 1
    elif nifty["dir"] == "BULLISH" and score <= SELL_ZONE:
        filters.append("Nifty bullish — sell downgraded")
        score = SELL_ZONE + 1

    # Sector alignment — NEW in v3
    sec_key = f"__SEC__{STOCK_SECTOR.get(symbol, '')}"
    if sec_key in sector_trend:
        sec = sector_trend[sec_key]
        if sec["dir"] == "BEARISH" and score >= BUY_ZONE:
            filters.append(f"Sector ({STOCK_SECTOR[symbol]}) bearish — buy downgraded")
            score = BUY_ZONE - 1
        elif sec["dir"] == "BULLISH" and score <= SELL_ZONE:
            filters.append(f"Sector ({STOCK_SECTOR.get(symbol,'')}) bullish — sell downgraded")
            score = SELL_ZONE + 1

    # ── Signal ────────────────────────────────────────────────────────────────
    if hard_filter:              sig, dirn = "FILTERED",   "NEUTRAL"
    elif score >= BUY_ZONE + 2: sig, dirn = "STRONG BUY", "BULLISH"
    elif score >= BUY_ZONE:     sig, dirn = "BUY",         "BULLISH"
    elif score <= SELL_ZONE - 2:sig, dirn = "STRONG SELL", "BEARISH"
    elif score <= SELL_ZONE:    sig, dirn = "SELL",        "BEARISH"
    else:                       sig, dirn = "WAIT",        "NEUTRAL"

    # ── Entry / SL / Target ───────────────────────────────────────────────────
    entry = stop = target = 0.0
    if dirn == "BULLISH" and p2 > 0:
        entry  = price
        stop   = orb_low
        target = entry + (entry - stop) * 1.5
    elif dirn == "BEARISH" and p2 < 0:
        entry  = price
        stop   = orb_high
        target = entry - (stop - entry) * 1.5

    return {
        "symbol":    symbol,
        "score":     score,
        "signal":    sig,
        "dir":       dirn,
        "price":     round(price,     2),
        "vwap":      round(vwap_val,  2),
        "entry":     round(entry,     2),
        "stop":      round(stop,      2),
        "target":    round(target,    2),
        "vol_ratio": round(vol_ratio, 2),
        "gap_pct":   round(gap_pct,   2),
        "orb_h":     round(orb_high,  2),
        "orb_l":     round(orb_low,   2),
        "orb_rng":   round(orb_rng,   2),
        "pdh":          round(pdh,       2),
        "pdl":          round(pdl,       2),
        "rs_alpha":     rs_alpha,
        "adr":          adr,
        "adr_consumed": adr_consumed,
        "filters":      filters,
        "sector":    STOCK_SECTOR.get(symbol, "Other"),
        "p1": p1, "p2": p2, "p3": p3, "p4": p4, "p5": p5, "p6": p6, "p7": p7,
    }


# ══════════════════════════════════════════════════════════════════════════════
# RENDER
# ══════════════════════════════════════════════════════════════════════════════

def _badge(sig):
    c = _SIG_COLOR.get(sig, "#9e9e9e")
    return (f"<span style='background:{c};color:#fff;padding:3px 10px;"
            f"border-radius:5px;font-size:12px;font-weight:700'>{sig}</span>")

def _trend_badge(d):
    c = {"BULLISH": "#00c853", "BEARISH": "#d50000"}.get(d, "#ff9800")
    return (f"<span style='background:{c};color:#fff;padding:2px 7px;"
            f"border-radius:4px;font-size:11px'>{d}</span>")


def render_stock_scanner(kite=None, alert_engine=None):
    st.markdown("## 📡 Intraday Stock Scanner")
    st.caption("IFS v4.0 · PDH/PDL · Directional Vol · Market Regime · 8 Sectors · 2-Candle ORB")

    if kite is None or not kite.is_connected():
        st.error("❌ Zerodha Kite connected nahi. Token refresh karo.")
        return

    kite_obj  = kite.kite
    now       = datetime.now()
    today_str = date.today().isoformat()

    # ── Time warnings ─────────────────────────────────────────────────────────
    h, m = now.hour, now.minute
    if h < 9 or (h == 9 and m < 15):
        st.warning("⏰ Market khula nahi hai abhi.")
    elif h == 9 and m < 30:
        st.info("⏳ ORB ban rahi hai (9:15–9:29). 9:30 ke baad scan karo.")
    elif h > 11 or (h == 11 and m > 30):
        st.warning("⚠️ 11:30 ke baad naye intraday setups mat lo.")

    # ── Load tokens + trends ──────────────────────────────────────────────────
    tokens = _load_tokens(kite_obj)
    if not tokens:
        st.error("Tokens load nahi hue. Kite connection check karo.")
        return

    import json
    tokens_json  = json.dumps(tokens)
    all_trends   = _fetch_trends(kite_obj, tokens_json, today_str)
    nifty_trend  = all_trends.get("__NIFTY__",  {"dir": "NEUTRAL", "score": 0, "price": 0, "vwap": 0})
    regime       = all_trends.get("__REGIME__", {"regime": "UNKNOWN", "move_pct": 0, "range_pct": 0})
    vix_val      = _vix(kite_obj)

    # ── Context strip ─────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    nd_c = {"BULLISH": "#00c853", "BEARISH": "#d50000"}.get(nifty_trend["dir"], "#ff9800")
    c1.markdown(
        f"<div style='padding:8px;background:#f5f5f5;border-radius:6px;text-align:center'>"
        f"<small>Nifty Trend</small><br>"
        f"<b style='color:{nd_c}'>{nifty_trend['dir']}</b></div>",
        unsafe_allow_html=True)
    vx_c = "#d50000" if vix_val > VIX_LIMIT else "#00c853"
    c2.markdown(
        f"<div style='padding:8px;background:#f5f5f5;border-radius:6px;text-align:center'>"
        f"<small>India VIX</small><br>"
        f"<b style='color:{vx_c}'>{vix_val:.1f}"
        f"{'  ⚠️' if vix_val > VIX_LIMIT else ''}</b></div>",
        unsafe_allow_html=True)
    c3.markdown(
        f"<div style='padding:8px;background:#f5f5f5;border-radius:6px;text-align:center'>"
        f"<small>Nifty Price</small><br><b>₹{nifty_trend['price']:,.0f}</b></div>",
        unsafe_allow_html=True)
    c4.markdown(
        f"<div style='padding:8px;background:#f5f5f5;border-radius:6px;text-align:center'>"
        f"<small>Nifty VWAP</small><br><b>₹{nifty_trend['vwap']:,.0f}</b></div>",
        unsafe_allow_html=True)

    # Sector trends strip — 2 rows of 4
    st.markdown("")
    sec_names = list(_SECTOR_STOCKS.keys())
    for row_start in range(0, len(sec_names), 4):
        row_secs = sec_names[row_start:row_start + 4]
        sec_cols = st.columns(4)
        for col, sec_name in zip(sec_cols, row_secs):
            key   = f"__SEC__{sec_name}"
            t     = all_trends.get(key, {"dir": "NEUTRAL"})
            label = sec_name.replace("NIFTY ", "")
            col.markdown(
                f"<div style='padding:6px;background:#fafafa;border-radius:5px;text-align:center'>"
                f"<small>{label}</small><br>"
                f"{_trend_badge(t['dir'])}</div>",
                unsafe_allow_html=True)

    st.markdown("")

    # ── Market Regime Banner ──────────────────────────────────────────────────
    r = regime["regime"]
    if r == "CHOPPY":
        st.error(
            f"⚠️ CHOPPY MARKET — Nifty pehle 30 min mein sideways raha "
            f"(Range: {regime['range_pct']}%). Scanner signals aaj unreliable hain.")
    elif r == "TRENDING_BULL":
        st.success(
            f"✅ TRENDING BULL — Nifty strong bullish opening "
            f"(+{regime['move_pct']}%). BUY setups aaj reliable hain.")
    elif r == "TRENDING_BEAR":
        st.warning(
            f"📉 TRENDING BEAR — Nifty strong bearish opening "
            f"({regime['move_pct']}%). SELL setups aaj reliable hain.")

    # Alert banners
    if nifty_trend["dir"] == "BEARISH" and vix_val > VIX_LIMIT:
        st.error("🚫 Nifty bearish + VIX high — aaj long trades avoid karo")
    elif nifty_trend["dir"] == "BEARISH":
        st.warning("⚠️ Nifty bearish — sirf SELL signals dekho aaj")
    elif vix_val > VIX_LIMIT:
        st.warning(f"⚠️ VIX {vix_val:.1f} > {VIX_LIMIT} — BUY signals blocked")

    st.divider()

    # ── Controls ──────────────────────────────────────────────────────────────
    fc1, fc2, fc3 = st.columns([1, 1, 1])
    with fc1:
        min_score = st.slider("Min Signal Strength (|IFS Score|)", 0, 15, 6)
    with fc2:
        dir_f = st.selectbox("Direction", ["ALL", "BULLISH", "BEARISH"])
    with fc3:
        sig_f = st.selectbox("Signal", ["ALL", "STRONG BUY", "BUY", "SELL", "STRONG SELL"])

    # Result date / skip list input
    skip_input = st.text_input(
        "⏭️ Result date wale stocks skip karo (comma separated)",
        placeholder="e.g.  INFY, TCS, HDFCBANK",
        help="Jin stocks ke results aaj/kal hain unhe yahan type karo — scan mein skip honge"
    )
    skip_list = {s.strip().upper() for s in skip_input.split(",") if s.strip()}

    btn_col, auto_col = st.columns([3, 1])
    with btn_col:
        run = st.button("🔍  Run Scanner", type="primary", use_container_width=True)
    with auto_col:
        auto_scan = st.checkbox(
            "🔄 Auto (6 min)",
            value=st.session_state.get("sc_auto_enabled", False),
            help="Har 6 minute mein scanner automatically run hoga aur STRONG signals pe Telegram jaayega",
        )
        st.session_state["sc_auto_enabled"] = auto_scan

    # Auto-scan timer trigger
    run = run or st.session_state.pop("sc_auto_trigger", False)

    # ── Scan ──────────────────────────────────────────────────────────────────
    if run:
        prev_day      = _prev_trading_day()
        hist_start    = _trading_days_ago(5)
        hist_from_dt  = datetime(hist_start.year, hist_start.month, hist_start.day, 9, 15)
        to_dt         = now
        today         = date.today()

        prog     = st.progress(0, text="Starting scan...")
        results  = []
        scan_sym = {k: v for k, v in tokens.items() if not k.startswith("__")}
        total    = len(scan_sym)

        for i, (sym, tok) in enumerate(scan_sym.items()):
            prog.progress((i + 1) / total, text=f"Scanning {sym}... ({i+1}/{total})")

            # Skip list fast path
            if sym.upper() in skip_list:
                results.append({
                    "symbol": sym, "score": 0, "signal": "FILTERED", "dir": "NEUTRAL",
                    "price": 0, "vwap": 0, "entry": 0, "stop": 0, "target": 0,
                    "vol_ratio": 0, "gap_pct": 0, "orb_h": 0, "orb_l": 0,
                    "orb_rng": 0, "pdh": 0, "pdl": 0, "rs_alpha": 0,
                    "filters": ["Result date / manual skip"],
                    "sector": STOCK_SECTOR.get(sym, "Other"),
                    "p1": 0, "p2": 0, "p3": 0, "p4": 0, "p5": 0, "p6": 0, "p7": 0,
                })
                continue

            df2 = _fetch(kite_obj, tok, hist_from_dt, to_dt)
            if df2 is not None and len(df2) >= 6:
                today_df = df2[df2["date"].dt.date == today].copy().reset_index(drop=True)
                prev_df  = df2[df2["date"].dt.date == prev_day].copy().reset_index(drop=True)
                hist_df  = df2[df2["date"].dt.date < today].copy().reset_index(drop=True)
                r = _ifs(today_df, prev_df, sym,
                         nifty_trend, all_trends, vix_val, skip_list,
                         hist_df=hist_df)
                if r:
                    results.append(r)
            time.sleep(0.35)  # Zerodha historical API: max ~3 req/sec

        prog.empty()
        st.session_state["sc_results"]      = results
        st.session_state["sc_time"]         = now.strftime("%H:%M:%S")
        st.session_state["sc_skip_used"]    = list(skip_list)
        st.session_state["sc_last_auto_ts"] = time.time()  # timer reset

        # ── Telegram alerts for STRONG signals ───────────────────────────────
        if alert_engine is not None:
            strong = [r for r in results if r["signal"] in ("STRONG BUY", "STRONG SELL")]
            for r in strong:
                alert_engine.send_stock_signal(r)

    # ── Display ───────────────────────────────────────────────────────────────
    results   = st.session_state.get("sc_results", [])
    scan_time = st.session_state.get("sc_time", "")

    if not results:
        st.info("👆 'Run Scanner' click karo")
        return

    shown = [r for r in results
             if abs(r["score"]) >= min_score and r["signal"] != "FILTERED"]
    if dir_f != "ALL":
        shown = [r for r in shown if r["dir"] == dir_f]
    if sig_f != "ALL":
        shown = [r for r in shown if r["signal"] == sig_f]
    shown.sort(key=lambda x: x["score"], reverse=True)

    filtered_ct = sum(1 for r in results if r["signal"] == "FILTERED")

    st.markdown(f"**{len(shown)} stocks found** · Scan: `{scan_time}`")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Scanned",       len(results))
    m2.metric("🟢 Strong Buy", sum(1 for r in results if r["signal"] == "STRONG BUY"))
    m3.metric("🟡 Buy",        sum(1 for r in results if r["signal"] == "BUY"))
    m4.metric("🔴 Sell+",      sum(1 for r in results if "SELL" in r["signal"]))
    m5.metric("🚫 Filtered",   filtered_ct)

    st.divider()

    if not shown:
        st.warning("Koi stock nahi mila is filter ke saath.")
        return

    # Table header
    hdr = st.columns([1.2, 0.7, 0.7, 0.8, 0.8, 0.8, 0.6, 0.7, 0.8, 1.3])
    for col, lbl in zip(hdr, ["Symbol","Sector","Price","VWAP","Entry","SL","Target","R:R","Score","Signal"]):
        col.markdown(f"<small><b>{lbl}</b></small>", unsafe_allow_html=True)

    for r in shown:
        cols = st.columns([1.2, 0.7, 0.7, 0.8, 0.8, 0.8, 0.6, 0.7, 0.8, 1.3])
        cols[0].markdown(f"**{r['symbol']}**")
        cols[1].markdown(f"<small>{r['sector']}</small>", unsafe_allow_html=True)
        cols[2].markdown(f"₹{r['price']:,.1f}")
        cols[3].markdown(f"₹{r['vwap']:,.1f}")
        if r["entry"] > 0:
            cols[4].markdown(f"₹{r['entry']:,.1f}")
            cols[5].markdown(f"₹{r['stop']:,.1f}")
            cols[6].markdown(f"₹{r['target']:,.1f}")
            cols[7].markdown("1:1.5")
        else:
            for c in cols[4:8]:
                c.markdown("—")
        cols[8].markdown(f"**{r['score']}**")
        cols[9].markdown(_badge(r["signal"]), unsafe_allow_html=True)

        with st.expander(f"↳ {r['symbol']} — breakdown"):
            bc = st.columns(7)
            bc[0].metric("VWAP",        f"{r['p1']:+d}/±2")
            bc[1].metric("ORB (2-C)",   f"{r['p2']:+d}/±3")
            bc[2].metric("Volume",      f"{r['p3']:+d}/±3  ({r['vol_ratio']}x)")
            bc[3].metric("PDH/PDL",     f"{r['p4']:+d}/±3")
            bc[4].metric("1st Candle",  f"{r['p5']:+d}/±1")
            bc[5].metric("Nifty Align", f"{r['p6']:+d}/±1")
            bc[6].metric("RS/Nifty",    f"{r['p7']:+d}/±2  ({r['rs_alpha']:+.1f}%)")
            if r["pdh"] > 0:
                st.caption(f"PDH: ₹{r['pdh']:,.1f}  |  PDL: ₹{r['pdl']:,.1f}  |  Price: ₹{r['price']:,.1f}")

            sec_key = f"__SEC__{STOCK_SECTOR.get(r['symbol'], '')}"
            sec_t   = all_trends.get(sec_key, {})
            if sec_t:
                st.caption(f"Sector ({r['sector']}) trend: **{sec_t.get('dir','—')}**")

            st.caption(
                f"ORB: ₹{r['orb_h']} – ₹{r['orb_l']}  |  "
                f"Range: {r['orb_rng']}%  |  "
                f"Gap: {r['gap_pct']:+.2f}%  |  "
                f"Vol: {r['vol_ratio']}x 5-day avg"
            )
            if r["adr"] > 0:
                adr_c = r["adr_consumed"]
                adr_color = (
                    "#d50000" if adr_c >= 85 else
                    "#ff6f00" if adr_c >= 70 else
                    "#00c853"
                )
                st.markdown(
                    f"<small>ADR: <b>{r['adr']}%</b>  |  "
                    f"Consumed: <b style='color:{adr_color}'>{adr_c}%"
                    f"{'  ⚠️ LATE ENTRY' if adr_c >= 70 else '  ✅ Room hai'}"
                    f"</b></small>",
                    unsafe_allow_html=True,
                )
            if r["filters"]:
                for msg in r["filters"]:
                    st.warning(f"⚠️ {msg}")

    st.divider()
    st.caption(
        f"IFS v4 · P1 VWAP(±2) + P2 ORB(±3) + P3 Vol(±3) + P4 PDH/PDL(±3) + "
        f"P5 1stCandle(±1) + P6 Nifty(±1) + P7 RS/Nifty(±2) · "
        f"Max±15 · Strong Buy≥{BUY_ZONE+2} · Buy≥{BUY_ZONE} · "
        f"Sell≤{SELL_ZONE} · Strong Sell≤{SELL_ZONE-2}"
    )

    # ── Auto-scan timer ───────────────────────────────────────────────────────
    if st.session_state.get("sc_auto_enabled", False):
        AUTO_INTERVAL = 360   # 6 minutes
        last_ts  = st.session_state.get("sc_last_auto_ts", 0)
        elapsed  = time.time() - last_ts
        remaining = int(AUTO_INTERVAL - elapsed)

        if remaining <= 0:
            # 6 min ho gaye — trigger scan on next render
            st.session_state["sc_auto_trigger"]  = True
            st.session_state["sc_last_auto_ts"]  = time.time()
            st.rerun()
        else:
            mins = remaining // 60
            secs = remaining % 60
            st.caption(f"⏱️ Auto-scan: {mins}m {secs}s mein — Tab khula rakho")
            # Countdown: 15 sec intervals (5 sec jab 1 min bacha ho)
            sleep_for = 5 if remaining <= 60 else 15
            time.sleep(sleep_for)
            st.rerun()
