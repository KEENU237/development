"""
Basket Order Builder — Multi-leg F&O strategies
Bull Call Spread, Bear Put Spread, Iron Condor
"""

import logging
from dataclasses import dataclass
from typing import List, Optional
from config.settings import STRATEGIES, RISK

logger = logging.getLogger(__name__)


@dataclass
class OrderLeg:
    action: str        # BUY / SELL
    tradingsymbol: str
    strike: float
    opt_type: str      # CE / PE
    qty: int
    ltp: float

    @property
    def premium(self) -> float:
        sign = 1 if self.action == "BUY" else -1
        return sign * self.ltp * self.qty


@dataclass
class BasketOrder:
    strategy_name: str
    symbol: str
    legs: List[OrderLeg]
    expiry: str

    @property
    def net_premium(self) -> float:
        return sum(leg.premium for leg in self.legs)

    @property
    def max_profit(self) -> Optional[float]:
        if "CONDOR" in self.strategy_name:
            return abs(self.net_premium)  # Net credit received
        return None

    @property
    def is_debit(self) -> bool:
        return self.net_premium > 0

    def to_dict(self) -> dict:
        """Serialise to dict for trade log persistence."""
        return {
            "strategy_name": self.strategy_name,
            "symbol":        self.symbol,
            "expiry":        self.expiry,
            "net_premium":   self.net_premium,
            "legs": [
                {
                    "action":   leg.action,
                    "symbol":   leg.tradingsymbol,
                    "strike":   leg.strike,
                    "opt_type": leg.opt_type,
                    "qty":      leg.qty,
                    "ltp":      leg.ltp,
                }
                for leg in self.legs
            ],
        }

    def summary(self) -> str:
        lines = [f"\n{'─'*50}", f"  {self.strategy_name} — {self.symbol}", f"{'─'*50}"]
        for leg in self.legs:
            sign = "+" if leg.action == "BUY" else "-"
            lines.append(
                f"  {leg.action:<4} {leg.opt_type} {int(leg.strike):<6} "
                f"x{leg.qty}  LTP: Rs{leg.ltp:.1f}  "
                f"Premium: Rs{abs(leg.premium):,.0f} ({sign})"
            )
        net_sign = "DEBIT" if self.net_premium > 0 else "CREDIT"
        lines.append(f"{'─'*50}")
        lines.append(f"  Net {net_sign}: Rs{abs(self.net_premium):,.0f}")
        lines.append(f"{'─'*50}\n")
        return "\n".join(lines)


class BasketOrderBuilder:
    """
    Excel sheet ke 3 strategies ko live build karta hai:
    1. Bull Call Spread
    2. Bear Put Spread
    3. Iron Condor
    """

    def __init__(self, kite_manager):
        self.kite = kite_manager

    def build_bull_call_spread(self, symbol: str, expiry: str,
                                lot_size: int) -> Optional[BasketOrder]:
        """ATM CE buy + OTM CE sell — Net debit, mild bullish"""
        cfg = STRATEGIES["BULL_CALL_SPREAD"]
        spot = self._get_spot(symbol)
        if not spot:
            return None

        atm_strike = self._round_strike(spot, symbol)
        otm_strike = atm_strike + cfg["otm_gap"]

        chain = self.kite.get_option_chain(symbol, expiry)
        atm_ce = self._find_instrument(chain, atm_strike, "CE")
        otm_ce = self._find_instrument(chain, otm_strike, "CE")

        if not atm_ce or not otm_ce:
            logger.error(f"Bull Call Spread: instruments nahi mile {symbol}")
            return None

        atm_ltp = self._get_ltp(atm_ce)
        otm_ltp = self._get_ltp(otm_ce)

        legs = [
            OrderLeg("BUY",  atm_ce, atm_strike, "CE", lot_size, atm_ltp),
            OrderLeg("SELL", otm_ce, otm_strike, "CE", lot_size, otm_ltp),
        ]

        order = BasketOrder("BULL CALL SPREAD", symbol, legs, expiry)

        if abs(order.net_premium) > RISK["max_capital_per_trade"]:
            logger.warning(f"Risk limit exceed: Rs{abs(order.net_premium):,} > Rs{RISK['max_capital_per_trade']:,}")
            return None

        return order

    def build_bear_put_spread(self, symbol: str, expiry: str,
                               lot_size: int) -> Optional[BasketOrder]:
        """ATM PE buy + OTM PE sell — Net debit, bearish"""
        cfg = STRATEGIES["BEAR_PUT_SPREAD"]
        spot = self._get_spot(symbol)
        if not spot:
            return None

        atm_strike = self._round_strike(spot, symbol)
        otm_strike = atm_strike - cfg["otm_gap"]

        chain = self.kite.get_option_chain(symbol, expiry)
        atm_pe = self._find_instrument(chain, atm_strike, "PE")
        otm_pe = self._find_instrument(chain, otm_strike, "PE")

        if not atm_pe or not otm_pe:
            logger.error(f"Bear Put Spread: instruments nahi mile {symbol}")
            return None

        atm_ltp = self._get_ltp(atm_pe)
        otm_ltp = self._get_ltp(otm_pe)

        legs = [
            OrderLeg("BUY",  atm_pe, atm_strike, "PE", lot_size, atm_ltp),
            OrderLeg("SELL", otm_pe, otm_strike, "PE", lot_size, otm_ltp),
        ]

        return BasketOrder("BEAR PUT SPREAD", symbol, legs, expiry)

    def build_iron_condor(self, symbol: str, expiry: str,
                           lot_size: int) -> Optional[BasketOrder]:
        """4-leg net credit strategy — range-bound"""
        cfg = STRATEGIES["IRON_CONDOR"]
        spot = self._get_spot(symbol)
        if not spot:
            return None

        atm = self._round_strike(spot, symbol)

        sell_ce = atm + cfg["ce_otm_gap"]
        buy_ce  = atm + cfg["ce_otm_gap"] + cfg["ce_hedge_gap"]
        sell_pe = atm - cfg["pe_otm_gap"]
        buy_pe  = atm - cfg["pe_otm_gap"] - cfg["pe_hedge_gap"]

        chain = self.kite.get_option_chain(symbol, expiry)

        inst_sell_ce = self._find_instrument(chain, sell_ce, "CE")
        inst_buy_ce  = self._find_instrument(chain, buy_ce,  "CE")
        inst_sell_pe = self._find_instrument(chain, sell_pe, "PE")
        inst_buy_pe  = self._find_instrument(chain, buy_pe,  "PE")

        if not all([inst_sell_ce, inst_buy_ce, inst_sell_pe, inst_buy_pe]):
            logger.error("Iron Condor: kuch instruments nahi mile")
            return None

        legs = [
            OrderLeg("SELL", inst_sell_ce, sell_ce, "CE", lot_size, self._get_ltp(inst_sell_ce)),
            OrderLeg("BUY",  inst_buy_ce,  buy_ce,  "CE", lot_size, self._get_ltp(inst_buy_ce)),
            OrderLeg("SELL", inst_sell_pe, sell_pe, "PE", lot_size, self._get_ltp(inst_sell_pe)),
            OrderLeg("BUY",  inst_buy_pe,  buy_pe,  "PE", lot_size, self._get_ltp(inst_buy_pe)),
        ]

        order = BasketOrder("IRON CONDOR", symbol, legs, expiry)

        if order.is_debit:
            logger.warning("Iron Condor net debit ban raha hai — check strikes")
            return None

        return order

    def execute_basket(self, order: BasketOrder) -> List[str]:
        """Saare legs ek saath place karo"""
        order_ids = []
        for leg in order.legs:
            oid = self.kite.place_order(
                symbol=leg.tradingsymbol,
                exchange="NFO",
                txn_type=leg.action,
                qty=leg.qty,
                order_type="MARKET",
                product="NRML",
            )
            if oid:
                order_ids.append(oid)
            else:
                logger.error(f"Leg failed: {leg.action} {leg.tradingsymbol}")

        logger.info(f"Basket placed: {len(order_ids)}/{len(order.legs)} legs successful")
        return order_ids

    # ── Helpers ─────────────────────────────────────────────────────────────────

    def _get_spot(self, symbol: str) -> Optional[float]:
        # Kite uses "NSE:NIFTY 50" for Nifty index, "NSE:NIFTY BANK" for BankNifty
        sym_map = {
            "NIFTY":     "NSE:NIFTY 50",
            "BANKNIFTY": "NSE:NIFTY BANK",
        }
        exchange_sym = sym_map.get(symbol, f"NSE:{symbol}")
        prices = self.kite.get_ltp([exchange_sym])
        return list(prices.values())[0] if prices else None

    def _round_strike(self, price: float, symbol: str) -> float:
        step = 50 if "NIFTY" in symbol else 100
        return round(price / step) * step

    def _find_instrument(self, chain: list, strike: float, opt_type: str) -> Optional[str]:
        for inst in chain:
            if inst["strike"] == strike and inst["instrument_type"] == opt_type:
                return inst["tradingsymbol"]
        return None

    def _get_ltp(self, tradingsymbol: str) -> float:
        prices = self.kite.get_ltp([f"NFO:{tradingsymbol}"])
        return list(prices.values())[0] if prices else 0.0
