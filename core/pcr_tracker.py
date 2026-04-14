"""
OI + PCR Tracker — Smart Money Positioning
"""

import os
import pickle
import logging
from dataclasses import dataclass
from typing import List, Dict, Optional
from config.settings import PCR_ZONES

logger = logging.getLogger(__name__)

_ROOT         = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PREV_OI_FILE = os.path.join(_ROOT, "data", "prev_oi.pkl")

_SYM_LTP = {
    "NIFTY":     "NSE:NIFTY 50",
    "BANKNIFTY": "NSE:NIFTY BANK",
    "FINNIFTY":  "NSE:NIFTY FIN SERVICE",
}

PCR_STRATEGY_MAP = {
    "EXTREME_BULL": "Bull Call Spread / Buy CE",
    "BULLISH":      "Bull Call Spread",
    "NEUTRAL":      "Iron Condor",
    "BEARISH":      "Bear Put Spread",
    "EXTREME_BEAR": "Bear Put Spread / Buy PE",
}


@dataclass
class OIStrike:
    strike: float
    ce_oi: int
    ce_oi_chg: int
    ce_ltp: float
    pe_oi: int
    pe_oi_chg: int
    pe_ltp: float
    ce_volume: int = 0
    pe_volume: int = 0

    @property
    def pcr(self) -> float:
        return round(self.pe_oi / self.ce_oi, 2) if self.ce_oi > 0 else 0

    @property
    def oi_signal(self) -> str:
        if   self.ce_oi_chg > 0 and self.pe_oi_chg < 0: return "FRESH_LONG"
        elif self.ce_oi_chg < 0 and self.pe_oi_chg > 0: return "FRESH_SHORT"
        elif self.ce_oi_chg < 0 and self.pe_oi_chg < 0: return "UNWINDING"
        else:                                             return "NEUTRAL"


@dataclass
class PCRReading:
    symbol: str
    pcr: float
    zone: str
    signal: str
    strategy: str

    def __str__(self):
        arrow = "^" if "BULL" in self.zone else ("v" if "BEAR" in self.zone else "->")
        return f"{self.symbol} PCR:{self.pcr:.2f} | {self.zone}{arrow} | {self.strategy}"


class PCRTracker:
    def __init__(self, kite_manager):
        self.kite     = kite_manager
        self._prev_oi: Dict[str, int] = {}
        self._load_prev_oi()           # ← restart ke baad bhi change data milega

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load_prev_oi(self):
        """Disk se pichhli OI values load karo."""
        try:
            if os.path.exists(_PREV_OI_FILE):
                with open(_PREV_OI_FILE, "rb") as f:
                    self._prev_oi = pickle.load(f)
                logger.info(f"prev_oi loaded: {len(self._prev_oi)} entries")
        except Exception as e:
            logger.warning(f"prev_oi load failed (fresh start): {e}")
            self._prev_oi = {}

    def _save_prev_oi(self):
        """OI snapshot disk pe save karo — next restart ke liye."""
        try:
            os.makedirs(os.path.dirname(_PREV_OI_FILE), exist_ok=True)
            with open(_PREV_OI_FILE, "wb") as f:
                pickle.dump(self._prev_oi, f)
        except Exception as e:
            logger.warning(f"prev_oi save failed: {e}")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get_spot(self, symbol: str) -> float:
        ltp_key = _SYM_LTP.get(symbol, f"NSE:{symbol}")
        try:
            return self.kite.get_ltp([ltp_key]).get(ltp_key, 0)
        except Exception:
            return 0

    def _nearest_strikes(self, all_strikes: list, spot: float, n: int) -> set:
        if not all_strikes or spot <= 0:
            return set(all_strikes[:n * 2])
        idx = min(range(len(all_strikes)), key=lambda i: abs(all_strikes[i] - spot))
        lo  = max(0, idx - n)
        hi  = min(len(all_strikes), idx + n + 1)
        return set(all_strikes[lo:hi])

    def _batch_quotes(self, tokens: list) -> dict:
        quotes = {}
        for i in range(0, len(tokens), 100):
            try:
                batch = self.kite.get_quote(tokens[i:i + 100])
                quotes.update(batch or {})
            except Exception as e:
                logger.error(f"Quote batch failed: {e}")
        return quotes

    # ── Public API ────────────────────────────────────────────────────────────

    def get_pcr(self, symbol: str, expiry: str) -> Optional[PCRReading]:
        """PCR — ATM ±30 strikes (1 API batch call)."""
        chain = self.kite.get_option_chain(symbol, expiry)
        if not chain:
            return None

        spot        = self._get_spot(symbol)
        all_strikes = sorted(set(i["strike"] for i in chain))
        keep        = self._nearest_strikes(all_strikes, spot, n=30)

        filtered = [i for i in chain if i["strike"] in keep]
        quotes   = self._batch_quotes([f"NFO:{i['tradingsymbol']}" for i in filtered])

        total_pe = total_ce = 0
        for inst in filtered:
            oi = quotes.get(f"NFO:{inst['tradingsymbol']}", {}).get("oi", 0)
            if inst["instrument_type"] == "PE":
                total_pe += oi
            else:
                total_ce += oi

        if total_ce == 0:
            return None

        pcr  = round(total_pe / total_ce, 2)
        zone = self._get_zone(pcr)
        return PCRReading(symbol=symbol, pcr=pcr, zone=zone,
                          signal=self._get_signal(zone),
                          strategy=PCR_STRATEGY_MAP.get(zone, "Wait"))

    def get_oi_chain(self, symbol: str, expiry: str,
                     strikes_around_atm: int = 10) -> List[OIStrike]:
        """
        OI chain — sirf ATM ±strikes fetch karo (1-2 API calls).
        _prev_oi disk-backed hai — restart ke baad bhi CHG dikhega.
        """
        chain = self.kite.get_option_chain(symbol, expiry)
        if not chain:
            return []

        spot        = self._get_spot(symbol)
        all_strikes = sorted(set(i["strike"] for i in chain))
        keep        = self._nearest_strikes(all_strikes, spot,
                                            n=strikes_around_atm + 2)

        # Build strike map and token list for only kept strikes
        strike_map: Dict[float, dict] = {}
        tokens = []
        for inst in chain:
            if inst["strike"] not in keep:
                continue
            s = inst["strike"]
            if s not in strike_map:
                strike_map[s] = {}
            strike_map[s][inst["instrument_type"]] = inst["tradingsymbol"]
            tokens.append(f"NFO:{inst['tradingsymbol']}")

        quotes = self._batch_quotes(tokens)

        result = []
        new_snapshot = {}          # disk save ke liye

        for strike in sorted(strike_map.keys()):
            pair  = strike_map[strike]
            ce_ts = pair.get("CE")
            pe_ts = pair.get("PE")

            ce_q = quotes.get(f"NFO:{ce_ts}", {}) if ce_ts else {}
            pe_q = quotes.get(f"NFO:{pe_ts}", {}) if pe_ts else {}

            ce_oi = ce_q.get("oi", 0)
            pe_oi = pe_q.get("oi", 0)

            # prev_oi disk se loaded hota hai — pehli run mein bhi change milta hai
            ce_key = f"CE_{symbol}_{strike}"
            pe_key = f"PE_{symbol}_{strike}"
            ce_prev = self._prev_oi.get(ce_key, ce_oi)
            pe_prev = self._prev_oi.get(pe_key, pe_oi)

            new_snapshot[ce_key] = ce_oi
            new_snapshot[pe_key] = pe_oi

            result.append(OIStrike(
                strike    = strike,
                ce_oi     = ce_oi,
                ce_oi_chg = ce_oi - ce_prev,
                ce_ltp    = ce_q.get("last_price", 0),
                pe_oi     = pe_oi,
                pe_oi_chg = pe_oi - pe_prev,
                pe_ltp    = pe_q.get("last_price", 0),
                ce_volume = ce_q.get("volume", 0),
                pe_volume = pe_q.get("volume", 0),
            ))

        # Update in-memory + save to disk
        self._prev_oi.update(new_snapshot)
        self._save_prev_oi()

        return result

    # ── Zone helpers ──────────────────────────────────────────────────────────

    def _get_zone(self, pcr: float) -> str:
        for zone, (lo, hi) in PCR_ZONES.items():
            if lo <= pcr < hi:
                return zone
        return "NEUTRAL"

    def _get_signal(self, zone: str) -> str:
        return {
            "EXTREME_BULL": "STRONG BUY",
            "BULLISH":      "BUY",
            "NEUTRAL":      "SIDEWAYS",
            "BEARISH":      "SELL",
            "EXTREME_BEAR": "STRONG SELL",
        }.get(zone, "NEUTRAL")
