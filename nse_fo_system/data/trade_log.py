"""
Trade Journal — SQLite-backed persistent trade log
Logs every basket/straddle order, tracks P&L, and supports daily summaries.
"""

import json
import logging
import os
import sqlite3
import threading
import uuid
from datetime import date, datetime
from typing import List, Optional

from config.settings import DATA_DIR

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(DATA_DIR, "trades.db")

_CREATE_TRADES = """
CREATE TABLE IF NOT EXISTS trades (
    trade_id       TEXT PRIMARY KEY,
    symbol         TEXT,
    strategy_name  TEXT,
    expiry         TEXT,
    entry_time     TEXT,
    exit_time      TEXT,
    entry_premium  REAL,
    exit_premium   REAL,
    realized_pnl   REAL,
    status         TEXT DEFAULT 'OPEN',
    legs_json      TEXT,
    order_ids      TEXT
)
"""

_CREATE_DAILY = """
CREATE TABLE IF NOT EXISTS daily_pnl (
    trade_date   TEXT PRIMARY KEY,
    gross_pnl    REAL DEFAULT 0,
    charges      REAL DEFAULT 0,
    net_pnl      REAL DEFAULT 0,
    trades_count INTEGER DEFAULT 0
)
"""


class TradeLog:
    """Thread-safe SQLite trade journal."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._lock   = threading.Lock()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.db_path, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    def _init_db(self) -> None:
        with self._conn() as c:
            c.execute(_CREATE_TRADES)
            c.execute(_CREATE_DAILY)
            c.commit()

    # ── Write ─────────────────────────────────────────────────────────────────

    def log_entry(self, basket_order, order_ids: list) -> str:
        """
        Persist a new basket trade entry.
        Returns the generated trade_id.
        """
        trade_id = str(uuid.uuid4())[:8].upper()
        legs_data = [
            {
                "action":   leg.action,
                "symbol":   leg.tradingsymbol,
                "strike":   leg.strike,
                "opt_type": leg.opt_type,
                "qty":      leg.qty,
                "ltp":      leg.ltp,
                "premium":  leg.premium,
            }
            for leg in basket_order.legs
        ]
        with self._lock:
            try:
                with self._conn() as c:
                    c.execute(
                        """INSERT INTO trades
                           (trade_id, symbol, strategy_name, expiry,
                            entry_time, entry_premium, status, legs_json, order_ids)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (
                            trade_id,
                            basket_order.symbol,
                            basket_order.strategy_name,
                            basket_order.expiry,
                            datetime.now().isoformat(timespec="seconds"),
                            basket_order.net_premium,
                            "OPEN",
                            json.dumps(legs_data),
                            json.dumps(order_ids),
                        ),
                    )
                    c.commit()
                logger.info(f"Trade logged: {trade_id} — {basket_order.strategy_name}")
            except Exception as exc:
                logger.error(f"Trade log error: {exc}")
        return trade_id

    def update_exit(self, trade_id: str, exit_premium: float) -> None:
        """Close a trade and compute its realised P&L."""
        with self._lock:
            try:
                with self._conn() as c:
                    row = c.execute(
                        "SELECT entry_premium FROM trades WHERE trade_id=?",
                        (trade_id,)
                    ).fetchone()
                    if not row:
                        logger.warning(f"trade_id {trade_id} not found")
                        return
                    pnl = exit_premium - row["entry_premium"]
                    c.execute(
                        """UPDATE trades
                           SET exit_time=?, exit_premium=?, realized_pnl=?, status='CLOSED'
                           WHERE trade_id=?""",
                        (datetime.now().isoformat(timespec="seconds"),
                         exit_premium, pnl, trade_id),
                    )
                    c.commit()
            except Exception as exc:
                logger.error(f"Exit update error: {exc}")

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_today_trades(self) -> List[dict]:
        today = date.today().isoformat()
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM trades WHERE entry_time LIKE ? ORDER BY entry_time DESC",
                (f"{today}%",)
            ).fetchall()
        return [self._row_dict(r) for r in rows]

    def get_all_trades(self, limit: int = 500) -> List[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM trades ORDER BY entry_time DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [self._row_dict(r) for r in rows]

    def get_open_trades(self) -> List[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM trades WHERE status='OPEN' ORDER BY entry_time DESC"
            ).fetchall()
        return [self._row_dict(r) for r in rows]

    def get_daily_summary(self) -> dict:
        trades = self.get_today_trades()
        closed = [t for t in trades if t["status"] == "CLOSED"]
        gross  = sum(t.get("realized_pnl") or 0 for t in closed)
        wins   = sum(1 for t in closed if (t.get("realized_pnl") or 0) > 0)
        return {
            "date":          date.today().isoformat(),
            "total_trades":  len(trades),
            "open_trades":   sum(1 for t in trades if t["status"] == "OPEN"),
            "closed_trades": len(closed),
            "gross_pnl":     round(gross, 2),
            "win_trades":    wins,
            "loss_trades":   len(closed) - wins,
            "win_rate":      round(wins / len(closed) * 100, 1) if closed else 0.0,
        }

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _row_dict(self, row: sqlite3.Row) -> dict:
        d = dict(row)
        try:
            d["legs"] = json.loads(d.pop("legs_json", "[]") or "[]")
        except Exception:
            d["legs"] = []
        try:
            d["order_ids"] = json.loads(d.get("order_ids", "[]") or "[]")
        except Exception:
            d["order_ids"] = []
        return d
