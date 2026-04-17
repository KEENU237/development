"""
Zerodha Kite Connect — Authentication & Data Fetcher
"""

import os
import pickle
import logging
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

# Project root (two levels up from core/kite_manager.py)
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_ROOT, "data")


class KiteManager:
    """Zerodha Kite API ka single entry point"""

    TOKEN_FILE = os.path.join(_DATA_DIR, "kite_token.pkl")

    def __init__(self, api_key: str, api_secret: str):
        self.api_key    = api_key
        self.api_secret = api_secret
        self.kite       = None
        self._instruments_cache     = None   # NFO instruments 30-min cache
        self._instruments_cache_ts  = 0
        self._connect()

    def _connect(self):
        try:
            from kiteconnect import KiteConnect
            self.kite = KiteConnect(api_key=self.api_key)
            self._load_or_login()
        except ImportError:
            logger.error("kiteconnect install karo: pip install kiteconnect")
            raise

    def _load_or_login(self):
        """Saved token load karo, warna fresh login karo"""
        today = date.today().isoformat()

        os.makedirs(_DATA_DIR, exist_ok=True)

        if os.path.exists(self.TOKEN_FILE):
            with open(self.TOKEN_FILE, "rb") as f:
                data = pickle.load(f)
            if data.get("date") == today:
                self.kite.set_access_token(data["access_token"])
                logger.info("Saved token se login successful")
                return

        # Fresh login
        login_url = self.kite.login_url()
        print(f"\n── Zerodha Login ─────────────────────────────")
        print(f"Browser mein yeh URL kholo:\n{login_url}")
        print(f"Login ke baad URL se 'request_token' copy karo")
        print(f"─────────────────────────────────────────────")

        request_token = input("Request Token paste karo: ").strip()
        session = self.kite.generate_session(request_token, api_secret=self.api_secret)
        access_token = session["access_token"]

        self.kite.set_access_token(access_token)

        with open(self.TOKEN_FILE, "wb") as f:
            pickle.dump({"date": today, "access_token": access_token}, f)

        logger.info("Login successful, token save ho gaya")

    # ── Market Data ──────────────────────────────────────────────────────────

    def get_ltp(self, instruments: list) -> dict:
        """Last Traded Price for multiple instruments"""
        try:
            data = self.kite.ltp(instruments)
            return {sym: data[sym]["last_price"] for sym in data}
        except Exception as e:
            logger.error(f"LTP fetch failed: {e}")
            return {}

    def get_quote(self, instruments: list) -> dict:
        """Full quote — OHLC, volume, OI sab"""
        try:
            return self.kite.quote(instruments)
        except Exception as e:
            logger.error(f"Quote fetch failed: {e}")
            return {}

    def _get_instruments_cached(self) -> list:
        """
        NFO instruments list — 30 minutes cache.
        Pehle call mein 2-5 sec lagta hai, baad mein instant.
        """
        import time
        now = time.time()
        if self._instruments_cache and (now - self._instruments_cache_ts) < 1800:
            return self._instruments_cache
        self._instruments_cache    = self.kite.instruments("NFO")
        self._instruments_cache_ts = now
        logger.info(f"NFO instruments refreshed: {len(self._instruments_cache)} records")
        return self._instruments_cache

    def get_option_chain(self, symbol: str, expiry: str) -> list:
        """
        NSE option chain fetch karo
        symbol: 'NIFTY' ya 'BANKNIFTY'
        expiry: '2024-03-28' format mein
        """
        try:
            instruments = self._get_instruments_cached()
            chain = [
                i for i in instruments
                if i["name"] == symbol
                and str(i["expiry"])[:10] == str(expiry)[:10]
                and i["instrument_type"] in ("CE", "PE")
            ]
            chain.sort(key=lambda x: (x["strike"], x["instrument_type"]))
            return chain
        except Exception as e:
            logger.error(f"Option chain fetch failed: {e}")
            return []

    def get_historical(self, instrument_token: int, from_date: str,
                       to_date: str, interval: str = "day") -> list:
        """Historical OHLCV data"""
        try:
            return self.kite.historical_data(
                instrument_token, from_date, to_date, interval
            )
        except Exception as e:
            logger.error(f"Historical data fetch failed: {e}")
            return []

    def get_vp_candles(self, symbol: str, session: str = "Today") -> list:
        """
        Volume Profile ke liye OHLCV candles fetch karo.
        session: "Today" | "Weekly" | "Monthly"

        Strategy:
          1. Nearest futures instrument fetch karo (real volume hota hai)
          2. Futures na mile toh index fallback (volume 0 hoga — code handles it)

        Index tokens (fallback only):
          NIFTY 50      → 256265
          NIFTY BANK    → 260105
          NIFTY FIN SVC → 257801
        """
        from datetime import datetime, timedelta

        _INDEX_TOKENS = {
            "NIFTY":     256265,
            "BANKNIFTY": 260105,
            "FINNIFTY":  257801,
        }

        now = datetime.now()

        if session == "Today":
            from_date = now.replace(hour=9, minute=15, second=0, microsecond=0)
            to_date   = now
            interval  = "5minute"
        elif session == "Weekly":
            from_date = now - timedelta(days=7)
            to_date   = now
            interval  = "15minute"
        else:                         # Monthly
            from_date = now - timedelta(days=30)
            to_date   = now
            interval  = "60minute"

        # ── Step 1: Nearest futures instrument dhundho (real volume) ──────────
        fut_token = None
        try:
            instruments = self._get_instruments_cached()
            # NFO futures for symbol — nearest expiry
            futures = [
                i for i in instruments
                if i.get("name") == symbol
                and i.get("instrument_type") == "FUT"
                and i.get("segment") == "NFO-FUT"
            ]
            if futures:
                # Sort by expiry — nearest first
                futures.sort(key=lambda x: str(x.get("expiry", "")))
                fut_token = futures[0]["instrument_token"]
                logger.info(f"VP using futures token {fut_token} "
                            f"({futures[0].get('tradingsymbol')})")
        except Exception as e:
            logger.warning(f"VP futures lookup failed: {e}")

        # ── Step 2: Use futures token, fallback to index ──────────────────────
        token = fut_token or _INDEX_TOKENS.get(symbol)
        if not token:
            logger.warning(f"VP: No token found for {symbol}")
            return []

        try:
            candles = self.kite.historical_data(
                token,
                from_date,
                to_date,
                interval,
                continuous=False,
                oi=False,
            )
            logger.info(f"VP candles: {len(candles)} ({symbol}/{session}/{interval})")
            return candles
        except Exception as e:
            logger.error(f"VP candles fetch failed ({symbol}): {e}")
            # Last resort: try index token if futures failed
            if fut_token and _INDEX_TOKENS.get(symbol):
                try:
                    return self.kite.historical_data(
                        _INDEX_TOKENS[symbol], from_date, to_date, interval,
                        continuous=False, oi=False,
                    )
                except Exception:
                    pass
            return []

    def place_order(self, symbol: str, exchange: str, txn_type: str,
                    qty: int, order_type: str = "MARKET",
                    price: float = 0.0, product: str = "NRML") -> Optional[str]:
        """
        Order place karo
        txn_type: 'BUY' ya 'SELL'
        product: 'NRML' (overnight) ya 'MIS' (intraday)
        """
        from kiteconnect import KiteConnect
        try:
            order_id = self.kite.place_order(
                variety=KiteConnect.VARIETY_REGULAR,
                exchange=exchange,
                tradingsymbol=symbol,
                transaction_type=txn_type,
                quantity=qty,
                order_type=order_type,
                price=price,
                product=product,
            )
            logger.info(f"Order placed: {order_id} | {txn_type} {qty} {symbol}")
            return order_id
        except Exception as e:
            logger.error(f"Order failed: {e}")
            return None

    def get_positions(self) -> dict:
        return self.kite.positions()

    def get_orders(self) -> list:
        return self.kite.orders()

    def get_margins(self) -> dict:
        """Fetch available + utilised margin breakdown."""
        try:
            return self.kite.margins()
        except Exception as e:
            logger.error(f"Margins fetch failed: {e}")
            return {}

    def get_access_token(self) -> str:
        """Return the current session access token (used by TickerManager)."""
        return self.kite.access_token or ""

    def is_connected(self) -> bool:
        """Check karo kya valid token hai aaj ka — web dashboard use karta hai."""
        try:
            from datetime import date
            import pickle, os
            if not os.path.exists(self.TOKEN_FILE):
                return False
            with open(self.TOKEN_FILE, "rb") as f:
                data = pickle.load(f)
            if data.get("date") != date.today().isoformat():
                return False
            # Quick API call to verify token is still valid
            self.kite.profile()
            return True
        except Exception:
            return False

    def get_ticker_instance(self):
        """
        Factory method: returns a KiteTicker bound to the current session.
        Keeps all Kite SDK construction centralised here.
        """
        from kiteconnect import KiteTicker
        return KiteTicker(self.api_key, self.get_access_token())
