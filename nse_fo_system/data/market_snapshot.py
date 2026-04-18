"""
Market Snapshot Collector
=========================
Har 5 minute mein market data SQLite mein save karta hai.
Backtest engine yahi data use karta hai.

Tables:
  snapshots  — PCR, VIX, OI, volume, IV, GEX, price, signal har 5 min
  signal_log — Generated BUY CE / BUY PE signals + outcome
"""

import os
import sqlite3
import threading
import logging
from datetime import datetime, date
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)

from config.settings import DATA_DIR

DB_PATH = os.path.join(DATA_DIR, "backtest.db")

_CREATE_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,
    date        TEXT    NOT NULL,
    time        TEXT    NOT NULL,
    symbol      TEXT    NOT NULL,
    spot        REAL    DEFAULT 0,
    pcr         REAL    DEFAULT 0,
    pcr_zone    TEXT    DEFAULT \'\',
    pcr_trend   TEXT    DEFAULT \'\',
    vix         REAL    DEFAULT 0,
    iv_rank     REAL    DEFAULT 0,
    atm_ce_ltp  REAL    DEFAULT 0,
    atm_pe_ltp  REAL    DEFAULT 0,
    oi_signal   TEXT    DEFAULT \'\',
    gex_regime  TEXT    DEFAULT \'\',
    gex_total   REAL    DEFAULT 0,
    signal      TEXT    DEFAULT \'NO TRADE\',
    score       INTEGER DEFAULT 0,
    atm         INTEGER DEFAULT 0,
    ce_oi       INTEGER DEFAULT 0,
    pe_oi       INTEGER DEFAULT 0,
    ce_volume   INTEGER DEFAULT 0,
    pe_volume   INTEGER DEFAULT 0
)
"""

_CREATE_SIGNAL_LOG = """
CREATE TABLE IF NOT EXISTS signal_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT    NOT NULL,
    symbol      TEXT    NOT NULL,
    signal      TEXT    NOT NULL,
    score       INTEGER DEFAULT 0,
    entry_price REAL    DEFAULT 0,
    target      REAL    DEFAULT 0,
    sl          REAL    DEFAULT 0,
    strike      INTEGER DEFAULT 0,
    vix         REAL    DEFAULT 0,
    pcr         REAL    DEFAULT 0,
    iv_rank     REAL    DEFAULT 0,
    outcome     TEXT    DEFAULT \'PENDING\',
    exit_price  REAL    DEFAULT 0,
    pnl_pct     REAL    DEFAULT 0
)
"""

_IDX_SNAP = "CREATE INDEX IF NOT EXISTS idx_snap_sym_date ON snapshots(symbol, date)"
_IDX_SIG  = "CREATE INDEX IF NOT EXISTS idx_sig_symbol ON signal_log(symbol)"

# Columns added after v1 — auto-migrated if DB already exists
_NEW_SNAP_COLS = {
    "ce_oi":     "INTEGER DEFAULT 0",
    "pe_oi":     "INTEGER DEFAULT 0",
    "ce_volume": "INTEGER DEFAULT 0",
    "pe_volume": "INTEGER DEFAULT 0",
}


class SnapshotDB:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._lock   = threading.Lock()
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init()

    def _conn(self):
        c = sqlite3.connect(self.db_path, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    def _init(self):
        with self._conn() as c:
            c.execute(_CREATE_SNAPSHOTS)
            c.execute(_CREATE_SIGNAL_LOG)
            c.execute(_IDX_SNAP)
            c.execute(_IDX_SIG)
            self._migrate(c)
            c.commit()

    def _migrate(self, c):
        """Purane DB mein naye columns add karo agar missing hain."""
        existing = {row[1] for row in c.execute("PRAGMA table_info(snapshots)").fetchall()}
        for col, defn in _NEW_SNAP_COLS.items():
            if col not in existing:
                c.execute(f"ALTER TABLE snapshots ADD COLUMN {col} {defn}")
                logger.info(f"Migration: snapshots.{col} column added")

    def save_snapshot(self, data):
        try:
            with self._lock:
                with self._conn() as c:
                    c.execute("""
                        INSERT INTO snapshots
                          (ts,date,time,symbol,spot,pcr,pcr_zone,pcr_trend,
                           vix,iv_rank,atm_ce_ltp,atm_pe_ltp,oi_signal,
                           gex_regime,gex_total,signal,score,atm,
                           ce_oi,pe_oi,ce_volume,pe_volume)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        data.get("ts",         datetime.now().isoformat()),
                        data.get("date",       date.today().isoformat()),
                        data.get("time",       datetime.now().strftime("%H:%M")),
                        data.get("symbol",     "NIFTY"),
                        data.get("spot",       0),
                        data.get("pcr",        0),
                        data.get("pcr_zone",   ""),
                        data.get("pcr_trend",  ""),
                        data.get("vix",        0),
                        data.get("iv_rank",    0),
                        data.get("atm_ce_ltp", 0),
                        data.get("atm_pe_ltp", 0),
                        data.get("oi_signal",  ""),
                        data.get("gex_regime", ""),
                        data.get("gex_total",  0),
                        data.get("signal",     "NO TRADE"),
                        data.get("score",      0),
                        data.get("atm",        0),
                        data.get("ce_oi",      0),
                        data.get("pe_oi",      0),
                        data.get("ce_volume",  0),
                        data.get("pe_volume",  0),
                    ))
                    c.commit()
            return True
        except Exception as e:
            logger.error(f"Snapshot save error: {e}")
            return False

    def save_signal(self, data):
        try:
            with self._lock:
                with self._conn() as c:
                    cur = c.execute("""
                        INSERT INTO signal_log
                          (ts,symbol,signal,score,entry_price,target,sl,
                           strike,vix,pcr,iv_rank)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """, (
                        datetime.now().isoformat(),
                        data.get("symbol",      ""),
                        data.get("signal",      ""),
                        data.get("score",       0),
                        data.get("entry_price", 0),
                        data.get("target",      0),
                        data.get("sl",          0),
                        data.get("strike",      0),
                        data.get("vix",         0),
                        data.get("pcr",         0),
                        data.get("iv_rank",     0),
                    ))
                    c.commit()
                    return cur.lastrowid
        except Exception as e:
            logger.error(f"Signal log error: {e}")
            return -1

    def update_signal_outcome(self, signal_id, outcome, exit_price, pnl_pct):
        try:
            with self._lock:
                with self._conn() as c:
                    c.execute(
                        "UPDATE signal_log SET outcome=?,exit_price=?,pnl_pct=? WHERE id=?",
                        (outcome, exit_price, pnl_pct, signal_id)
                    )
                    c.commit()
        except Exception as e:
            logger.error(f"Outcome update error: {e}")

    def get_snapshots(self, symbol, from_date, to_date):
        try:
            with self._conn() as c:
                rows = c.execute(
                    "SELECT * FROM snapshots WHERE symbol=? AND date>=? AND date<=? ORDER BY ts ASC",
                    (symbol, from_date, to_date)
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Snapshot load error: {e}")
            return []

    def get_signals(self, symbol, from_date="", to_date=""):
        try:
            with self._conn() as c:
                if from_date and to_date:
                    rows = c.execute(
                        "SELECT * FROM signal_log WHERE symbol=? AND date(ts)>=? AND date(ts)<=? ORDER BY ts",
                        (symbol, from_date, to_date)
                    ).fetchall()
                else:
                    rows = c.execute(
                        "SELECT * FROM signal_log WHERE symbol=? ORDER BY ts",
                        (symbol,)
                    ).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            return []

    def get_stats(self):
        try:
            with self._conn() as c:
                total     = c.execute("SELECT COUNT(*) as n FROM snapshots").fetchone()["n"]
                by_sym    = c.execute("SELECT symbol,COUNT(*) as n,MIN(date) as first_date,MAX(date) as last_date FROM snapshots GROUP BY symbol").fetchall()
                total_sig = c.execute("SELECT COUNT(*) as n FROM signal_log").fetchone()["n"]
                outcomes  = c.execute("SELECT outcome,COUNT(*) as n FROM signal_log WHERE outcome!=\'PENDING\' GROUP BY outcome").fetchall()
            return {
                "total_snapshots": total,
                "total_signals":   total_sig,
                "by_symbol":       [dict(r) for r in by_sym],
                "outcomes":        {r["outcome"]: r["n"] for r in outcomes},
            }
        except Exception as e:
            return {}

    def get_available_dates(self, symbol):
        try:
            with self._conn() as c:
                row = c.execute(
                    "SELECT MIN(date) as first,MAX(date) as last,COUNT(*) as total FROM snapshots WHERE symbol=?",
                    (symbol,)
                ).fetchone()
            if row and row["total"] > 0:
                return {"first": row["first"], "last": row["last"], "total": row["total"]}
        except Exception:
            pass
        return {}


class SnapshotCollector:
    MARKET_START = (9, 15)
    MARKET_END   = (15, 30)

    def __init__(self, db=None):
        self.db         = db or SnapshotDB()
        self._last_slot = {}

    def collect(self, cache, symbol, signal_result):
        now = datetime.now()
        if not self._market_hours(now):
            return False
        slot = f"{now.strftime('%Y%m%d_%H')}_{now.minute // 5}"
        if self._last_slot.get(symbol) == slot:
            return False
        try:
            snap  = self._extract(cache, symbol, signal_result, now)
            saved = self.db.save_snapshot(snap)
            if saved:
                self._last_slot[symbol] = slot
                sig_type = signal_result.get("signal", "")
                if sig_type in ("BUY CE", "BUY PE", "SELL — Iron Condor"):
                    entry = signal_result.get("entry", 0)
                    if sig_type == "SELL — Iron Condor":
                        entry = signal_result.get("total_prem", 0)
                    self.db.save_signal({
                        "symbol":      symbol,
                        "signal":      sig_type,
                        "score":       signal_result.get("score",  0),
                        "entry_price": entry,
                        "target":      signal_result.get("target", signal_result.get("sl_premium", 0)),
                        "sl":          signal_result.get("sl",     signal_result.get("sl_premium", 0)),
                        "strike":      signal_result.get("strike", snap["atm"]),
                        "vix":         snap["vix"],
                        "pcr":         snap["pcr"],
                        "iv_rank":     snap["iv_rank"],
                    })
            return saved
        except Exception as e:
            logger.error(f"Collect error: {e}")
            return False

    def _market_hours(self, now):
        h, m = now.hour, now.minute
        return (h, m) >= self.MARKET_START and (h, m) <= self.MARKET_END

    def _extract(self, cache, symbol, signal_result, now):
        sym_map  = {"NIFTY": "NSE:NIFTY 50", "BANKNIFTY": "NSE:NIFTY BANK", "FINNIFTY": "NSE:NIFTY FIN SERVICE"}
        prices   = cache.get("prices",   {})
        iv_data  = cache.get("iv_data",  {})
        gex_data = cache.get("gex_data", {})
        pcr_data = cache.get("pcr_data", {})
        oi_chain = cache.get("oi_chain", [])

        spot = prices.get(sym_map.get(symbol, ""), 0)
        vix  = prices.get("NSE:INDIA VIX", 0)

        pcr = pcr_zone = pcr_trend = ""
        if pcr_data.get(symbol):
            r, trend = pcr_data[symbol]
            pcr, pcr_zone, pcr_trend = r.pcr, r.zone, trend

        step = 50 if symbol == "NIFTY" else 100
        atm  = int(round(spot / step) * step) if spot else 0

        atm_ce = atm_pe = 0.0
        # Totals across all strikes
        total_ce_oi = total_pe_oi = 0
        total_ce_vol = total_pe_vol = 0

        for row in oi_chain:
            # ATM ltp — exact match only (avoids picking wrong strike LTP)
            if int(row.strike) == atm:
                atm_ce = row.ce_ltp or 0
                atm_pe = row.pe_ltp or 0
            # Sum totals
            total_ce_oi  += getattr(row, "ce_oi",     0) or 0
            total_pe_oi  += getattr(row, "pe_oi",     0) or 0
            total_ce_vol += getattr(row, "ce_volume",  0) or 0
            total_pe_vol += getattr(row, "pe_volume",  0) or 0

        return {
            "ts":        now.isoformat(),
            "date":      now.date().isoformat(),
            "time":      now.strftime("%H:%M"),
            "symbol":    symbol,
            "spot":      round(float(spot), 2),
            "pcr":       round(float(pcr), 2) if pcr else 0,
            "pcr_zone":  str(pcr_zone),
            "pcr_trend": str(pcr_trend),
            "vix":       round(float(vix), 2),
            "iv_rank":   round(float(iv_data.get("iv_rank", 0)), 1),
            "atm_ce_ltp": round(float(atm_ce), 2),
            "atm_pe_ltp": round(float(atm_pe), 2),
            "oi_signal":  str(signal_result.get("build", "")),
            "gex_regime": str(gex_data.get("regime", "")),
            "gex_total":  round(float(gex_data.get("total_gex", 0)), 2),
            "signal":     str(signal_result.get("signal", "NO TRADE")),
            "score":      int(signal_result.get("score", 0)),
            "atm":        atm,
            "ce_oi":      int(total_ce_oi),
            "pe_oi":      int(total_pe_oi),
            "ce_volume":  int(total_ce_vol),
            "pe_volume":  int(total_pe_vol),
        }
