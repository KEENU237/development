"""
Backtesting Engine — World Class F&O Signal Validator
=====================================================
Collected market snapshots use karke:
  1. Signals historically replay karo
  2. Realistic slippage + brokerage ke saath trade simulate karo
  3. Walk-Forward validation (Train / Validate / Test split)
  4. Monte Carlo robustness test (1000 iterations)
  5. Comprehensive analytics — Win Rate, PF, Sharpe, Drawdown
  6. Best Conditions analysis — konsa combination best kaam karta hai
"""

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)

# ── Trading costs (Zerodha approximate) ──────────────────────────────────────
BROKERAGE_PER_LOT  = 40.0    # Rs per lot flat
STT_SELL_PCT       = 0.0625  # STT on sell side (options)
EXCHANGE_CHARGES   = 0.0003  # NSE + SEBI charges
SLIPPAGE_RS        = 1.5     # Avg bid-ask spread slippage

LOT_SIZE = {"NIFTY": 75, "BANKNIFTY": 30, "FINNIFTY": 40}


# ══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class BacktestConfig:
    symbol:              str   = "NIFTY"
    from_date:           str   = ""
    to_date:             str   = ""

    # Signal filters
    min_score:           int   = 35     # Matches live full-data threshold (was 30)
    max_vix:             float = 20.0   # Skip BUY CE/PE if VIX above this (Iron Condor allowed)
    min_pcr_bull:        float = 1.2    # Min PCR for BUY CE
    max_pcr_bear:        float = 0.8    # Max PCR for BUY PE

    # Trade simulation
    slippage_rs:         float = SLIPPAGE_RS
    lots:                int   = 1
    capital:             float = 100_000.0   # Rs 1 lakh

    # Time filters
    entry_start:         str   = "09:45"
    entry_end:           str   = "11:30"
    force_exit_time:     str   = "14:00"

    # Robustness
    use_walk_forward:    bool  = True
    monte_carlo_runs:    int   = 1000


# ══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class BacktestTrade:
    snap_id:      int
    ts:           str
    date:         str
    time:         str
    symbol:       str
    direction:    str    # "BUY CE" | "BUY PE"
    strike:       int
    entry_price:  float
    target:       float
    sl:           float
    exit_price:   float = 0.0
    exit_reason:  str   = "PENDING"   # TARGET / SL / TIME_EXIT / END_DATA
    pnl_pts:      float = 0.0
    pnl_pct:      float = 0.0
    pnl_rs:       float = 0.0
    costs_rs:     float = 0.0
    score:        int   = 0
    vix:          float = 0.0
    pcr:          float = 0.0
    iv_rank:      float = 0.0
    hour:         int   = 10


@dataclass
class AnalyticsResult:
    total_trades:     int   = 0
    wins:             int   = 0
    losses:           int   = 0
    win_rate:         float = 0.0
    profit_factor:    float = 0.0
    avg_win_pct:      float = 0.0
    avg_loss_pct:     float = 0.0
    max_drawdown_rs:  float = 0.0
    max_win_streak:   int   = 0
    max_loss_streak:  int   = 0
    total_pnl_rs:     float = 0.0
    roi_pct:          float = 0.0
    sharpe_ratio:     float = 0.0
    expectancy_rs:    float = 0.0
    target_hit_rate:  float = 0.0
    sl_hit_rate:      float = 0.0
    time_exit_rate:   float = 0.0


@dataclass
class BacktestResult:
    config:          BacktestConfig
    trades:          List[BacktestTrade]  = field(default_factory=list)
    analytics:       AnalyticsResult      = field(default_factory=AnalyticsResult)
    walk_forward:    List[dict]           = field(default_factory=list)
    monte_carlo:     dict                 = field(default_factory=dict)
    daily_pnl:       List[dict]           = field(default_factory=list)
    best_conditions: dict                 = field(default_factory=dict)
    equity_curve:    List[dict]           = field(default_factory=list)
    error:           str                  = ""


# ══════════════════════════════════════════════════════════════════════════════
# ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class BacktestEngine:
    """
    World-class backtesting engine for NSE F&O signals.

    Usage:
        engine = BacktestEngine()
        config = BacktestConfig(symbol="NIFTY", from_date="2025-01-01",
                                to_date="2025-03-31")
        result = engine.run(config)
    """

    def __init__(self, snapshot_db=None):
        from data.market_snapshot import SnapshotDB
        self.db = snapshot_db or SnapshotDB()

    # ── Main Entry ────────────────────────────────────────────────────────────

    def run(self, config: BacktestConfig) -> BacktestResult:
        """
        Full backtest pipeline:
        Load data → Replay signals → Simulate trades →
        Analytics → Walk-forward → Monte Carlo
        """
        result = BacktestResult(config=config)

        try:
            # 1. Load snapshots from DB
            snapshots = self.db.get_snapshots(
                config.symbol, config.from_date, config.to_date
            )

            if len(snapshots) < 10:
                result.error = (
                    f"Sirf {len(snapshots)} snapshots mile "
                    f"({config.from_date} to {config.to_date}).\n"
                    f"Minimum 10 chahiye — system thoda aur time chalne do!"
                )
                return result

            # 2. Replay signals + simulate trades
            trades = self._replay(snapshots, config)
            result.trades = trades

            if not trades:
                result.error = (
                    "Koi qualifying signal nahi mila selected filters ke saath.\n"
                    "Score threshold ya VIX filter thoda loosen karo."
                )
                return result

            # 3. Core analytics
            result.analytics       = self._analytics(trades, config.capital)
            result.daily_pnl       = self._daily_pnl(trades)
            result.equity_curve    = self._equity_curve(trades, config.capital)
            result.best_conditions = self._best_conditions(trades)

            # 4. Walk-forward (needs enough data)
            if config.use_walk_forward and len(snapshots) >= 200:
                result.walk_forward = self._walk_forward(snapshots, config)

            # 5. Monte Carlo (needs ≥20 trades)
            if len(trades) >= 20:
                result.monte_carlo = self._monte_carlo(
                    trades, config.monte_carlo_runs, config.capital
                )

        except Exception as exc:
            logger.error(f"BacktestEngine.run error: {exc}", exc_info=True)
            result.error = f"Engine error: {exc}"

        return result

    # ── Signal Replay ─────────────────────────────────────────────────────────

    def _replay(self, snapshots: list,
                config: BacktestConfig) -> List[BacktestTrade]:
        """
        Step through every snapshot chronologically.
        Open trades when signal qualifies, close on TARGET / SL / TIME.
        One trade at a time (no overlapping positions).
        """
        trades: List[BacktestTrade] = []
        open_trade: Optional[BacktestTrade] = None

        for i, snap in enumerate(snapshots):
            t    = snap.get("time", "00:00")
            date = snap.get("date", "")

            # ── Manage open trade ─────────────────────────────────────────────
            if open_trade is not None:
                ltp = self._get_ltp(snap, open_trade.direction)

                if ltp > 0:
                    # Same-day expiry check — don't carry overnight
                    # Close at first snapshot of new day (>= 09:15, not 09:20)
                    if date != open_trade.date and t >= "09:15":
                        trade = self._close(
                            open_trade, ltp, "END_OF_DAY", config)
                        trades.append(trade)
                        open_trade = None
                        # Fall through to check new signal

                    elif ltp >= open_trade.target:
                        trades.append(
                            self._close(open_trade, ltp, "TARGET", config))
                        open_trade = None
                        continue

                    elif ltp <= open_trade.sl:
                        trades.append(
                            self._close(open_trade, ltp, "SL", config))
                        open_trade = None
                        continue

                    elif t >= config.force_exit_time:
                        trades.append(
                            self._close(open_trade, ltp, "TIME_EXIT", config))
                        open_trade = None
                        continue
                    else:
                        continue   # Still in trade, no close condition yet

            # ── Check for new signal ──────────────────────────────────────────
            if open_trade is not None:
                continue   # Already in position

            if not (config.entry_start <= t <= config.entry_end):
                continue   # Outside entry window

            signal  = snap.get("signal", "")
            score   = int(snap.get("score", 0))
            vix     = float(snap.get("vix",   0))
            pcr     = float(snap.get("pcr",   0))
            iv_rank = float(snap.get("iv_rank", 50))

            if signal not in ("BUY CE", "BUY PE", "SELL — Iron Condor"):
                continue
            if score < config.min_score:
                continue
            # VIX filter only blocks directional trades — Iron Condor is designed for high VIX
            if signal in ("BUY CE", "BUY PE") and vix > config.max_vix:
                continue
            if signal == "BUY CE" and pcr < config.min_pcr_bull:
                continue
            if signal == "BUY PE" and pcr >= config.max_pcr_bear:
                continue

            # Entry price from snapshot + slippage
            raw_entry = self._get_ltp(snap, signal)
            if raw_entry <= 0:
                continue

            entry = round(raw_entry + config.slippage_rs, 2)

            # Dynamic target/SL — mirrors live signal ratios (VIX-based)
            if vix < 15:
                gain_mult, sl_mult = 1.50, 0.70   # Low VIX: wider target, tighter SL
            elif vix < 20:
                gain_mult, sl_mult = 1.42, 0.72   # Normal VIX
            else:
                gain_mult, sl_mult = 1.35, 0.65   # High VIX: tighter target, wider SL
            target = round(entry * gain_mult, 2)
            sl     = round(entry * sl_mult,   2)

            open_trade = BacktestTrade(
                snap_id     = snap.get("id", i),
                ts          = snap.get("ts", ""),
                date        = date,
                time        = t,
                symbol      = config.symbol,
                direction   = signal,
                strike      = snap.get("atm", 0),
                entry_price = entry,
                target      = target,
                sl          = sl,
                score       = score,
                vix         = vix,
                pcr         = pcr,
                iv_rank     = iv_rank,
                hour        = int(t.split(":")[0]) if ":" in t else 10,
            )

        # Force-close any trade still open at end of data
        if open_trade is not None and snapshots:
            ltp = self._get_ltp(snapshots[-1], open_trade.direction)
            if ltp > 0:
                trades.append(
                    self._close(open_trade, ltp, "END_DATA", config))

        return trades

    # ── Trade Simulation ──────────────────────────────────────────────────────

    def _get_ltp(self, snap: dict, direction: str) -> float:
        if direction == "BUY CE":
            return float(snap.get("atm_ce_ltp") or 0)
        return float(snap.get("atm_pe_ltp") or 0)

    def _close(self, trade: BacktestTrade, ltp: float,
               reason: str, config: BacktestConfig) -> BacktestTrade:
        """Close trade — apply exit slippage + realistic costs."""
        lot = LOT_SIZE.get(config.symbol, 75)

        # Slippage against us on exit
        exit_px = max(ltp - config.slippage_rs, 0.5)

        # Costs
        brokerage = BROKERAGE_PER_LOT * config.lots
        stt       = exit_px * lot * config.lots * STT_SELL_PCT / 100
        exchange  = exit_px * lot * config.lots * EXCHANGE_CHARGES / 100
        costs     = round(brokerage + stt + exchange, 2)

        pnl_pts = round(exit_px - trade.entry_price, 2)
        pnl_pct = round(pnl_pts / trade.entry_price * 100, 1) \
                  if trade.entry_price > 0 else 0
        pnl_rs  = round(pnl_pts * lot * config.lots - costs, 2)

        trade.exit_price = round(exit_px, 2)
        trade.exit_reason = reason
        trade.pnl_pts  = pnl_pts
        trade.pnl_pct  = pnl_pct
        trade.pnl_rs   = pnl_rs
        trade.costs_rs = costs
        return trade

    # ── Core Analytics ────────────────────────────────────────────────────────

    def _analytics(self, trades: List[BacktestTrade],
                   capital: float) -> AnalyticsResult:
        if not trades:
            return AnalyticsResult()

        wins   = [t for t in trades if t.pnl_rs > 0]
        losses = [t for t in trades if t.pnl_rs <= 0]
        n      = len(trades)

        win_rate = round(len(wins) / n * 100, 1)

        gross_win  = sum(t.pnl_rs for t in wins)
        gross_loss = abs(sum(t.pnl_rs for t in losses))
        pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else 99.0

        avg_win_pct  = round(sum(t.pnl_pct for t in wins)   / len(wins),   1) if wins   else 0
        avg_loss_pct = round(sum(t.pnl_pct for t in losses) / len(losses), 1) if losses else 0

        # Max drawdown
        equity  = 0.0
        peak    = 0.0
        max_dd  = 0.0
        for t in trades:
            equity += t.pnl_rs
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd

        # Streaks
        mws = mls = cw = cl = 0
        for t in trades:
            if t.pnl_rs > 0:
                cw += 1; cl = 0; mws = max(mws, cw)
            else:
                cl += 1; cw = 0; mls = max(mls, cl)

        total_pnl = round(sum(t.pnl_rs for t in trades), 2)
        roi       = round(total_pnl / capital * 100, 1)

        # Sharpe (annualised, daily returns)
        daily: Dict[str, float] = {}
        for t in trades:
            daily[t.date] = daily.get(t.date, 0) + t.pnl_rs
        dvals = list(daily.values())
        if len(dvals) > 1:
            try:
                import statistics
                avg_d = statistics.mean(dvals)
                std_d = statistics.stdev(dvals)
                sharpe = round((avg_d / std_d) * (252 ** 0.5), 2) if std_d > 0 else 0
            except Exception:
                sharpe = 0
        else:
            sharpe = 0

        expectancy = round(total_pnl / n, 0)

        # Exit reason rates
        target_ct = sum(1 for t in trades if t.exit_reason == "TARGET")
        sl_ct     = sum(1 for t in trades if t.exit_reason == "SL")
        time_ct   = sum(1 for t in trades if t.exit_reason == "TIME_EXIT")

        return AnalyticsResult(
            total_trades    = n,
            wins            = len(wins),
            losses          = len(losses),
            win_rate        = win_rate,
            profit_factor   = pf,
            avg_win_pct     = avg_win_pct,
            avg_loss_pct    = avg_loss_pct,
            max_drawdown_rs = round(max_dd, 0),
            max_win_streak  = mws,
            max_loss_streak = mls,
            total_pnl_rs    = total_pnl,
            roi_pct         = roi,
            sharpe_ratio    = sharpe,
            expectancy_rs   = expectancy,
            target_hit_rate = round(target_ct / n * 100, 1),
            sl_hit_rate     = round(sl_ct     / n * 100, 1),
            time_exit_rate  = round(time_ct   / n * 100, 1),
        )

    # ── Equity Curve ──────────────────────────────────────────────────────────

    def _equity_curve(self, trades: List[BacktestTrade],
                      capital: float) -> List[dict]:
        equity = capital
        curve  = []
        for t in trades:
            equity += t.pnl_rs
            curve.append({
                "date":   t.date,
                "time":   t.time,
                "pnl":    t.pnl_rs,
                "equity": round(equity, 2),
                "trade":  t.direction,
            })
        return curve

    # ── Daily P&L ─────────────────────────────────────────────────────────────

    def _daily_pnl(self, trades: List[BacktestTrade]) -> List[dict]:
        daily: Dict[str, dict] = {}
        for t in trades:
            d = t.date
            if d not in daily:
                daily[d] = {"date": d, "pnl": 0.0, "trades": 0, "wins": 0}
            daily[d]["pnl"]    += t.pnl_rs
            daily[d]["trades"] += 1
            if t.pnl_rs > 0:
                daily[d]["wins"] += 1
        result = []
        for d, v in sorted(daily.items()):
            v["pnl"] = round(v["pnl"], 2)
            result.append(v)
        return result

    # ── Best Conditions ───────────────────────────────────────────────────────

    def _best_conditions(self, trades: List[BacktestTrade]) -> dict:
        """Slice trades by conditions — find winning combos."""
        def stats(subset: List[BacktestTrade]) -> dict:
            if not subset:
                return {}
            wins = [t for t in subset if t.pnl_rs > 0]
            return {
                "count":    len(subset),
                "win_rate": round(len(wins) / len(subset) * 100, 1),
                "total_pnl": round(sum(t.pnl_rs for t in subset), 0),
                "avg_pnl":  round(sum(t.pnl_rs for t in subset) / len(subset), 0),
                "avg_score": round(sum(t.score for t in subset) / len(subset), 0),
            }

        return {
            "by_pcr": {
                "PCR 1.5+":    stats([t for t in trades if t.pcr >= 1.5]),
                "PCR 1.2-1.5": stats([t for t in trades if 1.2 <= t.pcr < 1.5]),
                "PCR < 1.2":   stats([t for t in trades if t.pcr < 1.2]),
            },
            "by_vix": {
                "VIX < 13":  stats([t for t in trades if 0 < t.vix < 13]),
                "VIX 13-16": stats([t for t in trades if 13 <= t.vix < 16]),
                "VIX 16-20": stats([t for t in trades if 16 <= t.vix < 20]),
                "VIX 20+":   stats([t for t in trades if t.vix >= 20]),
            },
            "by_time": {
                "09:45-10:00": stats([t for t in trades if "09:45" <= t.time < "10:00"]),
                "10:00-10:30": stats([t for t in trades if "10:00" <= t.time < "10:30"]),
                "10:30-11:00": stats([t for t in trades if "10:30" <= t.time < "11:00"]),
                "11:00-11:30": stats([t for t in trades if "11:00" <= t.time <= "11:30"]),
            },
            "by_score": {
                "Score 30-45": stats([t for t in trades if 30 <= t.score < 45]),
                "Score 45-60": stats([t for t in trades if 45 <= t.score < 60]),
                "Score 60-80": stats([t for t in trades if 60 <= t.score < 80]),
                "Score 80+":   stats([t for t in trades if t.score >= 80]),
            },
            "by_exit": {
                "TARGET hit": stats([t for t in trades if t.exit_reason == "TARGET"]),
                "SL hit":     stats([t for t in trades if t.exit_reason == "SL"]),
                "Time exit":  stats([t for t in trades if t.exit_reason == "TIME_EXIT"]),
            },
            "by_iv_rank": {
                "IV < 20%":   stats([t for t in trades if t.iv_rank < 20]),
                "IV 20-40%":  stats([t for t in trades if 20 <= t.iv_rank < 40]),
                "IV 40-60%":  stats([t for t in trades if 40 <= t.iv_rank < 60]),
                "IV 60%+":    stats([t for t in trades if t.iv_rank >= 60]),
            },
        }

    # ── Walk-Forward ──────────────────────────────────────────────────────────

    def _walk_forward(self, snapshots: list,
                      config: BacktestConfig) -> List[dict]:
        """
        Split data into 3 sequential periods (no look-ahead bias):
          Train (50%) | Validate (25%) | Test (25%)
        Consistent results across all 3 = robust strategy.
        """
        n = len(snapshots)
        splits = [
            ("Train (50%)",    snapshots[:n // 2]),
            ("Validate (25%)", snapshots[n // 2: 3 * n // 4]),
            ("Test (25%)",     snapshots[3 * n // 4:]),
        ]
        results = []
        for name, chunk in splits:
            if len(chunk) < 5:
                continue
            t = self._replay(chunk, config)
            if t:
                an = self._analytics(t, config.capital)
                d_from = chunk[0]["date"]  if chunk else ""
                d_to   = chunk[-1]["date"] if chunk else ""
                results.append({
                    "period":         name,
                    "date_range":     f"{d_from} → {d_to}",
                    "snapshots":      len(chunk),
                    "trades":         len(t),
                    "win_rate":       an.win_rate,
                    "profit_factor":  an.profit_factor,
                    "total_pnl_rs":   an.total_pnl_rs,
                    "roi_pct":        an.roi_pct,
                    "max_dd_rs":      an.max_drawdown_rs,
                })
        return results

    # ── Monte Carlo ───────────────────────────────────────────────────────────

    def _monte_carlo(self, trades: List[BacktestTrade],
                     iterations: int, capital: float) -> dict:
        """
        Randomly shuffle trade order N times.
        Answers: "What's the worst this strategy can do by bad luck alone?"
        """
        pnls    = [t.pnl_rs for t in trades]
        finals  = []
        max_dds = []

        for _ in range(iterations):
            seq    = pnls.copy()
            random.shuffle(seq)

            equity = capital
            peak   = capital
            max_dd = 0.0
            for p in seq:
                equity += p
                if equity > peak:
                    peak = equity
                dd = peak - equity
                if dd > max_dd:
                    max_dd = dd

            finals.append(round(equity - capital, 2))
            max_dds.append(round(max_dd, 2))

        finals.sort()
        max_dds.sort()

        pct5  = finals[int(iterations * 0.05)]
        pct50 = finals[int(iterations * 0.50)]
        pct95 = finals[int(iterations * 0.95)]

        return {
            "iterations":      iterations,
            "pnl_5th_pct":     round(pct5,  0),    # Worst 5% scenario
            "pnl_median":      round(pct50, 0),    # Most likely outcome
            "pnl_95th_pct":    round(pct95, 0),    # Best 5% scenario
            "worst_dd_rs":     round(max_dds[-1], 0),
            "median_dd_rs":    round(max_dds[iterations // 2], 0),
            "prob_profitable": round(
                sum(1 for f in finals if f > 0) / iterations * 100, 1
            ),
        }
