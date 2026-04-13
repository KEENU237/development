"""
Black-Scholes Greeks & Implied Volatility Engine
NSE F&O analytics — Delta, Gamma, Theta, Vega, IV
"""

import math
import logging
from dataclasses import dataclass
from typing import Optional
from datetime import date, datetime

logger = logging.getLogger(__name__)

try:
    from scipy.stats import norm as _scipy_norm
    def _ncdf(x): return float(_scipy_norm.cdf(x))
    def _npdf(x): return float(_scipy_norm.pdf(x))
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False
    logger.warning("scipy unavailable — using polynomial approximation for N(x)")

    def _ncdf(x: float) -> float:
        """Abramowitz & Stegun polynomial approximation, error < 7.5e-8"""
        if x < 0:
            return 1.0 - _ncdf(-x)
        k = 1.0 / (1.0 + 0.2316419 * x)
        poly = k * (0.319381530
                    + k * (-0.356563782
                           + k * (1.781477937
                                  + k * (-1.821255978
                                         + k * 1.330274429))))
        return 1.0 - math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi) * poly

    def _npdf(x: float) -> float:
        return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


# India 10-year G-Sec approximate yield
RISK_FREE_RATE = 0.065


@dataclass
class Greeks:
    delta:      float   # Price sensitivity to underlying move
    gamma:      float   # Rate of delta change (curvature)
    theta:      float   # Daily time decay in rupees
    vega:       float   # P&L change per 1% IV change
    iv:         float   # Implied Volatility (%)
    theo_price: float   # Black-Scholes theoretical price

    def __str__(self) -> str:
        return (f"Δ={self.delta:+.3f}  Γ={self.gamma:.5f}  "
                f"Θ={self.theta:+.1f}/day  Vega={self.vega:.2f}  "
                f"IV={self.iv:.1f}%  Theo=₹{self.theo_price:.2f}")


def calc_greeks(
    S: float,
    K: float,
    T: float,
    sigma: float,
    opt_type: str = "CE",
    r: float = RISK_FREE_RATE,
) -> Optional[Greeks]:
    """
    Compute Black-Scholes Greeks for an NSE option.

    Parameters
    ----------
    S        : Spot (underlying) price
    K        : Strike price
    T        : Time to expiry in YEARS  (e.g. 7/365 = 0.01918)
    sigma    : Annualised implied vol as decimal  (0.15 = 15%)
    opt_type : "CE" (call) or "PE" (put)
    r        : Continuous risk-free rate as decimal (default 6.5%)

    Returns
    -------
    Greeks dataclass, or None if inputs are invalid.
    """
    if T < 1e-6 or sigma < 1e-6 or S <= 0 or K <= 0:
        return None
    try:
        sq_T = math.sqrt(T)
        d1   = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sq_T)
        d2   = d1 - sigma * sq_T
        df   = math.exp(-r * T)          # discount factor
        pdf1 = _npdf(d1)

        if opt_type == "CE":
            price = S * _ncdf(d1) - K * df * _ncdf(d2)
            delta = _ncdf(d1)
            theta = (
                (-S * pdf1 * sigma / (2.0 * sq_T))
                - r * K * df * _ncdf(d2)
            ) / 365.0
        else:  # PE
            price = K * df * _ncdf(-d2) - S * _ncdf(-d1)
            delta = _ncdf(d1) - 1.0
            theta = (
                (-S * pdf1 * sigma / (2.0 * sq_T))
                + r * K * df * _ncdf(-d2)
            ) / 365.0

        gamma = pdf1 / (S * sigma * sq_T)
        vega  = S * pdf1 * sq_T / 100.0   # per 1% IV move

        return Greeks(
            delta      = round(delta, 4),
            gamma      = round(gamma, 6),
            theta      = round(theta, 2),
            vega       = round(vega, 2),
            iv         = round(sigma * 100, 2),
            theo_price = round(price, 2),
        )
    except (ValueError, ZeroDivisionError, OverflowError) as exc:
        logger.debug(f"calc_greeks error: {exc}")
        return None


def calc_iv(
    market_price: float,
    S: float,
    K: float,
    T: float,
    opt_type: str = "CE",
    r: float = RISK_FREE_RATE,
    max_iter: int = 100,
    tol: float = 1e-5,
) -> Optional[float]:
    """
    Newton-Raphson Implied Volatility solver.

    Returns IV as a percentage (e.g. 15.2 = 15.2 %) or None if unsolvable.
    """
    if T < 1e-6 or market_price <= 0:
        return None

    # Reject if market_price is below intrinsic
    intrinsic = max(S - K, 0) if opt_type == "CE" else max(K - S, 0)
    if market_price < intrinsic - 0.50:
        return None

    sigma = 0.30  # sensible initial guess
    for _ in range(max_iter):
        g = calc_greeks(S, K, T, sigma, opt_type, r)
        if g is None:
            return None

        diff        = g.theo_price - market_price
        vega_actual = g.vega * 100.0          # vega stored per 1% → scale back

        if abs(vega_actual) < 1e-8:
            break

        sigma -= diff / vega_actual

        if sigma <= 0.001 or sigma > 10.0:
            return None

        if abs(diff) < tol:
            return round(sigma * 100.0, 2)

    return round(sigma * 100.0, 2) if 0.001 < sigma < 10.0 else None


def iv_rank(current_iv: float, iv_history: list) -> float:
    """
    IV Rank = (current_iv - 52w_low) / (52w_high - 52w_low) * 100
    Returns 0–100.  >50 = IV elevated, good for selling premium.
    """
    if not iv_history or len(iv_history) < 2:
        return 50.0
    lo, hi = min(iv_history), max(iv_history)
    if hi <= lo:
        return 50.0
    return round((current_iv - lo) / (hi - lo) * 100, 1)


def tte_years(expiry_str: str) -> float:
    """
    Time-to-expiry in years, including intraday fraction.
    expiry_str : 'YYYY-MM-DD'
    NSE market closes at 15:30 IST → treats that as T = 0 on expiry day.
    """
    try:
        exp   = date.fromisoformat(expiry_str)
        now   = datetime.now()
        today = now.date()
        days  = (exp - today).days

        # Intraday fraction: market hours 9:25–15:30 (≈ 6.08 hrs)
        h = now.hour + now.minute / 60.0
        if h < 9.42:
            frac = 1.0
        elif h >= 15.5:
            frac = 0.0
        else:
            frac = (15.5 - h) / 6.08

        total_days = max(days + frac, 0.001)
        return total_days / 365.0
    except Exception:
        return 0.001
