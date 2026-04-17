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
    opt_type: str      # CE ya PE
    strike: float
    volume: int
    avg_vol: int
    mult: float
    sentiment: str     # DEEP_ITM_INST / MILD_ITM_BULL / BULLISH / MILD_ITM_BEAR / BEARISH
    is_fire: bool = False
    itm_depth_pct: float = 0.0   # % kitna ITM hai (0 = ATM/OTM)
    spot_at_alert: float = 0.0   # Alert ke time NIFTY/BN spot kya tha

    def __str__(self):
        fire = " [FIRE]" if self.is_fire else ""
        itm_str = f" | ITM:{self.itm_depth_pct:.1f}%" if self.itm_depth_pct > 0 else ""
        return (
            f"[{self.time}] {self.symbol} {self.opt_type} {int(self.strike)} | "
            f"Vol: {self.volume:,} | {self.mult:.1f}x{fire} | {self.sentiment}{itm_str}"
        )


class UOAScanner:
    """
    Options volume ko average se compare karta hai.
    Agar volume 5x+ ho toh UNUSUAL alert generate karta hai.

    Logic (Excel sheet se):
    - mult = current_volume / avg_20day_volume
    - 5x+  = Unusual
    - 10x+ = Very unusual / Fire
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

    # Underlying spot instrument mapping (Zerodha Kite format)
    SPOT_MAP = {
        "NIFTY":     "NSE:NIFTY 50",
        "BANKNIFTY": "NSE:NIFTY BANK",
        "FINNIFTY":  "NSE:NIFTY FIN SERVICE",
        "MIDCPNIFTY":"NSE:NIFTY MIDCAP SELECT",
    }

    def _classify_sentiment(self, opt_type: str, strike: float,
                            spot: float) -> tuple:
        """
        Spot price ke base pe sahi sentiment classify karo.

        Returns: (sentiment_code, itm_depth_pct)

        Sentiment codes:
          DEEP_ITM_INST  — 5%+ ITM → Institutional hedge / roll
          MILD_ITM_BULL  — 2-5% ITM CE → Mildly bullish with protection
          BULLISH        — ATM/OTM CE → Pure directional bullish bet
          MILD_ITM_BEAR  — 2-5% ITM PE → Mildly bearish with protection
          BEARISH        — ATM/OTM PE → Pure directional bearish bet
          DEEP_ITM_INST  — 5%+ ITM PE → Institutional hedge / roll
        """
        if spot <= 0:
            # Spot nahi mila — fallback to old simple logic
            return ("BULLISH" if opt_type == "CE" else "BEARISH", 0.0)

        if opt_type == "CE":
            # CE ITM = strike < spot
            itm_pts = spot - strike
        else:
            # PE ITM = strike > spot
            itm_pts = strike - spot

        itm_depth_pct = max(0.0, round((itm_pts / spot) * 100, 2))

        if itm_depth_pct >= 5.0:
            return ("DEEP_ITM_INST", itm_depth_pct)
        elif itm_depth_pct >= 2.0:
            sentiment = "MILD_ITM_BULL" if opt_type == "CE" else "MILD_ITM_BEAR"
            return (sentiment, itm_depth_pct)
        else:
            # ATM or OTM — genuine directional signal
            sentiment = "BULLISH" if opt_type == "CE" else "BEARISH"
            return (sentiment, itm_depth_pct)

    def _scan_symbol(self, symbol: str, expiry: str) -> List[UOAAlert]:
        alerts = []
        chain = self.kite.get_option_chain(symbol, expiry)
        if not chain:
            return alerts

        # ── Spot price fetch karo (Zerodha Kite LTP) ─────────────────────────
        spot = 0.0
        spot_key = self.SPOT_MAP.get(symbol, "")
        if spot_key:
            try:
                ltp_data = self.kite.get_ltp([spot_key])
                spot = ltp_data.get(spot_key, 0.0)
            except Exception as e:
                logger.warning(f"Spot LTP fetch failed for {symbol}: {e}")

        # ── Options quotes batch fetch ─────────────────────────────────────────
        instruments_to_fetch = [f"NFO:{i['tradingsymbol']}" for i in chain[:60]]
        if not instruments_to_fetch:
            return alerts

        quotes = {}
        for i in range(0, len(instruments_to_fetch), 100):
            try:
                batch = self.kite.get_quote(instruments_to_fetch[i:i+100])
                quotes.update(batch or {})
            except Exception as e:
                logger.error(f"UOA quote batch failed for {symbol}: {e}")

        for instrument in chain[:60]:
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
                opt_type  = instrument["instrument_type"]  # CE or PE
                strike    = instrument["strike"]
                is_fire   = mult >= fire_mult

                sentiment, itm_depth_pct = self._classify_sentiment(
                    opt_type, strike, spot
                )

                alert = UOAAlert(
                    time=datetime.now().strftime("%H:%M:%S"),
                    symbol=symbol,
                    opt_type=opt_type,
                    strike=strike,
                    volume=volume,
                    avg_vol=avg_vol,
                    mult=round(mult, 1),
                    sentiment=sentiment,
                    is_fire=is_fire,
                    itm_depth_pct=itm_depth_pct,
                    spot_at_alert=round(spot, 1),
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
