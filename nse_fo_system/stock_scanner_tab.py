"""
Intraday Stock Scanner — IFS (Intraday Flow Score)
===================================================
5 pillars: VWAP + ORB + Volume Surge + 9 EMA + First Candle
Score range: -8 to +11
BUY zone: >= 7  |  SELL zone: <= -5
"""

import time
import logging
from datetime import datetime, date

import pandas as pd
import streamlit as st

logger = logging.getLogger(__name__)

# ── Nifty 100 — Most liquid NSE equity symbols ────────────────────────────────
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
    "UNIONBANK", "AUBANK", "BANDHANBNK", "RBLBANK", "KARURVYSYA",
    "KPITTECH", "NHPC", "ADANIGREEN", "TORNTPOWER", "EMAMILTD",
    "PIIND", "COROMANDEL", "DELHIVERY", "SPICEJET", "INDIGO",
]


# ══════════════════════════════════════════════════════════════════════════════
# CALCULATIONS
# ══════════════════════════════════════════════════════════════════════════════

def _vwap(df: pd.DataFrame) -> pd.Series:
    tp  = (df["high"] + df["low"] + df["close"]) / 3
    return (tp * df["volume"]).cumsum() / df["volume"].cumsum()


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _ema_slope(ema_series: pd.Series, lookback: int = 3) -> float:
    if len(ema_series) < lookback + 1:
        return 0.0
    return float(ema_series.iloc[-1] - ema_series.iloc[-lookback])


def calculate_ifs(df: pd.DataFrame, symbol: str) -> dict | None:
    """
    Intraday Flow Score — 5 pillars.
    Returns dict with score, signal, entry/stop/target and breakdown.
    Returns None if data insufficient.
    """
    if df is None or len(df) < 4:
        return None

    df = df.copy().reset_index(drop=True)
    df["vwap"] = _vwap(df)
    df["ema9"] = _ema(df["close"], 9)

    price   = float(df["close"].iloc[-1])
    vwap    = float(df["vwap"].iloc[-1])
    ema9    = float(df["ema9"].iloc[-1])
    avg_vol = float(df["volume"].mean())
    cur_vol = float(df["volume"].iloc[-1])
    vol_ratio = cur_vol / avg_vol if avg_vol > 0 else 0

    # ── ORB: first 3 candles (9:15 9:20 9:25) ────────────────────────────────
    orb      = df.head(3)
    orb_high = float(orb["high"].max())
    orb_low  = float(orb["low"].min())
    orb_rng  = (orb_high - orb_low) / orb_low * 100  # %

    # ── PILLAR 1 — VWAP (−2 … +2) ────────────────────────────────────────────
    vwap_slope = _ema_slope(df["vwap"])
    if price > vwap and vwap_slope > 0:
        p1 = 2
    elif price < vwap and vwap_slope < 0:
        p1 = -2
    else:
        p1 = 0

    # ── PILLAR 2 — ORB breakout (−3 … +3) ────────────────────────────────────
    if len(df) <= 3 or not (0.3 <= orb_rng <= 1.5):
        p2 = 0  # inside ORB period OR range too tight/wide
    elif price > orb_high:
        p2 = 3
    elif price < orb_low:
        p2 = -3
    else:
        p2 = 0

    # ── PILLAR 3 — Volume surge (0 … +3) ─────────────────────────────────────
    if   vol_ratio >= 3.0: p3 = 3
    elif vol_ratio >= 2.0: p3 = 2
    elif vol_ratio >= 1.5: p3 = 1
    else:                   p3 = 0

    # ── PILLAR 4 — 9 EMA momentum (−2 … +2) ──────────────────────────────────
    ema_slope = _ema_slope(df["ema9"])
    if price > ema9 and ema_slope > 0:
        p4 = 2
    elif price < ema9 and ema_slope < 0:
        p4 = -2
    else:
        p4 = 0

    # ── PILLAR 5 — First candle bias (−1 … +1) ────────────────────────────────
    fc = df.iloc[0]
    fc_rng = fc["high"] - fc["low"]
    if fc_rng > 0:
        pos = (fc["close"] - fc["low"]) / fc_rng
        if fc["close"] > fc["open"] and pos > 0.6:
            p5 = 1
        elif fc["close"] < fc["open"] and pos < 0.4:
            p5 = -1
        else:
            p5 = 0
    else:
        p5 = 0

    score = p1 + p2 + p3 + p4 + p5

    # ── Signal ────────────────────────────────────────────────────────────────
    if   score >= 9:  signal, direction = "STRONG BUY",  "BULLISH"
    elif score >= 7:  signal, direction = "BUY",          "BULLISH"
    elif score <= -6: signal, direction = "STRONG SELL",  "BEARISH"
    elif score <= -4: signal, direction = "SELL",         "BEARISH"
    else:             signal, direction = "WAIT",         "NEUTRAL"

    # ── Entry / Stop / Target ─────────────────────────────────────────────────
    entry = stop = target = 0.0
    if direction == "BULLISH" and p2 > 0:
        entry  = price
        stop   = orb_low
        risk   = entry - stop
        target = entry + risk * 1.5
    elif direction == "BEARISH" and p2 < 0:
        entry  = price
        stop   = orb_high
        risk   = stop - entry
        target = entry - risk * 1.5

    return {
        "symbol":    symbol,
        "score":     score,
        "signal":    signal,
        "direction": direction,
        "price":     round(price,     2),
        "vwap":      round(vwap,      2),
        "entry":     round(entry,     2),
        "stop":      round(stop,      2),
        "target":    round(target,    2),
        "vol_ratio": round(vol_ratio, 2),
        "orb_high":  round(orb_high,  2),
        "orb_low":   round(orb_low,   2),
        "orb_rng":   round(orb_rng,   2),
        # breakdown
        "p1_vwap":  p1, "p2_orb": p2, "p3_vol": p3,
        "p4_ema":   p4, "p5_fc":  p5,
    }


# ══════════════════════════════════════════════════════════════════════════════
# DATA FETCH
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=1800, show_spinner=False)
def _load_nse_tokens(_kite_obj) -> dict:
    """Nifty 100 symbols ke instrument tokens — 30-min cache."""
    try:
        instr  = _kite_obj.instruments("NSE")
        df     = pd.DataFrame(instr)
        eq     = df[df["instrument_type"] == "EQ"]
        result = {}
        for sym in SCAN_UNIVERSE:
            row = eq[eq["tradingsymbol"] == sym]
            if not row.empty:
                result[sym] = int(row.iloc[0]["instrument_token"])
        logger.info(f"Tokens loaded: {len(result)}/{len(SCAN_UNIVERSE)}")
        return result
    except Exception as e:
        logger.error(f"Token load error: {e}")
        return {}


def _fetch_5min(kite_obj, token: int, from_dt: datetime, to_dt: datetime) -> pd.DataFrame | None:
    try:
        raw = kite_obj.historical_data(token, from_dt, to_dt, "5minute")
        if not raw:
            return None
        df = pd.DataFrame(raw)
        df.columns = ["date", "open", "high", "low", "close", "volume"]
        return df
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# RENDER
# ══════════════════════════════════════════════════════════════════════════════

_SIG_COLOR = {
    "STRONG BUY":  ("#00c853", "#e8f5e9"),
    "BUY":         ("#43a047", "#f1f8e9"),
    "WAIT":        ("#9e9e9e", "#fafafa"),
    "SELL":        ("#e53935", "#fff3e0"),
    "STRONG SELL": ("#b71c1c", "#ffebee"),
}


def _badge(signal: str) -> str:
    color, _ = _SIG_COLOR.get(signal, ("#9e9e9e", "#fafafa"))
    return (
        f"<span style='background:{color};color:#fff;padding:3px 10px;"
        f"border-radius:5px;font-size:12px;font-weight:700'>{signal}</span>"
    )


def render_stock_scanner(kite=None):
    """Main entry — call karo web_dashboard.py se."""

    st.markdown("## 📡 Intraday Stock Scanner")
    st.caption("IFS (Intraday Flow Score) · 5 Pillars · Nifty 100 Universe")

    # ── Guard ─────────────────────────────────────────────────────────────────
    if kite is None or not kite.is_connected():
        st.error("❌ Zerodha Kite connected nahi hai. Token refresh karo.")
        return

    kite_obj = kite.kite   # underlying KiteConnect object

    # ── Controls row ──────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns([1, 1, 1, 1.5])
    with c1:
        min_score = st.slider("Min IFS Score", 0, 11, 7)
    with c2:
        dir_filter = st.selectbox("Direction", ["ALL", "BULLISH", "BEARISH"])
    with c3:
        sig_filter = st.selectbox(
            "Signal", ["ALL", "STRONG BUY", "BUY", "SELL", "STRONG SELL"]
        )
    with c4:
        run_btn = st.button("🔍  Run Scanner", type="primary", use_container_width=True)

    # ── Market hours warning ───────────────────────────────────────────────────
    now  = datetime.now()
    mkt_open  = now.replace(hour=9,  minute=15, second=0, microsecond=0)
    mkt_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    if not (mkt_open <= now <= mkt_close):
        st.warning("⚠️ Market closed hai — aaj ka live data nahi milega. Kal market khulne ke baad use karo.")

    # ── Scan ──────────────────────────────────────────────────────────────────
    if run_btn:
        today   = date.today()
        from_dt = datetime(today.year, today.month, today.day, 9, 15, 0)
        to_dt   = now

        prog    = st.progress(0, text="Instrument tokens load ho rahe hain...")
        tokens  = _load_nse_tokens(kite_obj)

        if not tokens:
            st.error("Instrument tokens nahi mile. Kite connection check karo.")
            return

        results = []
        total   = len(tokens)

        for i, (sym, token) in enumerate(tokens.items()):
            prog.progress((i + 1) / total, text=f"Scanning {sym}... ({i+1}/{total})")
            df = _fetch_5min(kite_obj, token, from_dt, to_dt)
            r  = calculate_ifs(df, sym)
            if r:
                results.append(r)
            time.sleep(0.08)   # Kite rate limit

        prog.empty()
        st.session_state["scanner_results"] = results
        st.session_state["scanner_time"]    = now.strftime("%H:%M:%S")
        st.session_state["scanner_ts"]      = now

    # ── Results ───────────────────────────────────────────────────────────────
    all_results = st.session_state.get("scanner_results", [])
    scan_time   = st.session_state.get("scanner_time", "")

    if not all_results:
        st.info("👆 'Run Scanner' click karo — Nifty 100 stocks scan honge")
        return

    # Apply filters
    shown = all_results
    shown = [r for r in shown if r["score"] >= min_score]
    if dir_filter != "ALL":
        shown = [r for r in shown if r["direction"] == dir_filter]
    if sig_filter != "ALL":
        shown = [r for r in shown if r["signal"] == sig_filter]
    shown.sort(key=lambda x: x["score"], reverse=True)

    # ── Summary strip ─────────────────────────────────────────────────────────
    st.markdown(f"**{len(shown)} stocks** · Last scan: `{scan_time}`")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Scanned",     len(all_results))
    m2.metric("🟢 Strong Buy", sum(1 for r in all_results if r["signal"] == "STRONG BUY"))
    m3.metric("🟡 Buy",        sum(1 for r in all_results if r["signal"] == "BUY"))
    m4.metric("🔴 Sell",       sum(1 for r in all_results if "SELL" in r["signal"]))
    m5.metric("⚪ Wait",       sum(1 for r in all_results if r["signal"] == "WAIT"))

    st.divider()

    if not shown:
        st.warning("Is filter ke saath koi stock nahi mila. Filter adjust karo.")
        return

    # ── Table header ─────────────────────────────────────────────────────────
    hc = st.columns([1.4, 0.8, 0.9, 0.9, 0.9, 0.9, 0.7, 1.3])
    for col, label in zip(hc, ["Symbol", "Price", "VWAP", "Entry", "SL", "Target", "Score", "Signal"]):
        col.markdown(f"<small><b>{label}</b></small>", unsafe_allow_html=True)

    # ── Rows ──────────────────────────────────────────────────────────────────
    for r in shown:
        cols = st.columns([1.4, 0.8, 0.9, 0.9, 0.9, 0.9, 0.7, 1.3])

        cols[0].markdown(f"**{r['symbol']}**")
        cols[1].markdown(f"₹{r['price']:,.1f}")
        cols[2].markdown(f"₹{r['vwap']:,.1f}")

        if r["entry"] > 0:
            cols[3].markdown(f"₹{r['entry']:,.1f}")
            cols[4].markdown(f"₹{r['stop']:,.1f}")
            cols[5].markdown(f"₹{r['target']:,.1f}")
        else:
            cols[3].markdown("—"); cols[4].markdown("—"); cols[5].markdown("—")

        cols[6].markdown(f"**{r['score']}**")
        cols[7].markdown(_badge(r["signal"]), unsafe_allow_html=True)

        # Score breakdown
        with st.expander(f"↳ {r['symbol']} — Score Breakdown"):
            bc = st.columns(5)
            bc[0].metric("VWAP",      f"{r['p1_vwap']:+d} / 2")
            bc[1].metric("ORB",       f"{r['p2_orb']:+d} / 3")
            bc[2].metric("Volume",    f"{r['p3_vol']} / 3  ({r['vol_ratio']}x)")
            bc[3].metric("9 EMA",     f"{r['p4_ema']:+d} / 2")
            bc[4].metric("1st Candle",f"{r['p5_fc']:+d} / 1")

            st.caption(
                f"ORB High: ₹{r['orb_high']}  |  "
                f"ORB Low: ₹{r['orb_low']}  |  "
                f"ORB Range: {r['orb_rng']}%  |  "
                f"Volume: {r['vol_ratio']}x average"
            )

    st.divider()
    st.caption(
        "IFS Score: VWAP(±2) + ORB(±3) + Volume(0-3) + 9EMA(±2) + FirstCandle(±1)  "
        "· BUY zone ≥ 7  · SELL zone ≤ −5"
    )
