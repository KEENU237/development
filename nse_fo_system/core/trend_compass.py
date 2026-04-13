"""
Trend Compass — Rule-Based Bullish/Bearish Engine
==================================================
NIFTY aur BANKNIFTY ke liye weekly + monthly trend identify karta hai.

9-Point Checklist per symbol per timeframe:
  1. Price > 20 EMA
  2. Price > 50 EMA
  3. Price > 200 EMA
  4. 20 EMA > 50 EMA  (short-term alignment)
  5. 50 EMA > 200 EMA (major trend intact)
  6. Higher Highs + Higher Lows (last 4 candles)
  7. RSI > 55 (bullish momentum)
  8. Price > Classic Pivot Point
  9. Price > Key Resistance Level broken

Score → Verdict:
  8-9  : STRONGLY BULLISH
  6-7  : BULLISH
  4-5  : NEUTRAL
  2-3  : BEARISH
  0-1  : STRONGLY BEARISH
"""

import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

# ── Instrument tokens (NSE Index via Kite) ────────────────────────────────────
INDEX_TOKENS = {
    "NIFTY":     256265,
    "BANKNIFTY": 260105,
}

TIMEFRAME_INTERVAL = {
    "Weekly":  "week",
    "Monthly": "month",
}

# How many days of history to fetch (enough candles for EMA-200)
TIMEFRAME_LOOKBACK_DAYS = {
    "Weekly":  365 * 5,   # 5 years → ~260 weekly candles
    "Monthly": 365 * 20,  # 20 years → ~240 monthly candles
}

SYMBOL_DISPLAY = {
    "NIFTY":     "NIFTY 50",
    "BANKNIFTY": "BANK NIFTY",
}


# ══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class CheckItem:
    name: str
    passed: bool
    detail: str
    weight: int = 1


@dataclass
class TrendResult:
    symbol: str
    timeframe: str
    score: int
    max_score: int
    verdict: str        # STRONGLY BULLISH / BULLISH / NEUTRAL / BEARISH / STRONGLY BEARISH
    color: str          # hex
    checks: List[CheckItem]
    price: float
    ema20: float
    ema50: float
    ema200: float
    rsi: float
    pivot: float
    support: float
    resistance: float
    candles_count: int
    error: str = ""


# ══════════════════════════════════════════════════════════════════════════════
# MATH HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _ema(closes: list, period: int) -> float:
    """Exponential Moving Average — last value."""
    if not closes:
        return 0.0
    if len(closes) < period:
        return sum(closes) / len(closes)
    k = 2.0 / (period + 1)
    ema = sum(closes[:period]) / period
    for price in closes[period:]:
        ema = price * k + ema * (1 - k)
    return round(ema, 2)


def _rsi(closes: list, period: int = 14) -> float:
    """Wilder's RSI — last value."""
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    recent = deltas[-period:]
    gains  = [max(d, 0.0) for d in recent]
    losses = [abs(min(d, 0.0)) for d in recent]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _pivot_classic(high: float, low: float, close: float) -> tuple:
    """
    Classic pivot point + R1/S1.
    Returns (pivot, resistance1, support1)
    """
    pp = (high + low + close) / 3.0
    r1 = 2 * pp - low
    s1 = 2 * pp - high
    return round(pp, 2), round(r1, 2), round(s1, 2)


def _higher_high_higher_low(candles: list, n: int = 4) -> bool:
    """
    True if last n candles show rising highs AND rising lows.
    Strict bullish price structure.
    """
    if len(candles) < n:
        return False
    recent = candles[-n:]
    highs = [c["high"] for c in recent]
    lows  = [c["low"]  for c in recent]
    hh = all(highs[i] >= highs[i - 1] for i in range(1, len(highs)))
    hl = all(lows[i]  >= lows[i - 1]  for i in range(1, len(lows)))
    return hh and hl


def _key_resistance_broken(candles: list, lookback: int = 20) -> tuple:
    """
    Key resistance = highest high of last `lookback` candles (excluding current).
    Returns (broken: bool, resistance_level: float)
    """
    if len(candles) < lookback + 1:
        return False, 0.0
    reference = candles[-(lookback + 1):-1]
    resistance = max(c["high"] for c in reference)
    current_close = candles[-1]["close"]
    return current_close > resistance, round(resistance, 2)


# ══════════════════════════════════════════════════════════════════════════════
# VERDICT MAPPING
# ══════════════════════════════════════════════════════════════════════════════

def _score_to_verdict(score: int, max_score: int) -> tuple:
    """Returns (verdict_str, hex_color)"""
    pct = score / max_score if max_score else 0
    if pct >= 0.88:
        return "STRONGLY BULLISH", "#00c853"
    elif pct >= 0.66:
        return "BULLISH", "#69f0ae"
    elif pct >= 0.44:
        return "NEUTRAL", "#ffeb3b"
    elif pct >= 0.22:
        return "BEARISH", "#ff6b35"
    else:
        return "STRONGLY BEARISH", "#ff1744"


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ENGINE
# ══════════════════════════════════════════════════════════════════════════════

class TrendCompass:
    """
    Rule-based trend identification engine.
    Usage:
        compass = TrendCompass(kite_manager)
        results = compass.analyze_all()
        # results["NIFTY"]["Weekly"] → TrendResult
    """

    def __init__(self, kite_manager):
        self.km = kite_manager

    # ── Single symbol + timeframe ─────────────────────────────────────────────

    def analyze(self, symbol: str, timeframe: str) -> TrendResult:
        """Run 9-point checklist for one symbol + timeframe."""

        EMPTY = TrendResult(
            symbol=symbol, timeframe=timeframe,
            score=0, max_score=9, verdict="NO DATA", color="#888888",
            checks=[], price=0, ema20=0, ema50=0, ema200=0,
            rsi=0, pivot=0, support=0, resistance=0, candles_count=0,
        )

        token = INDEX_TOKENS.get(symbol.upper())
        interval = TIMEFRAME_INTERVAL.get(timeframe)
        lookback = TIMEFRAME_LOOKBACK_DAYS.get(timeframe, 365 * 5)

        if not token or not interval:
            EMPTY.error = f"Unknown symbol/timeframe: {symbol}/{timeframe}"
            return EMPTY

        to_dt   = datetime.now()
        from_dt = to_dt - timedelta(days=lookback)

        try:
            candles = self.km.get_historical(
                token,
                from_dt.strftime("%Y-%m-%d"),
                to_dt.strftime("%Y-%m-%d"),
                interval,
            )
        except Exception as exc:
            logger.error(f"TrendCompass fetch error ({symbol}/{timeframe}): {exc}")
            EMPTY.error = str(exc)
            return EMPTY

        if not candles or len(candles) < 10:
            EMPTY.error = "Not enough candles (need at least 10)"
            return EMPTY

        # ── Prepare series ────────────────────────────────────────────────────
        closes  = [c["close"]  for c in candles]
        highs   = [c["high"]   for c in candles]
        lows    = [c["low"]    for c in candles]
        volumes = [c.get("volume", 0) for c in candles]

        price   = closes[-1]

        # ── EMAs ─────────────────────────────────────────────────────────────
        ema20  = _ema(closes, 20)
        ema50  = _ema(closes, 50)
        ema200 = _ema(closes, 200)

        # ── RSI ──────────────────────────────────────────────────────────────
        rsi = _rsi(closes, 14)

        # ── Pivot from second-to-last complete candle ─────────────────────────
        ref_idx = -2 if len(candles) >= 2 else -1
        pivot, r1, s1 = _pivot_classic(highs[ref_idx], lows[ref_idx], closes[ref_idx])

        # ── Key resistance ───────────────────────────────────────────────────
        res_broken, key_res = _key_resistance_broken(candles, lookback=20)

        # ── Volume filter ────────────────────────────────────────────────────
        recent_vols  = volumes[-21:-1]
        avg_vol      = sum(recent_vols) / len(recent_vols) if recent_vols else 0
        curr_vol     = volumes[-1]
        vol_confirm  = curr_vol > avg_vol if avg_vol > 0 else False

        # ── 9-Point Checklist ─────────────────────────────────────────────────
        checks: List[CheckItem] = [
            CheckItem(
                "Price > 20 EMA",
                price > ema20,
                f"Price {price:,.0f}  |  EMA20 {ema20:,.0f}",
            ),
            CheckItem(
                "Price > 50 EMA",
                price > ema50,
                f"Price {price:,.0f}  |  EMA50 {ema50:,.0f}",
            ),
            CheckItem(
                "Price > 200 EMA",
                price > ema200,
                f"Price {price:,.0f}  |  EMA200 {ema200:,.0f}",
            ),
            CheckItem(
                "20 EMA > 50 EMA  (short-term bullish)",
                ema20 > ema50,
                f"EMA20 {ema20:,.0f}  |  EMA50 {ema50:,.0f}",
            ),
            CheckItem(
                "50 EMA > 200 EMA  (major uptrend intact)",
                ema50 > ema200,
                f"EMA50 {ema50:,.0f}  |  EMA200 {ema200:,.0f}",
            ),
            CheckItem(
                "Higher Highs + Higher Lows  (last 4 candles)",
                _higher_high_higher_low(candles, 4),
                "Bullish price structure confirmed" if _higher_high_higher_low(candles, 4)
                else "Lower high or lower low detected",
            ),
            CheckItem(
                "RSI > 55  (bullish momentum)",
                rsi > 55,
                f"RSI = {rsi:.1f}  {'(Overbought)' if rsi > 70 else '(Bullish Zone)' if rsi > 55 else '(Neutral)' if rsi >= 45 else '(Bearish Zone)'}",
            ),
            CheckItem(
                "Price > Classic Pivot Point",
                price > pivot,
                f"Price {price:,.0f}  |  Pivot {pivot:,.0f}  |  R1 {r1:,.0f}  |  S1 {s1:,.0f}",
            ),
            CheckItem(
                "Key Resistance Broken  (20-candle high)",
                res_broken,
                f"Resistance {key_res:,.0f}  |  Price {'ABOVE' if res_broken else 'BELOW'}",
            ),
        ]

        score     = sum(c.weight for c in checks if c.passed)
        max_score = len(checks)
        verdict, color = _score_to_verdict(score, max_score)

        return TrendResult(
            symbol=symbol,
            timeframe=timeframe,
            score=score,
            max_score=max_score,
            verdict=verdict,
            color=color,
            checks=checks,
            price=price,
            ema20=ema20,
            ema50=ema50,
            ema200=ema200,
            rsi=rsi,
            pivot=pivot,
            support=s1,
            resistance=r1,
            candles_count=len(candles),
        )

    # ── All symbols + timeframes ──────────────────────────────────────────────

    def analyze_all(self) -> dict:
        """
        Returns nested dict:
          results["NIFTY"]["Weekly"]   → TrendResult
          results["NIFTY"]["Monthly"]  → TrendResult
          results["BANKNIFTY"]["Weekly"]  → TrendResult
          results["BANKNIFTY"]["Monthly"] → TrendResult
        """
        results = {}
        for symbol in ["NIFTY", "BANKNIFTY"]:
            results[symbol] = {}
            for tf in ["Weekly", "Monthly"]:
                results[symbol][tf] = self.analyze(symbol, tf)
        return results
