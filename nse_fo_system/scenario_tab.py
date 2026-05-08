"""
Scenario Analysis — What-If Engine
====================================
"Agar Nifty X points upar/neeche jaye toh mera portfolio kya karega?"

Two modes:
  1. Live Mode   — Kite se current option positions fetch karo
  2. Manual Mode — Hypothetical positions manually add karo

Engine: Black-Scholes repricing at each spot scenario.
Shows: Per-position P&L + Net P&L + Breakeven levels + Max Profit/Loss.
"""

import streamlit as st
from datetime import date, datetime
import logging

logger = logging.getLogger(__name__)

# ── Lot sizes (NSE current) ───────────────────────────────────────────────────
LOT_SIZES = {
    "NIFTY":      25,
    "BANKNIFTY":  15,
    "FINNIFTY":   40,
    "MIDCPNIFTY": 50,
}

SPOT_KEYS = {
    "NIFTY":      "NSE:NIFTY 50",
    "BANKNIFTY":  "NSE:NIFTY BANK",
    "FINNIFTY":   "NSE:NIFTY FIN SERVICE",
    "MIDCPNIFTY": "NSE:NIFTY MIDCAP SELECT",
}


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _lot(underlying: str) -> int:
    return LOT_SIZES.get(underlying.upper(), 1)


def _detect_underlying(sym: str) -> str:
    for k in LOT_SIZES:
        if sym.upper().startswith(k):
            return k
    return "NIFTY"


def _parse_kite_position(pos: dict) -> dict | None:
    """Kite position dict → scenario-ready dict. None if not an option or qty=0."""
    sym = pos.get("tradingsymbol", "")
    qty = pos.get("quantity", 0)
    if qty == 0:
        return None
    if not (sym.endswith("CE") or sym.endswith("PE")):
        return None

    opt_type    = "CE" if sym.endswith("CE") else "PE"
    strike      = float(pos.get("strike") or 0)
    avg_price   = float(pos.get("average_price") or pos.get("last_price") or 1)
    expiry      = str(pos.get("expiry", ""))
    ltp         = float(pos.get("last_price") or avg_price)
    underlying  = _detect_underlying(sym)
    lot         = _lot(underlying)

    if strike <= 0 or not expiry:
        return None

    return {
        "symbol":     sym,
        "underlying": underlying,
        "opt_type":   opt_type,
        "strike":     strike,
        "qty":        qty,          # signed: +long, -short
        "avg_price":  avg_price,
        "ltp":        ltp,
        "expiry":     expiry,
        "lot":        lot,
    }


def _pnl_at_spot(pos: dict, spot: float, days_fwd: int, iv_pct: float) -> float:
    """Black-Scholes P&L for one position at a given spot scenario."""
    try:
        from core.greeks import calc_greeks, tte_years
        T_base = tte_years(pos["expiry"])
        T_adj  = max(T_base - days_fwd / 365.0, 1 / 365.0)
        sigma  = iv_pct / 100.0

        g = calc_greeks(S=spot, K=pos["strike"], T=T_adj,
                        sigma=sigma, opt_type=pos["opt_type"])
        if g is None:
            return 0.0

        pnl = (g.theo_price - pos["avg_price"]) * pos["qty"]
        return round(pnl, 2)
    except Exception as e:
        logger.debug(f"_pnl_at_spot error: {e}")
        return 0.0


def _build_grid(positions: list, scenarios: list,
                days_fwd: int, iv_pct: float) -> dict:
    """
    Returns:
      grid["scenarios"]      — list of spot values
      grid["positions"]      — [{symbol, pnl:[...], qty, lot}, ...]
      grid["net_pnl"]        — list of net P&L per scenario
    """
    net = [0.0] * len(scenarios)
    pos_grids = []

    for pos in positions:
        pnl_list = [_pnl_at_spot(pos, s, days_fwd, iv_pct) for s in scenarios]
        pos_grids.append({
            "symbol":    pos["symbol"],
            "qty":       pos["qty"],
            "lot":       pos["lot"],
            "avg_price": pos["avg_price"],
            "pnl":       pnl_list,
        })
        for i, v in enumerate(pnl_list):
            net[i] += v

    return {
        "scenarios":  scenarios,
        "positions":  pos_grids,
        "net_pnl":    [round(v, 2) for v in net],
    }


def _color(pnl: float) -> str:
    """Hex color for P&L value."""
    if pnl >= 10000: return "#00c853"
    if pnl >= 5000:  return "#69f0ae"
    if pnl >= 2000:  return "#b9f6ca"
    if pnl >= 0:     return "#e8f5e9"
    if pnl >= -2000: return "#ffcdd2"
    if pnl >= -5000: return "#ef9a9a"
    return "#c62828"


def _txt_color(pnl: float) -> str:
    if pnl >= 0:
        return "#00c853"
    return "#ef5350"


# ══════════════════════════════════════════════════════════════════════════════
# RENDER
# ══════════════════════════════════════════════════════════════════════════════

def render_scenario(kite=None):
    st.markdown("## 🎯 Scenario Analysis")
    st.caption(
        "Spot price ke different levels pe portfolio ka P&L — "
        "Black-Scholes repricing at each scenario."
    )

    # ── Mode ─────────────────────────────────────────────────────────────────
    mode = st.radio(
        "Mode", ["📡 Live Positions (Kite se)", "✏️ Manual Position Builder"],
        horizontal=True,
    )

    positions    = []
    current_spot = {k: 0.0 for k in LOT_SIZES}

    # ── LIVE MODE ─────────────────────────────────────────────────────────────
    if mode == "📡 Live Positions (Kite se)":
        if kite is None or not kite.is_connected():
            st.error("❌ Kite connected nahi. Pehle login karo.")
            return

        with st.spinner("Positions fetch ho rahi hain..."):
            try:
                pos_data = kite.kite.get_positions()
                for p in pos_data.get("net", []):
                    parsed = _parse_kite_position(p)
                    if parsed:
                        positions.append(parsed)
            except Exception as e:
                st.error(f"Positions fetch failed: {e}")
                return

            # Fetch current spots
            try:
                ltp_data = kite.kite.ltp(list(SPOT_KEYS.values()))
                for k, v in SPOT_KEYS.items():
                    current_spot[k] = float(
                        ltp_data.get(v, {}).get("last_price", 0) or 0
                    )
            except Exception:
                pass

        if not positions:
            st.info(
                "ℹ️ Koi open option position nahi hai abhi.\n\n"
                "Manual mode use karo hypothetical positions ke liye."
            )
            return

        st.success(f"✅ **{len(positions)}** option position(s) mili Kite se")

        # Show positions table
        with st.expander("📋 Loaded Positions", expanded=False):
            h1, h2, h3, h4, h5 = st.columns([2, 1, 1, 1, 1])
            h1.markdown("**Symbol**"); h2.markdown("**Qty**")
            h3.markdown("**Avg Price**"); h4.markdown("**LTP**")
            h5.markdown("**Unrealized**")
            for p in positions:
                c1, c2, c3, c4, c5 = st.columns([2, 1, 1, 1, 1])
                lots   = p["qty"] // p["lot"]
                unreal = (p["ltp"] - p["avg_price"]) * p["qty"]
                c1.markdown(f"`{p['symbol']}`")
                c2.markdown(f"{'🟢' if lots > 0 else '🔴'} {lots:+d} lot")
                c3.markdown(f"₹{p['avg_price']:.1f}")
                c4.markdown(f"₹{p['ltp']:.1f}")
                col = "#00c853" if unreal >= 0 else "#ef5350"
                c5.markdown(
                    f"<span style='color:{col}'>₹{unreal:+,.0f}</span>",
                    unsafe_allow_html=True,
                )

    # ── MANUAL MODE ───────────────────────────────────────────────────────────
    else:
        if "sc_positions" not in st.session_state:
            st.session_state["sc_positions"] = []

        st.markdown("#### ➕ Position Add Karo")
        with st.form("add_pos_form", clear_on_submit=True):
            c1, c2, c3, c4 = st.columns(4)
            underlying = c1.selectbox("Index",    list(LOT_SIZES.keys()))
            opt_type   = c2.selectbox("CE / PE",  ["CE", "PE"])
            strike     = c3.number_input("Strike", value=24000, step=50, min_value=1)
            expiry_dt  = c4.date_input("Expiry",  value=date.today())

            c5, c6, c7 = st.columns(3)
            lots_in    = c5.number_input(
                "Lots (+long / −short)", value=1, step=1,
                min_value=-100, max_value=100,
            )
            avg_price  = c6.number_input("Avg Price (₹)", value=100.0, step=0.5, min_value=0.1)

            submitted = c7.form_submit_button("➕ Add Position", use_container_width=True)
            if submitted:
                lot = _lot(underlying)
                sym = (
                    f"{underlying}"
                    f"{expiry_dt.strftime('%y%b').upper()}"
                    f"{int(strike)}{opt_type}"
                )
                st.session_state["sc_positions"].append({
                    "symbol":     sym,
                    "underlying": underlying,
                    "opt_type":   opt_type,
                    "strike":     float(strike),
                    "qty":        int(lots_in) * lot,
                    "avg_price":  float(avg_price),
                    "ltp":        float(avg_price),
                    "expiry":     expiry_dt.isoformat(),
                    "lot":        lot,
                })
                st.rerun()

        # Show + delete existing manual positions
        if st.session_state["sc_positions"]:
            st.markdown("**Current Positions:**")
            for i, pos in enumerate(st.session_state["sc_positions"]):
                lots = pos["qty"] // pos["lot"]
                c1, c2 = st.columns([6, 1])
                c1.markdown(
                    f"{'🟢' if lots > 0 else '🔴'} `{pos['symbol']}` — "
                    f"**{lots:+d} lot(s)** @ ₹{pos['avg_price']}"
                )
                if c2.button("🗑️", key=f"del_sc_{i}"):
                    st.session_state["sc_positions"].pop(i)
                    st.rerun()

            if st.button("🗑️ Clear All Positions"):
                st.session_state["sc_positions"] = []
                st.rerun()
        else:
            st.info("Koi position nahi — upar add karo.")
            return

        positions = st.session_state["sc_positions"]

        # Manual spot input
        st.markdown("#### 📍 Current Spot Prices")
        c1, c2, c3 = st.columns(3)
        current_spot["NIFTY"]     = float(c1.number_input("Nifty",     value=24000, step=50))
        current_spot["BANKNIFTY"] = float(c2.number_input("BankNifty", value=52000, step=100))
        current_spot["FINNIFTY"]  = float(c3.number_input("FinNifty",  value=24000, step=50))

    # ── Settings ──────────────────────────────────────────────────────────────
    st.divider()
    st.markdown("### ⚙️ Scenario Settings")

    # Detect primary underlying from positions
    underlyings = list(dict.fromkeys(p["underlying"] for p in positions))
    primary     = underlyings[0]
    ref_spot    = current_spot.get(primary, 0)

    if ref_spot <= 0:
        st.warning(f"⚠️ {primary} spot price 0 hai — sahi spot enter karo.")
        return

    sc1, sc2, sc3 = st.columns(3)
    spot_range = sc1.slider("Spot Range (± points)", 100, 3000, 500, 50,
                            help="Kitne points up/down dekhnaa hai")
    step_size  = sc2.selectbox("Step Size", [25, 50, 100, 200], index=1)
    days_fwd   = sc3.slider("Days Forward", 0, 30, 0,
                            help="0=aaj, 1=kal — theta decay effect")

    iv_c1, iv_c2 = st.columns([2, 1])
    iv_val = iv_c1.slider(
        "IV Assumption (%)", 5, 60, 15,
        help="Expected IV. Nahi pata? 12-15% normal markets, 20-25% volatile."
    )
    iv_c2.metric("Reference Spot", f"₹{ref_spot:,.0f}", primary)

    # ── Build scenarios ───────────────────────────────────────────────────────
    scenarios = list(range(
        int(ref_spot) - spot_range,
        int(ref_spot) + spot_range + step_size,
        step_size,
    ))

    # For multi-underlying, warn user
    if len(underlyings) > 1:
        st.info(
            f"ℹ️ Multiple underlyings detected ({', '.join(underlyings)}). "
            f"Scenario spot moves {primary} ke hisaab se hain. "
            f"Other underlyings ke spots fixed rahenge."
        )

    with st.spinner("Calculating..."):
        grid = _build_grid(positions, scenarios, days_fwd, iv_val)

    # ── P&L Table ─────────────────────────────────────────────────────────────
    st.divider()
    st.markdown("### 📊 P&L Scenario Table")
    st.caption(f"Spot scenarios: ₹{scenarios[0]:,.0f} → ₹{scenarios[-1]:,.0f} | "
               f"IV: {iv_val}% | Days forward: {days_fwd}")

    # Build HTML table
    hdr = (
        "<tr style='background:#1a1f35;position:sticky;top:0'>"
        "<th style='padding:7px 14px;color:#90caf9;text-align:left'>Spot</th>"
        "<th style='padding:7px 14px;color:#90caf9;text-align:left'>Move</th>"
    )
    for pd_ in grid["positions"]:
        sym_s = pd_["symbol"]
        lots  = pd_["qty"] // pd_["lot"]
        dir_  = "L" if lots > 0 else "S"
        hdr  += (
            f"<th style='padding:7px 14px;color:#cfd8dc;white-space:nowrap'>"
            f"{sym_s}<br>"
            f"<small style='color:#78909c'>{dir_}{abs(lots)}L @₹{pd_['avg_price']:.0f}</small>"
            f"</th>"
        )
    hdr += "<th style='padding:7px 14px;color:#fff;font-size:14px;border-left:2px solid #333'>NET P&L</th></tr>"

    rows_html = ""
    for idx, spot in enumerate(grid["scenarios"]):
        chg     = spot - ref_spot
        chg_pct = chg / ref_spot * 100
        is_cur  = abs(chg) < step_size / 2
        row_bg  = "#252b40" if is_cur else ("#16192a" if idx % 2 == 0 else "transparent")
        border  = "border-left:3px solid #ffd740;" if is_cur else ""
        chg_col = "#00c853" if chg > 0 else ("#ef5350" if chg < 0 else "#ffd740")
        fw      = "700" if is_cur else "400"

        row = (
            f"<tr style='background:{row_bg};{border}'>"
            f"<td style='padding:5px 14px;color:#fff;font-weight:{fw};white-space:nowrap'>"
            f"₹{spot:,.0f}{'  ◀' if is_cur else ''}</td>"
            f"<td style='padding:5px 14px;color:{chg_col};white-space:nowrap'>"
            f"{chg:+,.0f} ({chg_pct:+.1f}%)</td>"
        )
        for pd_ in grid["positions"]:
            pnl    = pd_["pnl"][idx]
            tc     = _txt_color(pnl)
            bg_hex = _color(pnl)
            row   += (
                f"<td style='padding:5px 14px;background:{bg_hex}18;"
                f"color:{tc};text-align:right;white-space:nowrap'>"
                f"₹{pnl:+,.0f}</td>"
            )
        net    = grid["net_pnl"][idx]
        net_tc = _txt_color(net)
        net_bg = _color(net)
        row   += (
            f"<td style='padding:5px 14px;background:{net_bg}28;"
            f"color:{net_tc};font-weight:700;text-align:right;"
            f"border-left:2px solid #333;white-space:nowrap'>"
            f"₹{net:+,.0f}</td></tr>"
        )
        rows_html += row

    st.markdown(
        f"<div style='overflow-x:auto;border-radius:8px;border:1px solid #2a2f45'>"
        f"<table style='width:100%;border-collapse:collapse;font-size:13px;font-family:monospace'>"
        f"<thead>{hdr}</thead><tbody>{rows_html}</tbody></table></div>",
        unsafe_allow_html=True,
    )

    # ── Key Metrics ───────────────────────────────────────────────────────────
    st.divider()
    st.markdown("### 📌 Key Levels")

    net_pnls = grid["net_pnl"]
    spots    = grid["scenarios"]

    max_p = max(net_pnls)
    max_l = min(net_pnls)
    max_p_spot = spots[net_pnls.index(max_p)]
    max_l_spot = spots[net_pnls.index(max_l)]

    # Breakeven: sign changes
    breakevens = []
    for i in range(len(net_pnls) - 1):
        if net_pnls[i] * net_pnls[i + 1] <= 0 and net_pnls[i] != net_pnls[i + 1]:
            # Linear interpolation
            be = spots[i] + (
                (0 - net_pnls[i])
                / (net_pnls[i + 1] - net_pnls[i])
                * (spots[i + 1] - spots[i])
            )
            breakevens.append(int(round(be)))

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Max Profit",  f"₹{max_p:+,.0f}", f"at ₹{max_p_spot:,.0f}")
    m2.metric("Max Loss",    f"₹{max_l:+,.0f}", f"at ₹{max_l_spot:,.0f}")

    if breakevens:
        m3.metric("Breakeven 1", f"₹{breakevens[0]:,.0f}",
                  f"{breakevens[0] - ref_spot:+.0f} pts from spot")
        if len(breakevens) > 1:
            m4.metric("Breakeven 2", f"₹{breakevens[1]:,.0f}",
                      f"{breakevens[1] - ref_spot:+.0f} pts from spot")
        else:
            m4.metric("Breakeven 2", "—", "Single side")
    else:
        m3.metric("Breakeven", "Range mein nahi", "Extend range karo")
        m4.metric("—", "—", "")

    # Current level P&L
    try:
        cur_idx = next(
            i for i, s in enumerate(spots) if abs(s - ref_spot) < step_size / 2
        )
        cur_pnl = net_pnls[cur_idx]
        col     = "#00c853" if cur_pnl >= 0 else "#ef5350"
        st.markdown(
            f"<div style='padding:12px;background:#1a1f35;border-radius:8px;"
            f"border-left:4px solid {col};margin-top:8px'>"
            f"<b>📍 Current Spot (₹{ref_spot:,.0f})</b> pe estimated Net P&L: "
            f"<b style='color:{col};font-size:18px'>₹{cur_pnl:+,.0f}</b></div>",
            unsafe_allow_html=True,
        )
    except StopIteration:
        pass

    # Risk/Reward summary
    if max_l < 0 and max_p > 0:
        rr = round(max_p / abs(max_l), 2)
        st.markdown(
            f"<div style='margin-top:12px;padding:10px;background:#1e2130;"
            f"border-radius:6px;color:#cfd8dc;font-size:13px'>"
            f"⚖️ Risk-Reward (in this range): "
            f"<b style='color:#69f0ae'>+₹{max_p:,.0f}</b> vs "
            f"<b style='color:#ef9a9a'>−₹{abs(max_l):,.0f}</b> = "
            f"<b style='color:#ffd740'>{rr:.1f}:1</b></div>",
            unsafe_allow_html=True,
        )

    st.caption(
        "⚠️ Black-Scholes model use ho raha hai. Actual P&L alag ho sakta hai "
        "(bid-ask spread, IV change, early exercise, liquidity). "
        "Ye tool educational hai — trade decision ke liye single source mat banao."
    )
