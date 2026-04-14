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
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #ffffff; }

    div[data-testid="metric-container"] {
        background-color: #1e2130;
        border: 1px solid #2d3250;
        border-radius: 8px;
        padding: 12px;
    }
    div[data-testid="metric-container"] label {
        color: #888 !important; font-size: 12px;
    }
    div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
        font-size: 22px; font-weight: bold;
    }
    .stDataFrame { border-radius: 8px; }
    h1 { color: #00d4ff !important; }
    h2, h3 { color: #7fb3f5 !important; }
    #MainMenu { visibility: hidden; }
    footer    { visibility: hidden; }
    header    { visibility: hidden; }
    div[data-testid="stExpander"] {
        background-color: #1e2130;
        border-radius: 8px;
    }
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
            sym_exp = get_nearest_expiry(sym, kite=kite.kite).isoformat()
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

    # ── Run all in parallel ───────────────────────────────────────────────────
    TIMEOUT = 20   # seconds — agar koi thread hang kare toh 20s baad skip

    with ThreadPoolExecutor(max_workers=8) as ex:
        f_prices   = ex.submit(_fetch_prices)
        f_oi       = ex.submit(_fetch_oi_chain)
        f_mp       = ex.submit(_fetch_max_pain)
        f_pcr_n    = ex.submit(_fetch_pcr, "NIFTY")
        f_pcr_bn   = ex.submit(_fetch_pcr, "BANKNIFTY")
        f_uoa      = ex.submit(_fetch_uoa)
        f_risk     = ex.submit(_fetch_risk)
        f_vp       = ex.submit(_fetch_vp)

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
    <div style="background:#1a1f3a;padding:12px 20px;border-radius:10px;
                border:1px solid #2d3250;margin-bottom:16px;
                display:flex;justify-content:space-between;align-items:center;
                flex-wrap:wrap;gap:8px;">
        <span style="font-size:20px;font-weight:bold;color:#00d4ff;">
            📈 NSE F&amp;O Live Dashboard
        </span>
        <span>
            <span style="color:{s_color};font-weight:bold;">● {status}</span>
            &nbsp;&nbsp;
            <span style="color:#7fb3f5;font-weight:bold;">{symbol}</span>
            &nbsp;|&nbsp;
            <span style="color:#ccc;font-size:13px;">Expiry:
                <b style="color:#00d4ff">{expiry}</b>
            </span>
        </span>
        <span>
            <span style="color:{pnl_col};font-weight:bold;">
                Day P&amp;L: {pnl_str}
            </span>
            &nbsp;|&nbsp;
            <span style="color:#aaa;font-size:13px;">Trades: {trades}</span>
            &nbsp;|&nbsp;
            <span style="color:#555;font-size:12px;">🔄 {fetched}</span>
        </span>
    </div>
    """, unsafe_allow_html=True)


def render_market_overview(cache):
    prices  = cache.get("prices", {})
    entries = [
        ("NSE:NIFTY 50",          "📊 NIFTY 50",   False),
        ("NSE:NIFTY BANK",        "🏦 NIFTY BANK",  False),
        ("NSE:NIFTY FIN SERVICE", "💹 FIN NIFTY",   False),
        ("NSE:INDIA VIX",         "⚡ INDIA VIX",    True),
    ]
    cols = st.columns(4)
    for col, (key, label, is_vix) in zip(cols, entries):
        ltp = prices.get(key, 0)
        with col:
            if is_vix and ltp:
                note  = "High Fear!" if ltp > 20 else ("Low Vol" if ltp < 14 else "Moderate")
                st.metric(label, f"{ltp:,.2f}", note,
                          delta_color="inverse" if ltp > 20 else "normal")
            else:
                st.metric(label, f"₹{ltp:,.2f}" if ltp else "—")


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
        sig_c = "#00c853" if mp_result.signal == "BULLISH" else (
                "#ff1744" if mp_result.signal == "BEARISH" else "#ffd740")
        st.markdown(f"""
        <div style="background:#1a2a3a;padding:8px 16px;border-radius:8px;
                    margin-bottom:8px;font-size:13px;">
            🎯 <b>Max Pain:</b> {int(mp_result.max_pain_strike)}
            &nbsp;|&nbsp;
            🟢 <b>Support:</b> {int(mp_result.top_pe_oi_strike)}
            &nbsp;|&nbsp;
            🔴 <b>Resist:</b> {int(mp_result.top_ce_oi_strike)}
            &nbsp;|&nbsp;
            Signal: <b style="color:{sig_c}">{mp_result.signal}</b>
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

    df       = pd.DataFrame(rows)
    atm_mask = df["_atm"].tolist()
    df       = df.drop(columns=["_atm"])

    def highlight(row):
        if atm_mask[row.name]:
            # Bright white text on green bg — clearly visible
            return ["background-color:#1a4a00;color:#ffffff;font-weight:bold"] * len(row)
        return [""] * len(row)

    st.dataframe(df.style.apply(highlight, axis=1),
                 use_container_width=True, height=400, hide_index=True)


def render_uoa(cache):
    alerts = cache.get("uoa_alerts", [])
    if not alerts:
        st.markdown("""
        <div style="background:#1e2130;border-radius:8px;padding:20px;text-align:center">
            <div style="font-size:28px">📡</div>
            <div style="color:#ffd740;font-weight:bold;margin-top:8px">
                Baseline collect ho rahi hai...
            </div>
            <div style="color:#888;font-size:12px;margin-top:6px">
                Pehli scan mein volume baseline set hoti hai.<br>
                60 seconds mein 2x+ unusual activity alerts aayenge.
            </div>
            <div style="color:#555;font-size:11px;margin-top:8px">
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
    <div style="background:#1a1f35;border-radius:8px;padding:12px 16px;margin-top:8px;
                font-size:12px;line-height:1.9">
        <span style="color:#aaa;font-weight:bold">SIGNAL GUIDE &nbsp;|&nbsp; </span>
        <span style="color:#ff9800">&#9888; DEEP ITM — INSTITUTIONAL</span>
        <span style="color:#666"> &nbsp;= 5%+ ITM &rarr; Hedge/Roll. Retail ke liye NOT actionable directly.</span>
        &nbsp;&nbsp;
        <span style="color:#40c4ff">&#9679; MILD ITM</span>
        <span style="color:#666"> = 2-5% ITM &rarr; Strong conviction but protected entry.</span>
        &nbsp;&nbsp;
        <span style="color:#00c853">&#9679; BULLISH / </span>
        <span style="color:#ff1744">&#9679; BEARISH</span>
        <span style="color:#666"> = ATM/OTM &rarr; Pure directional. Most actionable for retail.</span>
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
                f'<div style="background:#1e2130;border-radius:8px;padding:12px;'
                f'margin-bottom:8px;color:#555;">{sym} — fetching...</div>',
                unsafe_allow_html=True)
            continue
        r, trend = pcr_data[sym]
        color     = zone_col.get(r.zone, "#888")
        trend_ico = {"▲": "🟢 ▲", "▼": "🔴 ▼", "→": "⚪ →"}.get(trend, "")
        st.markdown(f"""
        <div style="background:#1e2130;border:1px solid #2d3250;
                    border-radius:8px;padding:12px;margin-bottom:8px;">
            <b style="color:#fff;font-size:15px">{sym}</b>
            &nbsp;&nbsp;
            <span style="font-size:24px;font-weight:bold;color:{color}">{r.pcr:.2f}</span>
            &nbsp;{trend_ico}&nbsp;
            <span style="background:{color}22;color:{color};
                         padding:2px 10px;border-radius:10px;
                         font-size:12px">{r.zone}</span>
            <br/>
            <span style="color:#aaa;font-size:12px">
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
        <div style="background:#1e2130;border-radius:8px;padding:12px;margin-bottom:6px">
            <div style="color:#aaa;font-size:12px">IV Rank</div>
            <div style="font-size:28px;font-weight:bold;color:{ivr_c}">{ivr:.0f}%</div>
            <div style="color:{ivr_c};font-size:12px">{ivr_t}</div>
        </div>
        <div style="background:#1e2130;border-radius:8px;padding:12px;margin-bottom:6px">
            <div style="color:#aaa;font-size:12px">IV Skew (PE−CE)</div>
            <div style="font-size:22px;font-weight:bold;color:{sk_c}">{skew:+.2f}%</div>
            <div style="color:{sk_c};font-size:12px">{sk_t}</div>
        </div>
        <div style="background:#1e2130;border-radius:8px;padding:12px">
            <div style="color:#aaa;font-size:12px">⏰ Theta Clock</div>
            <div style="font-size:20px;font-weight:bold;color:{th_c}">
                ₹{abs(theta):,.0f}/day
            </div>
            <div style="color:#555;font-size:11px">7d ≈ ₹{abs(theta)*7:,.0f}</div>
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
        <div style="background:#1e2130;border-radius:8px;padding:24px;text-align:center">
            <div style="font-size:36px">📭</div>
            <div style="color:#aaa;margin-top:8px">No open positions</div>
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
            <tr><td style="color:#aaa;padding:4px">Net Delta</td>
                <td style="color:{dc};font-weight:bold;text-align:right">
                    {snap.net_delta:+.4f}</td></tr>
            <tr><td style="color:#aaa;padding:4px">Net Theta</td>
                <td style="color:{tc};font-weight:bold;text-align:right">
                    ₹{snap.net_theta:+,.0f}/day</td></tr>
            <tr><td style="color:#aaa;padding:4px">Net Vega</td>
                <td style="color:#7fb3f5;font-weight:bold;text-align:right">
                    {snap.net_vega:+,.0f}</td></tr>
            <tr><td style="color:#aaa;padding:4px">Unrealised P&amp;L</td>
                <td style="color:{pc};font-weight:bold;text-align:right">
                    ₹{snap.unrealized_pnl:+,.0f}</td></tr>
            <tr><td style="color:#aaa;padding:4px">Positions</td>
                <td style="color:#fff;font-weight:bold;text-align:right">
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
    <div style="background:#1e2130;border:2px solid {color};border-radius:12px;
                padding:16px;margin-bottom:12px">
        <div style="display:flex;justify-content:space-between;align-items:center">
            <div>
                <span style="font-size:24px">{emoji}</span>
                <span style="font-size:20px;font-weight:bold;color:{color};
                             margin-left:8px">{regime}</span>
            </div>
            <div style="text-align:right">
                <div style="color:#aaa;font-size:11px">Net GEX (Cr)</div>
                <div style="font-size:24px;font-weight:bold;color:{color}">
                    {"+" if total >= 0 else ""}{total:.2f}
                </div>
            </div>
        </div>
        <div style="color:#888;font-size:12px;margin-top:8px">{desc}</div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;
                    gap:8px;margin-top:12px">
            <div style="background:#ffffff11;border-radius:8px;padding:8px;
                         text-align:center">
                <div style="color:#aaa;font-size:10px">🧲 Gamma Wall</div>
                <div style="font-size:16px;font-weight:bold;color:#ffd740">
                    {wall:,}</div>
                <div style="color:#555;font-size:10px">Strongest magnet</div>
            </div>
            <div style="background:#ffffff11;border-radius:8px;padding:8px;
                         text-align:center">
                <div style="color:#aaa;font-size:10px">🔄 Flip Level</div>
                <div style="font-size:16px;font-weight:bold;color:#7fb3f5">
                    {flip if flip else "—"}</div>
                <div style="color:#555;font-size:10px">GEX zero crossing</div>
            </div>
            <div style="background:#ffffff11;border-radius:8px;padding:8px;
                         text-align:center">
                <div style="color:#aaa;font-size:10px">📍 Spot</div>
                <div style="font-size:16px;font-weight:bold;color:#fff">
                    {spot:,.0f}</div>
                <div style="color:#555;font-size:10px">
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

    score_penalty = 0
    ce_warning    = ""
    pe_warning    = ""

    # ── Call Wall warning (for BUY CE) ────────────────────────────────────────
    if nearest_call:
        dist    = nearest_call[0] - atm
        oi_l    = to_l(nearest_call[1])
        strike  = nearest_call[0]
        if dist <= step:
            score_penalty -= 15
            ce_warning = f"🧱 Bahut badi CALL WALL {strike} pe ({oi_l}L OI) — Sirf {dist} pts door! Target block ho sakta hai"
        elif dist <= step * 2:
            score_penalty -= 8
            ce_warning = f"⚠️ Call Wall: {strike} pe {oi_l}L OI — {dist} pts door, thodi resistance milegi"
        else:
            ce_warning = f"✅ Resistance {strike} pe ({oi_l}L OI) — {dist} pts door, abhi path clear hai"

    # ── Put Wall warning (for BUY PE) ─────────────────────────────────────────
    if nearest_put:
        dist    = atm - nearest_put[0]
        oi_l    = to_l(nearest_put[1])
        strike  = nearest_put[0]
        if dist <= step:
            score_penalty -= 15
            pe_warning = f"🛡️ Bahut bada PUT WALL {strike} pe ({oi_l}L OI) — Sirf {dist} pts neeche! Market rok sakta hai"
        elif dist <= step * 2:
            score_penalty -= 8
            pe_warning = f"⚠️ Put Wall: {strike} pe {oi_l}L OI — {dist} pts neeche, support hai"
        else:
            pe_warning = f"✅ Support {strike} pe ({oi_l}L OI) — {dist} pts neeche, bearish move possible"

    return {
        "call_walls":    [(s, to_l(v)) for s, v in top_ce],
        "put_walls":     [(s, to_l(v)) for s, v in top_pe],
        "nearest_call":  (nearest_call[0], to_l(nearest_call[1])) if nearest_call else None,
        "nearest_put":   (nearest_put[0],  to_l(nearest_put[1]))  if nearest_put  else None,
        "ce_warning":    ce_warning,
        "pe_warning":    pe_warning,
        "score_penalty": score_penalty,
    }


# ══════════════════════════════════════════════════════════════════════════════
# TRADE SIGNAL ENGINE — Live data se automatic BUY/SELL/NO TRADE
# ══════════════════════════════════════════════════════════════════════════════
def generate_trade_signal(cache: dict, symbol: str) -> dict:
    """
    Smart Trade Signal Engine v2.0
    ─────────────────────────────────────────────────────────
    6 factors analyze karta hai:
      1. PCR value + trend
      2. OI Build signal (FL/FS/LU/SC)
      3. VIX level
      4. IV Rank
      5. GEX Regime
      6. Max Pain / Support / Resistance

    Smart Strike Selection:
      Score  > 60 + IV < 30  → 1 OTM strike (cheap + leveraged)
      Score 30–60             → ATM strike (safe)
      VIX > 20                → ATM only (safer in high fear)
      Sell mode               → OI-based resistance/support strikes
    """
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

    spot = prices.get(sym_map.get(symbol, ""), 0)
    vix  = prices.get("NSE:INDIA VIX", 0)

    if not spot:
        return {"signal": "NO TRADE", "reason": "Market data unavailable", "score": 0}

    score     = 0
    step      = 50 if symbol == "NIFTY" else 100
    atm       = round(spot / step) * step
    lot       = get_lot_size(symbol)
    MAX_LOSS  = 2000   # 2% of ₹1L

    # ── Factor checklist (dikhega dashboard mein) ─────────────────────────────
    factors = {}

    # ── 1. PCR ────────────────────────────────────────────────────────────────
    pcr_value = 0
    pcr_info  = pcr_data.get(symbol)
    pcr_trend = "→"
    if pcr_info:
        r, trend = pcr_info
        pcr_value = r.pcr
        pcr_trend = trend
        if r.pcr > 1.2:
            score += 20
            factors["PCR"] = ("✅", f"{r.pcr:.2f} {trend}", "Bullish", "#00c853")
        elif r.pcr < 0.8:
            score -= 20
            factors["PCR"] = ("❌", f"{r.pcr:.2f} {trend}", "Bearish", "#ff1744")
        else:
            factors["PCR"] = ("⚠️", f"{r.pcr:.2f} {trend}", "Neutral", "#ffd740")
        if trend == "▲":
            score += 15
        elif trend == "▼":
            score -= 15
    else:
        factors["PCR"] = ("⚠️", "N/A", "No data", "#555")

    # ── 2. OI Build Signal ────────────────────────────────────────────────────
    # Threshold = 5% of total OI at that strike (min 200, max 5000)
    # Fixed 500 ki jagah relative threshold — expiry week mein false signals nahi aayenge
    atm_build = "⚪"
    atm_ce_ltp = atm_pe_ltp = 0
    for row in oi_chain:
        if abs(row.strike - atm) <= step:
            atm_ce_ltp = row.ce_ltp
            atm_pe_ltp = row.pe_ltp
            total_oi_at_strike = (row.ce_oi or 0) + (row.pe_oi or 0)
            oi_threshold = max(200, min(5000, int(total_oi_at_strike * 0.05)))

            if row.ce_oi_chg > oi_threshold:
                atm_build = "FL"; score += 25
                factors["OI Build"] = ("✅", f"Fresh Long (+{row.ce_oi_chg:,})", "Bulls entering", "#00c853")
            elif row.pe_oi_chg > oi_threshold:
                atm_build = "FS"; score -= 25
                factors["OI Build"] = ("❌", f"Fresh Short (+{row.pe_oi_chg:,})", "Bears entering", "#ff1744")
            elif row.ce_oi_chg < -oi_threshold:
                atm_build = "LU"; score -= 10
                factors["OI Build"] = ("⚠️", f"Long Unwind ({row.ce_oi_chg:,})", "Bulls exiting", "#ff6d00")
            elif row.pe_oi_chg < -oi_threshold:
                atm_build = "SC"; score += 10
                factors["OI Build"] = ("✅", f"Short Cover ({row.pe_oi_chg:,})", "Bears exiting", "#00c853")
            else:
                factors["OI Build"] = ("⚪", f"Neutral (threshold {oi_threshold:,})", "No significant change", "#555")
            break
    if "OI Build" not in factors:
        factors["OI Build"] = ("⚪", "⚪", "Waiting for OI data", "#555")

    # ── 3. VIX ────────────────────────────────────────────────────────────────
    sell_mode = False
    if vix > 0:
        if vix < 15:
            score += 10
            factors["VIX"] = ("✅", f"{vix:.1f}", "Low fear — Buy ok", "#00c853")
        elif vix > 20:
            score -= 10
            sell_mode = True
            factors["VIX"] = ("⚠️", f"{vix:.1f}", "High fear — Sell premium", "#ffd740")
        else:
            factors["VIX"] = ("⚠️", f"{vix:.1f}", "Moderate", "#ffd740")
    else:
        factors["VIX"] = ("⚪", "N/A", "No data", "#555")

    # ── 4. IV Rank ────────────────────────────────────────────────────────────
    iv_rank = iv_data.get("iv_rank", 50)
    if iv_rank > 60:
        sell_mode = True
        factors["IV Rank"] = ("⚠️", f"{iv_rank:.0f}%", "Expensive — Sell", "#ffd740")
    elif iv_rank < 30:
        score += 10
        factors["IV Rank"] = ("✅", f"{iv_rank:.0f}%", "Cheap — Buy ok", "#00c853")
    else:
        factors["IV Rank"] = ("⚠️", f"{iv_rank:.0f}%", "Normal", "#ffd740")

    # ── 5. GEX ────────────────────────────────────────────────────────────────
    gex_regime = gex_data.get("regime",    "NEUTRAL")
    gex_total  = gex_data.get("total_gex", 0)
    gamma_wall = gex_data.get("gamma_wall", atm)
    flip_level = gex_data.get("flip_level", None)

    if gex_regime == "RANGE BOUND":
        score -= 10; sell_mode = True
        factors["GEX"] = ("⚠️", f"+{gex_total:.1f}Cr", "Range bound — Sell", "#ffd740")
    elif gex_regime == "VOLATILE / TRENDING":
        score += 10 if score > 0 else -10
        factors["GEX"] = ("✅", f"{gex_total:.1f}Cr", "Volatile — Buy ok", "#00c853")
    else:
        factors["GEX"] = ("⚪", f"{gex_total:.1f}Cr", "Neutral", "#555")

    # ── 6. Max Pain ───────────────────────────────────────────────────────────
    top_ce_oi = mp_result.top_ce_oi_strike if mp_result else int(atm + step * 4)
    top_pe_oi = mp_result.top_pe_oi_strike if mp_result else int(atm - step * 4)
    mp_strike = mp_result.max_pain_strike  if mp_result else atm

    mp_dist = abs(spot - mp_strike)
    if mp_dist < step * 2:
        factors["Max Pain"] = ("✅", f"{int(mp_strike)}", "Near ATM — Balanced", "#00c853")
    elif spot > mp_strike:
        factors["Max Pain"] = ("⚠️", f"{int(mp_strike)}", "Above MP — may pull down", "#ffd740")
    else:
        factors["Max Pain"] = ("⚠️", f"{int(mp_strike)}", "Below MP — may pull up", "#ffd740")

    # ── 7. Volume Profile POC ─────────────────────────────────────────────────
    vp_data   = cache.get("vp_data", {})
    poc_level = vp_data.get("poc")
    vp_step   = vp_data.get("step", step)
    if poc_level and spot:
        poc_dist = spot - poc_level
        if poc_dist > vp_step:          # Price above POC → Bullish
            score += 10
            factors["POC"] = ("✅", f"{poc_level}  ▲{poc_dist:.0f}pts",
                              "Price above POC — Bullish", "#00c853")
        elif poc_dist < -vp_step:       # Price below POC → Bearish
            score -= 10
            factors["POC"] = ("❌", f"{poc_level}  ▼{abs(poc_dist):.0f}pts",
                              "Price below POC — Bearish", "#ff1744")
        else:                           # At POC → key S/R
            factors["POC"] = ("⚠️", f"{poc_level}  ↔ AT POC",
                              "Strongest S/R — watch for breakout", "#ffd740")
    else:
        factors["POC"] = ("⚪", "N/A", "VP loading...", "#555")

    # ── OI Wall Detection — score adjust + factor add ────────────────────────
    oi_walls = _detect_oi_walls(oi_chain, spot, step)
    if oi_walls:
        penalty = oi_walls.get("score_penalty", 0)
        if score > 0:     # BUY CE direction
            score = max(0, score + penalty)
            ce_warn = oi_walls.get("ce_warning", "")
            if penalty < -10:
                factors["OI Wall"] = ("🧱", ce_warn, "Strong resistance — target block ho sakta hai", "#ff6d00")
            elif penalty < 0:
                factors["OI Wall"] = ("⚠️", ce_warn, "Resistance hai — thoda caution", "#ffd740")
            elif oi_walls.get("nearest_call"):
                factors["OI Wall"] = ("✅", ce_warn, "Path clear", "#00c853")
        elif score < 0:   # BUY PE direction
            score = min(0, score - penalty)   # penalty already negative
            pe_warn = oi_walls.get("pe_warning", "")
            if penalty < -10:
                factors["OI Wall"] = ("🛡️", pe_warn, "Strong support — bearish move rok sakta hai", "#ff6d00")
            elif penalty < 0:
                factors["OI Wall"] = ("⚠️", pe_warn, "Support hai — thoda caution", "#ffd740")
            elif oi_walls.get("nearest_put"):
                factors["OI Wall"] = ("✅", pe_warn, "Path clear", "#00c853")

    abs_score = abs(score)

    # ── NO TRADE ──────────────────────────────────────────────────────────────
    if abs_score < 30:
        return {
            "signal":  "NO TRADE",
            "reason":  "Signals mixed — setup clear nahi hai, wait karo",
            "score":   abs_score,
            "factors": factors,
            "vix":     vix,
            "pcr":     pcr_value,
            "build":   atm_build,
        }

    # ── SELL — Iron Condor ────────────────────────────────────────────────────
    if sell_mode and iv_rank > 55:
        # CE sell: top CE OI strike (natural resistance)
        sell_ce = int(top_ce_oi)
        sell_pe = int(top_pe_oi)

        # Gamma wall adjust — sell above wall for CE
        if gamma_wall and gamma_wall > sell_ce:
            sell_ce = int(gamma_wall) + step

        # Estimate premiums from OI chain
        ce_prem = pe_prem = 0
        for row in oi_chain:
            if int(row.strike) == sell_ce: ce_prem = row.ce_ltp
            if int(row.strike) == sell_pe: pe_prem = row.pe_ltp

        total_prem   = ce_prem + pe_prem
        max_profit_r = round(total_prem * lot)
        sl_premium   = round(total_prem * 2)

        return {
            "signal":       "SELL — Iron Condor",
            "sell_ce":      sell_ce,
            "sell_pe":      sell_pe,
            "ce_prem":      ce_prem,
            "pe_prem":      pe_prem,
            "total_prem":   round(total_prem, 1),
            "max_profit_r": max_profit_r,
            "sl_premium":   sl_premium,
            "sl_rule":      f"Exit agar koi bhi side ₹{sl_premium:.0f} ho jaye",
            "score":        min(abs_score + 20, 100),
            "factors":      factors,
            "vix":          vix,
            "pcr":          pcr_value,
            "iv_rank":      iv_rank,
            "timeframe":    "Weekly / Swing",
            "gamma_wall":   gamma_wall,
            "flip_level":   flip_level,
            "strike_reason": f"CE at Resistance ({sell_ce}), PE at Support ({sell_pe})",
        }

    # ── Smart Strike Selection for BUY ────────────────────────────────────────
    def _pick_strike_and_ltp(direction: str):
        """
        direction: 'CE' or 'PE'
        Returns (strike, ltp, reason)
        """
        # ATM is default
        chosen = atm
        reason = "ATM strike (safest)"

        # Strong signal + cheap IV → 1 OTM (more leverage)
        if abs_score >= 55 and iv_rank < 30 and vix < 18:
            if direction == "CE":
                chosen = atm + step
                reason = f"1 OTM ({atm+step}) — Strong signal + Cheap IV = More leverage"
            else:
                chosen = atm - step
                reason = f"1 OTM ({atm-step}) — Strong signal + Cheap IV = More leverage"

        # High VIX → stick to ATM
        elif vix > 20:
            chosen = atm
            reason = f"ATM ({atm}) — VIX high, ATM safer"

        # Near gamma wall → use wall strike
        elif gamma_wall and abs(atm - gamma_wall) <= step * 2:
            chosen = int(gamma_wall)
            reason = f"Gamma Wall ({int(gamma_wall)}) — Strongest magnet level"

        # Get LTP from OI chain
        ltp = 0
        for row in oi_chain:
            if int(row.strike) == chosen:
                ltp = row.ce_ltp if direction == "CE" else row.pe_ltp
                break

        # Fallback estimate
        if ltp <= 0:
            ltp = round(spot * 0.003)

        return int(chosen), ltp, reason

    # ── BUY CE ────────────────────────────────────────────────────────────────
    if score >= 30:
        strike, entry, strike_reason = _pick_strike_and_ltp("CE")
        entry  = max(entry, 5)
        target = round(entry * 1.42)
        sl     = round(entry * 0.72)
        sl_pts = entry - sl
        lots   = max(1, int(MAX_LOSS / (sl_pts * lot))) if sl_pts > 0 else 1

        return {
            "signal":        "BUY CE",
            "strike":        strike,
            "strike_reason": strike_reason,
            "entry":         entry,
            "target":        target,
            "sl":            sl,
            "gain_pct":      42,
            "loss_pct":      28,
            "lot_size":      lot,
            "lots":          lots,
            "max_loss":      round(sl_pts * lot * lots),
            "max_profit":    round((target - entry) * lot * lots),
            "score":         min(score, 100),
            "factors":       factors,
            "vix":           vix,
            "pcr":           pcr_value,
            "build":         atm_build,
            "iv_rank":       iv_rank,
            "timeframe":     "Intraday",
            "gamma_wall":    gamma_wall,
            "flip_level":    flip_level,
            "oi_walls":      oi_walls,
        }

    # ── BUY PE ────────────────────────────────────────────────────────────────
    if score <= -30:
        strike, entry, strike_reason = _pick_strike_and_ltp("PE")
        entry  = max(entry, 5)
        target = round(entry * 1.42)
        sl     = round(entry * 0.72)
        sl_pts = entry - sl
        lots   = max(1, int(MAX_LOSS / (sl_pts * lot))) if sl_pts > 0 else 1

        return {
            "signal":        "BUY PE",
            "strike":        strike,
            "strike_reason": strike_reason,
            "entry":         entry,
            "target":        target,
            "sl":            sl,
            "gain_pct":      42,
            "loss_pct":      28,
            "lot_size":      lot,
            "lots":          lots,
            "max_loss":      round(sl_pts * lot * lots),
            "max_profit":    round((target - entry) * lot * lots),
            "score":         min(abs_score, 100),
            "factors":       factors,
            "vix":           vix,
            "pcr":           pcr_value,
            "build":         atm_build,
            "iv_rank":       iv_rank,
            "timeframe":     "Intraday",
            "gamma_wall":    gamma_wall,
            "flip_level":    flip_level,
            "oi_walls":      oi_walls,
        }

    return {"signal": "NO TRADE", "reason": "Inconclusive", "score": abs_score,
            "factors": factors}


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
        <div style="background:#1a1a3a;border-top:3px solid #ffd740;
                    border-radius:8px;padding:10px;text-align:center">
            <div style="color:#888;font-size:10px;letter-spacing:1px">POC</div>
            <div style="color:#ffd740;font-size:20px;font-weight:bold">{poc}</div>
            <div style="color:#555;font-size:10px">Point of Control</div>
            <div style="color:#888;font-size:10px">{vp['poc_volume_pct']}% volume</div>
        </div>
        <div style="background:#1a1a3a;border-top:3px solid #00c8ff;
                    border-radius:8px;padding:10px;text-align:center">
            <div style="color:#888;font-size:10px;letter-spacing:1px">VAH</div>
            <div style="color:#00c8ff;font-size:20px;font-weight:bold">{vah}</div>
            <div style="color:#555;font-size:10px">Value Area High</div>
            <div style="color:#888;font-size:10px">Upper boundary</div>
        </div>
        <div style="background:#1a1a3a;border-top:3px solid #00c8ff;
                    border-radius:8px;padding:10px;text-align:center">
            <div style="color:#888;font-size:10px;letter-spacing:1px">VAL</div>
            <div style="color:#00c8ff;font-size:20px;font-weight:bold">{val}</div>
            <div style="color:#555;font-size:10px">Value Area Low</div>
            <div style="color:#888;font-size:10px">Lower boundary</div>
        </div>
        <div style="background:#1a1a3a;border-top:3px solid #ffffff33;
                    border-radius:8px;padding:10px;text-align:center">
            <div style="color:#888;font-size:10px;letter-spacing:1px">SPOT</div>
            <div style="color:#ffffff;font-size:20px;font-weight:bold">{spot_str}</div>
            <div style="color:#555;font-size:10px">Current Price</div>
        </div>
        <div style="background:#1a1a3a;border-top:3px solid {vp_sig[1]};
                    border-radius:8px;padding:10px;text-align:center">
            <div style="color:#888;font-size:10px;letter-spacing:1px">SIGNAL</div>
            <div style="color:{vp_sig[1]};font-size:14px;font-weight:bold">{vp_sig[0]}</div>
            <div style="color:#555;font-size:10px">Price vs POC</div>
        </div>
        <div style="background:#1a1a3a;border-top:3px solid #555;
                    border-radius:8px;padding:10px;text-align:center">
            <div style="color:#888;font-size:10px;letter-spacing:1px">VOLUME</div>
            <div style="color:#aaa;font-size:18px;font-weight:bold">{total_vol_str}</div>
            <div style="color:#555;font-size:10px">{vp['candle_count']} candles</div>
            <div style="color:#555;font-size:10px">VA: {vp['va_volume_pct']}%</div>
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
            label_colors.append("#ffffff")
            label_positions.append("inside")
        else:                              # narrow bar → text outside
            label_colors.append("#aaaaaa")
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

    # Spot price line — white solid
    if spot:
        fig.add_shape(type="line", x0=0, x1=1, xref="paper",
                      y0=spot, y1=spot,
                      line=dict(color="rgba(255,255,255,0.9)", width=2))
        fig.add_annotation(x=1.01, xref="paper", y=spot,
                           text=f"<b>▶ {spot:.0f}</b>", showarrow=False,
                           font=dict(color="#FFFFFF", size=11), xanchor="left")

    # Layout — Y-axis range must include spot price too
    y_min = min(levels) - step_sz * 3
    y_max = max(levels) + step_sz * 3
    if spot:
        y_min = min(y_min, spot - step_sz * 5)
        y_max = max(y_max, spot + step_sz * 5)
    visible_range = [y_min, y_max]
    fig.update_layout(
        paper_bgcolor="#0e1117",
        plot_bgcolor="#141820",
        font=dict(color="#aaaaaa", size=10, family="monospace"),
        xaxis=dict(
            title="Volume",
            gridcolor="#1e2130",
            showgrid=True,
            zeroline=False,
            tickformat=".2s",          # 1.2M, 450K etc.
        ),
        yaxis=dict(
            title="Price",
            gridcolor="#1e2130",
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
    <div style="background:#ffffff0a;border-left:4px solid {vp_sig[1]};
                border-radius:6px;padding:10px 16px;margin-top:2px">
        <span style="color:{vp_sig[1]};font-weight:bold;font-size:13px">
            {vp_sig[0]} &nbsp;—&nbsp;</span>
        <span style="color:#ccc;font-size:12px">{vp_sig[2]}</span>
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
    """6-factor checklist — Streamlit native columns (no raw HTML embedding)."""
    if not factors:
        return

    st.markdown(
        "<div style='color:#7fb3f5;font-size:12px;font-weight:bold;"
        "margin:10px 0 4px 0'>📋 Factor Checklist</div>",
        unsafe_allow_html=True,
    )

    for name, info in factors.items():
        icon, val, desc, clr = info
        c1, c2, c3, c4 = st.columns([1, 3, 3, 4])
        with c1:
            st.markdown(
                f"<div style='font-size:16px;padding-top:2px'>{icon}</div>",
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                f"<div style='color:#cccccc;font-size:12px;"
                f"padding-top:4px'>{name}</div>",
                unsafe_allow_html=True,
            )
        with c3:
            st.markdown(
                f"<div style='color:{clr};font-size:12px;"
                f"font-weight:bold;padding-top:4px'>{val}</div>",
                unsafe_allow_html=True,
            )
        with c4:
            st.markdown(
                f"<div style='color:#666666;font-size:11px;"
                f"padding-top:5px'>{desc}</div>",
                unsafe_allow_html=True,
            )


def render_trade_signal(cache: dict, symbol: str):
    sig   = generate_trade_signal(cache, symbol)
    s     = sig.get("signal", "NO TRADE")
    score = sig.get("score", 0)
    bar   = "█" * int(score // 5) + "░" * (20 - int(score // 5))

    # ── Signal color config ───────────────────────────────────────────────────
    cfg = {
        "BUY CE":             ("#00c853", "🟢", "#0a2a0a"),
        "BUY PE":             ("#ff6d00", "🔴", "#2a1000"),
        "SELL — Iron Condor": ("#7fb3f5", "💰", "#0a1a2a"),
        "NO TRADE":           ("#555555", "⛔", "#1e2130"),
    }
    color, icon, bg = cfg.get(s, cfg["NO TRADE"])

    # ── NO TRADE ──────────────────────────────────────────────────────────────
    if s == "NO TRADE":
        st.markdown(f"""
        <div style="background:{bg};border:2px solid #333;border-radius:12px;
                    padding:20px;text-align:center;margin-bottom:8px">
            <div style="font-size:36px">{icon}</div>
            <div style="font-size:22px;font-weight:bold;color:#555;margin-top:6px">
                NO TRADE</div>
            <div style="color:#888;font-size:13px;margin-top:8px">
                {sig.get('reason','Mixed signals — wait karo')}</div>
            <div style="color:#444;font-size:11px;margin-top:10px">
                Confidence: {score:.0f}% &nbsp;|&nbsp;
                VIX: {sig.get('vix',0):.1f} &nbsp;|&nbsp;
                PCR: {sig.get('pcr',0):.2f}
            </div>
        </div>""", unsafe_allow_html=True)
        _render_factor_checklist(sig.get("factors", {}))

    # ── BUY CE / BUY PE ───────────────────────────────────────────────────────
    elif s in ("BUY CE", "BUY PE"):
        strike_reason = sig.get("strike_reason", "ATM strike")
        gw = sig.get("gamma_wall")
        fl = sig.get("flip_level")
        gw_str = f"Gamma Wall: {int(gw)}" if gw else ""
        fl_str = f"Flip Level: {int(fl)}" if fl else ""
        levels_str = " &nbsp;|&nbsp; ".join(filter(None, [gw_str, fl_str]))

        st.markdown(f"""
        <div style="background:{bg};border:2px solid {color};border-radius:12px;padding:20px;margin-bottom:8px">
            <div style="display:flex;justify-content:space-between;align-items:center">
                <div>
                    <span style="font-size:30px">{icon}</span>
                    <span style="font-size:26px;font-weight:bold;color:{color};margin-left:8px">{s}</span>
                    <span style="font-size:20px;color:#ffffff;margin-left:8px">{sig.get('strike','')} Strike</span>
                </div>
                <div style="text-align:right">
                    <div style="color:#aaa;font-size:11px">Confidence</div>
                    <div style="font-size:22px;font-weight:bold;color:{color}">{score:.0f}%</div>
                    <div style="font-family:monospace;color:{color};font-size:10px">{bar}</div>
                </div>
            </div>
            <div style="margin-top:10px;padding:8px 12px;background:#ffffff11;border-left:3px solid {color};border-radius:4px">
                <span style="color:#aaa;font-size:11px">&#128205; Strike Selected: </span>
                <span style="color:#fff;font-size:12px">{strike_reason}</span>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:10px;margin-top:14px">
                <div style="background:#ffffff11;border-radius:8px;padding:10px;text-align:center">
                    <div style="color:#aaa;font-size:11px">ENTRY</div>
                    <div style="color:#fff;font-size:20px;font-weight:bold">&#8377;{sig.get('entry',0)}</div>
                    <div style="color:#555;font-size:10px">per lot</div>
                </div>
                <div style="background:#00c85322;border-radius:8px;padding:10px;text-align:center">
                    <div style="color:#aaa;font-size:11px">TARGET</div>
                    <div style="color:#00c853;font-size:20px;font-weight:bold">&#8377;{sig.get('target',0)}</div>
                    <div style="color:#00c853;font-size:10px">+{sig.get('gain_pct',0)}%</div>
                </div>
                <div style="background:#ff174422;border-radius:8px;padding:10px;text-align:center">
                    <div style="color:#aaa;font-size:11px">STOP LOSS</div>
                    <div style="color:#ff1744;font-size:20px;font-weight:bold">&#8377;{sig.get('sl',0)}</div>
                    <div style="color:#ff1744;font-size:10px">-{sig.get('loss_pct',0)}%</div>
                </div>
                <div style="background:#ffffff11;border-radius:8px;padding:10px;text-align:center">
                    <div style="color:#aaa;font-size:11px">LOTS</div>
                    <div style="color:#ffd740;font-size:20px;font-weight:bold">{sig.get('lots',1)}</div>
                    <div style="color:#555;font-size:10px">Max loss &#8377;{sig.get('max_loss',0):,.0f}</div>
                </div>
            </div>
            <div style="margin-top:10px;display:flex;justify-content:space-between;color:#666;font-size:11px">
                <span>Max Profit: <b style="color:#00c853">&#8377;{sig.get('max_profit',0):,.0f}</b></span>
                <span>&#9201; {sig.get('timeframe','Intraday')} &nbsp;|&nbsp; VIX: {sig.get('vix',0):.1f} &nbsp;|&nbsp; IV Rank: {sig.get('iv_rank',0):.0f}%</span>
                <span style="color:#555">{levels_str}</span>
            </div>
        </div>""", unsafe_allow_html=True)
        _render_factor_checklist(sig.get("factors", {}))

        # ── OI Wall Map — human readable ──────────────────────────────────────
        walls = sig.get("oi_walls", {})
        if walls:
            call_walls = walls.get("call_walls", [])
            put_walls  = walls.get("put_walls",  [])
            is_buy_ce  = (s == "BUY CE")

            st.markdown("#### 📊 Market Structure — OI Walls")
            col_r, col_s = st.columns(2)

            with col_r:
                st.markdown("**🧱 Resistance (Call Walls)**")
                if call_walls:
                    for i, (strike, oi_l) in enumerate(call_walls):
                        bar_len   = int(min(oi_l / max(w[1] for w in call_walls) * 10, 10))
                        bar       = "█" * bar_len + "░" * (10 - bar_len)
                        nearest   = (i == 0 and is_buy_ce)
                        tag       = " ← ⚠️ NEAREST" if nearest else ""
                        color_tag = "🔴" if nearest else "🟠"
                        st.markdown(
                            f"`{strike}`&nbsp; {color_tag} `{bar}` &nbsp;**{oi_l}L**{tag}"
                        )
                else:
                    st.caption("Data loading...")

            with col_s:
                st.markdown("**🛡️ Support (Put Walls)**")
                if put_walls:
                    for i, (strike, oi_l) in enumerate(put_walls):
                        bar_len   = int(min(oi_l / max(w[1] for w in put_walls) * 10, 10))
                        bar       = "█" * bar_len + "░" * (10 - bar_len)
                        nearest   = (i == 0 and not is_buy_ce)
                        tag       = " ← ⚠️ NEAREST" if nearest else ""
                        color_tag = "🔴" if nearest else "🟢"
                        st.markdown(
                            f"`{strike}`&nbsp; {color_tag} `{bar}` &nbsp;**{oi_l}L**{tag}"
                        )
                else:
                    st.caption("Data loading...")

            # Plain language warning
            warn = walls.get("ce_warning" if is_buy_ce else "pe_warning", "")
            if warn:
                penalty = walls.get("score_penalty", 0)
                if penalty <= -15:
                    st.error(warn)
                elif penalty <= -8:
                    st.warning(warn)
                else:
                    st.success(warn)

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
        _render_factor_checklist(sig.get("factors", {}))


# ══════════════════════════════════════════════════════════════════════════════
# ALERT HISTORY PANEL
# ══════════════════════════════════════════════════════════════════════════════

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
            f"background:#1a1f35;border-radius:4px;margin-bottom:4px'>"
            f"<span style='color:{col};font-size:13px'>{emoji}</span>"
            f"<span style='color:#aaa;font-size:11px;min-width:38px'>{a.time}</span>"
            f"<span style='color:#fff;font-size:12px;font-weight:600'>{a.title}</span>"
            f"<span style='color:#555;font-size:11px;margin-left:auto'>{a.category}</span>"
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

    # ── Snapshot Collector — Backtest data save karo (har 5 min) ─────────────
    try:
        collector = st.session_state.get("snap_collector")
        if collector is not None:
            sig_result = generate_trade_signal(cache, symbol)
            collector.collect(cache, symbol, sig_result)
    except Exception as _sc:
        logger.error(f"Snapshot collect error: {_sc}")

    # ── Snapshot Collector — Backtest data save karo (har 5 min) ─────────────
    try:
        collector = st.session_state.get("snap_collector")
        if collector is not None:
            sig_result = generate_trade_signal(cache, symbol)
            collector.collect(cache, symbol, sig_result)
    except Exception as _sc:
        logger.error(f"Snapshot collect error: {_sc}")

    # ── Header ──────────────────────────────────────────────────────────────
    render_header(symbol, expiry, cache)

    # ── Recent Alerts Panel ──────────────────────────────────────────────────
    _render_alert_history()

    # ── Market Overview ──────────────────────────────────────────────────────
    st.markdown("### 🌐 Market Overview")
    render_market_overview(cache)
    st.divider()

    # ── TRADE SIGNAL — Sabse Important Panel ─────────────────────────────────
    st.markdown("### 🎯 Trade Signal")
    render_trade_signal(cache, symbol)
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

    # ── PCR | IV ─────────────────────────────────────────────────────────────
    col_pcr, col_iv = st.columns(2)
    with col_pcr:
        st.markdown("### 📉 PCR Readings")
        render_pcr(cache)
    with col_iv:
        st.markdown("### 🎯 IV Rank · Greeks · Skew")
        render_iv(cache)

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
    <div style="background:#1e2130;border:2px solid {sig_c};border-radius:12px;padding:16px;margin-bottom:12px">
        <div style="display:flex;justify-content:space-between;align-items:center">
            <div>
                <span style="font-size:22px">&#129504;</span>
                <span style="font-size:18px;font-weight:bold;color:#fff;margin-left:8px">Smart Money Index</span>
            </div>
            <div style="text-align:right">
                <div style="color:#aaa;font-size:11px">Today's SMI</div>
                <div style="font-size:26px;font-weight:bold;color:{chg_col}">{smi['smi']:,.0f}</div>
                <div style="color:{chg_col};font-size:12px">{chg_ico} {abs(chg):.1f} from yesterday</div>
            </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:12px">
            <div style="background:#ffffff11;border-radius:8px;padding:10px;text-align:center">
                <div style="color:#aaa;font-size:10px">Morning Move (9:15-9:45)</div>
                <div style="font-size:18px;font-weight:bold;color:{m_col}">{smi['morning_move']:+.1f}</div>
                <div style="color:#555;font-size:10px">Retail / Emotional</div>
            </div>
            <div style="background:#ffffff11;border-radius:8px;padding:10px;text-align:center">
                <div style="color:#aaa;font-size:10px">Evening Move (3:00-3:30)</div>
                <div style="font-size:18px;font-weight:bold;color:{e_col}">{smi['evening_move']:+.1f}</div>
                <div style="color:#555;font-size:10px">Smart Money</div>
            </div>
            <div style="background:#ffffff11;border-radius:8px;padding:10px;text-align:center">
                <div style="color:#aaa;font-size:10px">5-Day Trend</div>
                <div style="font-size:16px;font-weight:bold;color:#7fb3f5">{smi['trend']}</div>
                <div style="color:#555;font-size:10px">Institutional bias</div>
            </div>
        </div>
        <div style="margin-top:12px;padding:10px;background:{sig_c}22;border-left:4px solid {sig_c};border-radius:4px">
            <div style="color:{sig_c};font-weight:bold;font-size:13px">{smi['signal']}</div>
            <div style="color:#888;font-size:12px;margin-top:4px">Tomorrow Bias: <b style="color:{t_col}">{smi['tomorrow']}</b></div>
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
    <div style="background:#1e2130;border:2px solid {dir_c};border-radius:12px;padding:16px;margin-bottom:12px">
        <div style="display:flex;justify-content:space-between;align-items:center">
            <div>
                <span style="font-size:22px">&#9889;</span>
                <span style="font-size:18px;font-weight:bold;color:#fff;margin-left:8px">Gamma Acceleration</span>
            </div>
            <div style="text-align:right">
                <div style="color:#aaa;font-size:11px">Current GEX</div>
                <div style="font-size:22px;font-weight:bold;color:{dir_c}">{gex_sign}{ga['current']:.2f} Cr</div>
            </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:12px">
            <div style="background:#ffffff11;border-radius:8px;padding:10px;text-align:center">
                <div style="color:#aaa;font-size:10px">Change Rate</div>
                <div style="font-size:18px;font-weight:bold;color:{rate_col}">{rate_sign}{ga['rate']:.2f}</div>
                <div style="color:#555;font-size:10px">Cr / minute</div>
            </div>
            <div style="background:#ffffff11;border-radius:8px;padding:10px;text-align:center">
                <div style="color:#aaa;font-size:10px">Direction</div>
                <div style="font-size:15px;font-weight:bold;color:{dir_c}">{ga['direction']}</div>
                <div style="color:#555;font-size:10px">{ga['readings']} readings</div>
            </div>
            <div style="background:#ffffff11;border-radius:8px;padding:10px;text-align:center">
                <div style="color:#aaa;font-size:10px">Flip ETA</div>
                <div style="font-size:18px;font-weight:bold;color:{flip_col}">{flip_str}</div>
                <div style="color:#555;font-size:10px">Mins to regime change</div>
            </div>
        </div>
        <div style="margin-top:12px">
            <div style="color:#555;font-size:10px;margin-bottom:4px">Session decay: {decay:.0f}%</div>
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
        bar_col     = "#ffd740" if is_top else ("#00c8ff" if is_near else "#3a5a8a")
        label       = (f"&#9733; {s:,}" if is_top else
                       f"&#9658; {s:,}" if is_near else f"&nbsp;&nbsp;{s:,}")
        bars_html  += (
            f"<div style='display:flex;align-items:center;gap:10px;margin:4px 0'>"
            f"<span style='color:#aaa;font-size:11px;width:80px'>{label}</span>"
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
    <div style="background:#1e2130;border:2px solid #7fb3f5;
                border-radius:12px;padding:16px;margin-bottom:8px">
        <div style="display:flex;justify-content:space-between;align-items:center;
                    margin-bottom:12px">
            <div>
                <span style="font-size:22px">&#127919;</span>
                <span style="font-size:18px;font-weight:bold;color:#fff;margin-left:8px">
                    Expiry Pin Probability</span>
            </div>
            <div style="text-align:right">
                <div style="color:#aaa;font-size:11px">Most Likely Pin</div>
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
    <div style="background:#1e2130;border:2px solid {tone_c};border-radius:12px;padding:16px;margin-bottom:12px">
        <div style="display:flex;justify-content:space-between;align-items:center">
            <div>
                <span style="font-size:22px">&#128208;</span>
                <span style="font-size:18px;font-weight:bold;color:#fff;margin-left:8px">Expected Move &#8212; This Expiry</span>
            </div>
            <div style="text-align:right">
                <div style="color:#aaa;font-size:11px">ATM Straddle Value</div>
                <div style="font-size:28px;font-weight:bold;color:#ffd740">&#8377;{em['straddle']:.0f}</div>
                <div style="color:#aaa;font-size:11px">&#177;{em['move_pct']:.2f}% of spot</div>
            </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px">
            <div style="background:#ff6d0022;border-radius:8px;padding:10px;text-align:center">
                <div style="color:#aaa;font-size:11px">ATM {em['atm']} CE</div>
                <div style="color:#ff6d00;font-size:22px;font-weight:bold">&#8377;{em['ce_ltp']:.0f}</div>
            </div>
            <div style="background:#00c85322;border-radius:8px;padding:10px;text-align:center">
                <div style="color:#aaa;font-size:11px">ATM {em['atm']} PE</div>
                <div style="color:#00c853;font-size:22px;font-weight:bold">&#8377;{em['pe_ltp']:.0f}</div>
            </div>
        </div>
        <div style="margin-top:14px;padding:12px;background:#0e1117;border-radius:8px">
            <div style="display:flex;justify-content:space-between;margin-bottom:8px;font-size:12px">
                <span style="color:#ff1744;font-weight:bold">&#128308; Lower: {em['lower']:,.0f}</span>
                <span style="color:#fff">Spot: {spot:,.0f}</span>
                <span style="color:#00c853;font-weight:bold">&#128994; Upper: {em['upper']:,.0f}</span>
            </div>
            <div style="background:#1565c0;border-radius:4px;height:10px;position:relative;opacity:0.7"></div>
            <div style="text-align:center;color:#7fb3f5;font-size:11px;margin-top:6px">
                85% probability NIFTY stays within &#177;{em['straddle']:.0f} pts this expiry
            </div>
        </div>
        <div style="margin-top:12px;padding:10px;background:#7fb3f522;border-left:4px solid #7fb3f5;border-radius:4px">
            <div style="color:#7fb3f5;font-size:12px;font-weight:bold">&#128176; Iron Condor &#8212; Just outside expected move:</div>
            <div style="color:#fff;font-size:13px;margin-top:6px">
                SELL {em['ic_ce']} CE @ &#8377;{em['ic_ce_prem']:.0f} &nbsp;+&nbsp; SELL {em['ic_pe']} PE @ &#8377;{em['ic_pe_prem']:.0f} &nbsp;=&nbsp; <span style="color:#ffd740;font-weight:bold">&#8377;{em['ic_total']:.0f} total premium</span>
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
            f"margin:4px 0;background:#ffffff08;border-radius:6px;"
            f"border-left:3px solid {col}'>"
            f"<span style='font-size:18px'>{sig['icon']}</span>"
            f"<span style='color:#ccc;font-size:13px;flex:1'>{sig['name']}</span>"
            f"<span style='color:#fff;font-size:14px;font-weight:bold;"
            f"min-width:90px'>{sig['value']}</span>"
            f"<span style='color:{col};font-size:12px;font-weight:bold;"
            f"min-width:75px'>{sig['signal']}</span>"
            f"<span style='color:#555;font-size:11px;flex:2;text-align:right'>"
            f"{sig['note']}</span>"
            f"</div>"
        )

    # Single render call — header + rows + footer + closing div all together
    st.markdown(f"""
    <div style="background:#1e2130;border:2px solid {ov_col};
                border-radius:12px;padding:16px;margin-bottom:12px">
        <div style="display:flex;justify-content:space-between;align-items:center;
                    margin-bottom:12px">
            <div>
                <span style="font-size:22px">&#127758;</span>
                <span style="font-size:18px;font-weight:bold;color:#fff;margin-left:8px">
                    Cross-Asset Signals</span>
            </div>
            <div style="text-align:right">
                <div style="color:#aaa;font-size:11px">Overall Reading</div>
                <div style="font-size:18px;font-weight:bold;color:{ov_col}">
                    {cross['overall']}</div>
                <div style="color:#aaa;font-size:11px">
                    Score: {cross['score']:+d} / {cross['total']} signals</div>
            </div>
        </div>
        {rows_html}
        <div style='margin-top:10px;padding:8px 10px;background:#ffffff05;
                    border-radius:6px;color:#444;font-size:11px'>
            &#8505;&#65039; SGX Nifty &amp; US Futures not available via Kite API —
            check <b style="color:#555">sgxnifty.com</b> (pre-market) and
            <b style="color:#555">cnbc.com/world-markets</b> (US futures) manually.
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
<div style="background:#1e2130;border:2px solid #555;border-radius:12px;padding:16px;margin-bottom:12px">
<div style="color:#888;font-size:13px">&#9888; {result.error}</div>
</div>""", unsafe_allow_html=True)
        return

    bar_pct   = int((score / max_s) * 100) if max_s else 0
    bar_col   = color

    st.markdown(f"""
<div style="background:#1e2130;border:2px solid {color};border-radius:12px;padding:20px;margin-bottom:16px">
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
  <div>
    <span style="font-size:18px;font-weight:700;color:#fff">{sym_label}</span>
    <span style="font-size:13px;color:#888;margin-left:10px">{result.timeframe} Timeframe</span>
  </div>
  <div style="text-align:right">
    <span style="font-size:22px;font-weight:800;color:{color}">{verdict}</span>
    <div style="font-size:13px;color:#aaa">{score}/{max_s} checks passed</div>
  </div>
</div>
<div style="background:#333;border-radius:4px;height:6px;margin-bottom:14px">
  <div style="background:{bar_col};width:{bar_pct}%;height:6px;border-radius:4px"></div>
</div>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:12px">
  <div style="color:#aaa">Price: <b style="color:#fff">{result.price:,.0f}</b></div>
  <div style="color:#aaa">RSI: <b style="color:#fff">{result.rsi:.1f}</b></div>
  <div style="color:#aaa">EMA20: <b style="color:#fff">{result.ema20:,.0f}</b></div>
  <div style="color:#aaa">EMA50: <b style="color:#fff">{result.ema50:,.0f}</b></div>
  <div style="color:#aaa">EMA200: <b style="color:#fff">{result.ema200:,.0f}</b></div>
  <div style="color:#aaa">Pivot: <b style="color:#fff">{result.pivot:,.0f}</b></div>
  <div style="color:#aaa">Support: <b style="color:#00c853">{result.support:,.0f}</b></div>
  <div style="color:#aaa">Resistance: <b style="color:#ff6b35">{result.resistance:,.0f}</b></div>
</div>
</div>""", unsafe_allow_html=True)

    for chk in result.checks:
        icon  = "&#9989;" if chk.passed else "&#10060;"
        tcol  = "#00c853" if chk.passed else "#ff1744"
        st.markdown(f"""
<div style="display:flex;align-items:flex-start;padding:6px 0;border-bottom:1px solid #2a2a3a">
  <span style="font-size:14px;margin-right:10px">{icon}</span>
  <div>
    <div style="color:{tcol};font-size:13px;font-weight:600">{chk.name}</div>
    <div style="color:#888;font-size:11px">{chk.detail}</div>
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
<tr style="background:#1e2130;color:#aaa;font-size:12px">
  <th style="padding:10px;text-align:left;border-bottom:1px solid #333">Symbol</th>
  <th style="padding:10px;text-align:center;border-bottom:1px solid #333">Weekly Trend</th>
  <th style="padding:10px;text-align:center;border-bottom:1px solid #333">Monthly Trend</th>
  <th style="padding:10px;text-align:center;border-bottom:1px solid #333">Overall Bias</th>
</tr>
</thead>
<tbody>
<tr style="background:#161b27">
  <td style="padding:10px;color:#fff;font-weight:700">NIFTY 50</td>
  <td style="padding:10px;text-align:center">{nw_b}</td>
  <td style="padding:10px;text-align:center">{nm_b}</td>
  <td style="padding:10px;text-align:center;font-size:13px;color:#aaa">
    {_overall_bias(nw, nm)}
  </td>
</tr>
<tr style="background:#1e2130">
  <td style="padding:10px;color:#fff;font-weight:700">BANK NIFTY</td>
  <td style="padding:10px;text-align:center">{bnw_b}</td>
  <td style="padding:10px;text-align:center">{bnm_b}</td>
  <td style="padding:10px;text-align:center;font-size:13px;color:#aaa">
    {_overall_bias(bnw, bnm)}
  </td>
</tr>
</tbody>
</table>""", unsafe_allow_html=True)

    # ── Trading rule box ──────────────────────────────────────────────────────
    st.markdown("""
<div style="background:#0d1f0d;border:1px solid #00c853;border-radius:8px;padding:14px;margin-bottom:20px;font-size:13px;color:#ccc">
<b style="color:#00c853">&#128273; Trading Rules</b><br><br>
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
def render_sidebar():
    st.sidebar.markdown("## ⚙️ Controls")

    # Symbol selector
    current = st.session_state.get("symbol", "NIFTY")
    new_sym = st.sidebar.selectbox(
        "Symbol",
        ["NIFTY", "BANKNIFTY", "FINNIFTY"],
        index=["NIFTY", "BANKNIFTY", "FINNIFTY"].index(current),
    )
    if new_sym != current:
        st.session_state["symbol"] = new_sym
        st.rerun()

    st.sidebar.divider()
    st.sidebar.markdown("## 📋 Today's Trades")
    try:
        summary = st.session_state["trade_log"].get_daily_summary()
        pnl     = summary.get("gross_pnl", 0)
        st.sidebar.metric("Gross P&L", f"₹{pnl:,.0f}")
        st.sidebar.metric("Total Trades", summary.get("total_trades", 0))
        st.sidebar.metric("Win Rate",    f"{summary.get('win_rate',0):.1f}%")
    except Exception:
        st.sidebar.caption("No trades today")

    st.sidebar.divider()
    st.sidebar.markdown("""
    **How to use:**
    - Symbol change → sidebar dropdown
    - Data auto-refreshes every **60 seconds**
    - Page reload nahi hoga — smooth update
    """)
    st.sidebar.markdown(
        "<div style='color:#333;font-size:11px;text-align:center'>"
        "NSE F&O Dashboard v2.1</div>",
        unsafe_allow_html=True
    )


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
      <div style="background:#1e2130;border-radius:10px;padding:16px;text-align:center">
        <div style="color:#888;font-size:12px">Total Trades</div>
        <div style="font-size:28px;font-weight:bold;color:#fff">{an.total_trades}</div>
        <div style="color:#555;font-size:11px">{an.wins}W / {an.losses}L</div>
      </div>
      <div style="background:#1e2130;border-radius:10px;padding:16px;text-align:center">
        <div style="color:#888;font-size:12px">Win Rate</div>
        <div style="font-size:28px;font-weight:bold;color:{wr_color}">{an.win_rate}%</div>
        <div style="color:#555;font-size:11px">Avg Win {an.avg_win_pct:+.1f}% / Loss {an.avg_loss_pct:+.1f}%</div>
      </div>
      <div style="background:#1e2130;border-radius:10px;padding:16px;text-align:center">
        <div style="color:#888;font-size:12px">Profit Factor</div>
        <div style="font-size:28px;font-weight:bold;color:{pf_color}">{an.profit_factor}</div>
        <div style="color:#555;font-size:11px">&gt;1.5 = Good | &gt;2.0 = Excellent</div>
      </div>
      <div style="background:#1e2130;border-radius:10px;padding:16px;text-align:center">
        <div style="color:#888;font-size:12px">Total P&amp;L</div>
        <div style="font-size:28px;font-weight:bold;color:{roi_color}">₹{an.total_pnl_rs:,.0f}</div>
        <div style="color:#555;font-size:11px">ROI {an.roi_pct:+.1f}%</div>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px">
      <div style="background:#1e2130;border-radius:10px;padding:16px;text-align:center">
        <div style="color:#888;font-size:12px">Max Drawdown</div>
        <div style="font-size:22px;font-weight:bold;color:#ff6d00">₹{an.max_drawdown_rs:,.0f}</div>
      </div>
      <div style="background:#1e2130;border-radius:10px;padding:16px;text-align:center">
        <div style="color:#888;font-size:12px">Sharpe Ratio</div>
        <div style="font-size:22px;font-weight:bold;color:#7fb3f5">{an.sharpe_ratio}</div>
        <div style="color:#555;font-size:11px">&gt;1.0 = Good</div>
      </div>
      <div style="background:#1e2130;border-radius:10px;padding:16px;text-align:center">
        <div style="color:#888;font-size:12px">Expectancy / Trade</div>
        <div style="font-size:22px;font-weight:bold;color:#00d4ff">₹{an.expectancy_rs:,.0f}</div>
      </div>
      <div style="background:#1e2130;border-radius:10px;padding:16px;text-align:center">
        <div style="color:#888;font-size:12px">Max Streak</div>
        <div style="font-size:22px;font-weight:bold;color:#fff">
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
            paper_bgcolor = "#0e1117",
            plot_bgcolor  = "#0e1117",
            font          = dict(color="#fff"),
            xaxis         = dict(title="Time", gridcolor="#2d3250"),
            yaxis         = dict(title="Portfolio Value (₹)", gridcolor="#2d3250"),
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
            paper_bgcolor = "#0e1117",
            plot_bgcolor  = "#0e1117",
            font          = dict(color="#fff"),
            xaxis         = dict(gridcolor="#2d3250"),
            yaxis         = dict(title="P&L (₹)", gridcolor="#2d3250"),
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

    # Sidebar (static — refresh mein nahi badlega)
    render_sidebar()

    # ── Tabs ─────────────────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊  Live Dashboard",
        "🧠  Advanced Signals",
        "🧭  Trend Compass",
        "🔬  Backtester",
    ])

    with tab1:
        live_data_section(symbol, expiry)

    with tab2:
        advanced_signals_section(symbol, expiry)

    with tab3:
        trend_compass_section()

    with tab4:
        render_backtester(symbol)


if __name__ == "__main__":
    main()
