"""
Portfolio Risk Manager
Real-time Greeks aggregation, P&L tracking, and limit monitoring.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import date

logger = logging.getLogger(__name__)


@dataclass
class PortfolioSnapshot:
    net_delta:        float = 0.0
    net_gamma:        float = 0.0
    net_theta:        float = 0.0    # daily decay ₹
    net_vega:         float = 0.0    # per 1% IV
    unrealized_pnl:   float = 0.0
    realized_pnl:     float = 0.0
    margin_used:      float = 0.0
    margin_available: float = 0.0
    open_positions:   int   = 0

    @property
    def day_pnl(self) -> float:
        return self.unrealized_pnl + self.realized_pnl

    @property
    def margin_utilization(self) -> float:
        total = self.margin_used + self.margin_available
        return round(self.margin_used / total * 100, 1) if total > 0 else 0.0


@dataclass
class RiskAlert:
    level:         str    # "WARNING" or "BREACH"
    metric:        str
    current_value: float
    limit_value:   float
    message:       str


class RiskManager:
    """
    Aggregates portfolio Greeks from live Kite positions.
    Monitors risk limits defined in config/settings.py.
    """

    def __init__(self, kite_manager):
        self.kite = kite_manager

    def get_portfolio_snapshot(self) -> PortfolioSnapshot:
        """Fetch live positions and aggregate into a PortfolioSnapshot."""
        snap = PortfolioSnapshot()

        # ── Positions ────────────────────────────────────────────────────────
        try:
            pos_data     = self.kite.get_positions()
            net_pos      = pos_data.get("net", [])
            snap.open_positions = sum(
                1 for p in net_pos if abs(p.get("quantity", 0)) > 0
            )
            for pos in net_pos:
                if abs(pos.get("quantity", 0)) == 0:
                    continue
                snap.unrealized_pnl += pos.get("unrealised", 0) or 0
                snap.realized_pnl   += pos.get("realised",   0) or 0

                # Greeks for option positions
                self._add_greeks(pos, snap)
        except Exception as exc:
            logger.error(f"Positions fetch failed: {exc}")

        # ── Margins ───────────────────────────────────────────────────────────
        try:
            margins   = self.kite.get_margins()
            eq        = margins.get("equity", {})
            utilised  = eq.get("utilised",  {})
            available = eq.get("available", {})
            snap.margin_used      = utilised.get("total",        0) or 0
            snap.margin_available = available.get("live_balance", 0) or 0
        except Exception as exc:
            logger.debug(f"Margins fetch skipped: {exc}")

        return snap

    def _add_greeks(self, pos: dict, snap: PortfolioSnapshot) -> None:
        """Compute BS Greeks for one position and add to snapshot totals."""
        try:
            from core.greeks import calc_greeks, tte_years
            sym    = pos.get("tradingsymbol", "")
            qty    = pos.get("quantity", 0)
            ltp    = pos.get("last_price", 0) or 0
            strike = pos.get("strike") or pos.get("average_price", ltp)
            expiry = str(pos.get("expiry", ""))

            if not expiry or ltp <= 0 or not sym:
                return

            opt_type = "CE" if sym.endswith("CE") else "PE"
            T        = tte_years(expiry)
            if T <= 0:
                return

            # Use LTP as proxy for underlying (simplified — avoids extra API call)
            g = calc_greeks(S=float(strike), K=float(strike), T=T,
                            sigma=0.15, opt_type=opt_type)
            if g:
                snap.net_delta += g.delta * qty
                snap.net_gamma += g.gamma * qty
                snap.net_theta += g.theta * qty
                snap.net_vega  += g.vega  * qty
        except Exception as exc:
            logger.debug(f"Greeks skipped for position: {exc}")

    def check_risk_limits(self, snap: PortfolioSnapshot) -> List[RiskAlert]:
        """Return list of RiskAlerts for any breached or near-breach limits."""
        from config.settings import RISK
        alerts: List[RiskAlert] = []

        day_pnl    = snap.day_pnl
        max_loss   = RISK["max_daily_loss"]
        margin_pct = snap.margin_utilization

        # Daily P&L limit
        if day_pnl < -max_loss:
            alerts.append(RiskAlert(
                level         = "BREACH",
                metric        = "Daily P&L",
                current_value = day_pnl,
                limit_value   = -max_loss,
                message       = f"Daily loss limit HIT: ₹{abs(day_pnl):,.0f}",
            ))
        elif day_pnl < -max_loss * 0.8:
            alerts.append(RiskAlert(
                level         = "WARNING",
                metric        = "Daily P&L",
                current_value = day_pnl,
                limit_value   = -max_loss * 0.8,
                message       = f"80% of daily loss limit: ₹{abs(day_pnl):,.0f}",
            ))

        # Margin utilisation
        if margin_pct > 90:
            alerts.append(RiskAlert(
                level         = "BREACH",
                metric        = "Margin",
                current_value = margin_pct,
                limit_value   = 90,
                message       = f"Margin critical: {margin_pct:.1f}%",
            ))
        elif margin_pct > 75:
            alerts.append(RiskAlert(
                level         = "WARNING",
                metric        = "Margin",
                current_value = margin_pct,
                limit_value   = 75,
                message       = f"High margin usage: {margin_pct:.1f}%",
            ))

        return alerts

    def is_daily_loss_limit_hit(self, snap: PortfolioSnapshot) -> bool:
        from config.settings import RISK
        return snap.day_pnl < -RISK["max_daily_loss"]
