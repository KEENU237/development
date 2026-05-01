"""
NSE F&O Web Dashboard — Streamlit Browser UI  v2.1
===================================================
✅ Browser mein khulega — CMD ki zaroorat nahi
✅ Values har 60 seconds mein auto-update hongi
✅ Page reload nahi hoga — sirf data refresh hoga
✅ Kite connection ek baar banti hai, session mein rehti hai
"""

import os
import sys
import time
import logging
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from stock_scanner_tab import render_stock_scanner

import streamlit as st
import pandas as pd
from concurrent.futures import ThreadPoolExecutor

try:
    import plotly.graph_objects as go
    PLOTLY_OK = True
except ImportError:
    PLOTLY_OK = False

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="NSE F&O Live Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .stApp {
        background-color: #ffffff;
        color: #1a1a2e;
        font-family: 'Inter', 'Segoe UI', -apple-system, sans-serif;
        font-size: 13px;
    }

    [data-testid="stSidebar"] {
        background-color: #f4f6fb !important;
        border-right: 1px solid #e0e4ef;
    }
    [data-testid="stSidebar"] * { color: #2c3e60 !important; }

    div[data-testid="stSidebar"] .stRadio > div { gap: 2px; }
    div[data-testid="stSidebar"] .stRadio label {
        background: transparent;
        border: none;
        border-radius: 6px;
        padding: 9px 12px !important;
        cursor: pointer;
        transition: background 0.15s ease;
        font-size: 13px !important;
        font-weight: 500 !important;
        width: 100%;
        color: #3a4a6b !important;
    }
    div[data-testid="stSidebar"] .stRadio label:hover {
        background: #e8edf8 !important;
        color: #1a56db !important;
    }

    div[data-testid="metric-container"] {
        background-color: #f8f9fd;
        border: 1px solid #e0e4ef;
        border-radius: 8px;
        padding: 12px 16px;
    }
    div[data-testid="metric-container"] label {
        color: #7a8aaa !important;
        font-size: 11px !important;
        text-transform: uppercase;
        letter-spacing: 0.6px;
        font-weight: 500;
    }
    div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
        font-size: 20px !important;
        font-weight: 600 !important;
        color: #1a1a2e !important;
    }

    .stDataFrame {
        border-radius: 8px !important;
        border: 1px solid #e0e4ef !important;
    }

    h1 { color: #1a56db !important; font-size: 18px !important; font-weight: 700 !important; }
    h2 { color: #1a1a2e !important; font-size: 15px !important; font-weight: 600 !important; }
    h3 { color: #7a8aaa !important; font-size: 11px !important; font-weight: 600 !important;
         text-transform: uppercase; letter-spacing: 0.8px; }

    #MainMenu { visibility: hidden; }
    footer    { visibility: hidden; }
    header    { visibility: hidden; }
    [data-testid="stDecoration"] { display: none; }

    div[data-testid="stExpander"] {
        background-color: #f8f9fd;
        border: 1px solid #e0e4ef !important;
        border-radius: 8px;
    }

    .stButton > button {
        background-color: #f0f3fa;
        border: 1px solid #c8d0e8;
        border-radius: 6px;
        color: #3a4a6b !important;
        font-size: 13px;
        font-weight: 500;
        padding: 6px 16px;
        transition: all 0.15s ease;
    }
    .stButton > button:hover {
        background-color: #e0e8f8;
        border-color: #1a56db;
        color: #1a56db !important;
    }

    .stTabs [data-baseweb="tab-list"] {
        background-color: #f0f3fa;
        border-radius: 6px;
        padding: 3px;
        gap: 2px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 4px;
        color: #7a8aaa !important;
        font-size: 12px;
        font-weight: 500;
        padding: 5px 12px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #ffffff !important;
        color: #1a56db !important;
    }

    div[data-testid="stAlert"] { border-radius: 6px !important; }

    hr { border-color: #e0e4ef !important; margin: 10px 0 !important; }

    [data-testid="stSelectbox"] > div > div {
        background-color: #f8f9fd !important;
        border-color: #c8d0e8 !important;
        border-radius: 6px !important;
        color: #1a1a2e !important;
        font-size: 13px !important;
    }

    .block-container {
        padding-top: 1rem !important;
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
        max-width: 100% !important;
    }
    ::-webkit-scrollbar-thumb:hover { background: #363a45; }
</style>
""", unsafe_allow_html=True)

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# ── Imports ───────────────────────────────────────────────────────────────────
try:
    from config.settings   import KITE_API_KEY, KITE_API_SECRET, UOA_CONFIG, TELEGRAM_CONFIG
    from core.kite_manager  import KiteManager
    from core.pcr_tracker   import PCRTracker
    from core.max_pain      import MaxPainCalculator
    from core.uoa_scanner   import UOAScanner
    from core.risk_manager  import RiskManager
    from core.market_utils  import (
        get_nearest_expiry, get_market_status, get_lot_size
    )
    from core.greeks        import calc_greeks, calc_iv, tte_years
    from core.alert_engine   import AlertEngine
    from core.trend_compass  import TrendCompass
    from core.backtest_engine import BacktestEngine, BacktestConfig
    from data.trade_log       import TradeLog
    from data.market_snapshot import SnapshotDB, SnapshotCollector
    IMPORTS_OK   = True
    IMPORT_ERROR = ""
except Exception as exc:
    IMPORTS_OK   = False
    IMPORT_ERROR = str(exc)


# ══════════════════════════════════════════════════════════════════════════════
# SESSION INIT — Kite ek baar connect, sab refreshes mein reuse
# ══════════════════════════════════════════════════════════════════════════════
def init_session() -> bool:
    if not IMPORTS_OK:
        return False
    if "kite" not in st.session_state:
        try:
            kite = KiteManager(KITE_API_KEY, KITE_API_SECRET)
            st.session_state["kite"]       = kite
            st.session_state["pcr"]        = PCRTracker(kite)
            st.session_state["mp"]         = MaxPainCalculator(kite)
            st.session_state["uoa"]        = UOAScanner(kite, UOA_CONFIG)
            st.session_state["risk"]       = RiskManager(kite)
            st.session_state["trade_log"]  = TradeLog()
            st.session_state["symbol"]     = "NIFTY"
            st.session_state["prev_pcr"]   = {}
            st.session_state["vp_session"] = "Today"
            st.session_state["gex_history"]   = []   # Tab2: Gamma Acceleration history
            st.session_state["smi_history"]   = {}   # Tab2: SMI daily history
            st.session_state["alert_history"] = []   # Recent alerts (last 20)
            st.session_state["compass"] = TrendCompass(st.session_state["kite"])
            # Alert Engine — Telegram notifications
            st.session_state["alert_engine"] = AlertEngine(
                bot_token = TELEGRAM_CONFIG.get("bot_token", ""),
                chat_id   = TELEGRAM_CONFIG.get("chat_id",   ""),
                enabled   = TELEGRAM_CONFIG.get("enabled",   False),
            )
            # Backtesting — snapshot collector + engine
            _snap_db = SnapshotDB()
            st.session_state["snap_db"]        = _snap_db
            st.session_state["snap_collector"] = SnapshotCollector(_snap_db)
            st.session_state["bt_engine"]      = BacktestEngine(_snap_db)
        except Exception as exc:
            st.error(f"❌ Connection failed: {exc}")
            return False
    return True


# ══════════════════════════════════════════════════════════════════════════════
# DATA FETCH — sab kuch ek jagah
# ══════════════════════════════════════════════════════════════════════════════
def fetch_all_data(symbol: str, expiry: str) -> dict:
    """
    Parallel data fetch — sab APIs ek saath call hoti hain.
    Sequential se ~5x faster.
    """
    kite     = st.session_state["kite"]
    pcr_obj  = st.session_state["pcr"]
    mp_obj   = st.session_state["mp"]
    uoa_obj  = st.session_state["uoa"]
    risk_obj = st.session_state["risk"]
    cache    = {}

    # ── Other symbol (NIFTY↔BANKNIFTY) for dual signal panel ─────────────────
    other_symbol = {"NIFTY": "BANKNIFTY", "BANKNIFTY": "NIFTY",
                    "FINNIFTY": "NIFTY"}.get(symbol, "BANKNIFTY")

    # ── Pre-warm instruments cache + compute expiries BEFORE threads ──────────
    # Reason: kite.instruments("NFO") is a large download (~2MB).
    # If multiple threads call it simultaneously → Zerodha rate-limits/timeouts
    # → ALL NFO data (PCR, OI, MaxPain) returns empty → no signals ever.
    # Solution: download ONCE here (cached 30 min), then all threads use cache.
    _sym_expiries = {}
    try:
        _instr = kite._get_instruments_cached()   # warms 30-min cache
        from datetime import date as _date
        _today = _date.today()
        for _s in [symbol, other_symbol, "NIFTY", "BANKNIFTY"]:
            _exps = sorted(set(
                i["expiry"] for i in _instr
                if i["name"] == _s
                and i["instrument_type"] in ("CE", "PE")
                and i["expiry"] >= _today
            ))
            if _exps:
                _sym_expiries[_s] = _exps[0].isoformat()
    except Exception as _e:
        logger.warning(f"Expiry pre-compute failed: {_e}")

    _nifty_exp  = _sym_expiries.get("NIFTY",     expiry)
    _bnk_exp    = _sym_expiries.get("BANKNIFTY", expiry)
    _other_exp  = _sym_expiries.get(other_symbol, expiry)

    # ── Worker functions (parallel chalenge) ─────────────────────────────────
    def _fetch_prices():
        try:
            return kite.get_ltp([
                "NSE:NIFTY 50", "NSE:NIFTY BANK",
                "NSE:NIFTY FIN SERVICE", "NSE:INDIA VIX",
            ])
        except Exception as exc:
            logger.error(f"LTP: {exc}")
            return {}

    def _fetch_oi_chain():
        try:
            return pcr_obj.get_oi_chain(symbol, expiry, 10)
        except Exception as exc:
            logger.error(f"OI Chain: {exc}")
            return []

    def _fetch_max_pain():
        try:
            return mp_obj.compute(symbol, expiry)
        except Exception as exc:
            logger.error(f"MaxPain: {exc}")
            return None

    def _fetch_pcr(sym):
        try:
            # Use pre-computed expiry — avoids kite.instruments() inside thread
            sym_exp = _nifty_exp if sym == "NIFTY" else _bnk_exp
            return sym, pcr_obj.get_pcr(sym, sym_exp)
        except Exception as exc:
            logger.error(f"PCR {sym}: {exc}")
            return sym, None

    def _fetch_uoa():
        try:
            uoa_obj.scan(expiry)
            return uoa_obj.get_top_alerts(10)
        except Exception as exc:
            logger.error(f"UOA: {exc}")
            return []

    def _fetch_risk():
        try:
            snap = risk_obj.get_portfolio_snapshot()
            return snap, risk_obj.check_risk_limits(snap)
        except Exception as exc:
            logger.error(f"Risk: {exc}")
            return None, []

    # ── VP session read BEFORE threads (session_state thread-safe nahi) ────────
    vp_session = st.session_state.get("vp_session", "Today")

    def _fetch_vp():
        try:
            candles = kite.get_vp_candles(symbol, vp_session)
            result  = _calc_volume_profile(symbol, candles)
            result["session"] = vp_session
            return result
        except Exception as exc:
            logger.error(f"VP fetch: {exc}")
            return {}

    def _fetch_other_oi_chain():
        """Other symbol ki OI chain — dual signal panel ke liye."""
        try:
            chain = pcr_obj.get_oi_chain(other_symbol, _other_exp, 10)
            return _other_exp, chain
        except Exception as exc:
            logger.error(f"Other OI Chain ({other_symbol}): {exc}")
            return _other_exp, []

    def _fetch_other_max_pain():
        """Other symbol ka max pain — dual signal panel ke liye."""
        try:
            return mp_obj.compute(other_symbol, _other_exp)
        except Exception as exc:
            logger.error(f"Other MaxPain ({other_symbol}): {exc}")
            return None

    def _fetch_other_vp():
        """Other symbol ki Volume Profile — dual panel VP ke liye."""
        try:
            candles = kite.get_vp_candles(other_symbol, vp_session)
            result  = _calc_volume_profile(other_symbol, candles)
            result["session"] = vp_session
            return result
        except Exception as exc:
            logger.error(f"Other VP fetch ({other_symbol}): {exc}")
            return {}

    # ── Run all in parallel ───────────────────────────────────────────────────
    TIMEOUT = 20   # seconds — agar koi thread hang kare toh 20s baad skip

    with ThreadPoolExecutor(max_workers=12) as ex:
        f_prices      = ex.submit(_fetch_prices)
        f_oi          = ex.submit(_fetch_oi_chain)
        f_mp          = ex.submit(_fetch_max_pain)
        f_pcr_n       = ex.submit(_fetch_pcr, "NIFTY")
        f_pcr_bn      = ex.submit(_fetch_pcr, "BANKNIFTY")
        f_uoa         = ex.submit(_fetch_uoa)
        f_risk        = ex.submit(_fetch_risk)
        f_vp          = ex.submit(_fetch_vp)
        f_other_oi    = ex.submit(_fetch_other_oi_chain)
        f_other_mp    = ex.submit(_fetch_other_max_pain)
        f_other_vp    = ex.submit(_fetch_other_vp)

    # ── Collect results (timeout se kabhi hang nahi hoga) ────────────────────
    def _safe(fut, default, timeout=TIMEOUT):
        try:
            return fut.result(timeout=timeout)
        except Exception as e:
            logger.error(f"Future failed/timeout: {e}")
            return default

    cache["prices"]     = _safe(f_prices,  {})
    cache["oi_chain"]   = _safe(f_oi,      [])
    cache["mp_result"]  = _safe(f_mp,      None)
    cache["uoa_alerts"] = _safe(f_uoa,     [])
    cache["vp_data"]    = _safe(f_vp,      {})
    risk_result         = _safe(f_risk,    (None, []))
    cache["risk_snap"]  = risk_result[0]
    cache["risk_alerts"]= risk_result[1]

    # PCR trend tracking (session_state write — thread ke bahar karo)
    pcr_data = {}
    for fut in [f_pcr_n, f_pcr_bn]:
        sym, r = _safe(fut, ("UNKNOWN", None))
        if r:
            prev  = st.session_state["prev_pcr"].get(sym)
            trend = ""
            if prev is not None:
                trend = "▲" if r.pcr > prev else ("▼" if r.pcr < prev else "→")
            st.session_state["prev_pcr"][sym] = r.pcr
            pcr_data[sym] = (r, trend)
    cache["pcr_data"] = pcr_data

    # IV depends on prices — prices ke baad calculate karo
    try:
        cache["iv_data"] = _calc_iv(symbol, expiry, cache)
    except Exception as exc:
        logger.error(f"IV: {exc}")
        cache["iv_data"] = {}

    # GEX — iv_data ke baad (gamma calculation ke liye IV chahiye)
    try:
        cache["gex_data"] = _calc_gex(symbol, expiry, cache)
    except Exception as exc:
        logger.error(f"GEX: {exc}")
        cache["gex_data"] = {}

    # ── Other symbol cache — dual signal panel ke liye ────────────────────────
    other_oi_result          = _safe(f_other_oi, (expiry, []))
    cache["other_symbol"]    = other_symbol
    cache["other_expiry"]    = other_oi_result[0]
    cache["other_oi_chain"]  = other_oi_result[1]
    cache["other_mp_result"] = _safe(f_other_mp, None)

    # Build mini-cache: prices + PCR shared; OI/MP from other symbol
    _other_mini = {
        "prices":    cache["prices"],
        "oi_chain":  cache["other_oi_chain"],
        "mp_result": cache["other_mp_result"],
        "pcr_data":  cache["pcr_data"],
        "iv_data":   {},   # no extra API calls; GEX will use VIX fallback
        "vp_data":   _safe(f_other_vp, {}),
        "expiry":    cache["other_expiry"],
    }
    try:
        _other_mini["gex_data"] = _calc_gex(other_symbol, cache["other_expiry"], _other_mini)
    except Exception as exc:
        logger.error(f"Other GEX: {exc}")
        _other_mini["gex_data"] = {}
    cache["other_cache"] = _other_mini

    cache["fetched_at"] = datetime.now().strftime("%H:%M:%S")
    return cache


def _calc_volume_profile(symbol: str, candles: list) -> dict:
    """
    Candle-based Volume Profile.

    Algorithm:
      1. Har candle ka volume uske High-Low range ke beech uniformly distribute karo
      2. Har price bucket (10 pts NIFTY / 20 pts BANKNIFTY) ka total volume sum karo
      3. POC = max volume bucket
      4. Value Area = POC se expand karo jab tak 70% volume cover na ho

    Returns: poc, vah, val, volume_at_price dict, stats
    """
    if not candles:
        return {}

    step = 10 if symbol in ("NIFTY", "FINNIFTY") else 20

    vol_map: dict[int, float] = {}   # price_bucket → cumulative volume

    for c in candles:
        high = c.get("high", 0) if isinstance(c, dict) else getattr(c, "high", 0)
        low  = c.get("low",  0) if isinstance(c, dict) else getattr(c, "low",  0)
        vol  = c.get("volume", 0) if isinstance(c, dict) else getattr(c, "volume", 0)

        if not high or not low or high < low:
            continue

        # Snap to nearest step boundary
        low_b  = int(low  / step) * step
        high_b = int(high / step) * step

        if low_b == high_b:
            vol_map[low_b] = vol_map.get(low_b, 0.0) + vol
            continue

        num_buckets    = max(1, (high_b - low_b) // step + 1)
        vol_per_bucket = vol / num_buckets

        b = low_b
        while b <= high_b:
            vol_map[b] = vol_map.get(b, 0.0) + vol_per_bucket
            b += step

    if not vol_map:
        return {}

    # ── Total volume — if very low (index may report 0 vol), use uniform ─────
    total_vol = sum(vol_map.values())
    if total_vol < 100:
        # Zero-volume index data — use price-time profile (count ticks per bucket)
        for b in vol_map:
            vol_map[b] = 1.0
        total_vol = float(len(vol_map))

    sorted_levels = sorted(vol_map.keys())

    # ── POC ───────────────────────────────────────────────────────────────────
    poc     = max(sorted_levels, key=lambda b: vol_map[b])
    poc_idx = sorted_levels.index(poc)

    # ── Value Area (70% of total volume, expanding from POC) ─────────────────
    target_vol = total_vol * 0.70
    lo_idx     = poc_idx
    hi_idx     = poc_idx
    va_vol     = vol_map[poc]

    while va_vol < target_vol:
        can_up   = hi_idx + 1 < len(sorted_levels)
        can_down = lo_idx - 1 >= 0
        if not can_up and not can_down:
            break

        v_up   = vol_map[sorted_levels[hi_idx + 1]] if can_up   else 0.0
        v_down = vol_map[sorted_levels[lo_idx - 1]] if can_down else 0.0

        if v_up >= v_down:
            hi_idx += 1
            va_vol += v_up
        else:
            lo_idx -= 1
            va_vol += v_down

    vah      = sorted_levels[hi_idx]
    val      = sorted_levels[lo_idx]
    max_vol  = max(vol_map.values())

    return {
        "poc":             poc,
        "vah":             vah,
        "val":             val,
        "step":            step,
        "total_volume":    int(total_vol),
        "poc_volume":      int(vol_map[poc]),
        "poc_volume_pct":  round(vol_map[poc] / total_vol * 100, 1),
        "va_volume_pct":   round(va_vol / total_vol * 100, 1),
        "volume_at_price": {int(k): round(v) for k, v in vol_map.items()},
        "max_volume":      int(max_vol),
        "candle_count":    len(candles),
    }


def _calc_iv_rank(symbol: str, current_iv: float) -> float:
    """
    Real IV Rank = (Current IV - 52-week Low) / (52-week High - 52-week Low) × 100
    History daily iv_history.json mein store hota hai (max 252 entries per symbol).
    """
    import json
    from datetime import date

    iv_file = os.path.join(ROOT, "data", "iv_history.json")

    # Load history
    try:
        with open(iv_file, "r") as f:
            history = json.load(f)
    except Exception:
        history = {}

    # Save today's IV snapshot
    today = date.today().isoformat()
    if symbol not in history:
        history[symbol] = {}
    history[symbol][today] = round(current_iv, 2)

    # Keep only last 252 trading days (1 year)
    sorted_dates = sorted(history[symbol].keys())
    if len(sorted_dates) > 252:
        for old in sorted_dates[:-252]:
            del history[symbol][old]

    # Save updated history
    try:
        os.makedirs(os.path.dirname(iv_file), exist_ok=True)
        with open(iv_file, "w") as f:
            json.dump(history, f)
    except Exception:
        pass

    # Calculate rank from available history
    iv_values = list(history[symbol].values())
    if len(iv_values) < 5:
        # Not enough data yet — estimate from current IV vs typical range
        # NIFTY IV typically 10–30%, BANKNIFTY 12–35%
        typical_lo = 10.0
        typical_hi = 30.0 if symbol == "NIFTY" else 35.0
        iv_rank = max(0.0, min(100.0,
                      (current_iv - typical_lo) / (typical_hi - typical_lo) * 100))
    else:
        lo = min(iv_values)
        hi = max(iv_values)
        if hi == lo:
            iv_rank = 50.0
        else:
            iv_rank = max(0.0, min(100.0,
                          (current_iv - lo) / (hi - lo) * 100))

    return round(iv_rank, 1)


def _calc_iv(symbol, expiry, cache) -> dict:
    kite    = st.session_state["kite"]
    prices  = cache.get("prices", {})
    sym_map = {
        "NIFTY":     "NSE:NIFTY 50",
        "BANKNIFTY": "NSE:NIFTY BANK",
        "FINNIFTY":  "NSE:NIFTY FIN SERVICE",
    }
    spot = prices.get(sym_map.get(symbol, ""), 0)
    if not spot:
        return {}

    tte  = tte_years(expiry)
    if tte <= 0:
        return {}

    step = {"NIFTY": 50, "BANKNIFTY": 100, "FINNIFTY": 50}.get(symbol, 50)
    atm  = round(spot / step) * step

    try:
        chain  = kite.get_option_chain(symbol, expiry)
        atm_ce = next((i for i in chain if i["strike"] == atm and i["instrument_type"] == "CE"), None)
        atm_pe = next((i for i in chain if i["strike"] == atm and i["instrument_type"] == "PE"), None)
        otm_up = atm + step * 3
        otm_dn = atm - step * 3
        otm_ce = next((i for i in chain if i["strike"] == otm_up and i["instrument_type"] == "CE"), None)
        otm_pe = next((i for i in chain if i["strike"] == otm_dn and i["instrument_type"] == "PE"), None)

        if not atm_ce or not atm_pe:
            return {}

        tokens = [f"NFO:{i['tradingsymbol']}" for i in [atm_ce, atm_pe, otm_ce, otm_pe] if i]
        quotes = kite.get_quote(tokens)

        def _ltp(inst):
            return quotes.get(f"NFO:{inst['tradingsymbol']}", {}).get("last_price", 0) if inst else 0

        ce_ltp = _ltp(atm_ce)
        pe_ltp = _ltp(atm_pe)
        if ce_ltp is None or pe_ltp is None or ce_ltp <= 0 or pe_ltp <= 0:
            return {}

        iv_ce  = calc_iv(ce_ltp, spot, atm, tte, "CE") or 15.0
        iv_pe  = calc_iv(pe_ltp, spot, atm, tte, "PE") or 15.0
        atm_iv = (iv_ce + iv_pe) / 2

        g_ce     = calc_greeks(spot, atm, tte, atm_iv / 100, "CE")
        g_pe     = calc_greeks(spot, atm, tte, atm_iv / 100, "PE")
        lot      = get_lot_size(symbol)
        theta_rs = ((g_ce.theta if g_ce else 0) + (g_pe.theta if g_pe else 0)) * lot

        skew = 0.0
        if otm_ce and otm_pe:
            oce_ltp = _ltp(otm_ce)
            ope_ltp = _ltp(otm_pe)
            if oce_ltp and ope_ltp:
                iv_oce = calc_iv(oce_ltp, spot, otm_up, tte, "CE") or atm_iv
                iv_ope = calc_iv(ope_ltp, spot, otm_dn, tte, "PE") or atm_iv
                skew   = iv_ope - iv_oce

        # ── IV Rank — real 52-week history se calculate karo ─────────────────
        iv_rank = _calc_iv_rank(symbol, atm_iv)

        return {
            "atm_iv":           round(atm_iv, 2),
            "atm_delta":        round(g_ce.delta if g_ce else 0, 4),
            "atm_gamma":        round(g_ce.gamma if g_ce else 0, 6),
            "atm_theta_rs":     round(theta_rs, 0),
            "atm_vega":         round(g_ce.vega  if g_ce else 0, 4),
            "iv_rank":          round(iv_rank, 1),
            "iv_skew":          round(skew, 2),
            "theta_per_day_rs": round(abs(theta_rs), 0),
        }
    except Exception as exc:
        logger.error(f"IV calc: {exc}")
        return {}


# ══════════════════════════════════════════════════════════════════════════════
# GEX CALCULATOR — Gamma Exposure (Institutional-grade signal)
# ══════════════════════════════════════════════════════════════════════════════
def _calc_gex(symbol: str, expiry: str, cache: dict) -> dict:
    """
    Gamma Exposure (GEX) — Market makers ko kitna hedge karna padega.

    Formula per strike:
        GEX (Cr) = Gamma × OI × Lot × Spot / 1e7
        CE = positive  (stabilizing force)
        PE = negative  (destabilizing force)

    Net GEX > 0 → Range bound   (MM buy dips, sell rallies)
    Net GEX < 0 → Volatile/Trend (MM amplify moves)

    Gamma Wall  = Highest absolute GEX strike (strongest magnet)
    Flip Level  = Strike where cumulative GEX crosses zero
    """
    sym_map  = {
        "NIFTY":     "NSE:NIFTY 50",
        "BANKNIFTY": "NSE:NIFTY BANK",
        "FINNIFTY":  "NSE:NIFTY FIN SERVICE",
    }
    prices   = cache.get("prices",   {})
    oi_chain = cache.get("oi_chain", [])
    iv_data  = cache.get("iv_data",  {})

    spot = prices.get(sym_map.get(symbol, ""), 0)
    if not spot or not oi_chain:
        return {}

    tte = tte_years(expiry)
    if tte <= 0:
        tte = 0.001   # expiry day — use small value

    # IV: use ATM IV from iv_data, fallback to VIX-based estimate
    atm_iv  = iv_data.get("atm_iv", 0)
    vix     = prices.get("NSE:INDIA VIX", 15.0)
    sigma   = max(atm_iv, vix, 8.0) / 100.0   # never below 8%

    lot     = get_lot_size(symbol)
    step    = 50 if symbol == "NIFTY" else 100

    gex_strikes  = {}   # strike → net_gex
    total_ce_gex = 0.0
    total_pe_gex = 0.0

    for row in oi_chain:
        strike = row.strike
        if row.ce_oi == 0 and row.pe_oi == 0:
            continue

        # Gamma — same for CE and PE at same strike (BS property)
        g = calc_greeks(spot, strike, tte, sigma, "CE")
        if g is None:
            continue
        gamma = g.gamma   # e.g. 0.000045

        # GEX in Crores = Gamma × OI × Lot × Spot / 1e7
        ce_gex = gamma * row.ce_oi * lot * spot / 1e7
        pe_gex = gamma * row.pe_oi * lot * spot / 1e7

        net = ce_gex - pe_gex
        gex_strikes[int(strike)] = {
            "ce_gex": round(ce_gex, 4),
            "pe_gex": round(pe_gex, 4),
            "net":    round(net,    4),
        }
        total_ce_gex += ce_gex
        total_pe_gex += pe_gex

    if not gex_strikes:
        return {}

    total_gex = total_ce_gex - total_pe_gex

    # ── Gamma Wall — strike with highest absolute net GEX ────────────────
    gamma_wall = max(gex_strikes.keys(),
                     key=lambda k: abs(gex_strikes[k]["net"]))

    # ── Flip Level — cumulative GEX crosses zero ──────────────────────────
    flip_level  = None
    cumulative  = 0.0
    prev_sign   = None
    for s in sorted(gex_strikes.keys()):
        cumulative += gex_strikes[s]["net"]
        sign = 1 if cumulative >= 0 else -1
        if prev_sign is not None and sign != prev_sign:
            flip_level = s
            break
        prev_sign = sign

    # ── Regime ────────────────────────────────────────────────────────────
    if total_gex > 0.5:
        regime       = "RANGE BOUND"
        regime_color = "#00c853"
        regime_emoji = "📦"
        regime_desc  = "Market makers buy dips & sell rallies → Stable, range-bound"
    elif total_gex < -0.5:
        regime       = "VOLATILE / TRENDING"
        regime_color = "#ff1744"
        regime_emoji = "🌊"
        regime_desc  = "Market makers amplify moves → Big directional move possible"
    else:
        regime       = "NEUTRAL"
        regime_color = "#ffd740"
        regime_emoji = "⚖️"
        regime_desc  = "Balanced positioning → Wait for clearer signal"

    return {
        "total_gex":    round(total_gex, 3),
        "total_ce_gex": round(total_ce_gex, 3),
        "total_pe_gex": round(total_pe_gex, 3),
        "gex_strikes":  gex_strikes,
        "gamma_wall":   gamma_wall,
        "flip_level":   flip_level,
        "regime":       regime,
        "regime_color": regime_color,
        "regime_emoji": regime_emoji,
        "regime_desc":  regime_desc,
        "spot":         spot,
    }


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — CALCULATION ENGINES
# Smart Money Index | Gamma Acceleration | Pin Probability | Expected Move | Cross-Asset
# ══════════════════════════════════════════════════════════════════════════════

def _calc_smi(symbol: str) -> dict:
    """
    Smart Money Index (SMI)
    ────────────────────────────────────────────────────────────────────
    Theory:
      - Morning (9:15–9:45) = Retail traders — emotional, panic buy/sell
      - Evening (3:00–3:30) = Institutions / Smart Money — calm, deliberate

    Formula:
      SMI = Previous_SMI  – Morning_Move  + Evening_Move

    Interpretation:
      SMI rising  + Price falling  = Institutions quietly BUYING   → Tomorrow BULLISH
      SMI falling + Price rising   = Institutions quietly SELLING  → Tomorrow BEARISH
    ────────────────────────────────────────────────────────────────────
    Uses VP candles (5-min, today) — no extra API call needed.
    """
    from datetime import date, timedelta

    kite = st.session_state["kite"]
    try:
        candles = kite.get_vp_candles(symbol, "Today")
    except Exception as exc:
        return {"error": str(exc)}

    if not candles or len(candles) < 6:
        return {}

    def _c(c, k):
        return c.get(k, 0) if isinstance(c, dict) else getattr(c, k, 0)

    # Morning: first 6 candles = 9:15–9:45
    morning_open  = _c(candles[0], "open")
    morning_close = _c(candles[min(5, len(candles) - 1)], "close")
    morning_move  = morning_close - morning_open

    # Evening: last 6 candles = 3:00–3:30
    eve           = candles[-6:]
    evening_open  = _c(eve[0], "open")
    evening_close = _c(eve[-1], "close")
    evening_move  = evening_close - evening_open

    # Persist SMI history in session_state
    today_str  = date.today().isoformat()
    yesterday  = (date.today() - timedelta(days=1)).isoformat()
    smi_hist   = st.session_state.get("smi_history", {})
    prev_smi   = smi_hist.get(yesterday, 1000.0)

    current_smi = prev_smi - morning_move + evening_move
    smi_hist[today_str] = round(current_smi, 1)

    # Keep only last 10 trading days
    for old in sorted(smi_hist.keys())[:-10]:
        del smi_hist[old]
    st.session_state["smi_history"] = smi_hist

    # 5-day trend
    vals  = [smi_hist[d] for d in sorted(smi_hist.keys())[-5:]]
    trend = "RISING ▲" if (len(vals) >= 2 and vals[-1] > vals[0]) else "FALLING ▼"

    # Signal classification
    if evening_move > 0 and morning_move < 0:
        signal, sig_col, tomorrow = "INSTITUTIONS QUIETLY BUYING",       "#00c853", "BULLISH"
    elif evening_move < 0 and morning_move > 0:
        signal, sig_col, tomorrow = "DISTRIBUTION — INSTITUTIONS SELLING", "#ff1744", "BEARISH"
    elif evening_move > 0:
        signal, sig_col, tomorrow = "BULLISH MOMENTUM — SMART MONEY CONFIRMS", "#00c853", "BULLISH"
    else:
        signal, sig_col, tomorrow = "BEARISH PRESSURE — SELLING INTO CLOSE",   "#ff1744", "BEARISH"

    return {
        "smi":          round(current_smi, 1),
        "prev_smi":     round(prev_smi, 1),
        "smi_change":   round(current_smi - prev_smi, 1),
        "morning_move": round(morning_move, 1),
        "evening_move": round(evening_move, 1),
        "trend":        trend,
        "signal":       signal,
        "sig_color":    sig_col,
        "tomorrow":     tomorrow,
        "history":      dict(sorted(smi_hist.items())[-5:]),
    }


def _update_gex_history(gex_total: float):
    """
    Called every 60 sec after GEX calc.
    Stores (timestamp, gex_value) pairs — max 30 readings (= 30 minutes).
    Used by _calc_gamma_acceleration().
    """
    hist = st.session_state.get("gex_history", [])
    hist.append({"time": datetime.now(), "gex": round(gex_total, 4)})
    if len(hist) > 30:
        hist = hist[-30:]
    st.session_state["gex_history"] = hist


def _calc_gamma_acceleration() -> dict:
    """
    Gamma Acceleration (dGEX/dt)
    ────────────────────────────────────────────────────────────────────
    GEX ki SPEED of change — not just the current value.

    Why it matters:
      Looking only at GEX = "Is it raining?"
      Gamma Acceleration = "How fast is it starting / stopping?"

    Formula:
      Rate (Cr/min) = (Current_GEX – Previous_GEX) / Time_Delta_minutes

    Flip ETA:
      If GEX is at +2 Cr and falling at –0.4 Cr/min
      → Flip in 2/0.4 = 5 minutes → ALERT! Volatility incoming.
    ────────────────────────────────────────────────────────────────────
    """
    hist = st.session_state.get("gex_history", [])
    if len(hist) < 2:
        return {}

    cur  = hist[-1]
    prev = hist[-2]

    dt_min = max(0.5, (cur["time"] - prev["time"]).total_seconds() / 60)
    chg    = cur["gex"] - prev["gex"]
    rate   = chg / dt_min          # Cr per minute

    # Direction label
    if cur["gex"] > 0 and chg < 0:
        direction, dir_col = "DECAYING",   "#ff6d00"
    elif cur["gex"] < 0 and chg > 0:
        direction, dir_col = "RECOVERING", "#ffd740"
    elif chg > 0:
        direction, dir_col = "BUILDING",   "#00c853"
    else:
        direction, dir_col = "WEAKENING",  "#ff1744"

    # Flip ETA calculation
    flip_eta = None
    if rate != 0 and cur["gex"] != 0:
        eta = -cur["gex"] / rate
        if 0 < eta < 60:
            flip_eta = round(eta)

    # Alert logic
    alert = None
    if flip_eta and flip_eta <= 15:
        alert = f"GEX FLIP in ~{flip_eta} minutes — Regime change incoming! Prepare for volatile move."
    elif flip_eta and flip_eta <= 30:
        alert = f"GEX approaching flip in ~{flip_eta} min — Monitor closely."
    elif abs(rate) > 5:
        alert = f"Fast GEX movement: {'+' if rate > 0 else ''}{rate:.1f} Cr/min"

    # Session decay: how much has GEX decayed since first reading
    first_val = abs(hist[0]["gex"]) if hist else 0
    decay_pct = max(0.0, min(100.0,
                    (1 - abs(cur["gex"]) / first_val) * 100)) if first_val else 0

    return {
        "current":   round(cur["gex"], 3),
        "change":    round(chg, 3),
        "rate":      round(rate, 2),
        "direction": direction,
        "dir_color": dir_col,
        "flip_eta":  flip_eta,
        "alert":     alert,
        "decay_pct": round(decay_pct, 1),
        "readings":  len(hist),
    }


def _calc_pin_probability(gex_data: dict) -> dict:
    """
    Strike Pinning Probability
    ────────────────────────────────────────────────────────────────────
    On expiry day, NIFTY gravitates toward strikes with highest GEX.
    Market makers re-hedge most aggressively there → price "pins".

    Formula:
      Pin_Prob(strike) = |Net_GEX_at_strike| / Σ|Net_GEX_all_strikes| × 100

    Example:
      Strike 24000 has 580 Cr net GEX out of total 1050 Cr abs GEX
      → Pin probability = 580/1050 × 100 = 55%
    ────────────────────────────────────────────────────────────────────
    """
    strikes   = gex_data.get("gex_strikes", {})
    spot      = gex_data.get("spot", 0)
    if not strikes:
        return {}

    total_abs = sum(abs(v["net"]) for v in strikes.values())
    if total_abs == 0:
        return {}

    probs = {s: round(abs(d["net"]) / total_abs * 100, 1)
             for s, d in strikes.items()}
    sorted_pins = sorted(probs.items(), key=lambda x: x[1], reverse=True)

    top_strike, top_prob = sorted_pins[0]

    note = ""
    if top_prob > 30:
        note = (f"SELL {top_strike} Straddle — {top_prob:.0f}% pin probability. "
                f"Best entry: 1–2 days before expiry. "
                f"Exit if NIFTY moves ±100 pts from {top_strike}.")

    return {
        "probs":       probs,
        "sorted_pins": sorted_pins[:8],
        "top_strike":  top_strike,
        "top_prob":    top_prob,
        "spot":        spot,
        "note":        note,
    }


def _calc_expected_move(iv_data: dict, cache: dict, symbol: str) -> dict:
    """
    Expected Move Calculator
    ────────────────────────────────────────────────────────────────────
    The ATM straddle price = market's collective estimate of how much
    NIFTY will move by expiry (85% confidence interval).

    Formula:
      Expected_Move = ATM_CE_Price + ATM_PE_Price

    Example:
      ATM CE 24000 = ₹216
      ATM PE 24000 = ₹218
      Expected Move = ₹434 points

    Meaning:
      85% probability NIFTY stays between 23566 and 24434 this expiry.

    Iron Condor:
      Sell strikes JUST OUTSIDE expected move = 85% win probability.
    ────────────────────────────────────────────────────────────────────
    """
    oi_chain = cache.get("oi_chain", [])
    prices   = cache.get("prices", {})
    sym_map  = {
        "NIFTY":     "NSE:NIFTY 50",
        "BANKNIFTY": "NSE:NIFTY BANK",
        "FINNIFTY":  "NSE:NIFTY FIN SERVICE",
    }
    spot = prices.get(sym_map.get(symbol, ""), 0)
    if not spot or not oi_chain:
        return {}

    step = 50 if symbol == "NIFTY" else 100
    atm  = round(spot / step) * step

    ce_ltp = pe_ltp = 0
    for row in oi_chain:
        if int(row.strike) == atm:
            ce_ltp = row.ce_ltp
            pe_ltp = row.pe_ltp
            break

    if not ce_ltp or not pe_ltp:
        return {}

    straddle = ce_ltp + pe_ltp
    upper    = round(spot + straddle)
    lower    = round(spot - straddle)

    # Iron Condor strikes (1 step outside expected move)
    ic_ce = int(round((upper + step) / step) * step)
    ic_pe = int(round((lower - step) / step) * step)

    ic_ce_prem = ic_pe_prem = 0
    for row in oi_chain:
        if int(row.strike) == ic_ce: ic_ce_prem = row.ce_ltp
        if int(row.strike) == ic_pe: ic_pe_prem = row.pe_ltp

    move_pct = round(straddle / spot * 100, 2)

    if straddle > spot * 0.025:
        tone, tone_col = "HIGH FEAR — BIG MOVE EXPECTED", "#ff1744"
        advice = "Market is pricing in a large move. Buying directional options is better than selling."
    elif straddle < spot * 0.01:
        tone, tone_col = "CALM MARKET — LOW VOLATILITY",  "#00c853"
        advice = "Market expects a small move. Iron Condor is safe — best time to sell premium."
    else:
        tone, tone_col = "NORMAL VOLATILITY",             "#ffd740"
        advice = "Standard conditions. Both buying and selling strategies are viable."

    return {
        "atm":        atm,
        "spot":       spot,
        "ce_ltp":     round(ce_ltp, 1),
        "pe_ltp":     round(pe_ltp, 1),
        "straddle":   round(straddle, 1),
        "upper":      upper,
        "lower":      lower,
        "move_pct":   move_pct,
        "ic_ce":      ic_ce,
        "ic_pe":      ic_pe,
        "ic_ce_prem": round(ic_ce_prem, 1),
        "ic_pe_prem": round(ic_pe_prem, 1),
        "ic_total":   round(ic_ce_prem + ic_pe_prem, 1),
        "tone":       tone,
        "tone_col":   tone_col,
        "advice":     advice,
    }


def _calc_cross_assets(kite, prices: dict) -> dict:
    """
    Cross-Asset Signals
    ────────────────────────────────────────────────────────────────────
    NIFTY does not move in isolation. These correlated markets give
    early signals — some lead NIFTY by 15–30 minutes.

    Available via Kite API:
      1. India VIX      — Fear gauge. Low = Bullish. High = Caution.
      2. BankNifty/NIFTY ratio — Sectoral health. FII activity proxy.
      3. USD/INR        — Rupee strong = FII buying equities.

    Not available via Kite (check manually):
      - SGX Nifty  → sgxnifty.com  (pre-market, 15 min lead)
      - US Futures → cnbc.com/world-markets  (overnight signal)
      - Crude Oil  → MCX requires separate subscription
    ────────────────────────────────────────────────────────────────────
    """
    signals = []
    score   = 0

    # ── 1. India VIX ─────────────────────────────────────────────────
    vix = prices.get("NSE:INDIA VIX", 0)
    if vix:
        if vix < 14:
            sig_vix = ("BULLISH", "#00c853", "Low fear — market stable, buying strategies ok")
            score += 1
        elif vix > 20:
            sig_vix = ("CAUTION", "#ff6d00", "High fear — prefer selling premium, reduce buying")
            score -= 1
        else:
            sig_vix = ("NEUTRAL", "#ffd740", "Moderate volatility — standard conditions")
        signals.append({"name": "India VIX",  "value": f"{vix:.2f}",
                         "icon": "⚡", "signal": sig_vix[0],
                         "color": sig_vix[1], "note": sig_vix[2]})

    # ── 2. BankNifty vs NIFTY ratio ──────────────────────────────────
    nifty     = prices.get("NSE:NIFTY 50",         0)
    banknifty = prices.get("NSE:NIFTY BANK",       0)
    if nifty and banknifty:
        ratio      = banknifty / nifty
        expected   = 2.12   # historical average ratio
        ratio_diff = (ratio - expected) / expected * 100
        if ratio_diff > 1.5:
            sig_bn = ("BULLISH", "#00c853", "Banks outperforming — FII buying financials → broad rally likely")
            score += 1
        elif ratio_diff < -1.5:
            sig_bn = ("BEARISH", "#ff1744", "Banks underperforming — stress in financial sector")
            score -= 1
        else:
            sig_bn = ("NEUTRAL", "#ffd740", "BankNifty in line with NIFTY — balanced sector performance")
        signals.append({"name": f"BankNifty/NIFTY", "value": f"{ratio:.3f}x",
                         "icon": "🏦", "signal": sig_bn[0],
                         "color": sig_bn[1], "note": sig_bn[2]})

    # ── 3. USD / INR (CDS segment — may or may not be available) ─────
    try:
        usd_data = kite.get_ltp(["NSE:USDINR"])
        usd_inr  = list(usd_data.values())[0] if usd_data else 0
        if usd_inr and 50 < usd_inr < 120:   # sanity check
            if usd_inr < 83:
                sig_fx = ("BULLISH", "#00c853", "Strong Rupee = FII net buyers in equities")
                score += 1
            elif usd_inr > 85:
                sig_fx = ("BEARISH", "#ff1744", "Weak Rupee = FII net sellers, NIFTY under pressure")
                score -= 1
            else:
                sig_fx = ("NEUTRAL", "#ffd740", "Rupee stable — no directional FII signal")
            signals.append({"name": "USD/INR", "value": f"₹{usd_inr:.2f}",
                             "icon": "💵", "signal": sig_fx[0],
                             "color": sig_fx[1], "note": sig_fx[2]})
    except Exception:
        pass   # USD/INR not available — skip silently

    # ── Overall score ─────────────────────────────────────────────────
    if score >= 2:
        overall, ov_col = "BULLISH ▲", "#00c853"
    elif score <= -2:
        overall, ov_col = "BEARISH ▼", "#ff1744"
    else:
        overall, ov_col = "MIXED ↔",  "#ffd740"

    return {
        "signals":  signals,
        "score":    score,
        "total":    len(signals),
        "overall":  overall,
        "ov_color": ov_col,
    }


# ══════════════════════════════════════════════════════════════════════════════
# RENDER HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _badge(text, color):
    return (f'<span style="background:{color}33;color:{color};'
            f'padding:2px 10px;border-radius:10px;font-size:12px">{text}</span>')


def render_header(symbol, expiry, cache):
    status    = get_market_status()
    s_color   = {"OPEN": "#00c853", "CLOSED": "#ff1744",
                 "PRE-OPEN": "#ffd740", "WEEKEND": "#888"}.get(status, "#ffd740")
    now       = datetime.now().strftime("%d %b %Y  %H:%M:%S")
    fetched   = cache.get("fetched_at", "--:--:--")

    try:
        tlog    = st.session_state["trade_log"]
        summary = tlog.get_daily_summary()
        pnl     = summary.get("gross_pnl", 0)
        trades  = summary.get("total_trades", 0)
        pnl_str = f"+₹{pnl:,.0f}" if pnl >= 0 else f"₹{pnl:,.0f}"
        pnl_col = "#00c853" if pnl >= 0 else "#ff1744"
    except Exception:
        pnl_str, pnl_col, trades = "₹0", "#888", 0

    st.markdown(f"""
    <div style="background:#f8f9fd;border:1px solid #e0e4ef;border-radius:8px;
                padding:10px 18px;margin-bottom:14px;
                display:flex;justify-content:space-between;align-items:center;
                flex-wrap:wrap;gap:12px;">
        <div style="display:flex;align-items:center;gap:16px">
            <span style="font-size:18px;font-weight:700;color:#1a1a2e">{symbol}</span>
            <span style="background:#e8edf8;border-radius:4px;padding:3px 8px;
                         font-size:11px;color:#5a6a8a;font-weight:500">
                Expiry &nbsp;<b style="color:#1a1a2e">{expiry}</b>
            </span>
            <span style="display:inline-flex;align-items:center;gap:5px;font-size:12px">
                <span style="width:7px;height:7px;border-radius:50%;
                             background:{s_color};display:inline-block"></span>
                <span style="color:#5a6a8a">{status}</span>
            </span>
        </div>
        <div style="display:flex;align-items:center;gap:20px">
            <div>
                <div style="font-size:10px;color:#9aa0b4;text-transform:uppercase;
                             letter-spacing:0.6px">Day P&amp;L</div>
                <div style="font-size:16px;font-weight:600;color:{pnl_col}">
                    {pnl_str}&nbsp;<span style="font-size:11px;color:#9aa0b4;
                    font-weight:400">({trades} trades)</span>
                </div>
            </div>
            <div style="font-size:11px;color:#c0c8d8;border-left:1px solid #e0e4ef;
                         padding-left:16px">&#x1f504; {fetched}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_market_overview(cache):
    prices  = cache.get("prices", {})
    n50  = prices.get("NSE:NIFTY 50",          0)
    bnk  = prices.get("NSE:NIFTY BANK",        0)
    fin  = prices.get("NSE:NIFTY FIN SERVICE", 0)
    vix  = prices.get("NSE:INDIA VIX",         0)

    vix_clr  = "#ff1744" if vix > 20 else ("#00c853" if vix < 14 else "#ff6d00")
    vix_note = "High Fear" if vix > 20 else ("Low Vol" if vix < 14 else "Moderate")

    def _fmt(v): return f"₹{v:,.0f}" if v else "—"

    st.markdown(
        f"<div style='padding:8px 14px;background:#f8f9fd;"
        f"border:1px solid #e0e4ef;border-radius:8px;"
        f"display:flex;align-items:center;flex-wrap:wrap;gap:4px'>"
        f"<span style='color:#5a6a8a;font-size:12px;font-weight:600'>NIFTY 50</span>"
        f"&nbsp;<span style='font-size:16px;font-weight:700;color:#1a1a2e'>{_fmt(n50)}</span>"
        f"<span style='color:#e0e4ef;margin:0 12px'>|</span>"
        f"<span style='color:#5a6a8a;font-size:12px;font-weight:600'>BANK</span>"
        f"&nbsp;<span style='font-size:16px;font-weight:700;color:#1a1a2e'>{_fmt(bnk)}</span>"
        f"<span style='color:#e0e4ef;margin:0 12px'>|</span>"
        f"<span style='color:#5a6a8a;font-size:12px;font-weight:600'>FIN NIFTY</span>"
        f"&nbsp;<span style='font-size:16px;font-weight:700;color:#1a1a2e'>{_fmt(fin)}</span>"
        f"<span style='color:#e0e4ef;margin:0 12px'>|</span>"
        f"<span style='color:#5a6a8a;font-size:12px;font-weight:600'>VIX</span>"
        f"&nbsp;<span style='font-size:16px;font-weight:700;color:{vix_clr}'>{vix:.2f}</span>"
        f"&nbsp;<span style='background:{vix_clr}22;color:{vix_clr};padding:2px 9px;"
        f"border-radius:10px;font-size:11px;font-weight:600'>{vix_note}</span>"
        f"</div>",
        unsafe_allow_html=True
    )

    # ── PCR Row — inline, compact ─────────────────────────────────────────────
    pcr_data = cache.get("pcr_data", {})
    zone_col = {
        "EXTREME_BULL": "#00c853", "BULLISH":  "#69f0ae",
        "NEUTRAL":      "#ffd740", "BEARISH":  "#ff6d00",
        "EXTREME_BEAR": "#ff1744",
    }
    if pcr_data:
        parts = []
        for sym in ["NIFTY", "BANKNIFTY"]:
            if sym not in pcr_data:
                continue
            r, trend = pcr_data[sym]
            clr   = zone_col.get(r.zone, "#888")
            t_ico = {"▲": "▲", "▼": "▼", "→": "→"}.get(trend, "")
            parts.append(
                f"<span style='color:#5a6a8a;font-size:12px;font-weight:600'>{sym}</span>"
                f"&nbsp;<span style='font-size:18px;font-weight:700;color:{clr}'>{r.pcr:.2f}</span>"
                f"&nbsp;<span style='color:{clr};font-size:11px'>{t_ico}</span>"
                f"&nbsp;<span style='background:{clr}22;color:{clr};padding:2px 9px;"
                f"border-radius:10px;font-size:11px;font-weight:600'>{r.zone}</span>"
                f"&nbsp;<span style='color:#aab0c0;font-size:11px'>Signal: {r.signal}</span>"
            )
        if parts:
            divider = "<span style='color:#e0e4ef;font-size:16px;margin:0 16px'>|</span>"
            st.markdown(
                f"<div style='margin-top:10px;padding:8px 14px;background:#f8f9fd;"
                f"border:1px solid #e0e4ef;border-radius:8px;display:flex;"
                f"align-items:center;flex-wrap:wrap;gap:4px'>"
                f"<span style='color:#8a96b0;font-size:10px;font-weight:600;"
                f"text-transform:uppercase;letter-spacing:0.6px;margin-right:12px'>PCR</span>"
                f"{divider.join(parts)}</div>",
                unsafe_allow_html=True
            )


def render_oi_chain(cache, symbol):
    chain     = cache.get("oi_chain", [])
    mp_result = cache.get("mp_result")
    prices    = cache.get("prices", {})

    sym_map = {
        "NIFTY":     "NSE:NIFTY 50",
        "BANKNIFTY": "NSE:NIFTY BANK",
        "FINNIFTY":  "NSE:NIFTY FIN SERVICE",
    }
    spot = prices.get(sym_map.get(symbol, ""), 0)
    atm  = min(chain, key=lambda r: abs(r.strike - spot)).strike if (chain and spot) else 0
    mp_strike = mp_result.max_pain_strike if mp_result else None

    if mp_result:
        sig_c  = "#1b7a2e" if mp_result.signal == "BULLISH" else (
                 "#c0392b" if mp_result.signal == "BEARISH" else "#b07c00")
        sig_bg = "#e8f5e9" if mp_result.signal == "BULLISH" else (
                 "#ffeaea" if mp_result.signal == "BEARISH" else "#fff8e1")
        st.markdown(f"""
        <div style="background:#f8f9fd;border:1px solid #e0e4ef;padding:10px 16px;
                    border-radius:8px;margin-bottom:10px;font-size:13px;
                    display:flex;align-items:center;gap:20px;flex-wrap:wrap">
            <span style="color:#5a6a8a">🎯 Max Pain:
                <b style="color:#1a1a2e">{int(mp_result.max_pain_strike)}</b></span>
            <span style="color:#5a6a8a">🟢 Support:
                <b style="color:#1b7a2e">{int(mp_result.top_pe_oi_strike)}</b></span>
            <span style="color:#5a6a8a">🔴 Resist:
                <b style="color:#c0392b">{int(mp_result.top_ce_oi_strike)}</b></span>
            <span style="background:{sig_bg};color:{sig_c};font-weight:600;
                         padding:3px 12px;border-radius:20px;font-size:12px">
                {mp_result.signal}</span>
        </div>
        """, unsafe_allow_html=True)

    if not chain:
        st.info("⏳ OI data loading... (market may be closed)")
        return

    rows = []
    for r in chain:
        s = int(r.strike)
        if r.strike == atm and r.strike == mp_strike:
            slabel = f"★{s}"
        elif r.strike == atm:
            slabel = str(s)   # green highlight hi kaafi hai
        elif r.strike == mp_strike:
            slabel = f"MP {s}"
        else:
            slabel = str(s)

        # OI Buildup signal
        if r.ce_oi_chg > 500:
            build = "🟢 FL"
        elif r.ce_oi_chg < -500:
            build = "🔴 LU"
        elif r.pe_oi_chg > 500:
            build = "🔴 FS"
        elif r.pe_oi_chg < -500:
            build = "🟢 SC"
        else:
            build = "⚪"

        # OI in Lakh format — readable (19,796,335 → 197.96L)
        def _l(v):   return f"{v/100000:.1f}L"
        def _chg(v):
            if v == 0: return "+0"
            return f"+{v/100000:.1f}L" if v > 0 else f"{v/100000:.1f}L"

        rows.append({
            "CE OI":  _l(r.ce_oi),
            "CE CHG": _chg(r.ce_oi_chg),
            "CE LTP": f"{r.ce_ltp:.1f}",
            "STRIKE": slabel,
            "PE LTP": f"{r.pe_ltp:.1f}",
            "PE CHG": _chg(r.pe_oi_chg),
            "PE OI":  _l(r.pe_oi),
            "PCR":    f"{r.pcr:.2f}" if r.ce_oi > 0 else "—",
            "BUILD":  build,
            "_atm":   r.strike == atm,
        })

    # ── Auto-scroll to ATM: start display 2 rows before ATM ─────────────────
    atm_pos = next((i for i, r in enumerate(rows) if r["_atm"]), 0)
    start   = max(0, atm_pos - 2)
    rows    = rows[start:]

    df       = pd.DataFrame(rows)
    atm_mask = df["_atm"].tolist()
    df       = df.drop(columns=["_atm"])

    def highlight(row):
        if atm_mask[row.name]:
            return ["background-color:#e8f0fe;color:#1a1a2e;font-weight:700"] * len(row)
        return ["color:#1a1a2e"] * len(row)

    st.dataframe(df.style.apply(highlight, axis=1),
                 use_container_width=True, height=400, hide_index=True)


def render_uoa(cache):
    alerts = cache.get("uoa_alerts", [])
    if not alerts:
        st.markdown("""
        <div style="background:#f8f9fd;border:1px solid #e0e4ef;border-radius:8px;padding:20px;text-align:center">
            <div style="font-size:28px">📡</div>
            <div style="color:#b8860b;font-weight:bold;margin-top:8px">
                Baseline collect ho rahi hai...
            </div>
            <div style="color:#6b7a99;font-size:12px;margin-top:6px">
                Pehli scan mein volume baseline set hoti hai.<br>
                60 seconds mein 2x+ unusual activity alerts aayenge.
            </div>
            <div style="color:#8a96b0;font-size:11px;margin-top:8px">
                Threshold: 2x = Unusual &nbsp;|&nbsp; 5x = 🔥 Fire
            </div>
        </div>
        """, unsafe_allow_html=True)
        return

    # ── Sentiment display mapping ──────────────────────────────────────────────
    SENTIMENT_DISPLAY = {
        "DEEP_ITM_INST":  ("⚠️ DEEP ITM — INSTITUTIONAL", "#ff9800"),
        "MILD_ITM_BULL":  ("🔵 MILD ITM — BULLISH",        "#40c4ff"),
        "BULLISH":        ("🟢 BULLISH",                    "#00c853"),
        "MILD_ITM_BEAR":  ("🟣 MILD ITM — BEARISH",        "#ce93d8"),
        "BEARISH":        ("🔴 BEARISH",                    "#ff1744"),
    }

    rows = []
    for a in alerts:
        fire_tag = " 🔥" if a.is_fire else ""
        label, _ = SENTIMENT_DISPLAY.get(a.sentiment,
                                         (a.sentiment, "#aaaaaa"))
        # ITM depth column show karo agar applicable
        itm_str = f"{a.itm_depth_pct:.1f}% ITM" if a.itm_depth_pct > 0 else "ATM/OTM"
        spot_str = f"₹{a.spot_at_alert:,.0f}" if a.spot_at_alert > 0 else "—"
        rows.append({
            "TIME":    a.time,
            "SYMBOL":  a.symbol,
            "TYPE":    a.opt_type,
            "STRIKE":  int(a.strike),
            "SPOT":    spot_str,
            "DEPTH":   itm_str,
            "VOLUME":  f"{a.volume:,}",
            "MULT":    f"{a.mult:.1f}x{fire_tag}",
            "SIGNAL":  label,
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True,
                 height=300, hide_index=True)

    # ── Legend / Guide ─────────────────────────────────────────────────────────
    st.markdown("""
    <div style="background:#f0f4ff;border:1px solid #d0d8f0;border-radius:8px;padding:12px 16px;margin-top:8px;
                font-size:12px;line-height:1.9">
        <span style="color:#3a4a6b;font-weight:bold">SIGNAL GUIDE &nbsp;|&nbsp; </span>
        <span style="color:#e65100">&#9888; DEEP ITM — INSTITUTIONAL</span>
        <span style="color:#6b7a99"> &nbsp;= 5%+ ITM &rarr; Hedge/Roll. Retail ke liye NOT actionable directly.</span>
        &nbsp;&nbsp;
        <span style="color:#0077cc">&#9679; MILD ITM</span>
        <span style="color:#6b7a99"> = 2-5% ITM &rarr; Strong conviction but protected entry.</span>
        &nbsp;&nbsp;
        <span style="color:#1b7a2e">&#9679; BULLISH / </span>
        <span style="color:#c0392b">&#9679; BEARISH</span>
        <span style="color:#6b7a99"> = ATM/OTM &rarr; Pure directional. Most actionable for retail.</span>
    </div>
    """, unsafe_allow_html=True)


def render_pcr(cache):
    pcr_data  = cache.get("pcr_data", {})
    zone_col  = {
        "EXTREME_BULL": "#00c853", "BULLISH":  "#69f0ae",
        "NEUTRAL":      "#ffd740", "BEARISH":  "#ff6d00",
        "EXTREME_BEAR": "#ff1744",
    }
    for sym in ["NIFTY", "BANKNIFTY"]:
        if sym not in pcr_data:
            st.markdown(
                f'<div style="background:#f8f9fd;border:1px solid #e0e4ef;border-radius:8px;padding:12px;'
                f'margin-bottom:8px;color:#8a96b0;">{sym} — fetching...</div>',
                unsafe_allow_html=True)
            continue
        r, trend = pcr_data[sym]
        color     = zone_col.get(r.zone, "#888")
        trend_ico = {"▲": "🟢 ▲", "▼": "🔴 ▼", "→": "⚪ →"}.get(trend, "")
        st.markdown(f"""
        <div style="background:#f8f9fd;border:1px solid #e0e4ef;
                    border-radius:8px;padding:12px;margin-bottom:8px;">
            <b style="color:#1a1a2e;font-size:15px">{sym}</b>
            &nbsp;&nbsp;
            <span style="font-size:24px;font-weight:bold;color:{color}">{r.pcr:.2f}</span>
            &nbsp;{trend_ico}&nbsp;
            <span style="background:{color}22;color:{color};
                         padding:2px 10px;border-radius:10px;
                         font-size:12px">{r.zone}</span>
            <br/>
            <span style="color:#6b7a99;font-size:12px">
                Signal: {r.signal} &nbsp;|&nbsp; Strategy: {r.strategy}
            </span>
        </div>
        """, unsafe_allow_html=True)


def render_iv(cache):
    iv = cache.get("iv_data", {})
    if not iv:
        st.info("⏳ Calculating IV...")
        return

    ivr   = iv.get("iv_rank", 0)
    ivr_c = "#ff1744" if ivr > 70 else ("#ffd740" if ivr > 40 else "#00c853")
    ivr_t = "SELL PREMIUM" if ivr > 60 else ("BUY OPTIONS" if ivr < 30 else "NEUTRAL")

    skew  = iv.get("iv_skew", 0)
    sk_c  = "#ff1744" if skew > 2 else ("#00c853" if skew < -1 else "#ffd740")
    sk_t  = "PE>CE (Fear)" if skew > 1 else ("CE>PE (Greed)" if skew < -1 else "Balanced")

    theta = iv.get("atm_theta_rs", 0)
    th_c  = "#00c853" if theta > 0 else "#ff1744"

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**ATM Greeks**")
        st.dataframe(pd.DataFrame([
            {"Greek": "Δ Delta",  "Value": f"{iv.get('atm_delta',0):+.4f}"},
            {"Greek": "Γ Gamma",  "Value": f"{iv.get('atm_gamma',0):.6f}"},
            {"Greek": "Θ Theta",  "Value": f"₹{theta:+.0f}/day"},
            {"Greek": "ν Vega",   "Value": f"{iv.get('atm_vega',0):.4f}"},
            {"Greek": "ATM IV",   "Value": f"{iv.get('atm_iv',0):.2f}%"},
        ]), use_container_width=True, hide_index=True, height=215)

    with c2:
        st.markdown("**IV Rank & Skew**")
        st.markdown(f"""
        <div style="background:#f8f9fd;border:1px solid #e0e4ef;border-radius:8px;padding:12px;margin-bottom:6px">
            <div style="color:#6b7a99;font-size:12px">IV Rank</div>
            <div style="font-size:28px;font-weight:bold;color:{ivr_c}">{ivr:.0f}%</div>
            <div style="color:{ivr_c};font-size:12px">{ivr_t}</div>
        </div>
        <div style="background:#f8f9fd;border:1px solid #e0e4ef;border-radius:8px;padding:12px;margin-bottom:6px">
            <div style="color:#6b7a99;font-size:12px">IV Skew (PE−CE)</div>
            <div style="font-size:22px;font-weight:bold;color:{sk_c}">{skew:+.2f}%</div>
            <div style="color:{sk_c};font-size:12px">{sk_t}</div>
        </div>
        <div style="background:#f8f9fd;border:1px solid #e0e4ef;border-radius:8px;padding:12px">
            <div style="color:#6b7a99;font-size:12px">⏰ Theta Clock</div>
            <div style="font-size:20px;font-weight:bold;color:{th_c}">
                ₹{abs(theta):,.0f}/day
            </div>
            <div style="color:#8a96b0;font-size:11px">7d ≈ ₹{abs(theta)*7:,.0f}</div>
        </div>
        """, unsafe_allow_html=True)


def render_buildup(cache):
    chain = cache.get("oi_chain", [])
    if not chain:
        st.info("⏳ Loading OI data...")
        return
    rows = []
    for r in chain:
        for opt, oi_chg, ltp in [("CE", r.ce_oi_chg, r.ce_ltp),
                                  ("PE", r.pe_oi_chg, r.pe_ltp)]:
            if abs(oi_chg) < 1000:
                continue
            if   oi_chg > 0 and ltp > 0:
                sig = ("🟢 Fresh Long"  if opt == "CE" else "🔴 Fresh Short")
            elif oi_chg > 0 and ltp <= 0:
                sig = ("🔴 Fresh Short" if opt == "CE" else "🟢 Fresh Long")
            elif oi_chg < 0 and ltp > 0:
                sig = ("🟢 Short Cover" if opt == "CE" else "🔴 Long Unwind")
            else:
                sig = ("🔴 Long Unwind" if opt == "CE" else "🟢 Short Cover")
            rows.append({
                "STRIKE": int(r.strike), "TYPE": opt,
                "SIGNAL": sig, "OI CHG": f"{oi_chg:+,}", "LTP": f"{ltp:.1f}",
            })

    if not rows:
        st.info("No significant OI changes yet (min 1000 contracts)")
        return

    rows.sort(key=lambda x: abs(int(x["OI CHG"].replace(",","").replace("+","")
                                   .replace("-",""))), reverse=True)
    st.dataframe(pd.DataFrame(rows[:12]), use_container_width=True,
                 height=300, hide_index=True)


def render_risk(cache):
    snap   = cache.get("risk_snap")
    alerts = cache.get("risk_alerts", [])

    if not snap or snap.open_positions == 0:
        st.markdown("""
        <div style="background:#f8f9fd;border:1px solid #e0e4ef;border-radius:8px;padding:24px;text-align:center">
            <div style="font-size:36px">📭</div>
            <div style="color:#6b7a99;margin-top:8px">No open positions</div>
        </div>""", unsafe_allow_html=True)
    else:
        mu    = snap.margin_utilization
        mu_c  = "#ff1744" if mu > 90 else ("#ffd740" if mu > 75 else "#00c853")
        dc    = "#00c853" if snap.net_delta >= 0 else "#ff6d00"
        tc    = "#00c853" if snap.net_theta >= 0 else "#ff1744"
        pc    = "#00c853" if snap.day_pnl   >= 0 else "#ff1744"

        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"""
            <table style="width:100%;font-size:13px;border-collapse:collapse">
            <tr><td style="color:#6b7a99;padding:4px">Net Delta</td>
                <td style="color:{dc};font-weight:bold;text-align:right">
                    {snap.net_delta:+.4f}</td></tr>
            <tr><td style="color:#6b7a99;padding:4px">Net Theta</td>
                <td style="color:{tc};font-weight:bold;text-align:right">
                    ₹{snap.net_theta:+,.0f}/day</td></tr>
            <tr><td style="color:#6b7a99;padding:4px">Net Vega</td>
                <td style="color:#1a56db;font-weight:bold;text-align:right">
                    {snap.net_vega:+,.0f}</td></tr>
            <tr><td style="color:#6b7a99;padding:4px">Unrealised P&amp;L</td>
                <td style="color:{pc};font-weight:bold;text-align:right">
                    ₹{snap.unrealized_pnl:+,.0f}</td></tr>
            <tr><td style="color:#6b7a99;padding:4px">Positions</td>
                <td style="color:#1a1a2e;font-weight:bold;text-align:right">
                    {snap.open_positions}</td></tr>
            </table>""", unsafe_allow_html=True)
        with c2:
            bar = "█" * int(mu/5) + "░" * (20 - int(mu/5))
            st.markdown(f"""
            <div style="text-align:center;padding-top:8px">
                <div style="color:#aaa;font-size:12px">Margin Used</div>
                <div style="font-size:32px;font-weight:bold;color:{mu_c}">{mu:.1f}%</div>
                <div style="font-family:monospace;color:{mu_c}">{bar}</div>
            </div>""", unsafe_allow_html=True)

    for a in alerts:
        if a.level == "BREACH":
            st.error(f"🚨 {a.message}")
        else:
            st.warning(f"⚠️ {a.message}")


# ══════════════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════════════
# MAX PAIN RENDER
# ══════════════════════════════════════════════════════════════════════════════

def render_max_pain(cache: dict, symbol: str, expiry: str):
    """
    Max Pain Calculator panel.
    Dikhata hai: pain chart, max pain strike, support/resistance,
    spot vs max pain gap, expiry countdown, signal.
    """
    mp = cache.get("mp_result")

    if not mp:
        st.info("⏳ Max Pain loading — OI chain fetch ho rahi hai...")
        return

    # ── Expiry countdown ──────────────────────────────────────────────────────
    try:
        from datetime import date as _date
        exp_date  = _date.fromisoformat(expiry)
        days_left = (exp_date - _date.today()).days
        if days_left < 0:
            days_str = "Expired"
            day_col  = "#c0392b"
        elif days_left == 0:
            days_str = "Today — Expiry Day!"
            day_col  = "#c0392b"
        elif days_left == 1:
            days_str = "1 day left"
            day_col  = "#e65100"
        else:
            days_str = f"{days_left} days left"
            day_col  = "#1b7a2e" if days_left > 3 else "#e65100"
    except Exception:
        days_str = expiry
        day_col  = "#6b7a99"

    # ── Signal colors ─────────────────────────────────────────────────────────
    sig_cfg = {
        "BULLISH": ("#1b7a2e", "#e8f5e9", "▲ Market may drift UP to max pain"),
        "BEARISH": ("#c0392b", "#ffeaea", "▼ Market may drift DOWN to max pain"),
        "NEUTRAL": ("#b07c00", "#fff8e1", "→ Spot near max pain — balanced"),
    }
    sig_col, sig_bg, sig_desc = sig_cfg.get(mp.signal, sig_cfg["NEUTRAL"])

    dist_abs = abs(mp.distance_pts)
    dist_pct = abs(mp.distance_pct)

    # Pull strength — how strong is the magnetic pull
    if days_left <= 1:
        pull_str  = "🔴 VERY STRONG"
        pull_col  = "#c0392b"
        pull_note = "Expiry day — max pain pull at its strongest"
    elif days_left <= 2:
        pull_str  = "🟠 STRONG"
        pull_col  = "#e65100"
        pull_note = "1-2 days to expiry — significant pull"
    elif days_left <= 4:
        pull_str  = "🟡 MODERATE"
        pull_col  = "#b07c00"
        pull_note = "Mid-week — pull building up"
    else:
        pull_str  = "⚪ WEAK"
        pull_col  = "#8a96b0"
        pull_note = "Far from expiry — ignore max pain for now"

    # ── Header card ───────────────────────────────────────────────────────────
    st.markdown(f"""
    <div style="background:#f8f9fd;border:2px solid {sig_col};border-radius:12px;
                padding:16px;margin-bottom:14px">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;
                    flex-wrap:wrap;gap:12px">
            <div>
                <span style="font-size:22px">🎯</span>
                <span style="font-size:18px;font-weight:700;color:#1a1a2e;
                             margin-left:8px">Max Pain</span>
                <span style="font-size:12px;color:{day_col};font-weight:600;
                             margin-left:12px;background:{sig_bg};padding:2px 10px;
                             border-radius:12px">{days_str}</span>
            </div>
            <div style="text-align:right">
                <div style="color:#6b7a99;font-size:11px">Max Pain Strike</div>
                <div style="font-size:32px;font-weight:800;color:{sig_col};
                             line-height:1.1">{int(mp.max_pain_strike):,}</div>
                <div style="color:#6b7a99;font-size:11px">
                    Spot {int(mp.spot):,} &nbsp;|&nbsp;
                    Gap <b style="color:{sig_col}">{mp.distance_pts:+.0f} pts
                    ({mp.distance_pct:+.2f}%)</b>
                </div>
            </div>
        </div>
        <div style="margin-top:12px;padding:10px;background:{sig_bg};
                    border-left:4px solid {sig_col};border-radius:6px">
            <span style="color:{sig_col};font-weight:600;font-size:13px">
                {mp.signal} — {sig_desc}</span>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:10px">
            <div style="background:#f0f3fa;border:1px solid #e0e4ef;border-radius:8px;
                        padding:10px;text-align:center">
                <div style="color:#6b7a99;font-size:10px;letter-spacing:1px">
                    🟢 SUPPORT (Max PE OI)</div>
                <div style="font-size:20px;font-weight:700;color:#1b7a2e">
                    {int(mp.top_pe_oi_strike):,}</div>
                <div style="color:#8a96b0;font-size:10px">Puts ka wall</div>
            </div>
            <div style="background:#f0f3fa;border:1px solid #e0e4ef;border-radius:8px;
                        padding:10px;text-align:center">
                <div style="color:#6b7a99;font-size:10px;letter-spacing:1px">
                    🎯 MAX PAIN</div>
                <div style="font-size:20px;font-weight:700;color:{sig_col}">
                    {int(mp.max_pain_strike):,}</div>
                <div style="color:#8a96b0;font-size:10px">Writers ka sweet spot</div>
            </div>
            <div style="background:#f0f3fa;border:1px solid #e0e4ef;border-radius:8px;
                        padding:10px;text-align:center">
                <div style="color:#6b7a99;font-size:10px;letter-spacing:1px">
                    🔴 RESISTANCE (Max CE OI)</div>
                <div style="font-size:20px;font-weight:700;color:#c0392b">
                    {int(mp.top_ce_oi_strike):,}</div>
                <div style="color:#8a96b0;font-size:10px">Calls ka wall</div>
            </div>
        </div>
        <div style="margin-top:10px;padding:8px 12px;background:#f8f9fd;
                    border-radius:6px;display:flex;align-items:center;gap:10px">
            <span style="font-size:15px">🧲</span>
            <span style="color:#3a4a6b;font-size:12px;font-weight:600">
                Pull Strength: <span style="color:{pull_col}">{pull_str}</span>
                &nbsp;—&nbsp;
            </span>
            <span style="color:#6b7a99;font-size:11px">{pull_note}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Pain Chart ────────────────────────────────────────────────────────────
    if mp.strikes_pain and PLOTLY_OK:
        import plotly.graph_objects as go

        strikes = [int(s) for s, _ in mp.strikes_pain]
        pains   = [p for _, p in mp.strikes_pain]
        min_pain = min(pains)

        # Bar colors: gold for max pain, light blue for others
        bar_colors = []
        for s, p in mp.strikes_pain:
            if s == mp.max_pain_strike:
                bar_colors.append("#b8860b")   # gold — max pain
            elif s == mp.top_ce_oi_strike:
                bar_colors.append("#c0392b")   # red — resistance
            elif s == mp.top_pe_oi_strike:
                bar_colors.append("#1b7a2e")   # green — support
            else:
                bar_colors.append("#b0bec5")   # neutral gray

        fig = go.Figure()

        fig.add_trace(go.Bar(
            x           = strikes,
            y           = pains,
            marker_color= bar_colors,
            text        = [f"{int(s):,}" if s == mp.max_pain_strike else ""
                           for s, _ in mp.strikes_pain],
            textposition= "outside",
            textfont    = dict(size=11, color="#b8860b", family="monospace"),
            hovertemplate=(
                "<b>Strike: %{x}</b><br>"
                "Total Writers' Payout: %{y:,.0f}<br>"
                "<extra></extra>"
            ),
            name="Pain",
        ))

        # Spot vertical line
        fig.add_vline(
            x          = mp.spot,
            line_dash  = "dash",
            line_color = "#1a56db",
            line_width = 2,
            annotation_text      = f"Spot {int(mp.spot):,}",
            annotation_font_size = 11,
            annotation_font_color= "#1a56db",
            annotation_position  = "top right",
        )

        # Max Pain vertical line (solid gold)
        fig.add_vline(
            x          = mp.max_pain_strike,
            line_dash  = "solid",
            line_color = "#b8860b",
            line_width = 2,
            annotation_text      = f"Max Pain {int(mp.max_pain_strike):,}",
            annotation_font_size = 11,
            annotation_font_color= "#b8860b",
            annotation_position  = "top left",
        )

        fig.update_layout(
            paper_bgcolor = "#ffffff",
            plot_bgcolor  = "#f8f9fd",
            font          = dict(color="#3a4a6b", size=10),
            xaxis         = dict(
                title     = "Strike Price",
                gridcolor = "#e0e4ef",
                tickformat= "d",
                dtick     = 100 if symbol == "NIFTY" else 200,
            ),
            yaxis         = dict(
                title     = "Total Writers' Payout (₹ OI units)",
                gridcolor = "#e0e4ef",
                tickformat= ".2s",
            ),
            height        = 360,
            margin        = dict(l=10, r=10, t=40, b=40),
            showlegend    = False,
            bargap        = 0.15,
        )

        st.plotly_chart(fig, use_container_width=True,
                        config={"displayModeBar": False})

        # Legend below chart
        st.markdown("""
        <div style="display:flex;gap:20px;font-size:11px;color:#6b7a99;
                    padding:6px 12px;background:#f0f3fa;border-radius:6px;
                    flex-wrap:wrap">
            <span>&#9646; <b style="color:#b8860b">Gold bar</b> = Max Pain (minimum payout)</span>
            <span>&#9646; <b style="color:#1b7a2e">Green bar</b> = Max PE OI (Support)</span>
            <span>&#9646; <b style="color:#c0392b">Red bar</b> = Max CE OI (Resistance)</span>
            <span>&#9646; <b style="color:#1a56db">Blue line</b> = Current Spot</span>
        </div>
        """, unsafe_allow_html=True)

    elif not PLOTLY_OK:
        st.info("Plotly install karo chart ke liye: `pip install plotly`")

    # ── How it works ─────────────────────────────────────────────────────────
    with st.expander("📖 Max Pain kya hai aur kaise use karein (click to expand)"):
        st.markdown("""
**Max Pain Theory:**
Option writers (sellers) control huge OI. Market has a tendency to expire near the strike
where maximum option buyers lose money — that's the **Max Pain strike**.

**Formula:**
```
For each candidate strike P:
  Pain = Σ [ max(P−K, 0) × CE_OI(K) ]  +  Σ [ max(K−P, 0) × PE_OI(K) ]
Max Pain = Strike P where Pain is MINIMUM
```

**How to use:**

| Scenario | Action |
|---|---|
| Spot < Max Pain + Pull Strong | Market may drift UP — favour CE buyers |
| Spot > Max Pain + Pull Strong | Market may drift DOWN — favour PE buyers |
| Spot ≈ Max Pain | Straddle/Strangle sell — range bound expected |
| Pull = WEAK (>4 days) | Ignore max pain — follow GEX + PCR instead |

**Key Rule:**
Max Pain is most reliable in the **last 2 days before expiry** (Wed-Thu for weekly NIFTY).
On Monday/Tuesday, treat it as one of many signals — not the primary one.

**Support & Resistance from OI:**
- **Max PE OI strike** = Strongest Put writing = institutional support floor
- **Max CE OI strike** = Strongest Call writing = institutional resistance ceiling
- Price tends to stay between these two strikes before expiry
        """)


# ══════════════════════════════════════════════════════════════════════════════
# GEX RENDER
# ══════════════════════════════════════════════════════════════════════════════
def render_gex(cache: dict):
    gex = cache.get("gex_data", {})
    if not gex:
        st.info("⏳ GEX calculating...")
        return

    total      = gex["total_gex"]
    color      = gex["regime_color"]
    regime     = gex["regime"]
    emoji      = gex["regime_emoji"]
    desc       = gex["regime_desc"]
    wall       = gex["gamma_wall"]
    flip       = gex["flip_level"]
    spot       = gex["spot"]
    strikes    = gex["gex_strikes"]

    # ── Header card ──────────────────────────────────────────────────────────
    st.markdown(f"""
    <div style="background:#f8f9fd;border:2px solid {color};border-radius:12px;
                padding:16px;margin-bottom:12px">
        <div style="display:flex;justify-content:space-between;align-items:center">
            <div>
                <span style="font-size:24px">{emoji}</span>
                <span style="font-size:20px;font-weight:bold;color:{color};
                             margin-left:8px">{regime}</span>
            </div>
            <div style="text-align:right">
                <div style="color:#6b7a99;font-size:11px">Net GEX (Cr)</div>
                <div style="font-size:24px;font-weight:bold;color:{color}">
                    {"+" if total >= 0 else ""}{total:.2f}
                </div>
            </div>
        </div>
        <div style="color:#6b7a99;font-size:12px;margin-top:8px">{desc}</div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;
                    gap:8px;margin-top:12px">
            <div style="background:#f0f3fa;border:1px solid #e0e4ef;border-radius:8px;padding:8px;
                         text-align:center">
                <div style="color:#6b7a99;font-size:10px">🧲 Gamma Wall</div>
                <div style="font-size:16px;font-weight:bold;color:#b8860b">
                    {wall:,}</div>
                <div style="color:#8a96b0;font-size:10px">Strongest magnet</div>
            </div>
            <div style="background:#f0f3fa;border:1px solid #e0e4ef;border-radius:8px;padding:8px;
                         text-align:center">
                <div style="color:#6b7a99;font-size:10px">🔄 Flip Level</div>
                <div style="font-size:16px;font-weight:bold;color:#1a56db">
                    {flip if flip else "—"}</div>
                <div style="color:#8a96b0;font-size:10px">GEX zero crossing</div>
            </div>
            <div style="background:#f0f3fa;border:1px solid #e0e4ef;border-radius:8px;padding:8px;
                         text-align:center">
                <div style="color:#6b7a99;font-size:10px">📍 Spot</div>
                <div style="font-size:16px;font-weight:bold;color:#1a1a2e">
                    {spot:,.0f}</div>
                <div style="color:#8a96b0;font-size:10px">
                    {"Above Wall" if spot > wall else "Below Wall"}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Per-strike GEX bar chart ──────────────────────────────────────────────
    if strikes:
        rows = []
        for s in sorted(strikes.keys()):
            d   = strikes[s]
            net = d["net"]
            bar_len  = min(int(abs(net) * 20), 20)
            bar      = ("█" * bar_len).ljust(20)
            is_wall  = (s == wall)
            rows.append({
                "STRIKE": f"★{s}" if is_wall else str(s),
                "CE GEX": f"+{d['ce_gex']:.3f}",
                "PE GEX": f"-{d['pe_gex']:.3f}",
                "NET":    f"{'+' if net >= 0 else ''}{net:.3f}",
            })
        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            height=280,
            hide_index=True,
        )

    # ── How to use ───────────────────────────────────────────────────────────
    with st.expander("📖 GEX kaise use karein"):
        st.markdown(f"""
        **Gamma Wall ({wall}):**
        Price is strongly attracted here. Expiry ke paas price
        yahan khinchti hai. Support/Resistance dono.

        **Flip Level ({flip if flip else 'N/A'}):**
        Agar price flip level se neeche gaye → VOLATILE zone.
        Agar upar rahe → Range-bound zone.

        **Current Regime: {regime}**
        {desc}

        **Trading Rule:**
        - RANGE BOUND → Iron Condor/Sell Strangle between walls
        - VOLATILE → Directional trade with PCR + OI Build signal
        """)


# ══════════════════════════════════════════════════════════════════════════════
# OI WALL DETECTOR — Support / Resistance levels from OI chain
# ══════════════════════════════════════════════════════════════════════════════
def _detect_oi_walls(oi_chain: list, spot: float, step: int) -> dict:
    """
    OI chain se market ki natural walls dhundho.

    Call Wall = Jis strike pe sabse zyada CE OI hai → Resistance
    Put Wall  = Jis strike pe sabse zyada PE OI hai → Support

    Returns:
        call_walls      : [(strike, oi_lakhs), ...] top 3, above ATM
        put_walls       : [(strike, oi_lakhs), ...] top 3, below ATM
        nearest_call    : nearest resistance above spot
        nearest_put     : nearest support below spot
        ce_warning      : human-readable resistance message
        pe_warning      : human-readable support message
        score_penalty   : negative int (if wall blocks target)
    """
    if not oi_chain or not spot:
        return {}

    atm = int(round(spot / step) * step)

    # Saari strikes ka CE + PE OI collect karo
    ce_data = {}  # strike → ce_oi
    pe_data = {}  # strike → pe_oi
    for row in oi_chain:
        s = int(row.strike)
        if row.ce_oi and row.ce_oi > 0:
            ce_data[s] = row.ce_oi
        if row.pe_oi and row.pe_oi > 0:
            pe_data[s] = row.pe_oi

    # Top 3 CE OI strikes at/above ATM (resistance)
    ce_above = {s: v for s, v in ce_data.items() if s >= atm}
    top_ce   = sorted(ce_above.items(), key=lambda x: x[1], reverse=True)[:3]
    top_ce   = sorted(top_ce, key=lambda x: x[0])   # display: low to high

    # Top 3 PE OI strikes at/below ATM (support)
    pe_below = {s: v for s, v in pe_data.items() if s <= atm}
    top_pe   = sorted(pe_below.items(), key=lambda x: x[1], reverse=True)[:3]
    top_pe   = sorted(top_pe, key=lambda x: x[0], reverse=True)  # display: high to low

    # Convert to lakhs for readability
    def to_l(oi): return round(oi / 100_000, 1)

    # Nearest call wall strictly above ATM
    ce_strictly_above = [(s, v) for s, v in ce_above.items() if s > atm]
    nearest_call = min(ce_strictly_above, key=lambda x: x[0]) if ce_strictly_above else None

    # Nearest put wall strictly below ATM
    pe_strictly_below = [(s, v) for s, v in pe_below.items() if s < atm]
    nearest_put  = max(pe_strictly_below, key=lambda x: x[0]) if pe_strictly_below else None

    ce_score_penalty = 0   # penalty applied to BUY CE path (CE resistance)
    pe_score_penalty = 0   # penalty applied to BUY PE path (PE support = blocks downside)
    ce_warning    = ""
    pe_warning    = ""

    # ── Call Wall — resistance above spot, penalises BUY CE only ─────────────
    if nearest_call:
        dist   = nearest_call[0] - atm
        oi_l   = to_l(nearest_call[1])
        strike = nearest_call[0]
        if dist <= step:
            ce_score_penalty -= 15
            ce_warning = f"🧱 Bahut badi CALL WALL {strike} pe ({oi_l}L OI) — Sirf {dist} pts door! Target block ho sakta hai"
        elif dist <= step * 2:
            ce_score_penalty -= 8
            ce_warning = f"⚠️ Call Wall: {strike} pe {oi_l}L OI — {dist} pts door, thodi resistance milegi"
        else:
            ce_warning = f"✅ Resistance {strike} pe ({oi_l}L OI) — {dist} pts door, abhi path clear hai"

    # ── Put Wall — support below spot, penalises BUY PE only ─────────────────
    # A large PUT wall means MMs will defend that level — price may bounce, hurting BUY PE.
    if nearest_put:
        dist   = atm - nearest_put[0]
        oi_l   = to_l(nearest_put[1])
        strike = nearest_put[0]
        if dist <= step:
            pe_score_penalty -= 15
            pe_warning = f"🛡️ Bahut bada PUT WALL {strike} pe ({oi_l}L OI) — Sirf {dist} pts neeche! Bounce possible, BUY PE risky"
        elif dist <= step * 2:
            pe_score_penalty -= 8
            pe_warning = f"⚠️ Put Wall: {strike} pe {oi_l}L OI — {dist} pts neeche, support strong"
        else:
            pe_warning = f"✅ Support {strike} pe ({oi_l}L OI) — {dist} pts neeche, bearish move possible"

    return {
        "call_walls":        [(s, to_l(v)) for s, v in top_ce],
        "put_walls":         [(s, to_l(v)) for s, v in top_pe],
        "nearest_call":      (nearest_call[0], to_l(nearest_call[1])) if nearest_call else None,
        "nearest_put":       (nearest_put[0],  to_l(nearest_put[1]))  if nearest_put  else None,
        "ce_warning":        ce_warning,
        "pe_warning":        pe_warning,
        "ce_score_penalty":  ce_score_penalty,
        "pe_score_penalty":  pe_score_penalty,
        "score_penalty":     ce_score_penalty,   # legacy key — kept for render compat
    }


# ══════════════════════════════════════════════════════════════════════════════
# TRADE SIGNAL ENGINE — Live data se automatic BUY/SELL/NO TRADE
# ══════════════════════════════════════════════════════════════════════════════
def generate_trade_signal(cache: dict, symbol: str) -> dict:
    """
    Smart Trade Signal Engine v4.0
    ─────────────────────────────────────────────────────────
    7 factors — confluence required (min 3 agree):
      1. PCR (value + trend combined, max ±15) — single source, no double-count
      2. OI Build — direction-aware CE/PE LTP comparison (±20)
      3. VIX level           (±10)
      4. IV Rank             (±10)
      5. GEX Regime + direction (±10) — gex_total sign validated
      6. Max Pain direction  (±8)
      7. Volume Profile POC  (±10)

    Signal flow:
      Iron Condor (sell_mode + iv_rank>50 + score≥15 + NOT strong directional)
      → NO TRADE (score < threshold or no confluence)
      → NO TRADE (range_bound_block or block_buying)
      → BUY CE / BUY PE
      → Iron Condor fallback (VIX≥25 blocks directional but sell conditions met)
    """
    from datetime import date, time as dtime
    import datetime as _dt

    sym_map = {
        "NIFTY":     "NSE:NIFTY 50",
        "BANKNIFTY": "NSE:NIFTY BANK",
        "FINNIFTY":  "NSE:NIFTY FIN SERVICE",
    }
    prices    = cache.get("prices",   {})
    oi_chain  = cache.get("oi_chain", [])
    pcr_data  = cache.get("pcr_data", {})
    iv_data   = cache.get("iv_data",  {})
    mp_result = cache.get("mp_result")
    gex_data  = cache.get("gex_data", {})
    vp_data   = cache.get("vp_data",  {})

    spot = prices.get(sym_map.get(symbol, ""), 0)
    vix  = prices.get("NSE:INDIA VIX", 0)

    if not spot:
        return {"signal": "NO TRADE", "reason": "Market data unavailable", "score": 0}

    # ── Market closed / holiday / no data check ──────────────────────────────
    mkt_status  = get_market_status()
    data_missing = (not oi_chain and not pcr_data and not mp_result)
    if mkt_status in ("HOLIDAY",):
        return {
            "signal":  "MARKET CLOSED",
            "reason":  "NSE Trading Holiday — no signals today.",
            "score":   0,
            "vix":     vix,
            "status":  mkt_status,
        }
    if mkt_status != "OPEN" and data_missing:
        return {
            "signal":  "MARKET CLOSED",
            "reason":  f"Market is {mkt_status} — live OI/PCR data not available.",
            "score":   0,
            "vix":     vix,
            "status":  mkt_status,
        }

    score     = 0
    step      = 50 if symbol == "NIFTY" else 100
    atm       = round(spot / step) * step
    lot       = get_lot_size(symbol)
    MAX_LOSS  = 3000   # ₹3000 max risk per trade

    factors      = {}
    bull_count   = 0   # how many factors are bullish
    bear_count   = 0   # how many factors are bearish

    # ── Time of day check ─────────────────────────────────────────────────────
    now_time     = _dt.datetime.now().time()
    opening_risk = dtime(9, 15) <= now_time <= dtime(9, 45)
    closing_risk = dtime(15, 15) <= now_time < dtime(15, 31)
    time_warning = ""
    if opening_risk:
        time_warning = "⚠️ 9:15-9:45 — High volatility window. Wait for 9:45 for cleaner signals."
    elif closing_risk:
        time_warning = "⚠️ Market closing soon (15:15–15:30) — avoid fresh entries."

    # ── Opening hard block (9:15–9:30) ───────────────────────────────────────
    # First 15 minutes: gap opens, spike reversals, fake breakouts — all 8 factors
    # read noise, not signal. Hard block prevents any entry in this window.
    if dtime(9, 15) <= now_time < dtime(9, 30) and get_market_status() == "OPEN":
        return {
            "signal":       "NO TRADE",
            "reason":       "9:15–9:30 Opening Spike — wait for price to settle (9:30+)",
            "score":        0,
            "factors":      {},
            "vix":          prices.get("NSE:INDIA VIX", 0),
            "pcr":          0,
            "build":        "⚪",
            "time_warning": "🚫 Hard block: 9:15–9:30 opening window. Re-enter at 9:30.",
            "is_expiry_day": False,
        }

    # ── Expiry day check ──────────────────────────────────────────────────────
    today         = date.today()
    expiry_str    = cache.get("expiry", "")
    is_expiry_day = False
    if expiry_str:
        _exp_date = None
        for _fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y", "%d%b%Y", "%d%B%Y", "%Y/%m/%d"):
            try:
                _exp_date = _dt.datetime.strptime(expiry_str.strip(), _fmt).date()
                break
            except ValueError:
                continue
        if _exp_date is not None:
            is_expiry_day = (today == _exp_date)
        else:
            logger.warning(f"Could not parse expiry date {expiry_str!r} — assuming expiry day (fail-safe)")
            is_expiry_day = True  # fail-safe: block option buying on unknown expiry format

    # ── 1. PCR — combined value + trend, capped at ±15 ───────────────────────
    # Merging both into one factor prevents PCR from dominating 66% of the threshold.
    # Base ±12 from value; trend nudges ±3 — total never exceeds ±15.
    pcr_value = 0
    pcr_info  = pcr_data.get(symbol)
    pcr_trend = "→"
    if pcr_info:
        r, trend = pcr_info
        pcr_value = r.pcr
        pcr_trend = trend

        if r.pcr >= 1.3:   pcr_score = 12
        elif r.pcr >= 1.0: pcr_score = 7
        elif r.pcr <= 0.7: pcr_score = -12
        elif r.pcr < 1.0:  pcr_score = -7
        else:               pcr_score = 0

        if trend == "▲":   pcr_score = min(15,  pcr_score + 3)
        elif trend == "▼": pcr_score = max(-15, pcr_score - 3)

        if pcr_score > 0:
            score += pcr_score; bull_count += 1
            _lbl   = "Strong Bullish" if pcr_score >= 12 else "Bullish"
            _col   = "#00c853"       if pcr_score >= 12 else "#69f0ae"
            factors["PCR"] = ("✅", f"{r.pcr:.2f} {trend}", f"{_lbl} (PCR+trend → {pcr_score:+})", _col)
        elif pcr_score < 0:
            score += pcr_score; bear_count += 1
            _lbl   = "Strong Bearish" if pcr_score <= -12 else "Bearish"
            _col   = "#ff1744"        if pcr_score <= -12 else "#ff6d00"
            factors["PCR"] = ("❌", f"{r.pcr:.2f} {trend}", f"{_lbl} (PCR+trend → {pcr_score:+})", _col)
        else:
            factors["PCR"] = ("⚪", f"{r.pcr:.2f} {trend}", "Neutral PCR", "#888")
    else:
        factors["PCR"] = ("⚪", "N/A", "No data", "#555")

    # ── 3. OI Build — direction-aware (±20) ──────────────────────────────────
    # CE OI up + CE LTP > PE LTP  → buyers entering  (bullish)
    # CE OI up + CE LTP < PE LTP  → call writers      (bearish — they collect premium)
    # PE OI up + PE LTP > CE LTP  → put buyers        (bearish)
    # PE OI up + PE LTP < CE LTP  → put writers       (bullish — they collect premium)
    atm_build  = "⚪"
    atm_ce_ltp = atm_pe_ltp = 0
    for row in oi_chain:
        if int(row.strike) == int(atm):      # exact ATM match only (H-03)
            atm_ce_ltp = row.ce_ltp or 0
            atm_pe_ltp = row.pe_ltp or 0
            total_oi_at_strike = (row.ce_oi or 0) + (row.pe_oi or 0)
            oi_threshold = max(300, min(8000, int(total_oi_at_strike * 0.06)))

            ce_chg = row.ce_oi_chg or 0
            pe_chg = row.pe_oi_chg or 0

            if ce_chg > oi_threshold:
                if atm_ce_ltp > 0 and atm_pe_ltp > 0:
                    # CE LTP rising relative to PE LTP → call buyers (bullish)
                    # CE LTP falling relative to PE LTP → call writers (bearish)
                    # 0.85 threshold (not 0.90) — accounts for natural put-call skew
                    # where CE options are structurally cheaper than PE of same strike
                    if atm_ce_ltp >= atm_pe_ltp * 0.85:
                        atm_build = "FL"; score += 15; bull_count += 1
                        factors["OI Build"] = ("✅", f"CE OI +{ce_chg:,} | CE₹{atm_ce_ltp:.0f} PE₹{atm_pe_ltp:.0f}",
                                               "Fresh Call Buy — Buyers entering (bullish)", "#69f0ae")
                    else:
                        atm_build = "CW"; score -= 10; bear_count += 1
                        factors["OI Build"] = ("❌", f"CE OI +{ce_chg:,} | CE₹{atm_ce_ltp:.0f} < PE₹{atm_pe_ltp:.0f}",
                                               "Call Writing — Sellers entering at resistance (bearish)", "#ff6d00")
                elif atm_ce_ltp > 0:
                    atm_build = "FL"; score += 10; bull_count += 1
                    factors["OI Build"] = ("✅", f"CE OI +{ce_chg:,} | CE₹{atm_ce_ltp:.0f}",
                                           "CE OI Build — likely bullish (PE LTP unavailable)", "#69f0ae")
                else:
                    factors["OI Build"] = ("⚪", f"CE OI +{ce_chg:,}",
                                           "CE OI up but no LTP data — inconclusive", "#888")

            elif pe_chg > oi_threshold:
                if atm_pe_ltp > 0 and atm_ce_ltp > 0:
                    if atm_pe_ltp >= atm_ce_ltp * 0.9:
                        atm_build = "FS"; score -= 20; bear_count += 1
                        factors["OI Build"] = ("❌", f"PE OI +{pe_chg:,} | PE₹{atm_pe_ltp:.0f} CE₹{atm_ce_ltp:.0f}",
                                               "Fresh Put Buy — Bears entering (bearish)", "#ff1744")
                    else:
                        atm_build = "PW"; score += 10; bull_count += 1
                        factors["OI Build"] = ("✅", f"PE OI +{pe_chg:,} | PE₹{atm_pe_ltp:.0f} < CE₹{atm_ce_ltp:.0f}",
                                               "Put Writing — Sellers at support (bullish)", "#69f0ae")
                elif atm_pe_ltp > 0:
                    atm_build = "FS"; score -= 15; bear_count += 1
                    factors["OI Build"] = ("❌", f"PE OI +{pe_chg:,} | PE₹{atm_pe_ltp:.0f}",
                                           "PE OI building — likely bearish (CE LTP unavailable)", "#ff6d00")
                else:
                    # No LTP data — can't determine direction (same as CE case)
                    factors["OI Build"] = ("⚪", f"PE OI +{pe_chg:,}",
                                           "PE OI up but no LTP data — inconclusive", "#888")

            elif ce_chg < -oi_threshold:
                atm_build = "LU"; score -= 10; bear_count += 1
                factors["OI Build"] = ("⚠️", f"CE OI {ce_chg:,}",
                                       "Long Unwind — Bulls exiting", "#ff6d00")

            elif pe_chg < -oi_threshold:
                atm_build = "SC"; score += 10; bull_count += 1
                factors["OI Build"] = ("✅", f"PE OI {pe_chg:,}",
                                       "Short Cover — Bears exiting", "#69f0ae")
            else:
                factors["OI Build"] = ("⚪", f"Threshold {oi_threshold:,} not breached",
                                       "No significant OI change", "#888")
            break

    if "OI Build" not in factors:
        factors["OI Build"] = ("⚪", "No data", "OI chain not loaded", "#555")

    # ── 4. VIX (±10) ─────────────────────────────────────────────────────────
    sell_mode        = False
    range_bound_block = False   # GEX range-bound → block ALL directional entries
    block_buying     = False    # VIX 25+ → block option buying (IV crush risk)
    if vix > 0:
        if vix < 13:
            score += 10; bull_count += 1
            factors["VIX"] = ("✅", f"{vix:.1f}", "Very low fear — Buy confidently", "#00c853")
        elif vix < 17:
            score += 5; bull_count += 1
            factors["VIX"] = ("✅", f"{vix:.1f}", "Low fear — Buy ok", "#69f0ae")
        elif vix < 20:
            factors["VIX"] = ("⚪", f"{vix:.1f}", "Moderate — Neutral", "#ffd740")
        elif vix < 25:
            # BUG FIX: was missing bear_count increment — VIX 20-25 IS bearish
            score -= 10; sell_mode = True; bear_count += 1
            factors["VIX"] = ("❌", f"{vix:.1f}", "High fear — Bearish / Sell premium", "#ff6d00")
        else:
            # VIX 25+ = extreme fear: IV is so elevated that option buying leads to
            # IV crush even if direction is correct. Hard block on buying.
            score -= 10; sell_mode = True; bear_count += 1; block_buying = True
            factors["VIX"] = ("🚫", f"{vix:.1f}",
                              f"Extreme fear (VIX 25+) — IV crush risk. BUY blocked. Only sell premium.",
                              "#ff1744")
    else:
        factors["VIX"] = ("⚪", "N/A", "No data", "#555")

    # ── 5. IV Rank (±10) ─────────────────────────────────────────────────────
    iv_rank = iv_data.get("iv_rank", 50)
    if iv_rank > 70:
        if vix > 20: sell_mode = True   # block buying only when VIX also elevated
        if vix > 20: score -= 5; bear_count += 1   # penalise direction only in expensive+volatile env
        _iv_desc = "Very expensive + VIX high — sell premium, avoid buying" if vix > 20 else "Very expensive IV — but VIX low, buying not blocked"
        factors["IV Rank"] = ("⚠️", f"{iv_rank:.0f}%", _iv_desc, "#ff6d00")
    elif iv_rank > 55:
        if vix > 20: sell_mode = True
        if vix > 20: score -= 3; bear_count += 1
        _iv_desc2 = "Elevated IV + VIX high — premium selling favoured" if vix > 20 else "Elevated IV — VIX low, buying still ok"
        factors["IV Rank"] = ("⚠️", f"{iv_rank:.0f}%", _iv_desc2, "#ffd740")
    elif iv_rank < 20:
        score += 10; bull_count += 1
        factors["IV Rank"] = ("✅", f"{iv_rank:.0f}%", "Very cheap — Buy options now", "#00c853")
    elif iv_rank < 35:
        score += 5; bull_count += 1
        factors["IV Rank"] = ("✅", f"{iv_rank:.0f}%", "Cheap — Buying ok", "#69f0ae")
    else:
        factors["IV Rank"] = ("⚪", f"{iv_rank:.0f}%", "Normal IV — Neutral", "#888")

    # ── 6. GEX Regime (±10) ──────────────────────────────────────────────────
    gex_regime = gex_data.get("regime",    "NEUTRAL")
    gex_total  = gex_data.get("total_gex", 0)
    gamma_wall = gex_data.get("gamma_wall") or None   # fix: don't default to ATM (misleading label)
    flip_level = gex_data.get("flip_level", None)

    if gex_regime == "RANGE BOUND":
        # MMs are actively gamma-hedging to suppress big moves — directional entries fail here.
        score -= 10; sell_mode = True; range_bound_block = True
        factors["GEX"] = ("📦", f"{gex_total:+.1f}Cr",
                          "RANGE BOUND — MM suppressing moves. BUY CE/PE blocked.", "#ff6d00")
    elif gex_regime == "VOLATILE / TRENDING":
        # gex_total > 0 → MMs long gamma (bullish tilt), < 0 → short gamma (bearish tilt).
        _gex_abs  = abs(gex_total)
        score_dir = 1 if score >= 0 else -1
        gex_dir   = 1 if gex_total >= 0 else -1
        if _gex_abs >= 300 and score != 0:
            # Very strong GEX — amplify in whatever direction other factors indicate.
            # At this magnitude MMs are forced to hedge → price moves HARD in signal direction.
            bonus = score_dir * (15 if _gex_abs >= 400 else 10)
            score += bonus
            if bonus > 0: bull_count += 1
            else:         bear_count += 1
            factors["GEX"] = ("✅", f"{gex_total:+.1f}Cr",
                              f"Strong GEX momentum ({_gex_abs:.0f}Cr) — amplifying signal", "#00c853")
        elif abs(score) >= 15:
            if gex_dir == score_dir:
                bonus = gex_dir * 10
                score += bonus
                if bonus > 0: bull_count += 1
                else:         bear_count += 1
                factors["GEX"] = ("✅", f"{gex_total:+.1f}Cr", "Trending — GEX confirms direction", "#00c853")
            else:
                factors["GEX"] = ("⚠️", f"{gex_total:+.1f}Cr", "Trending but GEX opposes signal — reduce size", "#ffd740")
        else:
            factors["GEX"] = ("⚪", f"{gex_total:+.1f}Cr", "Trending — but signal too weak to amplify", "#888")
    else:
        factors["GEX"] = ("⚪", f"{gex_total:+.1f}Cr", "Neutral GEX — No strong push", "#888")

    # ── 7. Max Pain Direction (±8) — FIXED ───────────────────────────────────
    top_ce_oi = mp_result.top_ce_oi_strike if mp_result else int(atm + step * 4)
    top_pe_oi = mp_result.top_pe_oi_strike if mp_result else int(atm - step * 4)
    mp_strike = mp_result.max_pain_strike  if mp_result else atm

    if mp_result and spot:
        dist_pct = (mp_strike - spot) / spot * 100
        if dist_pct > 0.5:          # Spot below max pain → pull UP
            score += 8; bull_count += 1
            factors["Max Pain"] = ("✅", f"MP {int(mp_strike)} ▲{dist_pct:.1f}%",
                                   "Spot below Max Pain — price may drift UP", "#00c853")
        elif dist_pct < -0.5:       # Spot above max pain → pull DOWN
            score -= 8; bear_count += 1
            factors["Max Pain"] = ("❌", f"MP {int(mp_strike)} ▼{abs(dist_pct):.1f}%",
                                   "Spot above Max Pain — price may drift DOWN", "#ff1744")
        else:
            factors["Max Pain"] = ("⚪", f"MP {int(mp_strike)} ≈ Spot",
                                   "Near max pain — balanced, no pull", "#888")
    else:
        factors["Max Pain"] = ("⚪", "N/A", "Max pain not available", "#555")

    # ── 8. Volume Profile POC (±10) ──────────────────────────────────────────
    poc_level = vp_data.get("poc")
    vp_step   = vp_data.get("step", step)
    if poc_level and spot:
        poc_dist = spot - poc_level
        if poc_dist > vp_step:
            score += 10; bull_count += 1
            factors["Vol POC"] = ("✅", f"POC {int(poc_level)} | +{poc_dist:.0f}pts",
                                  "Price above POC — Bullish structure", "#00c853")
        elif poc_dist < -vp_step:
            score -= 10; bear_count += 1
            factors["Vol POC"] = ("❌", f"POC {int(poc_level)} | {poc_dist:.0f}pts",
                                  "Price below POC — Bearish structure", "#ff1744")
        else:
            factors["Vol POC"] = ("⚪", f"POC {int(poc_level)} ↔ AT POC",
                                  "At strongest S/R — wait for breakout", "#ffd740")
    else:
        factors["Vol POC"] = ("⚪", "N/A", "VP loading...", "#555")

    # ── OI Wall Detection — directional penalties ─────────────────────────────
    oi_walls = _detect_oi_walls(oi_chain, spot, step)
    if oi_walls:
        if score > 0:
            ce_pen  = oi_walls.get("ce_score_penalty", 0)
            # Strong GEX momentum likely breaks walls — reduce/eliminate penalty
            if abs(gex_total) >= 400 and gex_regime == "VOLATILE / TRENDING":
                ce_pen = 0
            elif gex_regime == "VOLATILE / TRENDING" and ce_pen <= -15:
                ce_pen = -8
            score   = max(0, score + ce_pen)
            ce_warn = oi_walls.get("ce_warning", "")
            if ce_pen < -10:
                factors["OI Wall"] = ("🧱", ce_warn, "Strong resistance — target may get blocked", "#ff6d00")
            elif ce_pen < 0:
                factors["OI Wall"] = ("⚠️", ce_warn, "Resistance present — reduce size", "#ffd740")
            elif oi_walls.get("nearest_call"):
                factors["OI Wall"] = ("✅", ce_warn, "Path clear above", "#00c853")
        elif score < 0:
            pe_pen  = oi_walls.get("pe_score_penalty", 0)   # pe_pen is ≤ 0 (e.g. -15)
            # Symmetric GEX override for PE path — same logic as CE
            if abs(gex_total) >= 400 and gex_regime == "VOLATILE / TRENDING":
                pe_pen = 0
            elif gex_regime == "VOLATILE / TRENDING" and pe_pen <= -15:
                pe_pen = -8
            score   = min(0, score + abs(pe_pen))            # reduce bearish magnitude when PUT wall blocks path
            pe_warn = oi_walls.get("pe_warning", "")
            if pe_pen < -10:
                factors["OI Wall"] = ("🛡️", pe_warn, "Strong PUT support — bounce likely, BUY PE risky", "#ff6d00")
            elif pe_pen < 0:
                factors["OI Wall"] = ("⚠️", pe_warn, "PUT support nearby — monitor for breakdown", "#ffd740")
            elif oi_walls.get("nearest_put"):
                factors["OI Wall"] = ("✅", pe_warn, "Path clear below", "#00c853")

    abs_score = abs(score)

    # ── Adaptive thresholds — based on how much real data is available ────────
    # When PCR/OI/MaxPain/IV APIs fail, fewer factors contribute.
    # Requiring 3/8 confluence from 2-3 working factors is impossible → no signal ever.
    # Solution: count real data sources, lower gate proportionally.
    _data_count = sum([
        bool(pcr_data.get(symbol)),  # PCR real
        bool(oi_chain),              # OI chain loaded
        bool(mp_result),             # Max Pain available
        bool(gex_data),              # GEX calculated
        bool(iv_data),               # IV calculated (not default)
        vix > 0,                     # VIX available
        bool(vp_data.get("poc")),    # Volume Profile loaded
    ])
    if _data_count >= 5:
        _need_score, _need_confluence = 35, 4   # Full data — strict gate (raised from 3→4)
    elif _data_count >= 3:
        _need_score, _need_confluence = 28, 3   # Partial data — moderate gate (raised from 2→3)
    else:
        _need_score, _need_confluence = 22, 2   # Poor data — relaxed gate
    # Strong GEX overrides → MMs forced to hedge = price WILL move, relax threshold
    if abs(gex_total) >= 400 and gex_regime == "VOLATILE / TRENDING":
        _need_score = min(_need_score, 28)

    # ── Confluence Gate ───────────────────────────────────────────────────────
    _total_factors  = len(factors)
    _bull_factors   = sum(1 for v in factors.values() if v[0] in ("✅",))
    _bear_factors   = sum(1 for v in factors.values() if v[0] in ("❌", "🚫", "📦"))
    if score > 0:
        confluence_ok  = _bull_factors >= _need_confluence
        confluence_msg = f"{_bull_factors}/{_total_factors} bullish factors"
    elif score < 0:
        confluence_ok  = _bear_factors >= _need_confluence
        confluence_msg = f"{_bear_factors}/{_total_factors} bearish factors"
    else:
        confluence_ok  = False
        confluence_msg = f"0/{_total_factors}"

    # ── Expiry Day — no buying ─────────────────────────────────────────────────
    if is_expiry_day:
        sell_mode   = True
        block_buying = True   # expiry = theta crush — block directional buying regardless of iv_rank
        factors["⏰ Expiry"] = ("⚠️", "TODAY IS EXPIRY",
                                "DO NOT buy options — theta crushes fast. Only sell.", "#ff6d00")

    # ── Smart Strike Selection for BUY ────────────────────────────────────────
    def _pick_strike_and_ltp(direction: str):
        chosen = atm
        reason = "ATM strike (safest)"

        # Very strong signal + cheap IV → 1 OTM
        if abs_score >= 60 and iv_rank < 25 and vix < 16:
            chosen = atm + step if direction == "CE" else atm - step
            reason = f"1 OTM — Very strong signal + cheap IV ({iv_rank:.0f}%)"

        # High VIX or expiry day → ATM only
        elif vix > 20 or is_expiry_day:
            chosen = atm
            reason = f"ATM — {'VIX high' if vix > 20 else 'Expiry day'}, staying safe"

        # Near gamma wall — only use if wall is on the correct side of ATM (H-05)
        elif gamma_wall:
            wall_ok = (direction == "CE" and gamma_wall > atm and abs(atm - gamma_wall) <= step * 2) or \
                      (direction == "PE" and gamma_wall < atm and abs(atm - gamma_wall) <= step * 2)
            if wall_ok:
                chosen = int(gamma_wall)
                reason = f"Gamma Wall {int(gamma_wall)} — strongest magnetic level"

        ltp = 0
        for row in oi_chain:
            if int(row.strike) == chosen:
                ltp = row.ce_ltp if direction == "CE" else row.pe_ltp
                break
        if ltp <= 0:
            ltp = round(spot * 0.003)

        # ── Greeks (Delta) filter — block deep OTM entries ──────────────────────
        if chosen != atm:
            try:
                tte   = max(tte_years(expiry_str), 0.001)
                sigma = max(iv_data.get("atm_iv", 0.0), vix, 8.0) / 100.0
                g     = calc_greeks(spot, chosen, tte, sigma, direction)
                if g is not None and abs(g.delta) < 0.15:
                    chosen = atm
                    reason = f"ATM fallback — delta {abs(g.delta):.2f} too low (deep OTM, theta risk)"
                    ltp = 0
                    for row in oi_chain:
                        if int(row.strike) == atm:
                            ltp = row.ce_ltp if direction == "CE" else row.pe_ltp
                            break
                    if ltp <= 0:
                        ltp = round(spot * 0.003)
            except Exception:
                pass  # never block signal due to greeks error

        # ── Minimum premium guard — illiquid strikes skipped (L-01) ─────────────
        min_prem = 15 if symbol == "NIFTY" else 25   # raised from 5/20/35
        if ltp < min_prem:
            if chosen != atm:
                chosen = atm
                reason = f"ATM fallback — OTM premium ₹{ltp:.0f} too thin (min ₹{min_prem})"
                ltp = 0
                for row in oi_chain:
                    if int(row.strike) == atm:
                        ltp = row.ce_ltp if direction == "CE" else row.pe_ltp
                        break
                if ltp <= 0:
                    ltp = round(spot * 0.003)
            if ltp < min_prem:
                return int(chosen), 0, f"No liquid premium at ATM ₹{ltp:.0f} — skip signal"

        return int(chosen), ltp, reason

    # ── Dynamic Target/SL based on VIX ───────────────────────────────────────
    if vix < 15:
        gain_mult, sl_mult = 1.50, 0.70
    elif vix < 20:
        gain_mult, sl_mult = 1.42, 0.72
    else:
        gain_mult, sl_mult = 1.35, 0.65

    # ── Helper to build Iron Condor return dict ───────────────────────────────
    def _iron_condor_signal():
        sell_ce = int(top_ce_oi)
        sell_pe = int(top_pe_oi) - step     # L-02: one step below support, not at it

        # Gamma wall adjust — sell CE above wall if wall is above ATM
        if gamma_wall and gamma_wall > atm and gamma_wall > sell_ce:
            sell_ce = int(gamma_wall) + step

        ce_prem = pe_prem = 0
        for row in oi_chain:
            if int(row.strike) == sell_ce: ce_prem = row.ce_ltp or 0
            if int(row.strike) == sell_pe: pe_prem = row.pe_ltp or 0

        total_prem   = ce_prem + pe_prem
        if total_prem < 1:
            return {"signal": "NO TRADE", "reason": "Iron Condor — LTP unavailable for selected strikes",
                    "score": abs_score, "factors": factors, "vix": vix, "pcr": 0, "iv_rank": iv_rank,
                    "confluence": confluence_msg, "oi_walls": oi_walls}
        max_profit_r = round(total_prem * lot)
        sl_premium   = round(total_prem * 1.5)
        return {
            "signal":        "SELL — Iron Condor",
            "sell_ce":       sell_ce,
            "sell_pe":       sell_pe,
            "ce_prem":       ce_prem,
            "pe_prem":       pe_prem,
            "total_prem":    round(total_prem, 1),
            "max_profit_r":  max_profit_r,
            "sl_premium":    sl_premium,
            "sl_rule":       f"Exit if either side crosses ₹{sl_premium:.0f}",
            "score":         min(abs_score + 20, 100),
            "confluence":    confluence_msg,
            "factors":       factors,
            "vix":           vix,
            "pcr":           pcr_value,
            "iv_rank":       iv_rank,
            "timeframe":     "Weekly / Swing",
            "gamma_wall":    gamma_wall,
            "flip_level":    flip_level,
            "strike_reason": f"CE Resistance: {sell_ce} | PE Support: {sell_pe}",
            "time_warning":  time_warning,
            "is_expiry_day": is_expiry_day,
        }

    # ── C-01: Iron Condor — fires BEFORE directional gate ────────────────────
    # Triggers when score is modest (not strong enough for directional) but
    # selling conditions are favourable.  Has its own lower threshold = 15.
    # strong_directional flag ensures condor doesn't override a clear BUY CE/PE.
    #
    # DATA QUALITY GATE: Iron Condor requires real OI + market data.
    # Without OI chain, strike selection falls back to dummy atm±4*step levels.
    # Without PCR/MaxPain, we have no confirmation of range-bound sentiment.
    # Firing Iron Condor on partial/failed API data = fabricated signal.
    _ic_data_ok = (
        bool(oi_chain)                          # real OI data loaded
        and (bool(pcr_data.get(symbol)) or bool(mp_result))  # PCR or MaxPain
    )
    CONDOR_MIN_SCORE = 15
    _strong_directional = (
        abs_score >= _need_score
        and confluence_ok
        and not range_bound_block
        and not block_buying
    )
    if sell_mode and iv_rank > 50 and abs_score >= CONDOR_MIN_SCORE and not _strong_directional and _ic_data_ok:
        return _iron_condor_signal()

    # ── NO TRADE — insufficient score or confluence for directional ───────────
    if abs_score < _need_score or not confluence_ok:
        reason = (f"Score {abs_score} < {_need_score}"
                  if abs_score < _need_score
                  else f"Only {confluence_msg} — need {_need_confluence}+ to confirm")
        return {
            "signal":        "NO TRADE",
            "reason":        reason,
            "confluence":    confluence_msg,
            "score":         abs_score,
            "factors":       factors,
            "vix":           vix,
            "pcr":           pcr_value,
            "build":         atm_build,
            "time_warning":  time_warning,
            "is_expiry_day": is_expiry_day,
            "oi_walls":      oi_walls,
        }

    # ── NO TRADE — directional blocked by risk guards ─────────────────────────
    if range_bound_block or block_buying:
        _block_reason = ("GEX: Market is RANGE BOUND — MMs suppressing directional moves"
                         if range_bound_block
                         else f"VIX {vix:.1f} ≥ 25 — Extreme IV, buying options risks IV crush")
        return {
            "signal":        "NO TRADE",
            "reason":        _block_reason,
            "confluence":    confluence_msg,
            "score":         abs_score,
            "factors":       factors,
            "vix":           vix,
            "pcr":           pcr_value,
            "build":         atm_build,
            "time_warning":  time_warning,
            "is_expiry_day": is_expiry_day,
            "oi_walls":      oi_walls,
        }

    # ── Time Window Filter — only best intraday windows ──────────────────────
    # 9:45–11:15 : ORB confirmed, institutions active, clean signals
    # 13:30–14:30: Post-lunch directional move, before closing noise
    # Outside these windows → downgrade to NO TRADE for directional signals
    _best_window = (
        dtime(9, 45)  <= now_time <= dtime(11, 15) or
        dtime(13, 30) <= now_time <= dtime(14, 30)
    )
    if not _best_window and get_market_status() == "OPEN" and not data_missing:
        if dtime(9, 30) <= now_time < dtime(9, 45):
            time_warning = (time_warning or "") + "  ⏳ 9:30–9:45: ORB forming — wait for 9:45 breakout confirmation."
        elif dtime(11, 15) < now_time < dtime(13, 30):
            time_warning = (time_warning or "") + "  😴 11:15–13:30: Midday chop zone — low reliability window."
        elif now_time > dtime(14, 30):
            time_warning = (time_warning or "") + "  🔔 Post 14:30: Closing positions — avoid fresh directional entries."
        return {
            "signal":        "NO TRADE",
            "reason":        f"Outside best signal window (9:45–11:15 or 13:30–14:30). Current: {now_time.strftime('%H:%M')}",
            "confluence":    confluence_msg,
            "score":         abs_score,
            "factors":       factors,
            "vix":           vix,
            "pcr":           pcr_value,
            "build":         atm_build,
            "time_warning":  time_warning,
            "is_expiry_day": is_expiry_day,
            "oi_walls":      oi_walls,
        }

    # ── Momentum Confirmation — price must be on the correct side of Volume POC ──
    # vp_data contains: poc, vah, val, step — no open_price key available.
    # POC = price level with highest traded volume; spot > POC = bullish control.
    _poc = vp_data.get("poc", 0)
    _momentum_ok = True
    if _poc and spot:
        _poc_dist_pct = (spot - _poc) / _poc * 100
        if score >= _need_score and spot < _poc:
            _momentum_ok = False
            factors["Momentum"] = ("❌", f"Spot ₹{spot:,.0f} < POC ₹{_poc:,.0f} ({_poc_dist_pct:+.2f}%)",
                                   "Price BELOW volume POC — bears in control, BUY CE risky", "#ff6d00")
        elif score <= -_need_score and spot > _poc:
            _momentum_ok = False
            factors["Momentum"] = ("❌", f"Spot ₹{spot:,.0f} > POC ₹{_poc:,.0f} ({_poc_dist_pct:+.2f}%)",
                                   "Price ABOVE volume POC — bulls in control, BUY PE risky", "#ff6d00")
        elif score >= _need_score:
            factors["Momentum"] = ("✅", f"Spot ₹{spot:,.0f} > POC ₹{_poc:,.0f} ({_poc_dist_pct:+.2f}%)",
                                   "Price above POC — momentum confirms BUY CE", "#00c853")
        elif score <= -_need_score:
            factors["Momentum"] = ("✅", f"Spot ₹{spot:,.0f} < POC ₹{_poc:,.0f} ({_poc_dist_pct:+.2f}%)",
                                   "Price below POC — momentum confirms BUY PE", "#00c853")

    if not _momentum_ok:
        return {
            "signal":        "NO TRADE",
            "reason":        "Momentum not confirming signal — price moving opposite to score direction",
            "confluence":    confluence_msg,
            "score":         abs_score,
            "factors":       factors,
            "vix":           vix,
            "pcr":           pcr_value,
            "build":         atm_build,
            "time_warning":  time_warning,
            "is_expiry_day": is_expiry_day,
            "oi_walls":      oi_walls,
        }

    # ── BUY CE ────────────────────────────────────────────────────────────────
    if score >= _need_score:
        strike, entry, strike_reason = _pick_strike_and_ltp("CE")
        if entry <= 0:   # illiquid — fall back to NO TRADE
            return {"signal": "NO TRADE", "reason": strike_reason,
                    "score": abs_score, "factors": factors,
                    "vix": vix, "pcr": pcr_value, "build": atm_build,
                    "time_warning": time_warning, "is_expiry_day": is_expiry_day,
                    "oi_walls": oi_walls}
        entry    = max(entry, 15)        # L-01: absolute floor
        target   = round(entry * gain_mult)
        sl       = round(entry * sl_mult)
        sl_pts   = entry - sl
        lots     = max(1, int(MAX_LOSS / (sl_pts * lot))) if sl_pts > 0 else 1
        gain_pct = round((gain_mult - 1) * 100)
        loss_pct = round((1 - sl_mult) * 100)
        return {
            "signal":        "BUY CE",
            "strike":        strike,
            "strike_reason": strike_reason,
            "entry":         entry,
            "target":        target,
            "sl":            sl,
            "gain_pct":      gain_pct,
            "loss_pct":      loss_pct,
            "lot_size":      lot,
            "lots":          lots,
            "max_loss":      round(sl_pts * lot * lots),
            "max_profit":    round((target - entry) * lot * lots),
            "score":         min(score, 100),
            "confluence":    confluence_msg,
            "factors":       factors,
            "vix":           vix,
            "pcr":           pcr_value,
            "build":         atm_build,
            "iv_rank":       iv_rank,
            "timeframe":     "Intraday",
            "gamma_wall":    gamma_wall,
            "flip_level":    flip_level,
            "oi_walls":      oi_walls,
            "time_warning":  time_warning,
            "is_expiry_day": is_expiry_day,
        }

    # ── BUY PE ────────────────────────────────────────────────────────────────
    if score <= -_need_score:
        strike, entry, strike_reason = _pick_strike_and_ltp("PE")
        if entry <= 0:
            return {"signal": "NO TRADE", "reason": strike_reason,
                    "score": abs_score, "factors": factors,
                    "vix": vix, "pcr": pcr_value, "build": atm_build,
                    "time_warning": time_warning, "is_expiry_day": is_expiry_day,
                    "oi_walls": oi_walls}
        entry    = max(entry, 15)        # L-01: absolute floor
        target   = round(entry * gain_mult)
        sl       = round(entry * sl_mult)
        sl_pts   = entry - sl
        lots     = max(1, int(MAX_LOSS / (sl_pts * lot))) if sl_pts > 0 else 1
        gain_pct = round((gain_mult - 1) * 100)
        loss_pct = round((1 - sl_mult) * 100)
        return {
            "signal":        "BUY PE",
            "strike":        strike,
            "strike_reason": strike_reason,
            "entry":         entry,
            "target":        target,
            "sl":            sl,
            "gain_pct":      gain_pct,
            "loss_pct":      loss_pct,
            "lot_size":      lot,
            "lots":          lots,
            "max_loss":      round(sl_pts * lot * lots),
            "max_profit":    round((target - entry) * lot * lots),
            "score":         min(abs_score, 100),
            "confluence":    confluence_msg,
            "factors":       factors,
            "vix":           vix,
            "pcr":           pcr_value,
            "build":         atm_build,
            "iv_rank":       iv_rank,
            "timeframe":     "Intraday",
            "gamma_wall":    gamma_wall,
            "flip_level":    flip_level,
            "oi_walls":      oi_walls,
            "time_warning":  time_warning,
            "is_expiry_day": is_expiry_day,
        }

    # ── Iron Condor fallback — strong sell_mode overrides directional ─────────
    # Handles: score=40 (directional) but VIX=26 (block_buying) blocks BUY CE/PE
    if sell_mode and iv_rank > 50:
        return _iron_condor_signal()

    return {"signal": "NO TRADE", "reason": "Inconclusive after all checks",
            "score": abs_score, "confluence": confluence_msg, "factors": factors,
            "oi_walls": oi_walls}


def render_volume_profile(cache: dict, symbol: str):
    """
    Volume Profile Panel — POC / VAH / VAL with interactive Plotly chart.
    Looks and works like a professional paid tool.
    """
    if not PLOTLY_OK:
        st.warning("⚠️ plotly install karo:  `pip install plotly`")
        return

    # ── Session selector ──────────────────────────────────────────────────────
    cur_session = st.session_state.get("vp_session", "Today")
    c1, c2, c3, c4 = st.columns([4, 1, 1, 1])
    with c1:
        st.markdown(
            "<span style='color:#7fb3f5;font-size:13px;font-weight:bold'>"
            "Session:</span>", unsafe_allow_html=True
        )
    for label, col in [("Today", c2), ("Weekly", c3), ("Monthly", c4)]:
        with col:
            btn_type = "primary" if cur_session == label else "secondary"
            if st.button(label, key=f"vp_{label.lower()}", type=btn_type,
                         use_container_width=True):
                st.session_state["vp_session"] = label
                st.rerun()

    # ── Data ─────────────────────────────────────────────────────────────────
    vp = cache.get("vp_data", {})

    # If session was just changed, cached data is stale — refetch
    if not vp or vp.get("session") != cur_session:
        with st.spinner(f"📊 Loading {cur_session} Volume Profile..."):
            try:
                kite    = st.session_state["kite"]
                candles = kite.get_vp_candles(symbol, cur_session)
                vp      = _calc_volume_profile(symbol, candles)
                vp["session"] = cur_session
                cache["vp_data"] = vp
            except Exception as exc:
                st.error(f"VP data fetch failed: {exc}")
                return

    if not vp or "poc" not in vp:
        st.info("⏳ Volume Profile data loading... Market open ke baad dikhega.")
        return

    poc = vp["poc"]
    vah = vp["vah"]
    val = vp["val"]
    step_sz = vp.get("step", 10)

    # ── Current spot ──────────────────────────────────────────────────────────
    sym_map = {
        "NIFTY":     "NSE:NIFTY 50",
        "BANKNIFTY": "NSE:NIFTY BANK",
        "FINNIFTY":  "NSE:NIFTY FIN SERVICE",
    }
    spot = cache.get("prices", {}).get(sym_map.get(symbol, ""), 0)

    # ── VP Signal ─────────────────────────────────────────────────────────────
    if not spot:
        vp_sig = ("NO SPOT ⚪", "#555555",
                  "Live price unavailable — market closed ya data loading")
    elif spot > poc + step_sz:
        vp_sig = ("BULLISH ▲", "#00c853",
                  f"Spot {spot:.0f} is ABOVE POC {poc} — Institutional support below, upside bias")
    elif spot < poc - step_sz:
        vp_sig = ("BEARISH ▼", "#ff1744",
                  f"Spot {spot:.0f} is BELOW POC {poc} — Institutional resistance above, downside bias")
    else:
        vp_sig = ("AT POC ↔", "#ffd740",
                  f"Spot {spot:.0f} is AT POC {poc} — Strongest S/R — watch breakout direction")

    # ── Summary cards ─────────────────────────────────────────────────────────
    total_vol_str = (f"{vp['total_volume']/1e7:.1f}Cr"
                     if vp['total_volume'] > 1e7
                     else f"{vp['total_volume']/1e5:.1f}L")
    spot_str = f"{spot:.0f}" if spot else "—"

    st.markdown(f"""
    <div style="display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin:10px 0 16px 0">
        <div style="background:#fffbf0;border-top:3px solid #b8860b;
                    border-radius:8px;padding:10px;text-align:center">
            <div style="color:#6b7a99;font-size:10px;letter-spacing:1px">POC</div>
            <div style="color:#b8860b;font-size:20px;font-weight:bold">{poc}</div>
            <div style="color:#8a96b0;font-size:10px">Point of Control</div>
            <div style="color:#6b7a99;font-size:10px">{vp['poc_volume_pct']}% volume</div>
        </div>
        <div style="background:#f0f8ff;border-top:3px solid #1a56db;
                    border-radius:8px;padding:10px;text-align:center">
            <div style="color:#6b7a99;font-size:10px;letter-spacing:1px">VAH</div>
            <div style="color:#1a56db;font-size:20px;font-weight:bold">{vah}</div>
            <div style="color:#8a96b0;font-size:10px">Value Area High</div>
            <div style="color:#6b7a99;font-size:10px">Upper boundary</div>
        </div>
        <div style="background:#f0f8ff;border-top:3px solid #1a56db;
                    border-radius:8px;padding:10px;text-align:center">
            <div style="color:#6b7a99;font-size:10px;letter-spacing:1px">VAL</div>
            <div style="color:#1a56db;font-size:20px;font-weight:bold">{val}</div>
            <div style="color:#8a96b0;font-size:10px">Value Area Low</div>
            <div style="color:#6b7a99;font-size:10px">Lower boundary</div>
        </div>
        <div style="background:#f8f9fd;border-top:3px solid #3a4a6b;
                    border-radius:8px;padding:10px;text-align:center">
            <div style="color:#6b7a99;font-size:10px;letter-spacing:1px">SPOT</div>
            <div style="color:#1a1a2e;font-size:20px;font-weight:bold">{spot_str}</div>
            <div style="color:#8a96b0;font-size:10px">Current Price</div>
        </div>
        <div style="background:#f8f9fd;border-top:3px solid {vp_sig[1]};
                    border-radius:8px;padding:10px;text-align:center">
            <div style="color:#6b7a99;font-size:10px;letter-spacing:1px">SIGNAL</div>
            <div style="color:{vp_sig[1]};font-size:14px;font-weight:bold">{vp_sig[0]}</div>
            <div style="color:#8a96b0;font-size:10px">Price vs POC</div>
        </div>
        <div style="background:#f8f9fd;border-top:3px solid #c8d0e8;
                    border-radius:8px;padding:10px;text-align:center">
            <div style="color:#6b7a99;font-size:10px;letter-spacing:1px">VOLUME</div>
            <div style="color:#3a4a6b;font-size:18px;font-weight:bold">{total_vol_str}</div>
            <div style="color:#8a96b0;font-size:10px">{vp['candle_count']} candles</div>
            <div style="color:#8a96b0;font-size:10px">VA: {vp['va_volume_pct']}%</div>
        </div>
    </div>""", unsafe_allow_html=True)

    # ── Plotly Volume Profile Chart ───────────────────────────────────────────
    vol_map = vp["volume_at_price"]
    levels  = sorted(vol_map.keys())
    volumes = [vol_map[lv] for lv in levels]
    max_v   = max(volumes) if volumes else 1

    # Bar colors
    bar_colors = []
    for lv in levels:
        if lv == poc:
            bar_colors.append("rgba(255,215,0,0.9)")       # Gold — POC
        elif val <= lv <= vah:
            bar_colors.append("rgba(21,101,192,0.75)")     # Blue — Value Area
        else:
            bar_colors.append("rgba(45,53,80,0.7)")        # Dark gray — Outside VA

    # Volume labels — har bar pe volume number dikhega
    def _vol_label(v: float) -> str:
        if v >= 1_00_000:
            return f"{v/1_00_000:.1f}L"    # 1.2L
        elif v >= 1_000:
            return f"{v/1_000:.1f}K"        # 87.4K
        return str(int(v))

    vol_labels      = [_vol_label(v) for v in volumes]
    label_colors    = []
    label_positions = []
    for i, lv in enumerate(levels):
        bar_pct = volumes[i] / max_v       # fraction of widest bar
        if lv == poc:
            label_colors.append("#1a1a1a")  # dark on gold
            label_positions.append("inside")
        elif bar_pct > 0.35:               # wide bar → text inside
            label_colors.append("#1a1a2e")
            label_positions.append("inside")
        else:                              # narrow bar → text outside
            label_colors.append("#6b7a99")
            label_positions.append("outside")

    fig = go.Figure()

    # Volume bars — labels ON each bar
    fig.add_trace(go.Bar(
        x=volumes,
        y=levels,
        orientation="h",
        marker=dict(
            color=bar_colors,
            line=dict(width=0),
        ),
        text=vol_labels,
        textposition=label_positions,
        textfont=dict(size=9, color=label_colors, family="monospace"),
        hovertemplate=(
            "<b>Price: %{y}</b><br>"
            "Volume: %{x:,.0f} lots<br>"
            "<extra></extra>"
        ),
        name="Volume",
    ))

    # POC line — gold dashed
    fig.add_shape(type="line", x0=0, x1=1, xref="paper",
                  y0=poc, y1=poc,
                  line=dict(color="rgba(255,215,0,0.9)", width=2, dash="dash"))
    fig.add_annotation(x=1.01, xref="paper", y=poc,
                       text=f"<b>POC {poc}</b>", showarrow=False,
                       font=dict(color="#FFD700", size=11), xanchor="left")

    # VAH line — cyan dotted
    fig.add_shape(type="line", x0=0, x1=1, xref="paper",
                  y0=vah, y1=vah,
                  line=dict(color="rgba(0,200,255,0.7)", width=1.5, dash="dot"))
    fig.add_annotation(x=1.01, xref="paper", y=vah,
                       text=f"VAH {vah}", showarrow=False,
                       font=dict(color="#00C8FF", size=10), xanchor="left")

    # VAL line — cyan dotted
    fig.add_shape(type="line", x0=0, x1=1, xref="paper",
                  y0=val, y1=val,
                  line=dict(color="rgba(0,200,255,0.7)", width=1.5, dash="dot"))
    fig.add_annotation(x=1.01, xref="paper", y=val,
                       text=f"VAL {val}", showarrow=False,
                       font=dict(color="#00C8FF", size=10), xanchor="left")

    # Spot price line — dark solid
    if spot:
        fig.add_shape(type="line", x0=0, x1=1, xref="paper",
                      y0=spot, y1=spot,
                      line=dict(color="rgba(26,26,46,0.85)", width=2))
        fig.add_annotation(x=1.01, xref="paper", y=spot,
                           text=f"<b>▶ {spot:.0f}</b>", showarrow=False,
                           font=dict(color="#1a1a2e", size=11), xanchor="left")

    # Layout — Y-axis range must include spot price too
    y_min = min(levels) - step_sz * 3
    y_max = max(levels) + step_sz * 3
    if spot:
        y_min = min(y_min, spot - step_sz * 5)
        y_max = max(y_max, spot + step_sz * 5)
    visible_range = [y_min, y_max]
    fig.update_layout(
        paper_bgcolor="#ffffff",
        plot_bgcolor="#f8f9fd",
        font=dict(color="#3a4a6b", size=10, family="monospace"),
        xaxis=dict(
            title="Volume",
            gridcolor="#e0e4ef",
            showgrid=True,
            zeroline=False,
            tickformat=".2s",          # 1.2M, 450K etc.
        ),
        yaxis=dict(
            title="Price",
            gridcolor="#e0e4ef",
            showgrid=True,
            range=visible_range,
            dtick=step_sz * 5,
        ),
        height=520,
        margin=dict(l=65, r=110, t=20, b=45),
        showlegend=False,
        bargap=0.08,
    )

    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ── Signal interpretation box ─────────────────────────────────────────────
    st.markdown(f"""
    <div style="background:#f0f3fa;border-left:4px solid {vp_sig[1]};
                border-radius:6px;padding:10px 16px;margin-top:2px">
        <span style="color:{vp_sig[1]};font-weight:bold;font-size:13px">
            {vp_sig[0]} &nbsp;—&nbsp;</span>
        <span style="color:#3a4a6b;font-size:12px">{vp_sig[2]}</span>
    </div>""", unsafe_allow_html=True)

    # ── How to use expander ───────────────────────────────────────────────────
    with st.expander("📚 How to trade using Volume Profile  (click to expand)"):
        st.markdown("""
**POC (Point of Control)** = Jahan SABSE ZYADA volume hua.
HFT & Institutions yahan automatic limit orders rakhte hain → Strong price reaction milti hai.

| Level | Price Position | Signal | Action |
|---|---|---|---|
| **POC** | Price > POC | 🟢 Bullish | POC = strong support, buy dips |
| **POC** | Price < POC | 🔴 Bearish | POC = strong resistance, sell rallies |
| **POC** | Price at POC | ⚠️ Wait | Breakout direction confirm karo |
| **VAH** | Price above VAH | 🟢 Breakout up | Buy CE — no sellers above |
| **VAL** | Price below VAL | 🔴 Breakdown | Buy PE — no buyers below |
| **VA** | Price inside VA | ⚠️ Range | Sell premium — range-bound |

**Key Rules:**
- **POC = Magnet** → Price yahan wapas aata hai. GEX Gamma Wall jaisi quality.
- **Value Area = Comfort zone** → 70% volume yahan hua. Institutions comfort feel karte hain.
- **VAH/VAL breakout** = Strongest move → Alag level pe koi previous support nahi hai
- **Use with GEX** → GEX Negative + Price above POC = STRONGEST BUY setup
        """)


def _render_factor_checklist(factors: dict):
    if not factors:
        return

    rows_html = ""
    for name, info in factors.items():
        icon, val, desc, clr = info
        if clr in ("#00c853", "#26a69a"):
            badge_bg, badge_txt = "#e8f5e9", "#1b7a2e"
        elif clr in ("#ff1744", "#ef5350"):
            badge_bg, badge_txt = "#ffeaea", "#c0392b"
        elif clr in ("#ffd740", "#ff6d00"):
            badge_bg, badge_txt = "#fff8e1", "#b07c00"
        else:
            badge_bg, badge_txt = "#f0f3fa", "#5a6a8a"

        rows_html += (
            f'<div style="display:flex;align-items:center;gap:12px;'
            f'padding:9px 14px;border-bottom:1px solid #eef0f6">'
            f'<span style="font-size:15px;width:24px;flex-shrink:0">{icon}</span>'
            f'<span style="font-size:12px;color:#5a6a8a;font-weight:500;'
            f'width:80px;flex-shrink:0">{name}</span>'
            f'<span style="background:{badge_bg};color:{badge_txt};font-size:11px;'
            f'font-weight:600;padding:3px 10px;border-radius:20px;flex-shrink:0">{val}</span>'
            f'<span style="font-size:11px;color:#aab0c0;flex:1;min-width:0;overflow-wrap:break-word">{desc}</span>'
            f'</div>'
        )

    st.markdown(
        f'<div style="margin:14px 0 4px">'
        f'<div style="font-size:10px;font-weight:600;color:#8a96b0;'
        f'text-transform:uppercase;letter-spacing:0.8px;margin-bottom:8px">'
        f'Factor Checklist</div>'
        f'<div style="background:#ffffff;border:1px solid #e0e4ef;border-radius:10px;overflow:hidden">'
        f'{rows_html}'
        f'</div></div>',
        unsafe_allow_html=True
    )


def render_trade_signal(cache: dict, symbol: str, precomputed: dict = None):
    sig   = precomputed if precomputed is not None else generate_trade_signal(cache, symbol)
    s     = sig.get("signal", "NO TRADE")
    score = sig.get("score", 0)
    bar   = "█" * int(score // 5) + "░" * (20 - int(score // 5))

    # ── Signal color config ───────────────────────────────────────────────────
    cfg = {
        "BUY CE":             ("#1b7a2e", "🟢", "#f0faf2"),
        "BUY PE":             ("#c0392b", "🔴", "#fff5f5"),
        "SELL — Iron Condor": ("#1a56db", "💰", "#f0f4ff"),
        "NO TRADE":           ("#8a96b0", "⛔", "#f8f9fd"),
        "MARKET CLOSED":      ("#5a6a8a", "🌙", "#f0f3fa"),
    }
    color, icon, bg = cfg.get(s, cfg["NO TRADE"])

    # ── MARKET CLOSED ─────────────────────────────────────────────────────────
    if s == "MARKET CLOSED":
        mkt_status = sig.get("status", "CLOSED")
        next_open  = "Kal 9:15 AM" if mkt_status == "CLOSED" else "Thodi der mein"
        st.markdown(f"""
        <div style="background:{bg};border:1px solid #dde2ef;border-radius:12px;
                    padding:20px;text-align:center;margin-bottom:8px">
            <div style="font-size:28px">{icon}</div>
            <div style="font-size:16px;font-weight:700;color:#5a6a8a;margin-top:6px">
                {symbol} — Market {mkt_status}</div>
            <div style="color:#aab0c0;font-size:12px;margin-top:6px">
                OI / PCR / Max Pain data tab ayega jab market khule</div>
            <div style="margin-top:10px;padding:8px 16px;display:inline-block;
                        background:#e8ecf8;border-radius:20px;">
                <span style="color:#5a6a8a;font-size:12px">
                    Next open: <b>{next_open}</b>
                    &nbsp;|&nbsp; VIX: <b style="color:#ff6d00">{sig.get('vix',0):.1f}</b>
                </span>
            </div>
        </div>""", unsafe_allow_html=True)
        return

    # ── NO TRADE ──────────────────────────────────────────────────────────────
    if s == "NO TRADE":
        st.markdown(f"""
        <div style="background:{bg};border:1px solid #e0e4ef;border-radius:12px;
                    padding:20px;text-align:center;margin-bottom:8px">
            <div style="font-size:32px">{icon}</div>
            <div style="font-size:20px;font-weight:700;color:#8a96b0;margin-top:6px">
                NO TRADE</div>
            <div style="color:#aab0c0;font-size:13px;margin-top:8px">
                {sig.get('reason','Mixed signals — wait karo')}</div>
            <div style="color:#c0c8d8;font-size:11px;margin-top:6px">
                Confluence: {sig.get('confluence','—')} &nbsp;|&nbsp;
                VIX: {sig.get('vix',0):.1f} &nbsp;|&nbsp;
                PCR: {sig.get('pcr',0):.2f}
            </div>
        </div>""", unsafe_allow_html=True)
        if sig.get("time_warning"):
            st.warning(sig["time_warning"])
        with st.expander("📊 Factor Analysis", expanded=False):
            _render_factor_checklist(sig.get("factors", {}))
            walls = sig.get("oi_walls", {})
            if walls:
                call_walls = walls.get("call_walls", [])
                put_walls  = walls.get("put_walls",  [])
                st.markdown("**📊 OI Walls**")
                col_r, col_s = st.columns(2)
                with col_r:
                    st.markdown("**🧱 Resistance**")
                    for i, (strike, oi_l) in enumerate(call_walls):
                        bar_len = int(min(oi_l / max(w[1] for w in call_walls) * 10, 10))
                        bar = "█" * bar_len + "░" * (10 - bar_len)
                        st.markdown(f"`{strike}` 🟠 `{bar}` **{oi_l}L**")
                with col_s:
                    st.markdown("**🛡️ Support**")
                    for i, (strike, oi_l) in enumerate(put_walls):
                        bar_len = int(min(oi_l / max(w[1] for w in put_walls) * 10, 10))
                        bar = "█" * bar_len + "░" * (10 - bar_len)
                        st.markdown(f"`{strike}` 🟢 `{bar}` **{oi_l}L**")

    # ── BUY CE / BUY PE ───────────────────────────────────────────────────────
    elif s in ("BUY CE", "BUY PE"):
        strike_reason = sig.get("strike_reason", "ATM strike")
        gw = sig.get("gamma_wall")
        fl = sig.get("flip_level")
        gw_str = f"Gamma Wall: {int(gw)}" if gw else ""
        fl_str = f"Flip Level: {int(fl)}" if fl else ""
        levels_str = " &nbsp;|&nbsp; ".join(filter(None, [gw_str, fl_str]))

        st.markdown(f"""
        <div style="background:{bg};border:1.5px solid {color}44;border-radius:12px;
                    padding:20px;margin-bottom:8px;
                    box-shadow:0 2px 12px {color}18">
            <div style="display:flex;justify-content:space-between;align-items:center">
                <div style="display:flex;align-items:center;gap:12px">
                    <div style="background:{color}18;border-radius:10px;
                                padding:8px 14px;border:1px solid {color}33">
                        <span style="font-size:22px;font-weight:800;
                                     color:{color}">{s}</span>
                    </div>
                    <span style="font-size:18px;font-weight:600;
                                 color:#1a1a2e">{sig.get('strike','')} Strike</span>
                </div>
                <div style="text-align:right">
                    <div style="font-size:10px;color:#8a96b0;
                                text-transform:uppercase;letter-spacing:0.6px">Confidence</div>
                    <div style="font-size:26px;font-weight:700;
                                color:{color}">{score:.0f}%</div>
                </div>
            </div>
            <div style="margin-top:12px;padding:8px 12px;background:{color}0d;
                        border-left:3px solid {color};border-radius:4px">
                <span style="color:#8a96b0;font-size:11px">Strike: </span>
                <span style="color:#1a1a2e;font-size:12px;font-weight:500">{strike_reason}</span>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;
                        gap:10px;margin-top:14px">
                <div style="background:#f8f9fd;border:1px solid #e0e4ef;
                            border-radius:8px;padding:12px;text-align:center">
                    <div style="color:#8a96b0;font-size:10px;text-transform:uppercase;
                                letter-spacing:0.5px">Entry</div>
                    <div style="color:#1a1a2e;font-size:20px;font-weight:700;
                                margin-top:4px">&#8377;{sig.get('entry',0)}</div>
                    <div style="color:#aab0c0;font-size:10px">per unit</div>
                </div>
                <div style="background:#e8f5e9;border:1px solid #c8e6c9;
                            border-radius:8px;padding:12px;text-align:center">
                    <div style="color:#5a8a6a;font-size:10px;text-transform:uppercase;
                                letter-spacing:0.5px">Target</div>
                    <div style="color:#1b7a2e;font-size:20px;font-weight:700;
                                margin-top:4px">&#8377;{sig.get('target',0)}</div>
                    <div style="color:#5a8a6a;font-size:10px">+{sig.get('gain_pct',0)}%</div>
                </div>
                <div style="background:#ffeaea;border:1px solid #ffcdd2;
                            border-radius:8px;padding:12px;text-align:center">
                    <div style="color:#8a5a5a;font-size:10px;text-transform:uppercase;
                                letter-spacing:0.5px">Stop Loss</div>
                    <div style="color:#c0392b;font-size:20px;font-weight:700;
                                margin-top:4px">&#8377;{sig.get('sl',0)}</div>
                    <div style="color:#8a5a5a;font-size:10px">-{sig.get('loss_pct',0)}%</div>
                </div>
                <div style="background:#fff8e1;border:1px solid #ffe082;
                            border-radius:8px;padding:12px;text-align:center">
                    <div style="color:#8a7a3a;font-size:10px;text-transform:uppercase;
                                letter-spacing:0.5px">Lots</div>
                    <div style="color:#b07c00;font-size:20px;font-weight:700;
                                margin-top:4px">{sig.get('lots',1)}</div>
                    <div style="color:#8a7a3a;font-size:10px">
                        Max loss &#8377;{sig.get('max_loss',0):,.0f}</div>
                </div>
            </div>
            <div style="margin-top:12px;display:flex;justify-content:space-between;
                        font-size:11px;color:#8a96b0">
                <span>Max Profit:
                    <b style="color:#1b7a2e">&#8377;{sig.get('max_profit',0):,.0f}</b></span>
                <span>{sig.get('timeframe','Intraday')} &nbsp;|&nbsp;
                    Confluence: {sig.get('confluence','—')} &nbsp;|&nbsp;
                    VIX: {sig.get('vix',0):.1f}</span>
                <span style="color:#aab0c0">{levels_str}</span>
            </div>
        </div>""", unsafe_allow_html=True)
        if sig.get("is_expiry_day"):
            st.error("⏰ EXPIRY DAY — Options premium decays fast. Use ATM only, small size, strict SL.")
        if sig.get("time_warning"):
            st.warning(sig["time_warning"])
        with st.expander("📊 Factor Analysis", expanded=False):
            _render_factor_checklist(sig.get("factors", {}))
            # ── OI Wall Map ────────────────────────────────────────────────────
            walls = sig.get("oi_walls", {})
            if walls:
                call_walls = walls.get("call_walls", [])
                put_walls  = walls.get("put_walls",  [])
                is_buy_ce  = (s == "BUY CE")
                st.markdown("**📊 OI Walls**")
                col_r, col_s = st.columns(2)
                with col_r:
                    st.markdown("**🧱 Resistance**")
                    for i, (strike, oi_l) in enumerate(call_walls):
                        bar_len   = int(min(oi_l / max(w[1] for w in call_walls) * 10, 10))
                        bar       = "█" * bar_len + "░" * (10 - bar_len)
                        tag       = " ← ⚠️" if (i == 0 and is_buy_ce) else ""
                        st.markdown(f"`{strike}` {'🔴' if (i==0 and is_buy_ce) else '🟠'} `{bar}` **{oi_l}L**{tag}")
                with col_s:
                    st.markdown("**🛡️ Support**")
                    for i, (strike, oi_l) in enumerate(put_walls):
                        bar_len   = int(min(oi_l / max(w[1] for w in put_walls) * 10, 10))
                        bar       = "█" * bar_len + "░" * (10 - bar_len)
                        tag       = " ← ⚠️" if (i == 0 and not is_buy_ce) else ""
                        st.markdown(f"`{strike}` {'🔴' if (i==0 and not is_buy_ce) else '🟢'} `{bar}` **{oi_l}L**{tag}")
                warn = walls.get("ce_warning" if is_buy_ce else "pe_warning", "")
                if warn:
                    penalty = walls.get("score_penalty", 0)
                    (st.error if penalty <= -15 else st.warning if penalty <= -8 else st.success)(warn)

    # ── SELL — Iron Condor ────────────────────────────────────────────────────
    else:
        ce_prem    = sig.get("ce_prem",    0)
        pe_prem    = sig.get("pe_prem",    0)
        total_prem = sig.get("total_prem", 0)
        max_profit = sig.get("max_profit_r", 0)
        sl_prem    = sig.get("sl_premium", 0)
        gw = sig.get("gamma_wall")
        fl = sig.get("flip_level")
        gw_str = f"Gamma Wall: {int(gw)}" if gw else ""
        fl_str = f"Flip Level: {int(fl)}" if fl else ""
        levels_str = " &nbsp;|&nbsp; ".join(filter(None, [gw_str, fl_str]))

        st.markdown(f"""
        <div style="background:{bg};border:2px solid {color};border-radius:12px;
                    padding:20px;margin-bottom:8px">

            <!-- Header -->
            <div style="display:flex;justify-content:space-between;align-items:center">
                <div>
                    <span style="font-size:28px">{icon}</span>
                    <span style="font-size:24px;font-weight:bold;color:{color};
                                 margin-left:8px">{s}</span>
                </div>
                <div style="text-align:right">
                    <div style="color:#aaa;font-size:11px">Confidence</div>
                    <div style="font-size:20px;font-weight:bold;color:{color}">
                        {score:.0f}%</div>
                    <div style="font-family:monospace;color:{color};font-size:10px">
                        {bar}</div>
                </div>
            </div>

            <!-- Strike reason -->
            <div style="margin-top:10px;padding:8px 12px;
                        background:#ffffff11;border-left:3px solid {color};
                        border-radius:4px">
                <span style="color:#aaa;font-size:11px">📍 Strikes: </span>
                <span style="color:#fff;font-size:12px">
                    {sig.get('strike_reason','')}</span>
            </div>

            <!-- CE | PE sell boxes -->
            <div style="display:grid;grid-template-columns:1fr 1fr;
                        gap:10px;margin-top:14px">
                <div style="background:#ff6d0022;border-radius:8px;padding:12px;
                             text-align:center">
                    <div style="color:#aaa;font-size:11px">SELL CE (Resistance)</div>
                    <div style="color:#ff6d00;font-size:22px;font-weight:bold">
                        {sig.get('sell_ce','—')}</div>
                    <div style="color:#ff6d00;font-size:12px">
                        Premium ₹{ce_prem:.0f}</div>
                </div>
                <div style="background:#00c85322;border-radius:8px;padding:12px;
                             text-align:center">
                    <div style="color:#aaa;font-size:11px">SELL PE (Support)</div>
                    <div style="color:#00c853;font-size:22px;font-weight:bold">
                        {sig.get('sell_pe','—')}</div>
                    <div style="color:#00c853;font-size:12px">
                        Premium ₹{pe_prem:.0f}</div>
                </div>
            </div>

            <!-- Premium math -->
            <div style="margin-top:12px;display:grid;
                        grid-template-columns:1fr 1fr 1fr;gap:10px">
                <div style="background:#ffffff11;border-radius:8px;padding:10px;
                             text-align:center">
                    <div style="color:#aaa;font-size:11px">TOTAL PREMIUM</div>
                    <div style="color:#ffd740;font-size:18px;font-weight:bold">
                        ₹{total_prem:.0f}</div>
                    <div style="color:#555;font-size:10px">per lot collected</div>
                </div>
                <div style="background:#00c85322;border-radius:8px;padding:10px;
                             text-align:center">
                    <div style="color:#aaa;font-size:11px">MAX PROFIT</div>
                    <div style="color:#00c853;font-size:18px;font-weight:bold">
                        ₹{max_profit:,.0f}</div>
                    <div style="color:#555;font-size:10px">both expire worthless</div>
                </div>
                <div style="background:#ff174422;border-radius:8px;padding:10px;
                             text-align:center">
                    <div style="color:#aaa;font-size:11px">SL TRIGGER</div>
                    <div style="color:#ff1744;font-size:18px;font-weight:bold">
                        ₹{sl_prem:.0f}</div>
                    <div style="color:#ff1744;font-size:10px">
                        Exit if either side hits this</div>
                </div>
            </div>

            <div style="margin-top:10px;padding:8px 10px;
                        background:#ff174411;border-radius:6px">
                <span style="color:#ff1744;font-size:12px">
                    ⚠️ SL Rule: {sig.get('sl_rule','')}</span>
            </div>

            <div style="margin-top:8px;color:#555;font-size:11px;
                        display:flex;justify-content:space-between">
                <span>⏱ {sig.get('timeframe','Weekly')} &nbsp;|&nbsp;
                    IV Rank: {sig.get('iv_rank',0):.0f}% &nbsp;|&nbsp;
                    VIX: {sig.get('vix',0):.1f}</span>
                <span>{levels_str}</span>
            </div>
        </div>""", unsafe_allow_html=True)
        with st.expander("📊 Factor Analysis", expanded=False):
            _render_factor_checklist(sig.get("factors", {}))


# ══════════════════════════════════════════════════════════════════════════════
# ALERT HISTORY PANEL
# ══════════════════════════════════════════════════════════════════════════════

def _track_signal_outcomes(db, cache: dict, symbol: str):
    """
    Har refresh pe PENDING signals check karo.
    Agar current option LTP target ya SL cross kar gaya → outcome update karo.
    Option LTP OI chain se milta hai (same cache jo display mein use hota hai).
    """
    if not db:
        return
    from datetime import date as _date
    today   = _date.today().isoformat()
    pending = db.get_signals(symbol, from_date=today, to_date=today)
    pending = [s for s in pending if s.get("outcome", "PENDING") == "PENDING"]
    if not pending:
        return

    oi_chain = cache.get("oi_chain", [])
    # Build a quick strike → (ce_ltp, pe_ltp) lookup
    ltp_map: dict = {}
    for row in oi_chain:
        try:
            ltp_map[int(row.strike)] = (row.ce_ltp or 0, row.pe_ltp or 0)
        except Exception:
            pass

    for sig in pending:
        sig_id   = sig.get("id", -1)
        sig_type = sig.get("signal", "")
        strike   = sig.get("strike", 0)
        entry    = sig.get("entry_price", 0)
        target   = sig.get("target", 0)
        sl       = sig.get("sl", 0)

        if sig_id < 0 or not strike or not entry:
            continue

        opt_type = "CE" if "CE" in sig_type else "PE"
        ce_ltp, pe_ltp = ltp_map.get(int(strike), (0, 0))
        curr_ltp = ce_ltp if opt_type == "CE" else pe_ltp

        if curr_ltp <= 0:
            continue  # LTP unavailable — check next cycle

        if curr_ltp >= target:
            pnl_pct = round((curr_ltp - entry) / entry * 100, 1)
            db.update_signal_outcome(sig_id, "WIN", curr_ltp, pnl_pct)
        elif curr_ltp <= sl:
            pnl_pct = round((curr_ltp - entry) / entry * 100, 1)
            db.update_signal_outcome(sig_id, "LOSS", curr_ltp, pnl_pct)


def _render_signal_history(db, symbol: str):
    """
    Aaj ke BUY CE / BUY PE / Iron Condor signals ka table.
    DB se read karta hai — live outcomes bhi dikhata hai.
    """
    from datetime import date as _date
    import pandas as _pd

    if not db:
        st.info("Database connected nahi — signal history unavailable.")
        return

    today   = _date.today().isoformat()
    signals = db.get_signals(symbol, from_date=today, to_date=today)
    # Only actionable signals
    signals = [s for s in signals if s.get("signal", "") in
               ("BUY CE", "BUY PE", "SELL — Iron Condor")]

    if not signals:
        st.info(f"Aaj ({today}) koi BUY/SELL signal generate nahi hua abhi tak.")
        return

    rows = []
    for s in signals:
        outcome = s.get("outcome", "PENDING")
        pnl_pct = s.get("pnl_pct", 0)
        exit_px = s.get("exit_price", 0)

        if outcome == "WIN":
            outcome_str = f"✅ WIN  (+{pnl_pct:.1f}%)"
        elif outcome == "LOSS":
            outcome_str = f"❌ LOSS ({pnl_pct:.1f}%)"
        else:
            outcome_str = "⏳ PENDING"

        rows.append({
            "Time":    s.get("ts", "")[:16].replace("T", " "),
            "Signal":  s.get("signal", ""),
            "Strike":  int(s.get("strike", 0)),
            "Entry ₹": round(s.get("entry_price", 0), 1),
            "Target ₹": round(s.get("target", 0), 1),
            "SL ₹":    round(s.get("sl", 0), 1),
            "Exit ₹":  round(exit_px, 1) if exit_px else "—",
            "Score":   s.get("score", 0),
            "PCR":     round(s.get("pcr", 0), 2),
            "VIX":     round(s.get("vix", 0), 1),
            "Outcome": outcome_str,
        })

    df = _pd.DataFrame(rows)

    # Summary metrics
    total  = len(rows)
    wins   = sum(1 for s in signals if s.get("outcome") == "WIN")
    losses = sum(1 for s in signals if s.get("outcome") == "LOSS")
    pend   = total - wins - losses
    win_rt = round(wins / (wins + losses) * 100) if (wins + losses) > 0 else 0

    mc1, mc2, mc3, mc4, mc5 = st.columns(5)
    mc1.metric("Total Signals", total)
    mc2.metric("✅ WIN",   wins)
    mc3.metric("❌ LOSS",  losses)
    mc4.metric("⏳ Pending", pend)
    mc5.metric("Win Rate", f"{win_rt}%" if (wins + losses) > 0 else "—")

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Signal":   st.column_config.TextColumn("Signal", width="medium"),
            "Outcome":  st.column_config.TextColumn("Outcome", width="medium"),
            "Score":    st.column_config.NumberColumn("Score", format="%d"),
        }
    )

    # All-time summary from DB
    stats = db.get_stats() if hasattr(db, "get_stats") else {}
    if stats.get("outcomes"):
        all_win  = stats["outcomes"].get("WIN",  0)
        all_loss = stats["outcomes"].get("LOSS", 0)
        if all_win + all_loss > 0:
            all_wr = round(all_win / (all_win + all_loss) * 100)
            st.caption(
                f"📈 All-time (DB): {stats['total_signals']} signals · "
                f"Win {all_win} / Loss {all_loss} · Win Rate **{all_wr}%**"
            )


def _render_alert_history():
    """
    Recent alerts ka chhota collapsible panel.
    Koi alert nahi hai toh kuch nahi dikhega.
    """
    history = st.session_state.get("alert_history", [])
    if not history:
        return   # Koi alert nahi — silently skip

    # Category color map
    cat_color = {
        "URGENT":    "#ff4444",
        "IMPORTANT": "#ff9800",
        "INFO":      "#40c4ff",
    }
    cat_emoji = {
        "URGENT":    "🚨",
        "IMPORTANT": "⚠️",
        "INFO":      "ℹ️",
    }

    rows_html = ""
    for a in history[:10]:   # Last 10 hi dikhao
        col   = cat_color.get(a.category, "#888888")
        emoji = cat_emoji.get(a.category, "📢")
        rows_html += (
            f"<div style='display:flex;align-items:center;gap:10px;"
            f"padding:6px 10px;border-left:3px solid {col};"
            f"background:#f0f3fa;border-radius:4px;margin-bottom:4px'>"
            f"<span style='color:{col};font-size:13px'>{emoji}</span>"
            f"<span style='color:#6b7a99;font-size:11px;min-width:38px'>{a.time}</span>"
            f"<span style='color:#1a1a2e;font-size:12px;font-weight:600'>{a.title}</span>"
            f"<span style='color:#8a96b0;font-size:11px;margin-left:auto'>{a.category}</span>"
            f"</div>"
        )

    telegram_status = ""
    engine = st.session_state.get("alert_engine")
    if engine and engine.enabled:
        telegram_status = (
            "<span style='color:#00c853;font-size:11px'>&#9679; Telegram ON</span>"
        )
    else:
        telegram_status = (
            "<span style='color:#555;font-size:11px'>&#9679; Telegram OFF "
            "(settings.py me enable karo)</span>"
        )

    with st.expander(f"🔔 Recent Alerts ({len(history)})", expanded=False):
        st.markdown(
            f"<div style='margin-bottom:8px'>{telegram_status}</div>"
            f"{rows_html}",
            unsafe_allow_html=True,
        )




# ══════════════════════════════════════════════════════════════════════════════
# LIVE DATA FRAGMENT — har 60 sec mein auto-refresh, page reload nahi hoga
# ══════════════════════════════════════════════════════════════════════════════
@st.fragment(run_every=60)          # ← KEY FIX: ye sirf data section refresh karta hai
def live_data_section(symbol, expiry):
    """
    Ye function har 60 seconds mein automatically re-run hota hai.
    Session state (Kite connection) preserve rehti hai.
    Sirf ye section update hota hai, poora page reload nahi hota.
    """

    # Fresh data fetch
    with st.spinner("🔄 Fetching live data..."):
        cache = fetch_all_data(symbol, expiry)

    # Share cache with Tab 2 (avoids duplicate API calls)
    st.session_state["last_cache"] = cache

    # Also share latest SMI data so alert engine can check it
    smi_latest = st.session_state.get("smi_latest", {})
    if smi_latest:
        cache["smi_data"] = smi_latest

    # ── Alert Engine — signals check karo, Telegram bhejo ───────────────────
    try:
        engine      = st.session_state.get("alert_engine")
        gex_history = st.session_state.get("gex_history", [])
        if engine is not None:
            new_alerts = engine.check_and_send(cache, symbol, gex_history)
            if new_alerts:
                hist = st.session_state.get("alert_history", [])
                hist = new_alerts + hist       # Naye alerts upar
                st.session_state["alert_history"] = hist[:20]   # Last 20 rakho
    except Exception as _ae:
        logger.error(f"Alert engine error: {_ae}")

    # ── Compute primary signal once — reuse for snapshot + render (M-04) ────────
    primary_sig = generate_trade_signal(cache, symbol)

    # ── Trade Signal Telegram Alert ───────────────────────────────────────────
    try:
        _eng = st.session_state.get("alert_engine")
        if _eng is not None:
            _eng.send_trade_signal(primary_sig)
    except Exception as _te:
        logger.error(f"Trade signal alert error: {_te}")

    # ── Snapshot Collector — Backtest data save karo (har 5 min) ─────────────
    try:
        collector = st.session_state.get("snap_collector")
        if collector is not None:
            collector.collect(cache, symbol, primary_sig)
    except Exception as _sc:
        logger.error(f"Snapshot collect error: {_sc}")

    # ── Outcome Tracker — PENDING signals ka WIN/LOSS check karo ─────────────
    try:
        _snap_db_ot = st.session_state.get("snap_db")
        if _snap_db_ot is not None:
            _track_signal_outcomes(_snap_db_ot, cache, symbol)
    except Exception as _ot:
        logger.error(f"Outcome tracking error: {_ot}")

    # ── UOA Alerts — DB save + Telegram alert ────────────────────────────────
    try:
        _snap_db  = st.session_state.get("snap_db")
        _uoa_eng  = st.session_state.get("alert_engine")
        for _uoa in cache.get("uoa_alerts", []):
            _is_new = _snap_db.save_uoa_alert(_uoa) if _snap_db else False
            if _is_new and _uoa_eng is not None:
                _uoa_eng.send_uoa_alert(_uoa)
    except Exception as _ue:
        logger.error(f"UOA save/alert error: {_ue}")

    # ── Header ──────────────────────────────────────────────────────────────
    render_header(symbol, expiry, cache)

    # ── Recent Alerts Panel ──────────────────────────────────────────────────
    _render_alert_history()

    # ── Market Overview (compact strip) ──────────────────────────────────────
    render_market_overview(cache)

    # ── TRADE SIGNALS — NIFTY + BANKNIFTY side by side ──────────────────────
    other_sym   = cache.get("other_symbol", "BANKNIFTY" if symbol == "NIFTY" else "NIFTY")
    other_cache = cache.get("other_cache", {})

    col_sig1, col_sig2 = st.columns(2)
    with col_sig1:
        st.markdown(f"### 🎯 Trade Signal — {symbol}")
        render_trade_signal(cache, symbol, precomputed=primary_sig)   # reuse — no extra call
    with col_sig2:
        st.markdown(f"### 🎯 Trade Signal — {other_sym}")
        if other_cache:
            render_trade_signal(other_cache, other_sym)
        else:
            st.info("⏳ Loading...")
    st.divider()

    # ── OI Chain | UOA ───────────────────────────────────────────────────────
    col_l, col_r = st.columns([3, 2])
    with col_l:
        st.markdown(f"### 📊 OI Chain — {symbol}")
        render_oi_chain(cache, symbol)
    with col_r:
        st.markdown("### 🔍 Unusual Options Activity")
        render_uoa(cache)

    st.divider()

    # ── IV (PCR now shown in Market Overview) ─────────────────────────────────
    st.markdown("### 🎯 IV Rank · Greeks · Skew")
    render_iv(cache)

    st.divider()

    # ── Max Pain Panel ────────────────────────────────────────────────────────
    st.markdown("### 🎯 Max Pain Calculator")
    render_max_pain(cache, symbol, expiry)

    st.divider()

    # ── GEX Panel ────────────────────────────────────────────────────────────
    st.markdown("### ⚡ GEX — Gamma Exposure (Institutional Signal)")
    render_gex(cache)
    st.divider()

    # ── Volume Profile ────────────────────────────────────────────────────────
    st.markdown("### 📊 Volume Profile — POC · VAH · VAL")
    render_volume_profile(cache, symbol)
    st.divider()

    # ── OI Buildup | Risk ────────────────────────────────────────────────────
    col_bu, col_rk = st.columns(2)
    with col_bu:
        st.markdown("### 🏗️ OI Buildup Analysis")
        render_buildup(cache)
    with col_rk:
        st.markdown("### 🛡️ Portfolio Risk")
        render_risk(cache)

    st.divider()

    # ── Signal History — Aaj ke sab trade signals + outcomes ─────────────────
    st.markdown("### 📋 Signal History — Aaj ke Trade Signals")
    st.caption("Har 60 sec pe auto-update · WIN/LOSS jab option price target/SL touch kare")
    _snap_db_sh = st.session_state.get("snap_db")
    _render_signal_history(_snap_db_sh, symbol)

    # ── Footer ───────────────────────────────────────────────────────────────
    st.divider()
    fetched = cache.get("fetched_at", "--")
    st.markdown(
        f"<div style='text-align:center;color:#333;font-size:11px'>"
        f"🔄 Data fetched at: {fetched} &nbsp;|&nbsp; "
        f"Auto-refresh: 60s &nbsp;|&nbsp; {symbol} · {expiry}"
        f"</div>",
        unsafe_allow_html=True
    )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — RENDER FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def render_smi(smi: dict):
    """Smart Money Index panel."""
    if not smi:
        st.info("⏳ Loading SMI — requires today's 5-min candles (market must be open).")
        return
    if "error" in smi:
        st.warning(f"SMI data unavailable: {smi['error']}")
        return

    chg     = smi["smi_change"]
    chg_col = "#00c853" if chg >= 0 else "#ff1744"
    chg_ico = "▲" if chg >= 0 else "▼"

    m_col  = '#ff1744' if smi['morning_move'] < 0 else '#00c853'
    e_col  = '#00c853' if smi['evening_move'] > 0 else '#ff1744'
    t_col  = '#00c853' if smi['tomorrow'] == 'BULLISH' else '#ff1744'
    sig_c  = smi['sig_color']

    st.markdown(f"""
    <div style="background:#f8f9fd;border:2px solid {sig_c};border-radius:12px;padding:16px;margin-bottom:12px">
        <div style="display:flex;justify-content:space-between;align-items:center">
            <div>
                <span style="font-size:22px">&#129504;</span>
                <span style="font-size:18px;font-weight:bold;color:#1a1a2e;margin-left:8px">Smart Money Index</span>
            </div>
            <div style="text-align:right">
                <div style="color:#6b7a99;font-size:11px">Today's SMI</div>
                <div style="font-size:26px;font-weight:bold;color:{chg_col}">{smi['smi']:,.0f}</div>
                <div style="color:{chg_col};font-size:12px">{chg_ico} {abs(chg):.1f} from yesterday</div>
            </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:12px">
            <div style="background:#f0f3fa;border:1px solid #e0e4ef;border-radius:8px;padding:10px;text-align:center">
                <div style="color:#6b7a99;font-size:10px">Morning Move (9:15-9:45)</div>
                <div style="font-size:18px;font-weight:bold;color:{m_col}">{smi['morning_move']:+.1f}</div>
                <div style="color:#8a96b0;font-size:10px">Retail / Emotional</div>
            </div>
            <div style="background:#f0f3fa;border:1px solid #e0e4ef;border-radius:8px;padding:10px;text-align:center">
                <div style="color:#6b7a99;font-size:10px">Evening Move (3:00-3:30)</div>
                <div style="font-size:18px;font-weight:bold;color:{e_col}">{smi['evening_move']:+.1f}</div>
                <div style="color:#8a96b0;font-size:10px">Smart Money</div>
            </div>
            <div style="background:#f0f3fa;border:1px solid #e0e4ef;border-radius:8px;padding:10px;text-align:center">
                <div style="color:#6b7a99;font-size:10px">5-Day Trend</div>
                <div style="font-size:16px;font-weight:bold;color:#1a56db">{smi['trend']}</div>
                <div style="color:#8a96b0;font-size:10px">Institutional bias</div>
            </div>
        </div>
        <div style="margin-top:12px;padding:10px;background:{sig_c}22;border-left:4px solid {sig_c};border-radius:4px">
            <div style="color:{sig_c};font-weight:bold;font-size:13px">{smi['signal']}</div>
            <div style="color:#6b7a99;font-size:12px;margin-top:4px">Tomorrow Bias: <b style="color:{t_col}">{smi['tomorrow']}</b></div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("📖 How to use Smart Money Index (click to expand)"):
        st.markdown("""
**What is SMI?**
Retail traders are emotional in the morning (9:15–9:45). Institutions quietly
position themselves in the last 30 minutes (3:00–3:30).

**Formula:**
```
SMI = Previous_SMI  –  Morning_Move  +  Evening_Move
```

| Scenario | Morning | Evening | Signal | Tomorrow Action |
|----------|---------|---------|--------|----------------|
| Institutions Buying | Down ▼ | Up ▲ | Smart money absorbing panic sell | **GO LONG** |
| Distribution | Up ▲ | Down ▼ | Retail buying while institutions exit | **GO SHORT** |
| Bullish Momentum | Up ▲ | Up ▲ | Both retail & smart money buying | **STAY LONG** |
| Bearish Pressure | Down ▼ | Down ▼ | Broad selling continues | **STAY SHORT** |

**Golden Rule:** SMI rising while price is falling = **strongest buy signal** for next session.
        """)


def render_gamma_acceleration(ga: dict):
    """Gamma Acceleration panel."""
    if not ga:
        st.info("⏳ Building GEX history — needs 2+ data points. Wait 60 seconds for first reading.")
        return

    rate_col  = "#00c853" if ga["rate"] > 0 else "#ff1744"
    flip_mins = ga.get("flip_eta")
    decay     = ga.get("decay_pct", 0)
    bar_fill  = int(decay / 5)
    bar_str   = "█" * bar_fill + "░" * (20 - bar_fill)
    dir_c     = ga['dir_color']
    gex_sign  = '+' if ga['current'] >= 0 else ''
    rate_sign = '+' if ga['rate'] >= 0 else ''
    flip_col  = "#ff1744" if (flip_mins and flip_mins < 15) else ("#ffd740" if flip_mins else "#555")
    flip_str  = f"{flip_mins}m" if flip_mins else "&#8212;"

    st.markdown(f"""
    <div style="background:#f8f9fd;border:2px solid {dir_c};border-radius:12px;padding:16px;margin-bottom:12px">
        <div style="display:flex;justify-content:space-between;align-items:center">
            <div>
                <span style="font-size:22px">&#9889;</span>
                <span style="font-size:18px;font-weight:bold;color:#1a1a2e;margin-left:8px">Gamma Acceleration</span>
            </div>
            <div style="text-align:right">
                <div style="color:#6b7a99;font-size:11px">Current GEX</div>
                <div style="font-size:22px;font-weight:bold;color:{dir_c}">{gex_sign}{ga['current']:.2f} Cr</div>
            </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:12px">
            <div style="background:#f0f3fa;border:1px solid #e0e4ef;border-radius:8px;padding:10px;text-align:center">
                <div style="color:#6b7a99;font-size:10px">Change Rate</div>
                <div style="font-size:18px;font-weight:bold;color:{rate_col}">{rate_sign}{ga['rate']:.2f}</div>
                <div style="color:#8a96b0;font-size:10px">Cr / minute</div>
            </div>
            <div style="background:#f0f3fa;border:1px solid #e0e4ef;border-radius:8px;padding:10px;text-align:center">
                <div style="color:#6b7a99;font-size:10px">Direction</div>
                <div style="font-size:15px;font-weight:bold;color:{dir_c}">{ga['direction']}</div>
                <div style="color:#8a96b0;font-size:10px">{ga['readings']} readings</div>
            </div>
            <div style="background:#f0f3fa;border:1px solid #e0e4ef;border-radius:8px;padding:10px;text-align:center">
                <div style="color:#6b7a99;font-size:10px">Flip ETA</div>
                <div style="font-size:18px;font-weight:bold;color:{flip_col}">{flip_str}</div>
                <div style="color:#8a96b0;font-size:10px">Mins to regime change</div>
            </div>
        </div>
        <div style="margin-top:12px">
            <div style="color:#8a96b0;font-size:10px;margin-bottom:4px">Session decay: {decay:.0f}%</div>
            <div style="font-family:monospace;color:{dir_c};font-size:12px">{bar_str} {decay:.0f}%</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if ga.get("alert"):
        alert_col = "#ff1744" if "FLIP" in ga["alert"] else "#ffd740"
        st.markdown(
            f"<div style='background:{alert_col}22;border:1px solid {alert_col};"
            f"border-radius:8px;padding:10px;color:{alert_col};font-size:13px'>"
            f"⚠️ {ga['alert']}</div>",
            unsafe_allow_html=True
        )

    with st.expander("📖 How to use Gamma Acceleration (click to expand)"):
        st.markdown("""
**What is Gamma Acceleration?**
GEX changes every minute as MMs re-hedge. The *speed* of this change warns you
when a regime shift (Range ↔ Volatile) is about to happen — before it actually happens.

**Think of it as:** GEX = temperature. Gamma Acceleration = how fast temperature is changing.

| Signal | Meaning | Immediate Action |
|--------|---------|-----------------|
| GEX decaying fast (+ve → 0) | Market about to go VOLATILE | Buy CE or PE. Stop selling. |
| GEX stable positive | Range-bound confirmed | Continue selling premium |
| GEX recovering (−ve → 0) | Volatility calming down | Start building selling positions |
| **Flip ETA < 15 min** | **URGENT — regime changing NOW** | **Close all short option positions** |

**Key Insight:** A GEX flip from positive to negative is one of the highest-conviction
intraday signals available. It typically precedes a 50–150 point directional move.
        """)


def render_pin_probability(pin: dict, symbol: str):
    """Strike Pinning Probability panel."""
    if not pin:
        st.info("⏳ Pin probability requires GEX data. Please wait for OI chain to load.")
        return

    spot     = pin["spot"]
    top      = pin["top_strike"]
    top_prob = pin["top_prob"]
    top_col  = ("#00c853" if top_prob > 40 else
                "#ffd740" if top_prob > 25 else "#aaa")

    # ── Build all bar HTML into ONE string (MUST be single st.markdown call) ───
    sorted_pins = pin["sorted_pins"]
    max_prob    = sorted_pins[0][1] if sorted_pins else 1
    bars_html   = ""
    for s, prob in sorted_pins[:8]:
        bar_len    = int(prob / max_prob * 20)
        bar_filled = "█" * bar_len + "░" * (20 - bar_len)
        is_top      = (s == top)
        is_near     = bool(spot) and abs(s - spot) <= 50
        bar_col     = "#b8860b" if is_top else ("#1a56db" if is_near else "#3a5a8a")
        label       = (f"&#9733; {s:,}" if is_top else
                       f"&#9658; {s:,}" if is_near else f"&nbsp;&nbsp;{s:,}")
        bars_html  += (
            f"<div style='display:flex;align-items:center;gap:10px;margin:4px 0'>"
            f"<span style='color:#3a4a6b;font-size:11px;width:80px'>{label}</span>"
            f"<span style='font-family:monospace;color:{bar_col};font-size:11px'>{bar_filled}</span>"
            f"<span style='color:{bar_col};font-size:12px;font-weight:bold;margin-left:6px'>"
            f"{prob:.1f}%</span>"
            f"</div>"
        )

    note_html = ""
    if pin.get("note"):
        note_html = (
            f"<div style='margin-top:12px;padding:10px;background:#ffd74022;"
            f"border-left:4px solid #ffd740;border-radius:4px'>"
            f"<span style='color:#ffd740;font-size:12px'>&#128161; {pin['note']}</span>"
            f"</div>"
        )

    # Single render call — no split divs
    st.markdown(f"""
    <div style="background:#f8f9fd;border:2px solid #1a56db;
                border-radius:12px;padding:16px;margin-bottom:8px">
        <div style="display:flex;justify-content:space-between;align-items:center;
                    margin-bottom:12px">
            <div>
                <span style="font-size:22px">&#127919;</span>
                <span style="font-size:18px;font-weight:bold;color:#1a1a2e;margin-left:8px">
                    Expiry Pin Probability</span>
            </div>
            <div style="text-align:right">
                <div style="color:#6b7a99;font-size:11px">Most Likely Pin</div>
                <div style="font-size:26px;font-weight:bold;color:{top_col}">{top:,}</div>
                <div style="color:{top_col};font-size:12px">{top_prob:.1f}% probability</div>
            </div>
        </div>
        {bars_html}
        {note_html}
    </div>
    """, unsafe_allow_html=True)

    with st.expander("📖 How to use Strike Pinning (click to expand)"):
        st.markdown("""
**What is Strike Pinning?**
On expiry day, NIFTY gravitates toward strikes where market makers have the most GEX.
MM re-hedging activity at those strikes creates a "gravity well" — price gets pulled there.

**Formula:**
```
Pin_Probability(strike) = |Net_GEX_at_strike| / Σ|Net_GEX_all_strikes| × 100
```

| Probability | Reliability | Suggested Trade |
|-------------|-------------|----------------|
| > 50% | Very High | Sell ATM Straddle at pin strike |
| 30–50% | High | Sell Strangle centered on pin strike |
| < 20% | Low | Wait — no clear pin. Use GEX + PCR together |

**Best Window:** Wednesday 2 PM → Thursday 10 AM (for weekly Nifty expiry).

**Stop Loss Rule:** If NIFTY moves more than ±100 points from pin strike → exit immediately.

**Important:** Pin probability is most reliable within 48 hours of expiry.
It degrades accuracy the further out you are from expiry.
        """)


def render_expected_move(em: dict, symbol: str):
    """Expected Move Calculator panel."""
    if not em:
        st.info("⏳ Expected move requires ATM options LTP. Please wait for data to load.")
        return

    spot   = em["spot"]
    tone_c = em['tone_col']

    st.markdown(f"""
    <div style="background:#f8f9fd;border:2px solid {tone_c};border-radius:12px;padding:16px;margin-bottom:12px">
        <div style="display:flex;justify-content:space-between;align-items:center">
            <div>
                <span style="font-size:22px">&#128208;</span>
                <span style="font-size:18px;font-weight:bold;color:#1a1a2e;margin-left:8px">Expected Move &#8212; This Expiry</span>
            </div>
            <div style="text-align:right">
                <div style="color:#6b7a99;font-size:11px">ATM Straddle Value</div>
                <div style="font-size:28px;font-weight:bold;color:#b8860b">&#8377;{em['straddle']:.0f}</div>
                <div style="color:#6b7a99;font-size:11px">&#177;{em['move_pct']:.2f}% of spot</div>
            </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px">
            <div style="background:#fff5f0;border:1px solid #ffccaa;border-radius:8px;padding:10px;text-align:center">
                <div style="color:#6b7a99;font-size:11px">ATM {em['atm']} CE</div>
                <div style="color:#c0392b;font-size:22px;font-weight:bold">&#8377;{em['ce_ltp']:.0f}</div>
            </div>
            <div style="background:#f0fff4;border:1px solid #aaecc0;border-radius:8px;padding:10px;text-align:center">
                <div style="color:#6b7a99;font-size:11px">ATM {em['atm']} PE</div>
                <div style="color:#1b7a2e;font-size:22px;font-weight:bold">&#8377;{em['pe_ltp']:.0f}</div>
            </div>
        </div>
        <div style="margin-top:14px;padding:12px;background:#f0f3fa;border:1px solid #e0e4ef;border-radius:8px">
            <div style="display:flex;justify-content:space-between;margin-bottom:8px;font-size:12px">
                <span style="color:#c0392b;font-weight:bold">&#128308; Lower: {em['lower']:,.0f}</span>
                <span style="color:#1a1a2e;font-weight:600">Spot: {spot:,.0f}</span>
                <span style="color:#1b7a2e;font-weight:bold">&#128994; Upper: {em['upper']:,.0f}</span>
            </div>
            <div style="background:#1a56db;border-radius:4px;height:10px;position:relative;opacity:0.5"></div>
            <div style="text-align:center;color:#1a56db;font-size:11px;margin-top:6px">
                85% probability NIFTY stays within &#177;{em['straddle']:.0f} pts this expiry
            </div>
        </div>
        <div style="margin-top:12px;padding:10px;background:#e8f0fe;border-left:4px solid #1a56db;border-radius:4px">
            <div style="color:#1a56db;font-size:12px;font-weight:bold">&#128176; Iron Condor &#8212; Just outside expected move:</div>
            <div style="color:#1a1a2e;font-size:13px;margin-top:6px">
                SELL {em['ic_ce']} CE @ &#8377;{em['ic_ce_prem']:.0f} &nbsp;+&nbsp; SELL {em['ic_pe']} PE @ &#8377;{em['ic_pe_prem']:.0f} &nbsp;=&nbsp; <span style="color:#b8860b;font-weight:bold">&#8377;{em['ic_total']:.0f} total premium</span>
            </div>
        </div>
        <div style="margin-top:10px;color:{tone_c};font-size:12px"><b>{em['tone']}</b> &#8212; {em['advice']}</div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("📖 How to use Expected Move (click to expand)"):
        st.markdown("""
**What is Expected Move?**
The ATM straddle price is the market's collective insurance cost.
Higher the price → bigger the move expected → more fear/uncertainty.

**Formula:**
```
Expected Move = ATM Call Price + ATM Put Price
```

| Straddle Size | Market Signal | Best Strategy |
|--------------|--------------|---------------|
| > 2.5% of spot | Big move expected (High IV) | Buy options directionally (CE or PE) |
| 1–2.5% | Normal | Both buying and selling viable |
| < 1% | Calm market (Low IV) | Sell Iron Condor — safest time |

**Iron Condor Logic:**
- Sell strikes OUTSIDE the expected move range
- 85% probability NIFTY stays within this range at expiry
- Collect full premium if NIFTY stays between Lower and Upper limits

**When NOT to use:**
- Results day / Budget / RBI policy = straddle may be mispriced
- Expiry morning: straddle becomes unreliable after 10:30 AM
        """)


def render_cross_assets(cross: dict):
    """Cross-Asset Signals panel."""
    if not cross or not cross.get("signals"):
        st.info("⏳ Loading cross-asset data...")
        return

    ov_col = cross["ov_color"]

    # ── Build all signal rows into ONE string (MUST be single st.markdown call) ─
    rows_html = ""
    for sig in cross["signals"]:
        col = sig["color"]
        rows_html += (
            f"<div style='display:flex;align-items:center;gap:10px;padding:8px 10px;"
            f"margin:4px 0;background:#f0f3fa;border-radius:6px;"
            f"border-left:3px solid {col}'>"
            f"<span style='font-size:18px'>{sig['icon']}</span>"
            f"<span style='color:#3a4a6b;font-size:13px;flex:1'>{sig['name']}</span>"
            f"<span style='color:#1a1a2e;font-size:14px;font-weight:bold;"
            f"min-width:90px'>{sig['value']}</span>"
            f"<span style='color:{col};font-size:12px;font-weight:bold;"
            f"min-width:75px'>{sig['signal']}</span>"
            f"<span style='color:#8a96b0;font-size:11px;flex:2;text-align:right'>"
            f"{sig['note']}</span>"
            f"</div>"
        )

    # Single render call — header + rows + footer + closing div all together
    st.markdown(f"""
    <div style="background:#f8f9fd;border:2px solid {ov_col};
                border-radius:12px;padding:16px;margin-bottom:12px">
        <div style="display:flex;justify-content:space-between;align-items:center;
                    margin-bottom:12px">
            <div>
                <span style="font-size:22px">&#127758;</span>
                <span style="font-size:18px;font-weight:bold;color:#1a1a2e;margin-left:8px">
                    Cross-Asset Signals</span>
            </div>
            <div style="text-align:right">
                <div style="color:#6b7a99;font-size:11px">Overall Reading</div>
                <div style="font-size:18px;font-weight:bold;color:{ov_col}">
                    {cross['overall']}</div>
                <div style="color:#6b7a99;font-size:11px">
                    Score: {cross['score']:+d} / {cross['total']} signals</div>
            </div>
        </div>
        {rows_html}
        <div style='margin-top:10px;padding:8px 10px;background:#f0f3fa;
                    border:1px solid #e0e4ef;border-radius:6px;color:#6b7a99;font-size:11px'>
            &#8505;&#65039; SGX Nifty &amp; US Futures not available via Kite API —
            check <b style="color:#3a4a6b">sgxnifty.com</b> (pre-market) and
            <b style="color:#3a4a6b">cnbc.com/world-markets</b> (US futures) manually.
            Crude Oil requires MCX subscription.
        </div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("📖 How to use Cross-Asset Signals (click to expand)"):
        st.markdown("""
**Why does this matter?**
NIFTY is connected to global markets. Knowing the cross-asset environment before trading
gives you an edge — especially for the first 30 minutes of the session.

| Signal | Leads NIFTY by | What to Watch |
|--------|---------------|--------------|
| India VIX falling | Simultaneous | Fear reducing → buying safe |
| BankNifty outperforming | Intraday | FII buying financials → broad rally likely |
| Rupee strengthening | Intraday | FII equity inflows → NIFTY support |
| SGX Nifty +50 pts at 9 AM | 15 min | NIFTY will gap-up open |
| US Futures up overnight | At open | Global risk-on → Indian market follows |

**Trading Rule:**
- 3+ signals BULLISH → Strong long setup → Buy CE
- 3+ signals BEARISH → Strong short setup → Buy PE
- Mixed signals → Reduce position size, wait for confirmation from OI Chain

**Check manually before 9 AM:**
- SGX Nifty: sgxnifty.com
- Dow/S&P Futures: cnbc.com/world-markets
        """)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — TREND COMPASS
# ══════════════════════════════════════════════════════════════════════════════

def _render_checklist(result):
    """Render one symbol+timeframe checklist card."""
    from core.trend_compass import SYMBOL_DISPLAY
    sym_label = SYMBOL_DISPLAY.get(result.symbol, result.symbol)
    verdict   = result.verdict
    color     = result.color
    score     = result.score
    max_s     = result.max_score

    if result.error:
        st.markdown(f"""
<div style="background:#f8f9fd;border:2px solid #c8d0e8;border-radius:12px;padding:16px;margin-bottom:12px">
<div style="color:#6b7a99;font-size:13px">&#9888; {result.error}</div>
</div>""", unsafe_allow_html=True)
        return

    bar_pct   = int((score / max_s) * 100) if max_s else 0
    bar_col   = color

    st.markdown(f"""
<div style="background:#f8f9fd;border:2px solid {color};border-radius:12px;padding:20px;margin-bottom:16px">
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
  <div>
    <span style="font-size:18px;font-weight:700;color:#1a1a2e">{sym_label}</span>
    <span style="font-size:13px;color:#6b7a99;margin-left:10px">{result.timeframe} Timeframe</span>
  </div>
  <div style="text-align:right">
    <span style="font-size:22px;font-weight:800;color:{color}">{verdict}</span>
    <div style="font-size:13px;color:#6b7a99">{score}/{max_s} checks passed</div>
  </div>
</div>
<div style="background:#e0e4ef;border-radius:4px;height:6px;margin-bottom:14px">
  <div style="background:{bar_col};width:{bar_pct}%;height:6px;border-radius:4px"></div>
</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:12px">
  <div style="color:#6b7a99">Price: <b style="color:#1a1a2e">{result.price:,.0f}</b></div>
  <div style="color:#6b7a99">RSI: <b style="color:#1a1a2e">{result.rsi:.1f}</b></div>
  <div style="color:#6b7a99">EMA20: <b style="color:#1a1a2e">{result.ema20:,.0f}</b></div>
  <div style="color:#6b7a99">EMA50: <b style="color:#1a1a2e">{result.ema50:,.0f}</b></div>
  <div style="color:#6b7a99">EMA200: <b style="color:#1a1a2e">{result.ema200:,.0f}</b></div>
  <div style="color:#6b7a99">Pivot: <b style="color:#1a1a2e">{result.pivot:,.0f}</b></div>
  <div style="color:#6b7a99">Support: <b style="color:#1b7a2e">{result.support:,.0f}</b></div>
  <div style="color:#6b7a99">Resistance: <b style="color:#c0392b">{result.resistance:,.0f}</b></div>
</div>
</div>""", unsafe_allow_html=True)

    for chk in result.checks:
        icon  = "&#9989;" if chk.passed else "&#10060;"
        tcol  = "#1b7a2e" if chk.passed else "#c0392b"
        st.markdown(f"""
<div style="display:flex;align-items:flex-start;padding:6px 0;border-bottom:1px solid #e0e4ef">
  <span style="font-size:14px;margin-right:10px">{icon}</span>
  <div>
    <div style="color:{tcol};font-size:13px;font-weight:600">{chk.name}</div>
    <div style="color:#6b7a99;font-size:11px">{chk.detail}</div>
  </div>
</div>""", unsafe_allow_html=True)


def _verdict_badge(result) -> str:
    """One-line HTML badge for the summary table."""
    if result.error:
        return '<span style="color:#888">NO DATA</span>'
    color   = result.color
    verdict = result.verdict
    score   = result.score
    max_s   = result.max_score
    return (f'<span style="color:{color};font-weight:700">{verdict}</span>'
            f'<span style="color:#888;font-size:11px"> ({score}/{max_s})</span>')


def trend_compass_section():
    """Tab 3 — Trend Compass: Nifty & BankNifty weekly + monthly bias."""
    st.markdown("## &#128506; Trend Compass")
    st.markdown(
        "<div style='color:#888;font-size:13px;margin-bottom:16px'>"
        "9-point rule-based checklist &mdash; EMA alignment, price structure, RSI, pivot levels"
        "</div>",
        unsafe_allow_html=True,
    )

    compass = st.session_state.get("compass")
    if compass is None:
        st.warning("Trend Compass not initialized. Please reconnect.")
        return

    with st.spinner("Fetching weekly & monthly candles from Zerodha..."):
        try:
            results = compass.analyze_all()
        except Exception as exc:
            st.error(f"Error: {exc}")
            return

    # ── Summary verdict table ─────────────────────────────────────────────────
    st.markdown("### Quick Summary")

    nw  = results["NIFTY"]["Weekly"]
    nm  = results["NIFTY"]["Monthly"]
    bnw = results["BANKNIFTY"]["Weekly"]
    bnm = results["BANKNIFTY"]["Monthly"]

    nw_b  = _verdict_badge(nw)
    nm_b  = _verdict_badge(nm)
    bnw_b = _verdict_badge(bnw)
    bnm_b = _verdict_badge(bnm)

    st.markdown(f"""
<table style="width:100%;border-collapse:collapse;font-size:14px;margin-bottom:24px">
<thead>
<tr style="background:#f0f3fa;color:#3a4a6b;font-size:12px">
  <th style="padding:10px;text-align:left;border-bottom:1px solid #e0e4ef">Symbol</th>
  <th style="padding:10px;text-align:center;border-bottom:1px solid #e0e4ef">Weekly Trend</th>
  <th style="padding:10px;text-align:center;border-bottom:1px solid #e0e4ef">Monthly Trend</th>
  <th style="padding:10px;text-align:center;border-bottom:1px solid #e0e4ef">Overall Bias</th>
</tr>
</thead>
<tbody>
<tr style="background:#ffffff">
  <td style="padding:10px;color:#1a1a2e;font-weight:700">NIFTY 50</td>
  <td style="padding:10px;text-align:center">{nw_b}</td>
  <td style="padding:10px;text-align:center">{nm_b}</td>
  <td style="padding:10px;text-align:center;font-size:13px;color:#6b7a99">
    {_overall_bias(nw, nm)}
  </td>
</tr>
<tr style="background:#f8f9fd">
  <td style="padding:10px;color:#1a1a2e;font-weight:700">BANK NIFTY</td>
  <td style="padding:10px;text-align:center">{bnw_b}</td>
  <td style="padding:10px;text-align:center">{bnm_b}</td>
  <td style="padding:10px;text-align:center;font-size:13px;color:#6b7a99">
    {_overall_bias(bnw, bnm)}
  </td>
</tr>
</tbody>
</table>""", unsafe_allow_html=True)

    # ── Trading rule box ──────────────────────────────────────────────────────
    st.markdown("""
<div style="background:#f0fff4;border:1px solid #aaecc0;border-radius:8px;padding:14px;margin-bottom:20px;font-size:13px;color:#2a4a2a">
<b style="color:#1b7a2e">&#128273; Trading Rules</b><br><br>
&#8226; <b>Both Weekly + Monthly BULLISH</b> &#8594; Buy Calls / Bull Spreads / Sell Puts<br>
&#8226; <b>Weekly BULLISH, Monthly NEUTRAL</b> &#8594; Cautious longs, tight SL<br>
&#8226; <b>Weekly BEARISH, Monthly BULLISH</b> &#8594; Wait for weekly reversal before buying<br>
&#8226; <b>Both BEARISH</b> &#8594; Buy Puts / Bear Spreads / Sell Calls<br>
&#8226; <b>NEUTRAL on both</b> &#8594; Sell straddle/strangle (range-bound market)
</div>""", unsafe_allow_html=True)

    # ── Detailed checklists ───────────────────────────────────────────────────
    st.markdown("### Detailed Checklist")

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("#### NIFTY 50")
        wtab, mtab = st.tabs(["Weekly", "Monthly"])
        with wtab:
            _render_checklist(results["NIFTY"]["Weekly"])
        with mtab:
            _render_checklist(results["NIFTY"]["Monthly"])

    with c2:
        st.markdown("#### BANK NIFTY")
        wtab2, mtab2 = st.tabs(["Weekly", "Monthly"])
        with wtab2:
            _render_checklist(results["BANKNIFTY"]["Weekly"])
        with mtab2:
            _render_checklist(results["BANKNIFTY"]["Monthly"])

    # ── Last refreshed ────────────────────────────────────────────────────────
    ts = datetime.now().strftime("%H:%M:%S")
    st.markdown(
        f"<div style='color:#555;font-size:11px;margin-top:8px'>Last refreshed: {ts}</div>",
        unsafe_allow_html=True,
    )


def _overall_bias(weekly_r, monthly_r) -> str:
    """Returns a short HTML bias string from weekly + monthly verdicts."""
    if weekly_r.error or monthly_r.error:
        return '<span style="color:#888">N/A</span>'
    w = weekly_r.score / weekly_r.max_score if weekly_r.max_score else 0
    m = monthly_r.score / monthly_r.max_score if monthly_r.max_score else 0
    combined = (w + m) / 2
    if combined >= 0.70:
        return '<span style="color:#00c853;font-weight:700">TRADE LONG</span>'
    elif combined >= 0.50:
        return '<span style="color:#69f0ae">LEAN LONG</span>'
    elif combined >= 0.40:
        return '<span style="color:#ffeb3b">WAIT / HEDGE</span>'
    elif combined >= 0.25:
        return '<span style="color:#ff6b35">LEAN SHORT</span>'
    else:
        return '<span style="color:#ff1744;font-weight:700">TRADE SHORT</span>'


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — ADVANCED SIGNALS FRAGMENT (auto-refresh every 60s)
# ══════════════════════════════════════════════════════════════════════════════
@st.fragment(run_every=60)
def advanced_signals_section(symbol: str, expiry: str):
    """
    Tab 2 — Advanced signals panel.
    Reuses last known cache from Tab 1 (session_state) if available,
    otherwise fetches independently.
    Only additional API call: SMI candles (5-min today).
    """
    # ── Reuse Tab 1 cache if fresh (< 90 sec old) ────────────────────────────
    last_cache = st.session_state.get("last_cache", {})
    cache      = last_cache if last_cache else fetch_all_data(symbol, expiry)

    gex_data = cache.get("gex_data", {})
    iv_data  = cache.get("iv_data",  {})

    # Update GEX history for acceleration calc (safe even if duplicate)
    if gex_data.get("total_gex") is not None:
        _update_gex_history(gex_data["total_gex"])

    # Calculate all 5 advanced signals
    with st.spinner("⚙️ Computing advanced signals..."):
        smi   = _calc_smi(symbol)
        # SMI result alert engine ke liye session_state me save karo
        if smi:
            st.session_state["smi_latest"] = smi
        ga    = _calc_gamma_acceleration()
        pin   = _calc_pin_probability(gex_data)
        em    = _calc_expected_move(iv_data, cache, symbol)
        kite  = st.session_state["kite"]
        cross = _calc_cross_assets(kite, cache.get("prices", {}))

    render_header(symbol, expiry, cache)

    # ── Row 1: SMI  +  Cross-Asset ────────────────────────────────────────────
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("### 🧠 Smart Money Index")
        render_smi(smi)
    with col_b:
        st.markdown("### 🌍 Cross-Asset Signals")
        render_cross_assets(cross)

    st.divider()

    # ── Row 2: Gamma Acceleration  +  Expected Move ───────────────────────────
    col_c, col_d = st.columns(2)
    with col_c:
        st.markdown("### ⚡ Gamma Acceleration")
        render_gamma_acceleration(ga)
    with col_d:
        st.markdown("### 📐 Expected Move Calculator")
        render_expected_move(em, symbol)

    st.divider()

    # ── Row 3: Strike Pinning (full width — bar chart needs space) ────────────
    st.markdown("### 🎯 Strike Pinning Probability")
    render_pin_probability(pin, symbol)

    # ── Footer ────────────────────────────────────────────────────────────────
    fetched = cache.get("fetched_at", "--")
    st.markdown(
        f"<div style='text-align:center;color:#333;font-size:11px;margin-top:16px'>"
        f"⚙️ Advanced signals computed at: {fetched}"
        f" &nbsp;|&nbsp; Auto-refresh: 60s &nbsp;|&nbsp; {symbol} · {expiry}"
        f"</div>",
        unsafe_allow_html=True
    )


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR (bahar hai — refresh se affect nahi hota)
# ══════════════════════════════════════════════════════════════════════════════
def render_topbar() -> str:
    """
    Sidebar hata ke top navigation bar — symbol + page dropdown + status.
    Returns: selected page name
    """
    # Hide sidebar + toggle button completely
    st.markdown("""<style>
    [data-testid="stSidebar"]{display:none!important}
    [data-testid="collapsedControl"]{display:none!important}
    </style>""", unsafe_allow_html=True)

    c_brand, c_sym, c_nav, c_status = st.columns([1, 1, 2, 2.5])

    with c_brand:
        st.markdown(
            "<div style='display:flex;align-items:center;gap:7px;padding:6px 0'>"
            "<div style='background:#2962ff;border-radius:6px;width:26px;height:26px;"
            "display:flex;align-items:center;justify-content:center;font-size:14px'>📈</div>"
            "<span style='font-size:13px;font-weight:700;color:#1a1a2e'>NSE F&amp;O</span>"
            "</div>",
            unsafe_allow_html=True
        )

    with c_sym:
        current     = st.session_state.get("symbol", "NIFTY")
        sym_options = ["NIFTY", "BANKNIFTY", "FINNIFTY"]
        new_sym     = st.selectbox("sym", sym_options,
                                   index=sym_options.index(current),
                                   label_visibility="collapsed")
        if new_sym != current:
            st.session_state["symbol"] = new_sym
            st.rerun()

    with c_nav:
        pages = ["📊  Live Dashboard", "🧠  Advanced Signals",
                 "🧭  Trend Compass",  "🔬  Backtester",
                 "📡  Stock Scanner"]
        page = st.selectbox("nav", pages, label_visibility="collapsed")

    with c_status:
        mkt     = get_market_status()
        dot_col = "#26a69a" if mkt == "OPEN" else ("#ffd740" if mkt == "PRE-OPEN" else "#ef5350")
        now_str = datetime.now().strftime("%H:%M:%S")
        try:
            summary  = st.session_state["trade_log"].get_daily_summary()
            pnl      = summary.get("gross_pnl", 0)
            pnl_col  = "#26a69a" if pnl >= 0 else "#ef5350"
            pnl_sym  = "▲" if pnl >= 0 else "▼"
            trades   = summary.get("total_trades", 0)
            wr       = summary.get("win_rate", 0)
            pnl_html = (
                f"<span style='color:{pnl_col};font-weight:600;font-size:13px'>"
                f"{pnl_sym} &#8377;{abs(pnl):,.0f}</span>"
                f"&nbsp;<span style='color:#aab0c0;font-size:11px'>"
                f"{trades}T &nbsp;WR {wr:.0f}%</span>"
            )
        except Exception:
            pnl_html = "<span style='color:#aab0c0;font-size:11px'>No trades</span>"

        st.markdown(
            f"<div style='display:flex;align-items:center;gap:10px;padding:6px 0'>"
            f"{pnl_html}"
            f"<span style='color:#e0e4ef'>|</span>"
            f"<span style='display:flex;align-items:center;gap:5px'>"
            f"<span style='width:7px;height:7px;border-radius:50%;background:{dot_col};"
            f"display:inline-block'></span>"
            f"<span style='color:#5a6a8a;font-size:12px'>{mkt}</span>"
            f"&nbsp;<span style='color:#b0b8cc;font-size:11px'>{now_str}</span>"
            f"</span></div>",
            unsafe_allow_html=True
        )

    st.markdown(
        "<hr style='margin:4px 0 12px;border:none;border-top:1px solid #e0e4ef'>",
        unsafe_allow_html=True
    )
    return page


# ══════════════════════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — BACKTESTER
# ══════════════════════════════════════════════════════════════════════════════

def render_backtester(symbol: str):
    """
    World-class Backtesting Tab.
    ─────────────────────────────
    Panel 1 : Data Collection Status
    Panel 2 : Configuration
    Panel 3 : Results — Summary, Equity Curve, Trade Table
    Panel 4 : Best Conditions Analysis
    Panel 5 : Walk-Forward Validation
    Panel 6 : Monte Carlo Robustness Test
    """
    st.markdown("## 🔬 Backtester — Signal Validator")
    st.caption(
        "System ne jo signals diye, unhe historically test karo. "
        "Real data, realistic costs, zero look-ahead bias."
    )

    snap_db    = st.session_state.get("snap_db")
    bt_engine  = st.session_state.get("bt_engine")

    if snap_db is None or bt_engine is None:
        st.error("Backtester initialize nahi hua. Dashboard restart karo.")
        return

    # ── Panel 1: Data Collection Status ──────────────────────────────────────
    with st.expander("📦 Data Collection Status", expanded=True):
        stats = snap_db.get_stats()
        total = stats.get("total_snapshots", 0)

        col1, col2, col3 = st.columns(3)
        col1.metric("Total Snapshots", f"{total:,}")
        col2.metric("Signals Logged", f"{stats.get('total_signals', 0):,}")

        by_sym = {r["symbol"]: r for r in stats.get("by_symbol", [])}
        sym_data = by_sym.get(symbol, {})
        col3.metric(
            f"{symbol} Data",
            f"{sym_data.get('n', 0):,} snapshots"
        )

        if total == 0:
            st.warning(
                "⏳ Abhi tak koi data collect nahi hua.\n\n"
                "**Kya karo:** Dashboard ko Live tab pe open rakho — "
                "har 5 minute mein automatically data save hota rahega. "
                "3-4 din baad backtesting shuru kar sakte ho!"
            )
        else:
            avail = snap_db.get_available_dates(symbol)
            if avail:
                st.success(
                    f"✅ **{symbol}** data available: "
                    f"`{avail.get('first', '?')}` to `{avail.get('last', '?')}` "
                    f"({avail.get('total', 0):,} snapshots)"
                )
            st.info(
                "💡 **Tip:** Jitna zyada data, utna reliable backtest. "
                "1 mahine ka data = 2,000+ snapshots = solid results!"
            )

    st.divider()

    # ── Panel 2: Configuration ────────────────────────────────────────────────
    st.markdown("### ⚙️ Backtest Configuration")

    avail_dates = snap_db.get_available_dates(symbol)
    default_from = avail_dates.get("first", "2025-01-01")
    default_to   = avail_dates.get("last",  "2025-12-31")

    with st.form("bt_config_form"):
        c1, c2 = st.columns(2)
        with c1:
            from_date = st.text_input(
                "From Date (YYYY-MM-DD)", value=default_from,
                help="Start date for backtest"
            )
            min_score = st.slider(
                "Min Confidence Score", 20, 80, 30, 5,
                help="Minimum signal score to trade"
            )
            min_pcr = st.number_input(
                "Min PCR (BUY CE)", value=1.2, step=0.1,
                help="PCR below this → skip BUY CE"
            )

        with c2:
            to_date = st.text_input(
                "To Date (YYYY-MM-DD)", value=default_to,
                help="End date for backtest"
            )
            max_vix = st.slider(
                "Max VIX", 10.0, 30.0, 20.0, 0.5,
                help="Skip trades if VIX above this"
            )
            lots = st.number_input(
                "Lots per Trade", value=1, min_value=1, max_value=10,
                help="Lot size for simulation"
            )

        c3, c4 = st.columns(2)
        with c3:
            entry_start = st.selectbox(
                "Entry Window Start",
                ["09:30", "09:45", "10:00", "10:15", "10:30"],
                index=1
            )
        with c4:
            entry_end = st.selectbox(
                "Entry Window End",
                ["10:30", "11:00", "11:30", "12:00"],
                index=2
            )

        use_wf = st.checkbox(
            "Walk-Forward Validation", value=True,
            help="Split data into Train/Validate/Test — prevents curve-fitting"
        )
        mc_runs = st.select_slider(
            "Monte Carlo Iterations",
            options=[100, 500, 1000, 2000, 5000],
            value=1000,
            help="More iterations = more reliable robustness score"
        )

        run_btn = st.form_submit_button(
            "🚀 Run Backtest",
            use_container_width=True,
            type="primary"
        )

    if not run_btn:
        st.info("👆 Configuration set karo aur **Run Backtest** dabao!")
        return

    # ── Run ───────────────────────────────────────────────────────────────────
    config = BacktestConfig(
        symbol           = symbol,
        from_date        = from_date,
        to_date          = to_date,
        min_score        = min_score,
        max_vix          = max_vix,
        min_pcr_bull     = float(min_pcr),
        lots             = int(lots),
        entry_start      = entry_start,
        entry_end        = entry_end,
        use_walk_forward = use_wf,
        monte_carlo_runs = mc_runs,
    )

    with st.spinner("🔬 Backtesting chal raha hai..."):
        result = bt_engine.run(config)

    if result.error:
        st.error(f"❌ {result.error}")
        return

    an = result.analytics
    st.divider()

    # ── Panel 3: Summary ──────────────────────────────────────────────────────
    st.markdown("### 📊 Results Summary")

    # Color coding
    wr_color  = "#00c853" if an.win_rate >= 55 else ("#ffd740" if an.win_rate >= 45 else "#ff1744")
    pf_color  = "#00c853" if an.profit_factor >= 1.5 else ("#ffd740" if an.profit_factor >= 1.0 else "#ff1744")
    roi_color = "#00c853" if an.roi_pct > 0 else "#ff1744"

    st.markdown(f"""
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px">
      <div style="background:#f8f9fd;border:1px solid #e0e4ef;border-radius:10px;padding:16px;text-align:center">
        <div style="color:#6b7a99;font-size:12px">Total Trades</div>
        <div style="font-size:28px;font-weight:bold;color:#1a1a2e">{an.total_trades}</div>
        <div style="color:#8a96b0;font-size:11px">{an.wins}W / {an.losses}L</div>
      </div>
      <div style="background:#f8f9fd;border:1px solid #e0e4ef;border-radius:10px;padding:16px;text-align:center">
        <div style="color:#6b7a99;font-size:12px">Win Rate</div>
        <div style="font-size:28px;font-weight:bold;color:{wr_color}">{an.win_rate}%</div>
        <div style="color:#8a96b0;font-size:11px">Avg Win {an.avg_win_pct:+.1f}% / Loss {an.avg_loss_pct:+.1f}%</div>
      </div>
      <div style="background:#f8f9fd;border:1px solid #e0e4ef;border-radius:10px;padding:16px;text-align:center">
        <div style="color:#6b7a99;font-size:12px">Profit Factor</div>
        <div style="font-size:28px;font-weight:bold;color:{pf_color}">{an.profit_factor}</div>
        <div style="color:#8a96b0;font-size:11px">&gt;1.5 = Good | &gt;2.0 = Excellent</div>
      </div>
      <div style="background:#f8f9fd;border:1px solid #e0e4ef;border-radius:10px;padding:16px;text-align:center">
        <div style="color:#6b7a99;font-size:12px">Total P&amp;L</div>
        <div style="font-size:28px;font-weight:bold;color:{roi_color}">₹{an.total_pnl_rs:,.0f}</div>
        <div style="color:#8a96b0;font-size:11px">ROI {an.roi_pct:+.1f}%</div>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px">
      <div style="background:#f8f9fd;border:1px solid #e0e4ef;border-radius:10px;padding:16px;text-align:center">
        <div style="color:#6b7a99;font-size:12px">Max Drawdown</div>
        <div style="font-size:22px;font-weight:bold;color:#c0392b">₹{an.max_drawdown_rs:,.0f}</div>
      </div>
      <div style="background:#f8f9fd;border:1px solid #e0e4ef;border-radius:10px;padding:16px;text-align:center">
        <div style="color:#6b7a99;font-size:12px">Sharpe Ratio</div>
        <div style="font-size:22px;font-weight:bold;color:#1a56db">{an.sharpe_ratio}</div>
        <div style="color:#8a96b0;font-size:11px">&gt;1.0 = Good</div>
      </div>
      <div style="background:#f8f9fd;border:1px solid #e0e4ef;border-radius:10px;padding:16px;text-align:center">
        <div style="color:#6b7a99;font-size:12px">Expectancy / Trade</div>
        <div style="font-size:22px;font-weight:bold;color:#1a56db">₹{an.expectancy_rs:,.0f}</div>
      </div>
      <div style="background:#f8f9fd;border:1px solid #e0e4ef;border-radius:10px;padding:16px;text-align:center">
        <div style="color:#6b7a99;font-size:12px">Max Streak</div>
        <div style="font-size:22px;font-weight:bold;color:#1a1a2e">
          🟢{an.max_win_streak}  🔴{an.max_loss_streak}
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Exit reason breakdown
    ec1, ec2, ec3 = st.columns(3)
    ec1.metric("🎯 Target Hit",  f"{an.target_hit_rate:.1f}%")
    ec2.metric("🛑 SL Hit",      f"{an.sl_hit_rate:.1f}%")
    ec3.metric("⏱️ Time Exit",   f"{an.time_exit_rate:.1f}%")

    st.divider()

    # ── Equity Curve ──────────────────────────────────────────────────────────
    if result.equity_curve and PLOTLY_OK:
        st.markdown("### 📈 Equity Curve")
        import plotly.graph_objects as go
        eq = result.equity_curve
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x     = [f"{e['date']} {e['time']}" for e in eq],
            y     = [e["equity"] for e in eq],
            mode  = "lines",
            name  = "Portfolio Value",
            line  = dict(color="#00c853", width=2),
            fill  = "tozeroy",
            fillcolor = "rgba(0,200,83,0.1)",
        ))
        fig.update_layout(
            paper_bgcolor = "#ffffff",
            plot_bgcolor  = "#f8f9fd",
            font          = dict(color="#1a1a2e"),
            xaxis         = dict(title="Time", gridcolor="#e0e4ef"),
            yaxis         = dict(title="Portfolio Value (₹)", gridcolor="#e0e4ef"),
            height        = 350,
            margin        = dict(l=10, r=10, t=30, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)

    # ── Daily P&L Bar Chart ───────────────────────────────────────────────────
    if result.daily_pnl and PLOTLY_OK:
        st.markdown("### 📅 Daily P&L")
        dp = result.daily_pnl
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            x     = [d["date"] for d in dp],
            y     = [d["pnl"]  for d in dp],
            marker_color = [
                "#00c853" if d["pnl"] >= 0 else "#ff1744"
                for d in dp
            ],
            name = "Daily P&L",
        ))
        fig2.update_layout(
            paper_bgcolor = "#ffffff",
            plot_bgcolor  = "#f8f9fd",
            font          = dict(color="#1a1a2e"),
            xaxis         = dict(gridcolor="#e0e4ef"),
            yaxis         = dict(title="P&L (₹)", gridcolor="#e0e4ef"),
            height        = 280,
            margin        = dict(l=10, r=10, t=20, b=10),
        )
        st.plotly_chart(fig2, use_container_width=True)

    # ── Trade Table ───────────────────────────────────────────────────────────
    st.markdown("### 📋 Trade Log")
    if result.trades:
        import pandas as pd
        rows = []
        for t in result.trades:
            rows.append({
                "Date":      t.date,
                "Time":      t.time,
                "Signal":    t.direction,
                "Strike":    t.strike,
                "Entry ₹":   t.entry_price,
                "Exit ₹":    t.exit_price,
                "Exit":      t.exit_reason,
                "P&L %":     f"{t.pnl_pct:+.1f}%",
                "P&L ₹":     f"₹{t.pnl_rs:+,.0f}",
                "Score":     t.score,
                "VIX":       t.vix,
                "PCR":       t.pcr,
            })
        df = pd.DataFrame(rows)
        st.dataframe(
            df,
            use_container_width = True,
            height              = 300,
        )

        # Download button
        csv = df.to_csv(index=False)
        st.download_button(
            "⬇️ Download Trade Log (CSV)",
            data      = csv,
            file_name = f"backtest_{symbol}_{from_date}_{to_date}.csv",
            mime      = "text/csv",
        )

    st.divider()

    # ── Panel 4: Best Conditions ──────────────────────────────────────────────
    st.markdown("### 🏆 Best Conditions Analysis")
    st.caption("Konsa combination sabse zyada kaam karta hai?")

    bc = result.best_conditions
    cond_tabs = st.tabs(["PCR", "VIX", "Time", "Score", "Exit", "IV Rank"])

    def _cond_table(data: dict):
        if not data:
            st.caption("Data nahi hai.")
            return
        rows = []
        for label, v in data.items():
            if v:
                wr = v.get("win_rate", 0)
                rows.append({
                    "Condition": label,
                    "Trades":    v.get("count", 0),
                    "Win Rate":  f"{wr:.1f}%",
                    "Total P&L": f"₹{v.get('total_pnl', 0):+,.0f}",
                    "Avg P&L":   f"₹{v.get('avg_pnl', 0):+,.0f}",
                    "Verdict":   "✅ Best" if wr >= 60 else ("⚠️ OK" if wr >= 45 else "❌ Avoid"),
                })
        if rows:
            import pandas as pd
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with cond_tabs[0]: _cond_table(bc.get("by_pcr", {}))
    with cond_tabs[1]: _cond_table(bc.get("by_vix", {}))
    with cond_tabs[2]: _cond_table(bc.get("by_time", {}))
    with cond_tabs[3]: _cond_table(bc.get("by_score", {}))
    with cond_tabs[4]: _cond_table(bc.get("by_exit", {}))
    with cond_tabs[5]: _cond_table(bc.get("by_iv_rank", {}))

    st.divider()

    # ── Panel 5: Walk-Forward ─────────────────────────────────────────────────
    if result.walk_forward:
        st.markdown("### 🔄 Walk-Forward Validation")
        st.caption(
            "Data ko 3 periods mein split kiya — Train → Validate → Test. "
            "Teeno mein consistent results = strategy robust hai!"
        )
        import pandas as pd
        wf_rows = []
        for w in result.walk_forward:
            pf = w.get("profit_factor", 0)
            wr = w.get("win_rate", 0)
            wf_rows.append({
                "Period":         w.get("period", ""),
                "Date Range":     w.get("date_range", ""),
                "Snapshots":      w.get("snapshots", 0),
                "Trades":         w.get("trades", 0),
                "Win Rate":       f"{wr:.1f}%",
                "Profit Factor":  f"{pf:.2f}",
                "Total P&L":      f"₹{w.get('total_pnl_rs', 0):+,.0f}",
                "ROI":            f"{w.get('roi_pct', 0):+.1f}%",
                "Max Drawdown":   f"₹{w.get('max_dd_rs', 0):,.0f}",
                "Result":         "✅ Robust" if wr >= 50 and pf >= 1.2 else "⚠️ Inconsistent",
            })
        st.dataframe(
            pd.DataFrame(wf_rows),
            use_container_width = True,
            hide_index          = True,
        )
        # Consistency verdict
        consistent = sum(
            1 for w in result.walk_forward
            if w.get("win_rate", 0) >= 50 and w.get("profit_factor", 0) >= 1.2
        )
        total_periods = len(result.walk_forward)
        if consistent == total_periods:
            st.success(f"🎯 Strategy {total_periods}/{total_periods} periods mein consistent — ROBUST hai!")
        elif consistent >= total_periods // 2:
            st.warning(f"⚠️ Strategy {consistent}/{total_periods} periods mein consistent — Theek hai but monitor karo.")
        else:
            st.error(f"❌ Strategy sirf {consistent}/{total_periods} periods mein kaam ki — Curve-fitting ho sakta hai!")

    st.divider()

    # ── Panel 6: Monte Carlo ──────────────────────────────────────────────────
    if result.monte_carlo:
        st.markdown("### 🎲 Monte Carlo Robustness Test")
        mc = result.monte_carlo
        st.caption(
            f"{mc.get('iterations', 0):,} random simulations — "
            "bad luck worst case scenario test."
        )

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric(
            "Profitable Probability",
            f"{mc.get('prob_profitable', 0):.1f}%",
            help="Kitni baar strategy profitable rahi?"
        )
        m2.metric(
            "Median P&L",
            f"₹{mc.get('pnl_median', 0):+,.0f}",
            help="50% scenarios mein yeh result"
        )
        m3.metric(
            "Best 5% Scenario",
            f"₹{mc.get('pnl_95th_pct', 0):+,.0f}",
            help="Top 5% lucky scenarios"
        )
        m4.metric(
            "Worst 5% Scenario",
            f"₹{mc.get('pnl_5th_pct', 0):+,.0f}",
            help="Bottom 5% unlucky scenarios"
        )
        m5.metric(
            "Worst Drawdown",
            f"₹{mc.get('worst_dd_rs', 0):,.0f}",
            help="Absolute worst drawdown across all simulations"
        )

        prob = mc.get("prob_profitable", 0)
        if prob >= 80:
            st.success(f"✅ Monte Carlo: {prob:.1f}% simulations profitable — Strategy ROBUST hai!")
        elif prob >= 60:
            st.warning(f"⚠️ Monte Carlo: {prob:.1f}% simulations profitable — Theek hai.")
        else:
            st.error(f"❌ Monte Carlo: Sirf {prob:.1f}% simulations profitable — Strategy shaky hai.")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    # Import check
    if not IMPORTS_OK:
        st.error(f"❌ Import failed: {IMPORT_ERROR}")
        st.code("pip install kiteconnect rich scipy openpyxl pandas streamlit")
        st.stop()

    # Session init
    if not init_session():
        st.stop()

    kite = st.session_state["kite"]

    # Token check
    if not kite.is_connected():
        st.warning("⚠️ Kite token expired ya nahi hai!")
        st.markdown("""
        ### 🔑 Pehle token generate karo:
        ```
        cd D:\\HDFC\\nse_fo_system
        python get_token.py
        ```
        Token banne ke baad **yahan click karo:**
        """)
        if st.button("🔄 Retry Connection", use_container_width=True):
            for key in ["kite", "pcr", "mp", "uoa", "risk", "trade_log"]:
                st.session_state.pop(key, None)
            st.rerun()
        st.stop()

    # Symbol & expiry
    symbol = st.session_state.get("symbol", "NIFTY")
    try:
        expiry = get_nearest_expiry(symbol, kite=kite.kite).isoformat()
    except Exception:
        expiry = get_nearest_expiry(symbol).isoformat()

    # ── Top navigation bar (sidebar hata diya) ───────────────────────────────
    page = render_topbar()

    # ── Page routing ──────────────────────────────────────────────────────────
    if "Live Dashboard" in page:
        live_data_section(symbol, expiry)

    elif "Advanced Signals" in page:
        advanced_signals_section(symbol, expiry)

    elif "Trend Compass" in page:
        trend_compass_section()

    elif "Backtester" in page:
        render_backtester(symbol)

    elif "Stock Scanner" in page:
        render_stock_scanner(kite)


if __name__ == "__main__":
    main()
