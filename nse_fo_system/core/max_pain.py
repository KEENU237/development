"""
Max Pain Calculator
Finds the strike price where option writers' total payout is minimised.
Also computes OI skew (call-heavy vs put-heavy) for sentiment context.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

_INDEX_SPOT_MAP = {
    "NIFTY":     "NSE:NIFTY 50",
    "BANKNIFTY": "NSE:NIFTY BANK",
    "FINNIFTY":  "NSE:NIFTY FIN SERVICE",   # Kite uses this exact name
    "MIDCPNIFTY":"NSE:NIFTY MIDCAP SELECT",
}


@dataclass
class MaxPainResult:
    symbol:           str
    expiry:           str
    max_pain_strike:  float
    spot:             float
    distance_pts:     float          # max_pain - spot
    distance_pct:     float          # distance as % of spot
    signal:           str            # BULLISH / BEARISH / NEUTRAL
    total_oi:         int
    top_ce_oi_strike: float          # strike with highest CE OI  (resistance)
    top_pe_oi_strike: float          # strike with highest PE OI  (support)
    strikes_pain:     List[Tuple[float, float]] = field(default_factory=list)

    def __str__(self) -> str:
        arrow = "▲" if self.signal == "BULLISH" else ("▼" if self.signal == "BEARISH" else "→")
        return (f"Max Pain: {int(self.max_pain_strike)}  "
                f"Spot: {int(self.spot)}  "
                f"Gap: {self.distance_pts:+.0f} ({self.distance_pct:+.2f}%)  "
                f"{arrow} {self.signal}  "
                f"Support(PE OI): {int(self.top_pe_oi_strike)}  "
                f"Resist(CE OI): {int(self.top_ce_oi_strike)}")


class MaxPainCalculator:
    """Compute Max Pain from live NSE option chain OI data."""

    def __init__(self, kite_manager):
        self.kite = kite_manager

    def compute(self, symbol: str, expiry: str) -> Optional[MaxPainResult]:
        chain = self.kite.get_option_chain(symbol, expiry)
        if not chain:
            return None

        # Bulk-fetch quotes (up to 100 instruments per call)
        tokens  = [f"NFO:{i['tradingsymbol']}" for i in chain]
        quotes: dict = {}
        for i in range(0, len(tokens), 100):
            batch = tokens[i:i + 100]
            try:
                quotes.update(self.kite.get_quote(batch) or {})
            except Exception:
                pass

        # Build strike → {CE_OI, PE_OI} map
        strike_oi: dict = {}
        for inst in chain:
            k  = inst["strike"]
            ot = inst["instrument_type"]
            key = f"NFO:{inst['tradingsymbol']}"
            oi  = quotes.get(key, {}).get("oi", 0)
            if k not in strike_oi:
                strike_oi[k] = {"CE": 0, "PE": 0}
            strike_oi[k][ot] += oi

        if not strike_oi:
            return None

        strikes = sorted(strike_oi.keys())

        # ── Max Pain ──────────────────────────────────────────────────────────
        # For each candidate expiry price P, compute total writer payout:
        #   CE writers pay out (P − K) × CE_OI  for all K < P
        #   PE writers pay out (K − P) × PE_OI  for all K > P
        # Max pain = P that minimises this total.
        min_pain  = float("inf")
        mp_strike = strikes[0]
        pain_data: List[Tuple[float, float]] = []

        for P in strikes:
            pain = sum(
                max(P - K, 0) * strike_oi[K]["CE"] +
                max(K - P, 0) * strike_oi[K]["PE"]
                for K in strikes
            )
            pain_data.append((P, pain))
            if pain < min_pain:
                min_pain  = pain
                mp_strike = P

        # ── Spot ──────────────────────────────────────────────────────────────
        spot_sym = _INDEX_SPOT_MAP.get(symbol, f"NSE:{symbol}")
        try:
            spot = list(self.kite.get_ltp([spot_sym]).values())[0]
        except Exception as e:
            logger.error(f"Max Pain: spot fetch failed for {spot_sym}: {e}")
            spot = mp_strike

        dist   = mp_strike - spot
        dist_p = round(dist / spot * 100, 2) if spot > 0 else 0.0

        if dist > spot * 0.003:
            signal = "BULLISH"   # writers want price to move up to max pain
        elif dist < -spot * 0.003:
            signal = "BEARISH"
        else:
            signal = "NEUTRAL"

        # ── Support & Resistance from OI ─────────────────────────────────────
        top_ce = max(strikes, key=lambda k: strike_oi[k]["CE"])
        top_pe = max(strikes, key=lambda k: strike_oi[k]["PE"])
        total  = sum(v["CE"] + v["PE"] for v in strike_oi.values())

        return MaxPainResult(
            symbol           = symbol,
            expiry           = expiry,
            max_pain_strike  = mp_strike,
            spot             = spot,
            distance_pts     = round(dist, 1),
            distance_pct     = dist_p,
            signal           = signal,
            total_oi         = total,
            top_ce_oi_strike = top_ce,
            top_pe_oi_strike = top_pe,
            strikes_pain     = pain_data,
        )
