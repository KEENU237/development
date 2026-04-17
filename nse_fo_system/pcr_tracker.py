"""
OI + PCR Tracker — Smart Money Positioning
Excel sheet ke OI tracker ko live karta hai
"""

import logging
from dataclasses import dataclass
from typing import List, Dict, Optional
from config.settings import PCR_ZONES

logger = logging.getLogger(__name__)


@dataclass
class OIStrike:
    strike: float
    ce_oi: int
    ce_oi_chg: int
    ce_ltp: float
    pe_oi: int
    pe_oi_chg: int
    pe_ltp: float

    @property
    def pcr(self) -> float:
        return round(self.pe_oi / self.ce_oi, 2) if self.ce_oi > 0 else 0

    @property
    def oi_signal(self) -> str:
        """Price + OI combination se signal"""
        # Simplified — price change context bahar se chahiye
        if self.ce_oi_chg > 0 and self.pe_oi_chg < 0:
            return "FRESH_LONG"
        elif self.ce_oi_chg < 0 and self.pe_oi_chg > 0:
            return "FRESH_SHORT"
        elif self.ce_oi_chg < 0 and self.pe_oi_chg < 0:
            return "UNWINDING"
        else:
            return "NEUTRAL"


@dataclass
class PCRReading:
    symbol: str
    pcr: float
    zone: str
    signal: str
    strategy: str

    def __str__(self):
        arrow = "▲" if "BULL" in self.zone else ("▼" if "BEAR" in self.zone else "→")
        return f"{self.symbol} PCR: {self.pcr:.2f} | {self.zone} {arrow} | Strategy: {self.strategy}"


# PCR zone -> strategy mapping (Excel sheet se)
PCR_STRATEGY_MAP = {
    "EXTREME_BULL": "Bull Call Spread / Buy CE",
    "BULLISH":      "Bull Call Spread",
    "NEUTRAL":      "Iron Condor",
    "BEARISH":      "Bear Put Spread",
    "EXTREME_BEAR": "Bear Put Spread / Buy PE",
}


class PCRTracker:
    """
    NSE option chain se PCR calculate karta hai
    aur sentiment + strategy suggest karta hai.
    """

    def __init__(self, kite_manager):
        self.kite = kite_manager
        self._prev_oi: Dict[str, dict] = {}  # OI change track karne ke liye

    def get_pcr(self, symbol: str, expiry: str) -> Optional[PCRReading]:
        """Symbol ka overall PCR calculate karo"""
        chain = self.kite.get_option_chain(symbol, expiry)
        if not chain:
            return None

        total_pe_oi = 0
        total_ce_oi = 0

        instruments_to_fetch = [f"NFO:{i['tradingsymbol']}" for i in chain[:60]]
        quotes = self.kite.get_quote(instruments_to_fetch)

        for instrument in chain[:60]:
            key = f"NFO:{instrument['tradingsymbol']}"
            if key not in quotes:
                continue
            oi = quotes[key].get("oi", 0)
            if instrument["instrument_type"] == "PE":
                total_pe_oi += oi
            else:
                total_ce_oi += oi

        if total_ce_oi == 0:
            return None

        pcr = round(total_pe_oi / total_ce_oi, 2)
        zone = self._get_zone(pcr)
        signal = self._get_signal(zone)
        strategy = PCR_STRATEGY_MAP.get(zone, "Wait")

        return PCRReading(symbol=symbol, pcr=pcr, zone=zone, signal=signal, strategy=strategy)

    def get_oi_chain(self, symbol: str, expiry: str,
                     strikes_around_atm: int = 10) -> List[OIStrike]:
        """Option chain OI snapshot — ATM ke aaspaas"""
        chain = self.kite.get_option_chain(symbol, expiry)
        if not chain:
            return []

        # ATM strike dhundho (LTP se)
        spot_key = f"NSE:{symbol} 50" if symbol == "NIFTY" else f"NSE:{symbol}"
        try:
            spot = list(self.kite.get_ltp([f"NSE:{symbol}"]).values())[0]
        except Exception:
            spot = 0

        # Strikes ko group karo CE/PE pairs mein
        strike_map: Dict[float, dict] = {}
        instruments_to_fetch = []

        for inst in chain:
            s = inst["strike"]
            if s not in strike_map:
                strike_map[s] = {}
            strike_map[s][inst["instrument_type"]] = inst["tradingsymbol"]
            instruments_to_fetch.append(f"NFO:{inst['tradingsymbol']}")

        quotes = self.kite.get_quote(instruments_to_fetch[:80])

        # ATM ke nearest strikes
        all_strikes = sorted(strike_map.keys())
        if spot > 0:
            atm_idx = min(range(len(all_strikes)), key=lambda i: abs(all_strikes[i] - spot))
            start = max(0, atm_idx - strikes_around_atm)
            end = min(len(all_strikes), atm_idx + strikes_around_atm)
            selected_strikes = all_strikes[start:end]
        else:
            selected_strikes = all_strikes[:strikes_around_atm * 2]

        result = []
        for strike in selected_strikes:
            pair = strike_map.get(strike, {})
            ce_ts = pair.get("CE")
            pe_ts = pair.get("PE")

            ce_q = quotes.get(f"NFO:{ce_ts}", {}) if ce_ts else {}
            pe_q = quotes.get(f"NFO:{pe_ts}", {}) if pe_ts else {}

            ce_oi = ce_q.get("oi", 0)
            pe_oi = pe_q.get("oi", 0)
            ce_prev = self._prev_oi.get(f"CE_{strike}", ce_oi)
            pe_prev = self._prev_oi.get(f"PE_{strike}", pe_oi)

            self._prev_oi[f"CE_{strike}"] = ce_oi
            self._prev_oi[f"PE_{strike}"] = pe_oi

            result.append(OIStrike(
                strike=strike,
                ce_oi=ce_oi,
                ce_oi_chg=ce_oi - ce_prev,
                ce_ltp=ce_q.get("last_price", 0),
                pe_oi=pe_oi,
                pe_oi_chg=pe_oi - pe_prev,
                pe_ltp=pe_q.get("last_price", 0),
            ))

        return result

    def _get_zone(self, pcr: float) -> str:
        for zone, (low, high) in PCR_ZONES.items():
            if low <= pcr < high:
                return zone
        return "NEUTRAL"

    def _get_signal(self, zone: str) -> str:
        signals = {
            "EXTREME_BULL": "STRONG BUY",
            "BULLISH":      "BUY",
            "NEUTRAL":      "SIDEWAYS",
            "BEARISH":      "SELL",
            "EXTREME_BEAR": "STRONG SELL",
        }
        return signals.get(zone, "NEUTRAL")
