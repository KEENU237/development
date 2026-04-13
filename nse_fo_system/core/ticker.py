"""
KiteTicker WebSocket Manager
Real-time streaming tick data — replaces REST polling during market hours.
Thread-safe multi-subscriber architecture.
"""

import logging
import threading
import time
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class TickerManager:
    """
    Wraps a single KiteTicker WebSocket connection.

    Multiple components (Greeks cache, risk manager, dashboard) can register
    tick callbacks without opening multiple connections.
    Auto-reconnects on disconnect with exponential backoff.
    """

    MODE_LTP  = "ltp"
    MODE_FULL = "full"

    def __init__(self, api_key: str, access_token: str):
        self._api_key      = api_key
        self._access_token = access_token
        self._ticker       = None
        self._connected    = False
        self._subscribed:  set          = set()
        self._callbacks:   List[Callable] = []
        self._prices:      Dict[int, dict] = {}
        self._lock         = threading.Lock()
        self._reconnect_delay = 5       # seconds, doubles on each failed attempt
        self._max_delay       = 120

    # ── Public API ────────────────────────────────────────────────────────────

    def add_tick_callback(self, fn: Callable) -> None:
        """Register fn(ticks: list) to receive every live tick batch."""
        if fn not in self._callbacks:
            self._callbacks.append(fn)

    def subscribe(self, tokens: List[int]) -> None:
        """Subscribe to instrument tokens for full-mode ticks."""
        with self._lock:
            self._subscribed.update(tokens)
        if self._ticker and self._connected:
            self._ticker.subscribe(list(self._subscribed))
            self._ticker.set_mode(self._ticker.MODE_FULL, list(self._subscribed))

    def unsubscribe(self, tokens: List[int]) -> None:
        with self._lock:
            self._subscribed.difference_update(tokens)
        if self._ticker and self._connected:
            try:
                self._ticker.unsubscribe(tokens)
            except Exception:
                pass

    def start(self) -> None:
        """Start the WebSocket in a daemon background thread."""
        t = threading.Thread(target=self._run_loop, daemon=True, name="KiteTicker")
        t.start()
        logger.info("TickerManager started")

    def stop(self) -> None:
        """Gracefully close the WebSocket."""
        self._connected = False
        if self._ticker:
            try:
                self._ticker.close()
            except Exception:
                pass
        logger.info("TickerManager stopped")

    def is_connected(self) -> bool:
        return self._connected

    def get_ltp(self, token: int) -> Optional[float]:
        """Fast in-memory last traded price (no REST call)."""
        tick = self._prices.get(token)
        return tick.get("last_price") if tick else None

    def get_tick(self, token: int) -> Optional[dict]:
        """Full cached tick for a given instrument token."""
        return self._prices.get(token)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        delay = self._reconnect_delay
        while True:
            try:
                self._connect()
            except Exception as exc:
                logger.error(f"Ticker connection error: {exc}")
            self._connected = False
            logger.info(f"Ticker reconnecting in {delay}s ...")
            time.sleep(delay)
            delay = min(delay * 2, self._max_delay)

    def _connect(self) -> None:
        from kiteconnect import KiteTicker
        self._ticker = KiteTicker(self._api_key, self._access_token)

        def on_connect(ws, _response):
            self._connected = True
            delay = self._reconnect_delay          # reset backoff on success
            logger.info("WebSocket connected")
            with self._lock:
                tokens = list(self._subscribed)
            if tokens:
                ws.subscribe(tokens)
                ws.set_mode(ws.MODE_FULL, tokens)

        def on_ticks(ws, ticks):
            with self._lock:
                for tick in ticks:
                    tok = tick.get("instrument_token")
                    if tok:
                        self._prices[tok] = tick
            for cb in self._callbacks:
                try:
                    cb(ticks)
                except Exception as exc:
                    logger.error(f"Tick callback error: {exc}")

        def on_close(ws, code, reason):
            self._connected = False
            logger.warning(f"WebSocket closed [{code}]: {reason}")

        def on_error(ws, code, reason):
            logger.error(f"WebSocket error [{code}]: {reason}")

        def on_reconnect(ws, attempts_count):
            logger.info(f"Reconnecting (attempt {attempts_count}) ...")

        self._ticker.on_connect   = on_connect
        self._ticker.on_ticks     = on_ticks
        self._ticker.on_close     = on_close
        self._ticker.on_error     = on_error
        self._ticker.on_reconnect = on_reconnect

        # blocks until WebSocket closes
        self._ticker.connect(threaded=False)
        self._connected = False
