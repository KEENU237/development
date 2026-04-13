"""
UOA Scanner — Unusual Options Activity Detector
Excel sheet ke logic ko live data se replicate karta hai
"""

import logging
from datetime import datetime
from dataclasses import dataclass
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class UOAAlert:
    time: str
    symbol: str
    opt_type: str   # CE ya PE
    strike: float
    volume: int
    avg_vol: int
    mult: float
    sentiment: str  # BULLISH ya BEARISH
    is_fire: bool = False

    def __str__(self):
        fire = " 🔥" if self.is_fire else ""
        return (
            f"[{self.time}] {self.symbol} {self.opt_type} {int(self.strike)} | "
            f"Vol: {self.volume:,} | {self.mult:.1f}x{fire} | {self.sentiment}"
        )


class UOAScanner:
    """
    Options volume ko average se compare karta hai.
    Agar volume 5x+ ho toh UNUSUAL alert generate karta hai.

    Logic (Excel sheet se):
    - mult = current_volume / avg_20day_volume
    - 5x+  = Unusual
    - 10x+ = Very unusual
    - 15x+ = Fire
    - CE unusual = BULLISH sentiment
    - PE unusual = BEARISH sentiment
    """

    def __init__(self, kite_manager, config: dict):
        self.kite = kite_manager
        self.config = config
        self.alerts: List[UOAAlert] = []
        self._vol_history: dict = {}  # tradingsymbol -> rolling avg volume

    def scan(self, expiry: str) -> List[UOAAlert]:
        """Saare configured symbols scan karo"""
        new_alerts = []

        for symbol in self.config["scan_symbols"]:
            alerts = self._scan_symbol(symbol, expiry)
            new_alerts.extend(alerts)

        self.alerts = new_alerts
        return new_alerts

    def _scan_symbol(self, symbol: str, expiry: str) -> List[UOAAlert]:
        alerts = []
        chain = self.kite.get_option_chain(symbol, expiry)
        if not chain:
            return alerts

        # Top 30 strikes fetch karo (ATM ke aaspaas)
        instruments_to_fetch = [f"NFO:{i['tradingsymbol']}" for i in chain[:30]]
        if not instruments_to_fetch:
            return alerts

        quotes = self.kite.get_quote(instruments_to_fetch)

        for instrument in chain[:30]:
            ts = instrument["tradingsymbol"]
            key = f"NFO:{ts}"

            if key not in quotes:
                continue

            q = quotes[key]
            volume = q.get("volume", 0)
            if volume == 0:
                continue

            avg_vol = self._get_avg_volume(key, volume)
            if avg_vol == 0:
                continue

            mult = volume / avg_vol
            min_mult = self.config["min_multiplier"]
            fire_mult = self.config["fire_multiplier"]

            if mult >= min_mult:
                opt_type = instrument["instrument_type"]  # CE or PE
                sentiment = "BULLISH" if opt_type == "CE" else "BEARISH"
                is_fire = mult >= fire_mult

                alert = UOAAlert(
                    time=datetime.now().strftime("%H:%M:%S"),
                    symbol=symbol,
                    opt_type=opt_type,
                    strike=instrument["strike"],
                    volume=volume,
                    avg_vol=avg_vol,
                    mult=round(mult, 1),
                    sentiment=sentiment,
                    is_fire=is_fire,
                )
                alerts.append(alert)
                logger.info(f"UOA Alert: {alert}")

        return alerts

    def _get_avg_volume(self, key: str, current_vol: int) -> int:
        """
        Simple rolling average.
        Production mein: historical data se calculate karo.
        Abhi ke liye: first scan mein baseline set karte hain.
        """
        if key not in self._vol_history:
            # Pehli baar dekha — baseline set karo (assume karo yeh normal hai)
            self._vol_history[key] = [current_vol]
            return current_vol if current_vol > 0 else 1

        history = self._vol_history[key]

        # Average of last 20 readings
        avg = int(sum(history[-20:]) / len(history[-20:]))

        # History update karo
        history.append(current_vol)
        if len(history) > 100:
            self._vol_history[key] = history[-100:]

        return avg if avg > 0 else 1

    def get_top_alerts(self, n: int = 10) -> List[UOAAlert]:
        """Highest multiplier wale alerts return karo"""
        return sorted(self.alerts, key=lambda x: x.mult, reverse=True)[:n]
