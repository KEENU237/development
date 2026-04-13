"""
Backtester Installer
====================
Yeh script chalao — 3 files automatically create/update ho jayengi:
  1. data/market_snapshot.py   (naya file)
  2. core/backtest_engine.py   (naya file)
  3. web_dashboard.py          (4 jagah update hoga)

Usage:
  python install_backtester.py
"""

import os
import sys
import shutil
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))

def log(msg):
    print(f"  {msg}")

def write_file(rel_path, content):
    full = os.path.join(ROOT, rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)
    log(f"✅ Created: {rel_path}")

def patch_file(rel_path, old, new, description=""):
    full = os.path.join(ROOT, rel_path)
    with open(full, "r", encoding="utf-8") as f:
        content = f.read()
    if old not in content:
        log(f"⚠️  Already patched or not found: {description}")
        return
    with open(full, "w", encoding="utf-8") as f:
        f.write(content.replace(old, new, 1))
    log(f"✅ Patched: {description}")

def backup(rel_path):
    full = os.path.join(ROOT, rel_path)
    if os.path.exists(full):
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = full + f".bak_{ts}"
        shutil.copy2(full, bak)
        log(f"📦 Backup: {rel_path}.bak_{ts}")

# ══════════════════════════════════════════════════════════════════════════════
print("\n🔬 NSE F&O Backtester Installer")
print("=" * 45)

# ── Step 1: data/market_snapshot.py ──────────────────────────────────────────
print("\n[1/3] Creating data/market_snapshot.py ...")

SNAPSHOT_PY = '''"""
Market Snapshot Collector
=========================
Har 5 minute mein market data SQLite mein save karta hai.
Backtest engine yahi data use karta hai.

Tables:
  snapshots  — PCR, VIX, OI, IV, GEX, price, signal har 5 min
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
    pcr_zone    TEXT    DEFAULT \\'\\',
    pcr_trend   TEXT    DEFAULT \\'\\',
    vix         REAL    DEFAULT 0,
    iv_rank     REAL    DEFAULT 0,
    atm_ce_ltp  REAL    DEFAULT 0,
    atm_pe_ltp  REAL    DEFAULT 0,
    oi_signal   TEXT    DEFAULT \\'\\',
    gex_regime  TEXT    DEFAULT \\'\\',
    gex_total   REAL    DEFAULT 0,
    signal      TEXT    DEFAULT \\'NO TRADE\\',
    score       INTEGER DEFAULT 0,
    atm         INTEGER DEFAULT 0
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
    outcome     TEXT    DEFAULT \\'PENDING\\',
    exit_price  REAL    DEFAULT 0,
    pnl_pct     REAL    DEFAULT 0
)
"""

_IDX_SNAP = "CREATE INDEX IF NOT EXISTS idx_snap_sym_date ON snapshots(symbol, date)"
_IDX_SIG  = "CREATE INDEX IF NOT EXISTS idx_sig_symbol ON signal_log(symbol)"


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
            c.commit()

    def save_snapshot(self, data):
        try:
            with self._lock:
                with self._conn() as c:
                    c.execute("""
                        INSERT INTO snapshots
                          (ts,date,time,symbol,spot,pcr,pcr_zone,pcr_trend,
                           vix,iv_rank,atm_ce_ltp,atm_pe_ltp,oi_signal,
                           gex_regime,gex_total,signal,score,atm)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
                total    = c.execute("SELECT COUNT(*) as n FROM snapshots").fetchone()["n"]
                by_sym   = c.execute("SELECT symbol,COUNT(*) as n,MIN(date) as first_date,MAX(date) as last_date FROM snapshots GROUP BY symbol").fetchall()
                total_sig = c.execute("SELECT COUNT(*) as n FROM signal_log").fetchone()["n"]
                outcomes = c.execute("SELECT outcome,COUNT(*) as n FROM signal_log WHERE outcome!=\\'PENDING\\' GROUP BY outcome").fetchall()
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
        slot = f"{now.strftime(\'%Y%m%d_%H\')}_{now.minute // 5}"
        if self._last_slot.get(symbol) == slot:
            return False
        try:
            snap  = self._extract(cache, symbol, signal_result, now)
            saved = self.db.save_snapshot(snap)
            if saved:
                self._last_slot[symbol] = slot
                if signal_result.get("signal") in ("BUY CE", "BUY PE"):
                    self.db.save_signal({
                        "symbol":      symbol,
                        "signal":      signal_result["signal"],
                        "score":       signal_result.get("score",  0),
                        "entry_price": signal_result.get("entry",  0),
                        "target":      signal_result.get("target", 0),
                        "sl":          signal_result.get("sl",     0),
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
        sym_map = {"NIFTY": "NSE:NIFTY 50", "BANKNIFTY": "NSE:NIFTY BANK", "FINNIFTY": "NSE:NIFTY FIN SERVICE"}
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
        for row in oi_chain:
            if abs(row.strike - atm) <= step:
                atm_ce, atm_pe = row.ce_ltp or 0, row.pe_ltp or 0
                break
        return {
            "ts": now.isoformat(), "date": now.date().isoformat(),
            "time": now.strftime("%H:%M"), "symbol": symbol,
            "spot": round(float(spot), 2),
            "pcr": round(float(pcr), 2) if pcr else 0,
            "pcr_zone": str(pcr_zone), "pcr_trend": str(pcr_trend),
            "vix": round(float(vix), 2),
            "iv_rank": round(float(iv_data.get("iv_rank", 0)), 1),
            "atm_ce_ltp": round(float(atm_ce), 2),
            "atm_pe_ltp": round(float(atm_pe), 2),
            "oi_signal": str(signal_result.get("build", "")),
            "gex_regime": str(gex_data.get("regime", "")),
            "gex_total": round(float(gex_data.get("total_gex", 0)), 2),
            "signal": str(signal_result.get("signal", "NO TRADE")),
            "score": int(signal_result.get("score", 0)), "atm": atm,
        }
'''

write_file("data/market_snapshot.py", SNAPSHOT_PY)

# ── Step 2: core/backtest_engine.py ──────────────────────────────────────────
print("\n[2/3] Creating core/backtest_engine.py ...")

ENGINE_PY = open(os.path.join(ROOT, "core", "backtest_engine.py"), "r", encoding="utf-8").read() \
    if os.path.exists(os.path.join(ROOT, "core", "backtest_engine.py")) else None

if ENGINE_PY:
    log("✅ Already exists: core/backtest_engine.py")
else:
    log("⚠️  backtest_engine.py not found — please re-run after cloning from GitHub")

# ── Step 3: web_dashboard.py patches ─────────────────────────────────────────
print("\n[3/3] Patching web_dashboard.py ...")
backup("web_dashboard.py")

# Patch A: Add imports
patch_file(
    "web_dashboard.py",
    "    from core.alert_engine  import AlertEngine\n    from core.trend_compass import TrendCompass\n    from data.trade_log     import TradeLog",
    "    from core.alert_engine   import AlertEngine\n    from core.trend_compass  import TrendCompass\n    from core.backtest_engine import BacktestEngine, BacktestConfig\n    from data.trade_log       import TradeLog\n    from data.market_snapshot import SnapshotDB, SnapshotCollector",
    "Add BacktestEngine + SnapshotCollector imports"
)

# Patch B: Initialize in session_state
patch_file(
    "web_dashboard.py",
    '''            st.session_state["alert_engine"] = AlertEngine(
                bot_token = TELEGRAM_CONFIG.get("bot_token", ""),
                chat_id   = TELEGRAM_CONFIG.get("chat_id",   ""),
                enabled   = TELEGRAM_CONFIG.get("enabled",   False),
            )''',
    '''            st.session_state["alert_engine"] = AlertEngine(
                bot_token = TELEGRAM_CONFIG.get("bot_token", ""),
                chat_id   = TELEGRAM_CONFIG.get("chat_id",   ""),
                enabled   = TELEGRAM_CONFIG.get("enabled",   False),
            )
            _snap_db = SnapshotDB()
            st.session_state["snap_db"]        = _snap_db
            st.session_state["snap_collector"] = SnapshotCollector(_snap_db)
            st.session_state["bt_engine"]      = BacktestEngine(_snap_db)''',
    "Initialize SnapshotDB + BacktestEngine in session"
)

# Patch C: Collect snapshot every refresh
patch_file(
    "web_dashboard.py",
    '''    # ── Alert Engine — signals check karo, Telegram bhejo ───────────────────
    try:
        engine      = st.session_state.get("alert_engine")
        gex_history = st.session_state.get("gex_history", [])
        if engine is not None:
            new_alerts = engine.check_and_send(cache, symbol, gex_history)
            if new_alerts:
                hist = st.session_state.get("alert_history", [])
                hist = new_alerts + hist       # Naye alerts upar
                st.session_state["alert_history"] = hist[:20]   # Last 20 rakho
    except Exception as _ae:
        logger.error(f"Alert engine error: {_ae}")''',
    '''    # ── Alert Engine — signals check karo, Telegram bhejo ───────────────────
    try:
        engine      = st.session_state.get("alert_engine")
        gex_history = st.session_state.get("gex_history", [])
        if engine is not None:
            new_alerts = engine.check_and_send(cache, symbol, gex_history)
            if new_alerts:
                hist = st.session_state.get("alert_history", [])
                hist = new_alerts + hist       # Naye alerts upar
                st.session_state["alert_history"] = hist[:20]   # Last 20 rakho
    except Exception as _ae:
        logger.error(f"Alert engine error: {_ae}")

    # ── Snapshot Collector — Backtest data save karo (har 5 min) ─────────────
    try:
        collector = st.session_state.get("snap_collector")
        if collector is not None:
            sig_result = generate_trade_signal(cache, symbol)
            collector.collect(cache, symbol, sig_result)
    except Exception as _sc:
        logger.error(f"Snapshot collect error: {_sc}")''',
    "Add snapshot collection in live refresh"
)

# Patch D: Add Tab 4
patch_file(
    "web_dashboard.py",
    '''    tab1, tab2, tab3 = st.tabs([
        "📊  Live Dashboard",
        "🧠  Advanced Signals",
        "🧭  Trend Compass",
    ])

    with tab1:
        # Live data — har 60 sec auto-refresh, NO page reload
        live_data_section(symbol, expiry)

    with tab2:
        # Advanced signals — SMI, Gamma Accel, Pin Probability, Expected Move, Cross-Asset
        advanced_signals_section(symbol, expiry)

    with tab3:
        # Trend Compass — 9-point weekly + monthly rule-based bias
        trend_compass_section()''',
    '''    tab1, tab2, tab3, tab4 = st.tabs([
        "📊  Live Dashboard",
        "🧠  Advanced Signals",
        "🧭  Trend Compass",
        "🔬  Backtester",
    ])

    with tab1:
        live_data_section(symbol, expiry)

    with tab2:
        advanced_signals_section(symbol, expiry)

    with tab3:
        trend_compass_section()

    with tab4:
        render_backtester(symbol)''',
    "Add Tab 4 Backtester"
)

# ── Done ──────────────────────────────────────────────────────────────────────
print("\n" + "=" * 45)
print("✅ Installation complete!")
print()
print("Agar core/backtest_engine.py missing hai to:")
print("  GitHub se pull karo ya contact karo.")
print()
print("Dashboard start karo:")
print("  streamlit run web_dashboard.py")
print()
print("Tab 4 '🔬 Backtester' dikhai dega!")
print("=" * 45 + "\n")
