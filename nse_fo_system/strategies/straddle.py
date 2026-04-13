"""
Straddle & Strangle Strategy Builder
Short/Long Straddle and Short/Long Strangle for NIFTY, BANKNIFTY, FINNIFTY
"""

import logging
from typing import Optional

from strategies.basket_builder import BasketOrder, OrderLeg
from core.market_utils import round_to_strike, get_lot_size

logger = logging.getLogger(__name__)

_SPOT_MAP = {
    "NIFTY":        "NSE:NIFTY 50",
    "BANKNIFTY":    "NSE:NIFTY BANK",
    "FINNIFTY":     "NSE:NIFTY FIN SERVICE",
    "MIDCPNIFTY":   "NSE:NIFTY MIDCAP SELECT",
}


class StraddleBuilder:
    """
    Builds:
      - Short Straddle  : Sell ATM CE + Sell ATM PE  (net credit, range-bound)
      - Long Straddle   : Buy  ATM CE + Buy  ATM PE  (net debit,  big move)
      - Short Strangle  : Sell OTM CE + Sell OTM PE  (wider BEP, smaller credit)
      - Long Strangle   : Buy  OTM CE + Buy  OTM PE  (cheaper directional play)
    """

    def __init__(self, kite_manager):
        self.kite = kite_manager

    # ── Public builders ───────────────────────────────────────────────────────

    def build_short_straddle(
        self, symbol: str, expiry: str, lot_size: int
    ) -> Optional[BasketOrder]:
        """Sell ATM CE + Sell ATM PE — net credit, profit if market stays flat."""
        return self._build_straddle(symbol, expiry, lot_size, "SELL", "SELL",
                                    "SHORT STRADDLE")

    def build_long_straddle(
        self, symbol: str, expiry: str, lot_size: int
    ) -> Optional[BasketOrder]:
        """Buy ATM CE + Buy ATM PE — net debit, profit from large move either way."""
        return self._build_straddle(symbol, expiry, lot_size, "BUY", "BUY",
                                    "LONG STRADDLE")

    def build_short_strangle(
        self, symbol: str, expiry: str, lot_size: int, otm_gap: int = None
    ) -> Optional[BasketOrder]:
        """Sell OTM CE + Sell OTM PE — wider breakevens, smaller credit than straddle."""
        gap = otm_gap or (200 if symbol == "NIFTY" else 500)
        return self._build_strangle(symbol, expiry, lot_size, gap,
                                    "SELL", "SELL", "SHORT STRANGLE")

    def build_long_strangle(
        self, symbol: str, expiry: str, lot_size: int, otm_gap: int = None
    ) -> Optional[BasketOrder]:
        """Buy OTM CE + Buy OTM PE — cheaper way to play a big directional move."""
        gap = otm_gap or (200 if symbol == "NIFTY" else 500)
        return self._build_strangle(symbol, expiry, lot_size, gap,
                                    "BUY", "BUY", "LONG STRANGLE")

    # ── Internal builders ─────────────────────────────────────────────────────

    def _build_straddle(
        self, symbol, expiry, lot_size,
        ce_action, pe_action, name
    ) -> Optional[BasketOrder]:
        spot = self._get_spot(symbol)
        if not spot:
            return None

        atm   = round_to_strike(spot, symbol)
        chain = self.kite.get_option_chain(symbol, expiry)

        ce_ts = self._find(chain, atm, "CE")
        pe_ts = self._find(chain, atm, "PE")

        if not ce_ts or not pe_ts:
            logger.error(f"{name}: instruments not found — {symbol} {atm}")
            return None

        legs = [
            OrderLeg(ce_action, ce_ts, atm, "CE", lot_size, self._ltp(ce_ts)),
            OrderLeg(pe_action, pe_ts, atm, "PE", lot_size, self._ltp(pe_ts)),
        ]
        return BasketOrder(name, symbol, legs, expiry)

    def _build_strangle(
        self, symbol, expiry, lot_size, otm_gap,
        ce_action, pe_action, name
    ) -> Optional[BasketOrder]:
        spot = self._get_spot(symbol)
        if not spot:
            return None

        atm    = round_to_strike(spot, symbol)
        ce_str = atm + otm_gap
        pe_str = atm - otm_gap

        chain = self.kite.get_option_chain(symbol, expiry)
        ce_ts = self._find(chain, ce_str, "CE")
        pe_ts = self._find(chain, pe_str, "PE")

        if not ce_ts or not pe_ts:
            logger.error(f"{name}: instruments not found — {symbol} {ce_str}/{pe_str}")
            return None

        legs = [
            OrderLeg(ce_action, ce_ts, ce_str, "CE", lot_size, self._ltp(ce_ts)),
            OrderLeg(pe_action, pe_ts, pe_str, "PE", lot_size, self._ltp(pe_ts)),
        ]
        return BasketOrder(name, symbol, legs, expiry)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_spot(self, symbol: str) -> Optional[float]:
        sym = _SPOT_MAP.get(symbol, f"NSE:{symbol}")
        p   = self.kite.get_ltp([sym])
        return list(p.values())[0] if p else None

    def _find(self, chain: list, strike: float, opt_type: str) -> Optional[str]:
        for inst in chain:
            if inst["strike"] == strike and inst["instrument_type"] == opt_type:
                return inst["tradingsymbol"]
        return None

    def _ltp(self, tradingsymbol: str) -> float:
        p = self.kite.get_ltp([f"NFO:{tradingsymbol}"])
        return list(p.values())[0] if p else 0.0
