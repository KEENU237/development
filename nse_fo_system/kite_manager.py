"""
Zerodha Kite Connect — Authentication & Data Fetcher
"""

import os
import json
import pickle
import logging
from datetime import datetime, date
from typing import Optional

logger = logging.getLogger(__name__)


class KiteManager:
    """Zerodha Kite API ka single entry point"""

    TOKEN_FILE = "data/kite_token.pkl"

    def __init__(self, api_key: str, api_secret: str):
        self.api_key    = api_key
        self.api_secret = api_secret
        self.kite       = None
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

        os.makedirs("data", exist_ok=True)
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

    def get_option_chain(self, symbol: str, expiry: str) -> list:
        """
        NSE option chain fetch karo
        symbol: 'NIFTY' ya 'BANKNIFTY'
        expiry: '2024-03-28' format mein
        """
        try:
            instruments = self.kite.instruments("NFO")
            chain = [
                i for i in instruments
                if i["name"] == symbol
                and str(i["expiry"]) == expiry
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
