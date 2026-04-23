"""
Intraday Stock Scanner — IFS v2.0
==================================
6-pillar score + 4 hard filters = High probability signals

Pillars:
  P1 VWAP alignment         : ±2
  P2 ORB breakout           : ±3
  P3 Volume (prev-day base) : 0–3
  P4 9 EMA momentum         : ±2
  P5 First candle bias      : ±1
  P6 Nifty alignment bonus  : ±1
  Max: +12  Buy zone: ≥8  Sell zone: ≤-6

Hard filters:
  1. Gap > 1.5%   → skip
  2. VIX > 22     → no buy signals
  3. ORB invalid  → p2 = 0
  4. Nifty strong opposite → downgrade
"""

import time
import logging
from datetime import datetime, date, timedelta
from typing import Optional

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

VIX_LIMIT   = 22.0
GAP_LIMIT   = 1.5
ORB_MIN     = 0.3
ORB_MAX     = 1.5
BUY_ZONE    = 8
SELL_ZONE   = -6

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
    """Instrument tokens for all scan symbols + Nifty index. Cache 30 min."""
    try:
        instr = pd.DataFrame(_kite.instruments("NSE"))
        eq    = instr[instr["instrument_type"] == "EQ"]
        idx   = instr[instr["instrument_type"] == "INDEX"]

        tokens = {}
        for sym in SCAN_UNIVERSE:
            row = eq[eq["tradingsymbol"] == sym]
            if not row.empty:
                tokens[sym] = int(row.iloc[0]["instrument_token"])

        nifty_row = idx[idx["tradingsymbol"] == "NIFTY 50"]
        tokens["__NIFTY__"] = (
            int(nifty_row.iloc[0]["instrument_token"])
            if not nifty_row.empty else 256265
        )
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


@st.cache_data(ttl=300, show_spinner=False)
def _nifty_trend(_kite, nifty_token, cache_key):
    """Nifty 5-min trend. Refresh every 5 min."""
    today = date.today()
    df = _fetch(
        _kite, nifty_token,
        datetime(today.year, today.month, today.day, 9, 15),
        datetime.now(),
    )
    if df is None or len(df) < 4:
        return {"dir": "NEUTRAL", "score": 0, "price": 0, "vwap": 0}

    df["vwap"] = _vwap(df)
    df["ema9"] = _ema(df["close"], 9)
    price = float(df["close"].iloc[-1])
    vwap  = float(df["vwap"].iloc[-1])
    ema9  = float(df["ema9"].iloc[-1])

    bull = sum([
        price > vwap,
        _slope(df["vwap"]) > 0,
        price > ema9,
        _slope(df["ema9"]) > 0,
    ])

    if   bull >= 3: d, s = "BULLISH", 1
    elif bull <= 1: d, s = "BEARISH", -1
    else:           d, s = "NEUTRAL", 0

    return {"dir": d, "score": s,
            "price": round(price, 2), "vwap": round(vwap, 2)}


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


# ══════════════════════════════════════════════════════════════════════════════
# IFS SCORE
# ══════════════════════════════════════════════════════════════════════════════

def _ifs(today_df, prev_df, symbol, nifty, vix_val):
    if today_df is None or len(today_df) < 4:
        return None

    df = today_df.copy().reset_index(drop=True)
    df["vwap"] = _vwap(df)
    df["ema9"] = _ema(df["close"], 9)

    price    = float(df["close"].iloc[-1])
    open_px  = float(df["open"].iloc[0])
    vwap_val = float(df["vwap"].iloc[-1])
    ema9_val = float(df["ema9"].iloc[-1])
    cur_vol  = float(df["volume"].iloc[-1])

    # Previous day volume baseline
    if prev_df is not None and len(prev_df) >= 20:
        avg_vol = float(prev_df["volume"].mean())
    else:
        avg_vol = float(df["volume"].mean())
    vol_ratio = cur_vol / avg_vol if avg_vol > 0 else 0

    # Gap
    if prev_df is not None and len(prev_df) > 0:
        prev_close = float(prev_df["close"].iloc[-1])
        gap_pct    = (open_px - prev_close) / prev_close * 100
    else:
        gap_pct = 0.0

    # ORB
    orb      = df.head(3)
    orb_high = float(orb["high"].max())
    orb_low  = float(orb["low"].min())
    orb_rng  = (orb_high - orb_low) / orb_low * 100

    # ── Hard filters ──────────────────────────────────────────────────────────
    filters = []
    if abs(gap_pct) > GAP_LIMIT:
        filters.append(f"Gap {gap_pct:+.1f}% (limit ±{GAP_LIMIT}%)")
    if len(df) > 3 and not (ORB_MIN <= orb_rng <= ORB_MAX):
        tag = "tight" if orb_rng < ORB_MIN else "wide"
        filters.append(f"ORB too {tag} ({orb_rng:.2f}%)")

    # ── P1 VWAP ───────────────────────────────────────────────────────────────
    if price > vwap_val and _slope(df["vwap"]) > 0:   p1 =  2
    elif price < vwap_val and _slope(df["vwap"]) < 0: p1 = -2
    else:                                               p1 =  0

    # ── P2 ORB ────────────────────────────────────────────────────────────────
    if len(df) <= 3 or filters:          p2 = 0
    elif price > orb_high:               p2 = 3
    elif price < orb_low:                p2 = -3
    else:                                p2 = 0

    # ── P3 Volume (prev-day baseline) ─────────────────────────────────────────
    if   vol_ratio >= 3.0: p3 = 3
    elif vol_ratio >= 2.0: p3 = 2
    elif vol_ratio >= 1.5: p3 = 1
    else:                  p3 = 0

    # ── P4 9 EMA ──────────────────────────────────────────────────────────────
    if price > ema9_val and _slope(df["ema9"]) > 0:   p4 =  2
    elif price < ema9_val and _slope(df["ema9"]) < 0: p4 = -2
    else:                                               p4 =  0

    # ── P5 First candle ───────────────────────────────────────────────────────
    fc = df.iloc[0]
    rng = fc["high"] - fc["low"]
    if rng > 0:
        pos = (fc["close"] - fc["low"]) / rng
        if fc["close"] > fc["open"] and pos > 0.6:   p5 =  1
        elif fc["close"] < fc["open"] and pos < 0.4: p5 = -1
        else:                                          p5 =  0
    else:
        p5 = 0

    # ── P6 Nifty alignment ────────────────────────────────────────────────────
    p6 = nifty.get("score", 0)

    score = p1 + p2 + p3 + p4 + p5 + p6

    # ── Post-score filters ────────────────────────────────────────────────────
    if vix_val > VIX_LIMIT and score > 0:
        filters.append(f"VIX {vix_val:.1f} > {VIX_LIMIT}")
        score = 0

    if nifty["dir"] == "BEARISH" and score >= BUY_ZONE:
        filters.append("Nifty bearish — buy downgraded")
        score = BUY_ZONE - 1
    elif nifty["dir"] == "BULLISH" and score <= SELL_ZONE:
        filters.append("Nifty bullish — sell downgraded")
        score = SELL_ZONE + 1

    # ── Signal ────────────────────────────────────────────────────────────────
    if len(filters) >= 2:           sig, dirn = "FILTERED",    "NEUTRAL"
    elif score >= BUY_ZONE + 2:     sig, dirn = "STRONG BUY",  "BULLISH"
    elif score >= BUY_ZONE:         sig, dirn = "BUY",          "BULLISH"
    elif score <= SELL_ZONE - 2:    sig, dirn = "STRONG SELL",  "BEARISH"
    elif score <= SELL_ZONE:        sig, dirn = "SELL",         "BEARISH"
    else:                           sig, dirn = "WAIT",         "NEUTRAL"

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
        "symbol":  symbol,
        "score":   score,
        "signal":  sig,
        "dir":     dirn,
        "price":   round(price,     2),
        "vwap":    round(vwap_val,  2),
        "entry":   round(entry,     2),
        "stop":    round(stop,      2),
        "target":  round(target,    2),
        "vol_ratio": round(vol_ratio, 2),
        "gap_pct": round(gap_pct,   2),
        "orb_h":   round(orb_high,  2),
        "orb_l":   round(orb_low,   2),
        "orb_rng": round(orb_rng,   2),
        "filters": filters,
        "p1": p1, "p2": p2, "p3": p3, "p4": p4, "p5": p5, "p6": p6,
    }


# ══════════════════════════════════════════════════════════════════════════════
# RENDER
# ══════════════════════════════════════════════════════════════════════════════

def _badge(sig):
    c = _SIG_COLOR.get(sig, "#9e9e9e")
    return (f"<span style='background:{c};color:#fff;padding:3px 10px;"
            f"border-radius:5px;font-size:12px;font-weight:700'>{sig}</span>")


def render_stock_scanner(kite=None):
    st.markdown("## 📡 Intraday Stock Scanner")
    st.caption("IFS v2.0 · 6-Pillar Score · Nifty 100 · Prev-day Volume Baseline")

    if kite is None or not kite.is_connected():
        st.error("❌ Zerodha Kite connected nahi. Token refresh karo.")
        return

    kite_obj  = kite.kite
    now       = datetime.now()
    today_str = date.today().isoformat()

    # ── Time warnings ─────────────────────────────────────────────────────────
    h, m = now.hour, now.minute
    if h < 9 or (h == 9 and m < 15):
        st.warning("⏰ Market abhi khula nahi.")
    elif h == 9 and m < 30:
        st.info("⏳ ORB ban rahi hai (9:15–9:29). 9:30 ke baad scan karo.")
    elif (h == 11 and m > 30) or h >= 12:
        st.warning("⚠️ 11:30 ke baad naye intraday setups mat lo.")

    # ── Live context ──────────────────────────────────────────────────────────
    tokens    = _load_tokens(kite_obj)
    nifty_tok = tokens.get("__NIFTY__", 256265)
    nifty     = _nifty_trend(kite_obj, nifty_tok, today_str)
    vix_val   = _vix(kite_obj)

    c1, c2, c3, c4 = st.columns(4)
    nd_color = {"BULLISH": "#00c853", "BEARISH": "#d50000"}.get(nifty["dir"], "#ff9800")
    c1.markdown(
        f"<div style='padding:8px;background:#f5f5f5;border-radius:6px;text-align:center'>"
        f"<small>Nifty Trend</small><br><b style='color:{nd_color}'>{nifty['dir']}</b></div>",
        unsafe_allow_html=True)
    vx_color = "#d50000" if vix_val > VIX_LIMIT else "#00c853"
    c2.markdown(
        f"<div style='padding:8px;background:#f5f5f5;border-radius:6px;text-align:center'>"
        f"<small>India VIX</small><br><b style='color:{vx_color}'>{vix_val:.1f}"
        f"{'  ⚠️' if vix_val > VIX_LIMIT else ''}</b></div>",
        unsafe_allow_html=True)
    c3.markdown(
        f"<div style='padding:8px;background:#f5f5f5;border-radius:6px;text-align:center'>"
        f"<small>Nifty Price</small><br><b>₹{nifty['price']:,.0f}</b></div>",
        unsafe_allow_html=True)
    c4.markdown(
        f"<div style='padding:8px;background:#f5f5f5;border-radius:6px;text-align:center'>"
        f"<small>Nifty VWAP</small><br><b>₹{nifty['vwap']:,.0f}</b></div>",
        unsafe_allow_html=True)

    st.markdown("")

    # ── Alert banner ──────────────────────────────────────────────────────────
    if nifty["dir"] == "BEARISH" and vix_val > VIX_LIMIT:
        st.error("🚫 Nifty bearish + VIX high — aaj long intraday setups avoid karo")
    elif nifty["dir"] == "BEARISH":
        st.warning("⚠️ Nifty bearish — sirf SELL signals dekho aaj")
    elif vix_val > VIX_LIMIT:
        st.warning(f"⚠️ VIX {vix_val:.1f} > {VIX_LIMIT} — BUY signals blocked")

    # ── Controls ──────────────────────────────────────────────────────────────
    fc1, fc2, fc3, fc4 = st.columns([1, 1, 1, 1.5])
    with fc1:
        min_score  = st.slider("Min Score", 0, 12, BUY_ZONE)
    with fc2:
        dir_f = st.selectbox("Direction", ["ALL", "BULLISH", "BEARISH"])
    with fc3:
        sig_f = st.selectbox("Signal", ["ALL", "STRONG BUY", "BUY", "SELL", "STRONG SELL"])
    with fc4:
        run = st.button("🔍  Run Scanner", type="primary", use_container_width=True)

    st.divider()

    # ── Scan ──────────────────────────────────────────────────────────────────
    if run:
        if not tokens:
            st.error("Instrument tokens nahi mile.")
            return

        prev_day = _prev_trading_day()
        from_dt  = datetime(prev_day.year, prev_day.month, prev_day.day, 9, 15)
        to_dt    = now
        today    = date.today()

        prog     = st.progress(0, text="Starting scan...")
        results  = []
        scan_sym = {k: v for k, v in tokens.items() if not k.startswith("__")}
        total    = len(scan_sym)

        for i, (sym, tok) in enumerate(scan_sym.items()):
            prog.progress((i + 1) / total, text=f"Scanning {sym}... ({i+1}/{total})")
            df2 = _fetch(kite_obj, tok, from_dt, to_dt)
            if df2 is not None and len(df2) >= 6:
                today_df = df2[df2["date"].dt.date == today].copy().reset_index(drop=True)
                prev_df  = df2[df2["date"].dt.date == prev_day].copy().reset_index(drop=True)
                r = _ifs(today_df, prev_df, sym, nifty, vix_val)
                if r:
                    results.append(r)
            time.sleep(0.08)

        prog.empty()
        st.session_state["sc_results"] = results
        st.session_state["sc_time"]    = now.strftime("%H:%M:%S")

    # ── Results ───────────────────────────────────────────────────────────────
    results   = st.session_state.get("sc_results", [])
    scan_time = st.session_state.get("sc_time", "")

    if not results:
        st.info("👆 'Run Scanner' click karo")
        return

    # Apply filters
    shown = [r for r in results
             if r["score"] >= min_score and r["signal"] != "FILTERED"]
    if dir_f != "ALL":
        shown = [r for r in shown if r["dir"] == dir_f]
    if sig_f != "ALL":
        shown = [r for r in shown if r["signal"] == sig_f]
    shown.sort(key=lambda x: x["score"], reverse=True)

    filtered_ct = sum(1 for r in results if r["signal"] == "FILTERED")

    # Summary strip
    st.markdown(f"**{len(shown)} stocks found** · Scan time: `{scan_time}`")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Scanned", len(results))
    m2.metric("🟢 Strong Buy",  sum(1 for r in results if r["signal"] == "STRONG BUY"))
    m3.metric("🟡 Buy",         sum(1 for r in results if r["signal"] == "BUY"))
    m4.metric("🔴 Sell",        sum(1 for r in results if "SELL" in r["signal"]))
    m5.metric("🚫 Filtered",    filtered_ct)

    st.divider()

    if not shown:
        st.warning("Koi stock nahi mila is filter ke saath.")
        return

    # Header row
    hdr = st.columns([1.4, 0.8, 0.8, 0.9, 0.9, 0.9, 0.6, 0.7, 1.3])
    for col, lbl in zip(hdr, ["Symbol","Price","VWAP","Entry","SL","Target","R:R","Score","Signal"]):
        col.markdown(f"<small><b>{lbl}</b></small>", unsafe_allow_html=True)

    for r in shown:
        cols = st.columns([1.4, 0.8, 0.8, 0.9, 0.9, 0.9, 0.6, 0.7, 1.3])
        cols[0].markdown(f"**{r['symbol']}**")
        cols[1].markdown(f"₹{r['price']:,.1f}")
        cols[2].markdown(f"₹{r['vwap']:,.1f}")
        if r["entry"] > 0:
            cols[3].markdown(f"₹{r['entry']:,.1f}")
            cols[4].markdown(f"₹{r['stop']:,.1f}")
            cols[5].markdown(f"₹{r['target']:,.1f}")
            cols[6].markdown("1:1.5")
        else:
            for c in cols[3:7]:
                c.markdown("—")
        cols[7].markdown(f"**{r['score']}**")
        cols[8].markdown(_badge(r["signal"]), unsafe_allow_html=True)

        with st.expander(f"↳ {r['symbol']} — breakdown"):
            bc = st.columns(6)
            bc[0].metric("VWAP",        f"{r['p1']:+d} / ±2")
            bc[1].metric("ORB",         f"{r['p2']:+d} / ±3")
            bc[2].metric("Volume",      f"{r['p3']} / 3  ({r['vol_ratio']}x)")
            bc[3].metric("9 EMA",       f"{r['p4']:+d} / ±2")
            bc[4].metric("1st Candle",  f"{r['p5']:+d} / ±1")
            bc[5].metric("Nifty Align", f"{r['p6']:+d} / ±1")
            st.caption(
                f"ORB: ₹{r['orb_h']} – ₹{r['orb_l']}  |  "
                f"Range: {r['orb_rng']}%  |  "
                f"Gap: {r['gap_pct']:+.2f}%  |  "
                f"Volume: {r['vol_ratio']}x prev-day avg"
            )
            if r["filters"]:
                for msg in r["filters"]:
                    st.warning(f"⚠️ {msg}")

    st.divider()
    st.caption(
        f"IFS v2 · P1 VWAP(±2) + P2 ORB(±3) + P3 Vol/prev-day(0–3) + "
        f"P4 EMA9(±2) + P5 1stCandle(±1) + P6 Nifty(±1) · "
        f"Buy ≥{BUY_ZONE} · Sell ≤{SELL_ZONE}"
    )
