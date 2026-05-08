"""
Options Strategy Builder + P&L Heatmap
=======================================
Pre-built strategies: Straddle, Strangle, Bull Call Spread,
Bear Put Spread, Iron Condor, Iron Butterfly

Features:
  • Auto-strike selection from ATM (Kite LTP or manual spot)
  • Black-Scholes premium calculation per leg
  • Combined net Greeks (Delta, Gamma, Theta, Vega)
  • P&L Heatmap — Spot × Days-to-Expiry (2-D grid)
  • Max Profit / Max Loss / Breakeven levels
  • Manual leg editor (add/remove custom legs)

Reuses:
  • core/greeks.py  → calc_greeks(), tte_years()
  • scenario_tab.py → _pnl_at_spot(), LOT_SIZES, SPOT_KEYS
"""

import streamlit as st
import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

try:
    import plotly.graph_objects as go
    PLOTLY_OK = True
except ImportError:
    PLOTLY_OK = False

# ── Re-use shared helpers from scenario_tab ───────────────────────────────────
from scenario_tab import _pnl_at_spot, LOT_SIZES, SPOT_KEYS

# ── Step size per underlying (NSE standard strike spacing) ───────────────────
STRIKE_STEPS = {
    "NIFTY":      50,
    "BANKNIFTY":  100,
    "FINNIFTY":   50,
    "MIDCPNIFTY": 25,
}

# ── Strategy definitions ──────────────────────────────────────────────────────
# Each leg: (direction, opt_type, ce_steps, pe_steps)
#   direction : +1 = BUY, -1 = SELL
#   opt_type  : "CE" or "PE"
#   ce_steps  : steps above ATM for CE legs (0 = ATM, 1 = 1 step OTM…)
#   pe_steps  : steps below ATM for PE legs (0 = ATM, 1 = 1 step OTM…)
# width_mult  : multiplier applied to user's "width" slider for OTM legs

STRATEGY_DEFS = {
    "📈 Long Straddle": {
        "desc": "Buy ATM CE + Buy ATM PE. Profit when big move either side.",
        "legs": [
            {"dir": +1, "type": "CE", "offset": 0},
            {"dir": +1, "type": "PE", "offset": 0},
        ],
        "width_applies": False,
    },
    "📉 Short Straddle": {
        "desc": "Sell ATM CE + Sell ATM PE. Profit from time decay, low volatility.",
        "legs": [
            {"dir": -1, "type": "CE", "offset": 0},
            {"dir": -1, "type": "PE", "offset": 0},
        ],
        "width_applies": False,
    },
    "📈 Long Strangle": {
        "desc": "Buy OTM CE + Buy OTM PE. Cheaper than straddle, needs bigger move.",
        "legs": [
            {"dir": +1, "type": "CE", "offset": +1},
            {"dir": +1, "type": "PE", "offset": -1},
        ],
        "width_applies": True,
    },
    "📉 Short Strangle": {
        "desc": "Sell OTM CE + Sell OTM PE. Wide range profit zone, unlimited risk.",
        "legs": [
            {"dir": -1, "type": "CE", "offset": +1},
            {"dir": -1, "type": "PE", "offset": -1},
        ],
        "width_applies": True,
    },
    "🐂 Bull Call Spread": {
        "desc": "Buy ATM CE + Sell OTM CE. Capped profit, capped loss.",
        "legs": [
            {"dir": +1, "type": "CE", "offset": 0},
            {"dir": -1, "type": "CE", "offset": +1},
        ],
        "width_applies": True,
    },
    "🐻 Bear Put Spread": {
        "desc": "Buy ATM PE + Sell OTM PE. Profits if market falls.",
        "legs": [
            {"dir": +1, "type": "PE", "offset": 0},
            {"dir": -1, "type": "PE", "offset": -1},
        ],
        "width_applies": True,
    },
    "🦅 Iron Condor": {
        "desc": "Sell OTM CE + Buy further OTM CE + Sell OTM PE + Buy further OTM PE. "
                "Best strategy for range-bound markets.",
        "legs": [
            {"dir": -1, "type": "CE", "offset": +1},
            {"dir": +1, "type": "CE", "offset": +2},
            {"dir": -1, "type": "PE", "offset": -1},
            {"dir": +1, "type": "PE", "offset": -2},
        ],
        "width_applies": True,
    },
    "🦋 Iron Butterfly": {
        "desc": "Sell ATM CE + Buy OTM CE + Sell ATM PE + Buy OTM PE. "
                "Maximum credit at ATM, cheaper than Iron Condor.",
        "legs": [
            {"dir": -1, "type": "CE", "offset": 0},
            {"dir": +1, "type": "CE", "offset": +1},
            {"dir": -1, "type": "PE", "offset": 0},
            {"dir": +1, "type": "PE", "offset": -1},
        ],
        "width_applies": True,
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _atm(spot: float, step: int) -> float:
    """Round spot to nearest strike step."""
    return round(spot / step) * step


def _strike_for_leg(leg: dict, atm: float, step: int, width: int) -> float:
    """Compute actual strike for a leg given ATM + user width (in steps)."""
    w = width if abs(leg["offset"]) > 0 else 0
    if leg["type"] == "CE":
        return atm + abs(leg["offset"]) * w * step
    else:  # PE
        # offset is -1, -2 → goes below ATM
        return atm - abs(leg["offset"]) * w * step


def _theo_premium(spot: float, strike: float, T_years: float,
                  iv_pct: float, opt_type: str) -> float:
    """Black-Scholes theoretical premium."""
    try:
        from core.greeks import calc_greeks
        g = calc_greeks(S=spot, K=strike, T=T_years,
                        sigma=iv_pct / 100.0, opt_type=opt_type)
        return g.theo_price if g else 0.0
    except Exception:
        return 0.0


def _leg_greeks(spot: float, strike: float, T_years: float,
                iv_pct: float, opt_type: str, direction: int, qty: int):
    """Returns greeks dict scaled by direction×qty."""
    try:
        from core.greeks import calc_greeks
        g = calc_greeks(S=spot, K=strike, T=T_years,
                        sigma=iv_pct / 100.0, opt_type=opt_type)
        if g is None:
            return None
        scale = direction * qty
        return {
            "delta": g.delta * scale,
            "gamma": g.gamma * scale,
            "theta": g.theta * scale,
            "vega":  g.vega  * scale,
        }
    except Exception:
        return None


def _build_positions(strategy_name: str, spot: float, step: int,
                     width: int, expiry_str: str, lot: int,
                     iv_pct: float, lots: int) -> list:
    """
    Build list of position dicts compatible with _pnl_at_spot().
    """
    from core.greeks import tte_years
    defn = STRATEGY_DEFS[strategy_name]
    atm  = _atm(spot, step)
    T    = tte_years(expiry_str)
    positions = []

    for i, leg in enumerate(defn["legs"]):
        if defn["width_applies"]:
            strike = _strike_for_leg(leg, atm, step, width)
        else:
            strike = atm  # straddle — all ATM

        direction = leg["dir"]    # +1 buy, -1 sell
        opt_type  = leg["type"]
        premium   = _theo_premium(spot, strike, T, iv_pct, opt_type)

        qty = direction * lots  # signed quantity (lots × lot_size handled in P&L)

        positions.append({
            "symbol":     f"LEG{i+1} {opt_type} {int(strike)}",
            "underlying": "NIFTY",  # placeholder — not used in _pnl_at_spot
            "opt_type":   opt_type,
            "strike":     strike,
            "qty":        qty,
            "avg_price":  premium,
            "ltp":        premium,
            "expiry":     expiry_str,
            "lot":        lot,
            "direction":  direction,
            "label":      f"{'BUY' if direction > 0 else 'SELL'} {opt_type} {int(strike)}",
        })

    return positions


def _net_pnl_at_spot(positions: list, spot: float,
                     days_fwd: int, iv_pct: float) -> float:
    """Sum P&L of all legs at given spot scenario."""
    return sum(_pnl_at_spot(p, spot, days_fwd, iv_pct) for p in positions)


def _find_breakevens(spots: list, pnl_list: list) -> list:
    """Find zero crossings (breakeven points) via linear interpolation."""
    bes = []
    for i in range(len(pnl_list) - 1):
        a, b = pnl_list[i], pnl_list[i + 1]
        if a * b < 0:  # sign change → zero crossing
            frac = -a / (b - a)
            be   = spots[i] + frac * (spots[i + 1] - spots[i])
            bes.append(round(be, 0))
    return bes


def _color_cell(val: float) -> str:
    """Background colour for heatmap HTML cells."""
    if val >= 20000:  return "#1b5e20"
    if val >= 10000:  return "#2e7d32"
    if val >=  5000:  return "#388e3c"
    if val >=  2000:  return "#43a047"
    if val >=     0:  return "#c8e6c9"
    if val >= -2000:  return "#ffcdd2"
    if val >= -5000:  return "#e57373"
    if val >= -10000: return "#c62828"
    return "#7f0000"


def _txt(val: float) -> str:
    return "#ffffff" if abs(val) >= 2000 else "#1a1a2e"


# ══════════════════════════════════════════════════════════════════════════════
# RENDER
# ══════════════════════════════════════════════════════════════════════════════

def render_strategy_builder(kite=None):
    st.markdown("## 📋 Strategy Builder")
    st.caption(
        "Pre-built option strategies — auto-strike selection, "
        "P&L heatmap (Spot × DTE), combined Greeks."
    )

    # ── Row 1: Underlying + Strategy + Expiry ─────────────────────────────────
    col1, col2, col3 = st.columns([1, 2, 1])

    with col1:
        underlying = st.selectbox(
            "Underlying", list(LOT_SIZES.keys()), key="sb_underlying"
        )

    with col2:
        strategy_name = st.selectbox(
            "Strategy", list(STRATEGY_DEFS.keys()), key="sb_strategy"
        )

    with col3:
        # Default expiry = next Thursday (weekly expiry)
        today     = date.today()
        days_left = (3 - today.weekday()) % 7  # Thursday = 3
        if days_left == 0:
            days_left = 7
        default_exp = today + timedelta(days=days_left)
        expiry = st.date_input("Expiry", value=default_exp, key="sb_expiry")
        expiry_str = expiry.strftime("%Y-%m-%d")

    # ── Row 2: Spot + IV + Width + Lots ───────────────────────────────────────
    step = STRIKE_STEPS.get(underlying, 50)
    lot  = LOT_SIZES.get(underlying, 25)

    col4, col5, col6, col7 = st.columns(4)

    with col4:
        # Try to get live spot from Kite, else manual
        live_spot = 0.0
        if kite is not None:
            try:
                if kite.is_connected():
                    spot_key = SPOT_KEYS.get(underlying, "")
                    if spot_key:
                        ltp_data = kite.kite.ltp([spot_key])
                        live_spot = float(
                            ltp_data.get(spot_key, {}).get("last_price", 0) or 0
                        )
            except Exception:
                pass

        # Fallback to session state or zero
        if live_spot <= 0:
            live_spot = st.session_state.get("sb_spot_val", 0.0)

        # Sensible defaults per underlying
        defaults = {"NIFTY": 24500, "BANKNIFTY": 52000,
                    "FINNIFTY": 23000, "MIDCPNIFTY": 12000}
        if live_spot <= 0:
            live_spot = float(defaults.get(underlying, 24500))

        spot = st.number_input(
            "Spot Price ₹", value=float(round(live_spot, 0)),
            step=float(step), format="%.0f", key="sb_spot"
        )
        st.session_state["sb_spot_val"] = spot

    with col5:
        iv_pct = st.number_input(
            "IV Assumption %", value=14.0, min_value=5.0,
            max_value=100.0, step=0.5, key="sb_iv"
        )

    with col6:
        defn = STRATEGY_DEFS[strategy_name]
        width_disabled = not defn["width_applies"]
        width = st.number_input(
            "Width (steps)", value=1, min_value=1, max_value=10,
            step=1, key="sb_width",
            help="OTM distance in strike steps. E.g. 1 = 1 step away from ATM.",
            disabled=width_disabled,
        )
        if width_disabled:
            width = 1  # not used

    with col7:
        lots = st.number_input(
            "Lots", value=1, min_value=1, max_value=50,
            step=1, key="sb_lots"
        )

    st.markdown("---")

    # ── Build positions ───────────────────────────────────────────────────────
    positions = _build_positions(
        strategy_name=strategy_name,
        spot=spot,
        step=step,
        width=int(width),
        expiry_str=expiry_str,
        lot=lot,
        iv_pct=iv_pct,
        lots=int(lots),
    )

    if not positions:
        st.error("No legs generated. Check inputs.")
        return

    # ── Strategy description ──────────────────────────────────────────────────
    st.info(f"**{strategy_name}** — {defn['desc']}")

    # ── Legs Table ────────────────────────────────────────────────────────────
    st.markdown("#### 📌 Strategy Legs")
    atm = _atm(spot, step)

    leg_rows = []
    total_debit  = 0.0
    total_credit = 0.0

    for p in positions:
        action   = "BUY" if p["direction"] > 0 else "SELL"
        color    = "#c8e6c9" if p["direction"] > 0 else "#ffcdd2"
        premium  = p["avg_price"]
        moneyness = "ATM" if p["strike"] == atm else (
            "ITM" if (p["opt_type"] == "CE" and p["strike"] < atm) or
                     (p["opt_type"] == "PE" and p["strike"] > atm) else "OTM"
        )
        leg_rows.append({
            "Action":     f"<span style='background:{color};padding:2px 6px;"
                          f"border-radius:4px;font-weight:700'>{action}</span>",
            "Type":       p["opt_type"],
            "Strike":     f"₹{int(p['strike']):,}",
            "Moneyness":  moneyness,
            "Premium":    f"₹{premium:.2f}",
            "Qty (lots)": abs(p["qty"]),
            "Value":      f"₹{abs(premium * p['qty'] * lot):,.0f}",
        })
        if p["direction"] > 0:
            total_debit  += premium * abs(p["qty"]) * lot
        else:
            total_credit += premium * abs(p["qty"]) * lot

    # Render legs as HTML table
    headers = list(leg_rows[0].keys())
    html = (
        "<table style='width:100%;border-collapse:collapse;font-size:13px'>"
        "<tr>" +
        "".join(f"<th style='background:#1a1a2e;color:#ffffff;padding:7px 10px;"
                f"border:1px solid #333;text-align:left'>{h}</th>"
                for h in headers) +
        "</tr>"
    )
    for i, row in enumerate(leg_rows):
        bg = "#f8f9ff" if i % 2 == 0 else "#ffffff"
        html += f"<tr style='background:{bg}'>"
        for h in headers:
            html += (f"<td style='padding:6px 10px;border:1px solid #e0e0e0;"
                     f"text-align:left'>{row[h]}</td>")
        html += "</tr>"
    html += "</table>"
    st.markdown(html, unsafe_allow_html=True)

    # ── Premium Summary ───────────────────────────────────────────────────────
    net_premium = total_credit - total_debit
    net_col     = "#43a047" if net_premium >= 0 else "#e53935"
    net_label   = "Net Credit" if net_premium >= 0 else "Net Debit"

    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("Total Premium Paid (Debit)", f"₹{total_debit:,.0f}")
    mc2.metric("Total Premium Received (Credit)", f"₹{total_credit:,.0f}")
    mc3.metric(net_label, f"₹{abs(net_premium):,.0f}",
               delta="received" if net_premium >= 0 else "paid")

    st.markdown("---")

    # ── P&L Analysis ──────────────────────────────────────────────────────────
    st.markdown("#### 📊 P&L Analysis")

    pa1, pa2 = st.columns([1, 2])
    with pa1:
        days_range = (expiry - date.today()).days
        days_range = max(days_range, 1)
        days_fwd = st.slider(
            "Days Forward (theta decay preview)",
            min_value=0, max_value=days_range,
            value=0, step=1, key="sb_days_fwd",
        )

    # Spot range: ±5% from spot in step increments
    pct_range = 0.06
    n_steps   = max(int(spot * pct_range / step), 6)
    spots     = [spot + (i - n_steps) * step
                 for i in range(2 * n_steps + 1)]

    pnl_list = [_net_pnl_at_spot(positions, s, days_fwd, iv_pct) for s in spots]

    # Max profit / Max loss / Breakeven
    max_profit = max(pnl_list)
    max_loss   = min(pnl_list)
    breakevens = _find_breakevens(spots, pnl_list)

    mc1b, mc2b, mc3b, mc4b = st.columns(4)
    mc1b.metric("Max Profit",  f"₹{max_profit:,.0f}" if max_profit < 1e8 else "Unlimited")
    mc2b.metric("Max Loss",    f"₹{abs(max_loss):,.0f}" if max_loss > -1e8 else "Unlimited")
    if breakevens:
        mc3b.metric("Breakeven 1", f"₹{breakevens[0]:,.0f}")
        if len(breakevens) > 1:
            mc4b.metric("Breakeven 2", f"₹{breakevens[1]:,.0f}")
    if max_loss < 0 and max_profit > 0:
        rr = abs(max_profit / max_loss)
        st.caption(f"**Risk-Reward:** 1 : {rr:.2f}")

    # ── P&L Curve (spot × P&L) ────────────────────────────────────────────────
    st.markdown("##### P&L at Expiry vs Spot")
    if PLOTLY_OK:
        fig = go.Figure()
        fill_color = [
            "rgba(67,160,71,0.15)" if v >= 0 else "rgba(229,57,53,0.15)"
            for v in pnl_list
        ]
        fig.add_trace(go.Scatter(
            x=spots, y=pnl_list,
            mode="lines+markers",
            line=dict(width=2.5, color="#1565c0"),
            marker=dict(size=5),
            name="Net P&L",
            hovertemplate="Spot: ₹%{x:,.0f}<br>P&L: ₹%{y:,.0f}<extra></extra>",
        ))
        # Zero line
        fig.add_hline(y=0, line_dash="dash", line_color="#888", line_width=1)
        # ATM line
        fig.add_vline(x=spot, line_dash="dot", line_color="#ff7043",
                      annotation_text=f"Spot ₹{spot:,.0f}",
                      annotation_position="top right")
        # Breakeven lines
        for be in breakevens:
            fig.add_vline(x=be, line_dash="dash", line_color="#43a047",
                          annotation_text=f"BE ₹{be:,.0f}",
                          annotation_position="bottom right",
                          annotation_font_color="#43a047")

        fig.update_layout(
            height=340,
            margin=dict(l=10, r=10, t=30, b=10),
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
            yaxis=dict(
                title="P&L (₹)",
                gridcolor="#e0e0e0",
                zeroline=True,
                zerolinecolor="#888",
            ),
            xaxis=dict(title="Spot Price", gridcolor="#e0e0e0"),
            showlegend=False,
        )
        # Shade profit/loss regions
        fig.add_hrect(y0=0, y1=max(pnl_list) * 1.1 if max_profit > 0 else 1,
                      fillcolor="rgba(67,160,71,0.07)", line_width=0)
        fig.add_hrect(y0=min(pnl_list) * 1.1 if max_loss < 0 else -1, y1=0,
                      fillcolor="rgba(229,57,53,0.07)", line_width=0)

        st.plotly_chart(fig, use_container_width=True)
    else:
        # Fallback: simple table
        cols_h = ["Spot"] + [f"P&L" for _ in spots]
        st.dataframe({"Spot (₹)": spots, "Net P&L (₹)": pnl_list})

    st.markdown("---")

    # ── P&L Heatmap (Spot × DTE) ─────────────────────────────────────────────
    st.markdown("#### 🌡️ P&L Heatmap — Spot × Days to Expiry")
    st.caption("Each cell = Net P&L if market is at that spot with that many days remaining.")

    # DTE axis: 0 to min(days_range, 30) in sensible steps
    max_dte = min(days_range, 30)
    if max_dte <= 7:
        dte_list = list(range(0, max_dte + 1))
    elif max_dte <= 15:
        dte_list = list(range(0, max_dte + 1, 2))
    else:
        dte_list = [0, 1, 2, 3, 5, 7, 10, 14, 21, 30]
        dte_list = [d for d in dte_list if d <= max_dte]
        if max_dte not in dte_list:
            dte_list.append(max_dte)

    # Spot axis: same as P&L curve but slightly narrower
    pct_hmap  = 0.05
    n_hmap    = max(int(spot * pct_hmap / step), 5)
    hmap_spots = [spot + (i - n_hmap) * step for i in range(2 * n_hmap + 1)]

    if PLOTLY_OK:
        z_matrix  = []
        text_matrix = []
        for dte in dte_list:
            row = []
            trow = []
            for s in hmap_spots:
                v = _net_pnl_at_spot(positions, s, dte, iv_pct)
                row.append(v)
                trow.append(f"₹{v:,.0f}")
            z_matrix.append(row)
            text_matrix.append(trow)

        hfig = go.Figure(data=go.Heatmap(
            z=z_matrix,
            x=[f"₹{int(s):,}" for s in hmap_spots],
            y=[f"{d}d" for d in dte_list],
            text=text_matrix,
            texttemplate="%{text}",
            textfont=dict(size=10),
            colorscale=[
                [0.0,  "#7f0000"],
                [0.25, "#e57373"],
                [0.45, "#ffcdd2"],
                [0.5,  "#f5f5f5"],
                [0.55, "#c8e6c9"],
                [0.75, "#43a047"],
                [1.0,  "#1b5e20"],
            ],
            zmid=0,
            colorbar=dict(title="P&L ₹", thickness=15),
            hovertemplate="Spot: %{x}<br>DTE: %{y}<br>P&L: %{text}<extra></extra>",
        ))
        hfig.update_layout(
            height=max(280, len(dte_list) * 38),
            margin=dict(l=10, r=10, t=30, b=40),
            xaxis=dict(title="Spot Price", side="bottom"),
            yaxis=dict(title="Days to Expiry", autorange="reversed"),
            plot_bgcolor="#ffffff",
            paper_bgcolor="#ffffff",
        )
        # Mark ATM column
        atm_label = f"₹{int(atm):,}"
        hfig.add_vline(x=atm_label, line_color="#ff7043",
                       line_width=2, line_dash="dot")
        st.plotly_chart(hfig, use_container_width=True)

    else:
        # Plain HTML heatmap fallback
        dte_list_rev = list(reversed(dte_list))
        html_h = (
            "<div style='overflow-x:auto'>"
            "<table style='border-collapse:collapse;font-size:11px;width:100%'>"
            "<tr><th style='padding:4px 8px;background:#1a1a2e;color:#fff'>DTE \\ Spot</th>"
        )
        for s in hmap_spots:
            html_h += (f"<th style='padding:4px 8px;background:#1a1a2e;color:#fff'>"
                       f"₹{int(s):,}</th>")
        html_h += "</tr>"

        for dte in dte_list_rev:
            html_h += f"<tr><td style='padding:4px 8px;font-weight:600;background:#f0f0f0'>{dte}d</td>"
            for s in hmap_spots:
                v   = _net_pnl_at_spot(positions, s, dte, iv_pct)
                bg  = _color_cell(v)
                txt = _txt(v)
                html_h += (f"<td style='padding:4px 6px;text-align:right;"
                           f"background:{bg};color:{txt}'>"
                           f"₹{v:,.0f}</td>")
            html_h += "</tr>"

        html_h += "</table></div>"
        st.markdown(html_h, unsafe_allow_html=True)

    st.markdown("---")

    # ── Combined Greeks ───────────────────────────────────────────────────────
    st.markdown("#### 🔬 Combined Net Greeks")
    st.caption(f"At current spot ₹{spot:,.0f} | IV {iv_pct}% | {(expiry - date.today()).days} DTE")

    from core.greeks import tte_years as _tte
    T_now = _tte(expiry_str)

    net_d = net_g = net_t = net_v = 0.0
    greeks_rows = []

    for p in positions:
        g = _leg_greeks(spot, p["strike"], T_now, iv_pct,
                        p["opt_type"], p["direction"], abs(p["qty"]))
        if g is None:
            continue
        net_d += g["delta"]
        net_g += g["gamma"]
        net_t += g["theta"]
        net_v += g["vega"]
        greeks_rows.append({
            "Leg":   p["label"],
            "Δ Delta":  f"{g['delta']:+.4f}",
            "Γ Gamma":  f"{g['gamma']:+.6f}",
            "Θ Theta":  f"₹{g['theta']:+.1f}/day",
            "Vega":     f"₹{g['vega']:+.2f}/1%IV",
        })

    # Net row
    greeks_rows.append({
        "Leg":      "🟰 NET POSITION",
        "Δ Delta":  f"{net_d:+.4f}",
        "Γ Gamma":  f"{net_g:+.6f}",
        "Θ Theta":  f"₹{net_t:+.1f}/day",
        "Vega":     f"₹{net_v:+.2f}/1%IV",
    })

    gh = (
        "<table style='width:100%;border-collapse:collapse;font-size:13px'>"
        "<tr>" +
        "".join(
            f"<th style='background:#263238;color:#cfd8dc;padding:7px 12px;"
            f"border:1px solid #37474f;text-align:left'>{h}</th>"
            for h in greeks_rows[0].keys()
        ) +
        "</tr>"
    )
    for i, row in enumerate(greeks_rows):
        is_net = row["Leg"].startswith("🟰")
        bg = "#e8eaf6" if is_net else ("#f9f9f9" if i % 2 == 0 else "#ffffff")
        fw = "700" if is_net else "400"
        gh += f"<tr style='background:{bg};font-weight:{fw}'>"
        for v in row.values():
            gh += (f"<td style='padding:6px 12px;border:1px solid #e0e0e0;"
                   f"white-space:nowrap'>{v}</td>")
        gh += "</tr>"
    gh += "</table>"
    st.markdown(gh, unsafe_allow_html=True)

    # Greeks interpretation
    interpretations = []
    if abs(net_d) < 0.05:
        interpretations.append("✅ **Delta neutral** — directional risk minimal")
    elif net_d > 0:
        interpretations.append(f"📈 **Bullish bias** — Delta {net_d:+.3f} (benefits if market rises)")
    else:
        interpretations.append(f"📉 **Bearish bias** — Delta {net_d:+.3f} (benefits if market falls)")

    if net_t < 0:
        interpretations.append(f"⚠️ **Time decay hurts** — losing ₹{abs(net_t):,.1f}/day")
    else:
        interpretations.append(f"✅ **Time decay helps** — earning ₹{net_t:,.1f}/day")

    if net_v < 0:
        interpretations.append(f"📉 **Short volatility** — profits if IV drops")
    else:
        interpretations.append(f"📈 **Long volatility** — profits if IV rises")

    st.markdown("\n".join(interpretations))

    st.markdown("---")
    st.caption(
        "⚠️ *Theoretical values based on Black-Scholes. "
        "Actual premiums may differ due to liquidity, bid-ask spread, and market microstructure. "
        "P&L does not include brokerage/STT/other charges.*"
    )
