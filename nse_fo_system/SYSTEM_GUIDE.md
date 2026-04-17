# NSE F&O Enterprise Trading System — Complete User Guide

---

## Table of Contents

1. [What This System Does](#1-what-this-system-does)
2. [Project Structure — Every File Explained](#2-project-structure--every-file-explained)
3. [How to Start Every Day](#3-how-to-start-every-day)
4. [The Dashboard — Complete Screen Guide](#4-the-dashboard--complete-screen-guide)
5. [Keyboard Controls](#5-keyboard-controls)
6. [How to Read Each Panel](#6-how-to-read-each-panel)
7. [Trading Strategies — How to Use Them](#7-trading-strategies--how-to-use-them)
8. [Risk Management — What It Monitors](#8-risk-management--what-it-monitors)
9. [P&L Reports — How to Generate](#9-pl-reports--how-to-generate)
10. [Configuration — What You Can Change](#10-configuration--what-you-can-change)
11. [Common Errors and Fixes](#11-common-errors-and-fixes)
12. [Trading Concepts Explained](#12-trading-concepts-explained)

---

## 1. What This System Does

This is a **live NSE F&O options trading terminal** built on top of Zerodha Kite Connect API.

It replaces a manual Excel sheet with a real-time terminal dashboard that:

- Shows live NIFTY / BANKNIFTY / FINNIFTY option chain with OI data
- Calculates Max Pain, PCR (Put-Call Ratio), and OI Buildup signals
- Detects Unusual Options Activity (large volume spikes)
- Calculates Greeks (Delta, Gamma, Theta, Vega) and IV Rank
- Lets you build and place multi-leg strategies (Spreads, Straddles, Iron Condor) with one keypress
- Monitors your portfolio risk in real time
- Logs every trade to SQLite and exports P&L reports to Excel

**It does NOT make trading decisions for you.** It gives you the data to make faster, better-informed decisions.

---

## 2. Project Structure — Every File Explained

```
D:\HDFC\nse_fo_system\
│
├── main.py                        ← START HERE — runs the dashboard
├── get_token.py                   ← Run every morning to get Kite token
├── debug_chain.py                 ← Troubleshooting tool (check if Kite API works)
│
├── config\
│   └── settings.py                ← All configuration: API keys, risk limits, strategies
│
├── core\
│   ├── kite_manager.py            ← Zerodha Kite API wrapper
│   ├── market_utils.py            ← Lot sizes, strike steps, expiry dates, cost calculator
│   ├── greeks.py                  ← Black-Scholes: Delta, Gamma, Theta, Vega, IV solver
│   ├── pcr_tracker.py             ← Put-Call Ratio + OI chain live calculator
│   ├── max_pain.py                ← Max Pain strike calculator
│   ├── uoa_scanner.py             ← Unusual Options Activity detector
│   ├── risk_manager.py            ← Portfolio Greeks aggregation + risk limits
│   └── ticker.py                  ← WebSocket tick feed (for future use)
│
├── strategies\
│   ├── basket_builder.py          ← Bull Call Spread, Bear Put Spread, Iron Condor
│   └── straddle.py                ← Short/Long Straddle and Strangle builder
│
├── ui\
│   └── dashboard.py               ← Main terminal UI (Rich-based, no flicker)
│
├── data\
│   ├── trade_log.py               ← SQLite trade journal
│   └── trades.db                  ← Auto-created database (do not delete)
│
├── reports\
│   └── pnl_report.py              ← Excel P&L report generator
│
├── logs\
│   └── system.log                 ← All errors logged here
│
└── requirements.txt               ← Python packages needed
```

---

## 3. How to Start Every Day

### Step 1 — Get a fresh Kite token (REQUIRED every morning)

Zerodha's access tokens expire at midnight every day. You must regenerate one before trading.

```
cd D:\HDFC\nse_fo_system
python get_token.py
```

The script will:
1. Print a login URL
2. Open it in your browser and log in with your Zerodha credentials
3. After login, your browser will redirect to a URL like:
   ```
   http://127.0.0.1/?request_token=KovsJRtdvilUwAqbYVPlKk4D2BT6OMcL&status=success
   ```
4. Copy **only the part after `request_token=` and before `&`** — that long string
5. Paste it in the terminal when asked
6. The script verifies login and saves the token to `data/kite_token.pkl`

**IMPORTANT:**
- Each request_token works **only once** and expires in ~60 seconds
- Do this within 60 seconds of seeing the browser URL
- The token is valid for the **rest of the trading day** only

### Step 2 — Start the dashboard

```
cd D:\HDFC\nse_fo_system
python main.py
```

The system will:
- Load the saved token automatically
- Detect the nearest expiry date (queried live from Kite, handles holidays)
- Ask you to confirm the expiry date (press Enter to accept the default)
- Load all market data
- Launch the live dashboard

---

## 4. The Dashboard — Complete Screen Guide

The terminal is divided into these panels:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  HEADER BAR — Time, Market Status, Expiry, Symbol, Day P&L, Data time  │
├─────────────────────────────────────────────────────────────────────────┤
│          MARKET OVERVIEW — NIFTY 50 | NIFTY BANK | FIN NIFTY | VIX     │
├──────────────────────────────────┬──────────────────────────────────────┤
│  OI CHAIN (left, wider)          │  UNUSUAL OPTIONS ACTIVITY (right)   │
│  CE OI | CHG | LTP | STRIKE |   │  Time | Symbol | Type | Strike |     │
│  LTP | CHG | PE OI | PCR | BUILD │  Multiplier | Signal                │
├──────────────────────────────────┬──────────────────────────────────────┤
│  PCR READINGS                    │  IV RANK · GREEKS · SKEW             │
│  NIFTY PCR | BANKNIFTY PCR      │  Delta, Gamma, Theta, Vega, ATM IV   │
│  Zone | Signal | Strategy        │  IV Rank | IV Skew | Theta Clock     │
├──────────────────────────────────┬──────────────────────────────────────┤
│  OI BUILDUP ANALYSIS             │  PORTFOLIO RISK                      │
│  Strike | Type | Signal |        │  Net Delta, Gamma, Theta, Vega       │
│  OI Change | Price Change        │  Unrealised P&L | Margin Bar         │
├─────────────────────────────────────────────────────────────────────────┤
│  FOOTER — Keyboard shortcuts                                             │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Keyboard Controls

| Key | Action |
|-----|--------|
| `R` | Refresh all data immediately |
| `T` | Switch symbol (NIFTY → BANKNIFTY → FINNIFTY → NIFTY) |
| `B` | Open Basket Order Builder menu |
| `S` | Open Straddle / Strangle Builder menu |
| `I` | Open Iron Condor Builder menu |
| `X` | Generate Excel P&L report (saved to `data/` folder) |
| `Q` | Quit the dashboard |

Data auto-refreshes every **60 seconds** automatically. You do not need to press R.

---

## 6. How to Read Each Panel

### MARKET OVERVIEW Panel

Shows live Last Traded Price (LTP) for:
- **NIFTY 50** — Nifty 50 index spot price
- **NIFTY BANK** — Bank Nifty spot price
- **FIN NIFTY** — Fin Nifty spot price
- **INDIA VIX** — Volatility index
  - Green = VIX below 14 (calm market, good for selling premium)
  - Yellow = VIX 14–20 (moderate volatility)
  - Red = VIX above 20 (high fear, options are expensive)

---

### OI CHAIN Panel

This is the most important panel. It shows the live option chain for the currently selected symbol.

| Column | What It Means |
|--------|---------------|
| CE OI | Number of open Call contracts at this strike (red = call writers = resistance) |
| CHG | Change in CE OI since last refresh. Green = OI increasing, Red = decreasing |
| LTP | Last Traded Price of the Call option |
| **STRIKE** | The strike price. `►ATM◄` = At The Money (nearest to current spot). `[MP]` = Max Pain strike. `★` = ATM and Max Pain are same |
| LTP | Last Traded Price of the Put option |
| CHG | Change in PE OI since last refresh |
| PE OI | Number of open Put contracts (green = support level) |
| PCR | Put-Call Ratio at this strike (PE OI ÷ CE OI). >1 = more puts = bullish support |
| BUILD | OI Buildup signal: FL (Fresh Long), LU (Long Unwind), FS (Fresh Short), SC (Short Cover) |

**Max Pain line (above table):**
Shows the strike where option writers collectively lose the least money — market tends to gravitate here near expiry.
- Support (PE OI) = strike with highest Put OI = likely price floor
- Resist (CE OI) = strike with highest Call OI = likely price ceiling

---

### UNUSUAL OPTIONS ACTIVITY (UOA) Panel

Detects when someone buys options in abnormally large quantities compared to average.

| Column | What It Means |
|--------|---------------|
| TIME | When the activity was detected |
| SYMBOL | Which stock/index |
| T | CE (Call) or PE (Put) |
| STRIKE | Strike price where activity detected |
| MULT | Volume ÷ Average Volume. 5x = 5 times normal. 10x+ shows as `!!!` |
| SIGNAL | BULLISH (unusual CE buying) or BEARISH (unusual PE buying) |

**How to use it:**
- 5x–9x = Unusual — someone may know something. Watch but do not blindly follow.
- 10x+ (FIRE) = Very unusual — large institutional position. Take note of the direction.
- Always check if it is a hedge or a directional bet by looking at the PCR context.

---

### PCR READINGS Panel

Put-Call Ratio = Total Put OI ÷ Total Call OI for the whole chain.

| PCR Value | Zone | What It Means | Suggested Strategy |
|-----------|------|---------------|--------------------|
| > 1.5 | EXTREME BULL | Market is very well protected with puts. Bullish. | Buy CE or Bull Call Spread |
| 1.2 – 1.5 | BULLISH | More puts than calls. Mild bullish. | Bull Call Spread |
| 0.8 – 1.2 | NEUTRAL | Balanced. Sideways market expected. | Iron Condor |
| 0.5 – 0.8 | BEARISH | More calls than puts. Bearish. | Bear Put Spread |
| < 0.5 | EXTREME BEAR | Very bearish market. | Buy PE or Bear Put Spread |

**Trend arrow (▲/▼/→):** Shows if PCR is rising (more bullish) or falling (more bearish) since last refresh.

---

### IV RANK · GREEKS · SKEW Panel

This panel tells you whether options are cheap or expensive right now.

**ATM GREEKS** (at-the-money options):

| Greek | What It Tells You |
|-------|-------------------|
| Delta | How much the option price moves per 1 point move in the index. CE Delta near 0.5 = ATM |
| Gamma | How fast Delta changes. High near expiry — options move faster |
| Theta | How much premium decays PER DAY in Rupees. Negative = you lose this much daily if you bought |
| Vega | How much the option price changes per 1% change in IV |
| ATM IV | Current Implied Volatility of ATM options. Higher = more expensive options |

**IV METRICS:**

| Metric | What It Tells You | When to Act |
|--------|------------------|-------------|
| IV Rank | Where current IV sits vs its 52-week range (0–100%) | >70% = IV high = sell premium. <30% = IV low = buy options |
| IV Skew | OTM Put IV minus OTM Call IV | Positive = fear (puts expensive). Negative = greed (calls expensive) |

**THETA CLOCK:**
- Shows how much premium an ATM Short Straddle earns per day
- Example: "₹4,200/day" means selling one straddle earns ~₹4,200 of time decay daily
- At expiry (7d): shows total potential decay if market stays flat

---

### OI BUILDUP ANALYSIS Panel

Classifies OI changes at each strike into one of 4 categories:

| Signal | What Happened | What It Means |
|--------|--------------|---------------|
| **Fresh Long** | CE OI increased + CE LTP positive | Bulls are entering new positions. Bullish |
| **Long Unwinding** | CE OI decreased + CE LTP falling | Bulls are exiting. Bearish |
| **Fresh Short** | PE OI increased + PE LTP positive | Bears entering new positions. Bearish |
| **Short Covering** | PE OI decreased + PE LTP rising | Bears exiting. Can cause upside |

Only strikes with OI changes of 1,000+ contracts are shown.
Sorted by magnitude (biggest changes at top).

---

### PORTFOLIO RISK Panel

Shows the Greeks of your **entire live open positions** aggregated together.

| Metric | What It Means |
|--------|---------------|
| Net Delta | Total directional exposure. Positive = net long (profits if market rises). Negative = net short |
| Net Gamma | How fast your Delta changes. High gamma = risky near expiry |
| Net Theta | How much money you earn (positive) or lose (negative) per day from time decay |
| Net Vega | How much your portfolio P&L changes per 1% change in IV |
| Unrealised | Current mark-to-market P&L on open positions |
| Positions | Number of open position legs |
| Margin Used % | What percentage of your available capital is being used. Red if >90% |

The margin bar visually shows utilisation. Green = safe. Yellow = watch. Red = urgent.

**Risk Alerts** appear in red if:
- Daily loss exceeds ₹10,000 (configurable)
- Margin usage exceeds 90%
- Warning at 80% of daily loss limit / 75% margin usage

---

## 7. Trading Strategies — How to Use Them

### Press `B` — Basket Order Builder

After pressing B, you see a menu:
```
1  Bull Call Spread  — NIFTY
2  Bear Put Spread   — BANKNIFTY
3  Iron Condor       — NIFTY
0  Back
```

#### Bull Call Spread (Option 1)
- **Market view:** Mildly bullish (expect 1–3% rise)
- **Structure:** BUY ATM CE + SELL OTM CE (200 points above for NIFTY)
- **Cost:** Net Debit (you pay premium upfront)
- **Profit:** If NIFTY rises above the bought strike. Max profit capped.
- **Risk:** Only the premium paid. Max loss = net debit paid.
- **Best when:** IV is moderate (not too high), 7–15 days to expiry, PCR > 1.2

#### Bear Put Spread (Option 2)
- **Market view:** Mildly bearish (expect 1–3% fall)
- **Structure:** BUY ATM PE + SELL OTM PE (500 points below for BANKNIFTY)
- **Cost:** Net Debit
- **Profit:** If index falls below bought strike. Max profit capped.
- **Risk:** Only the premium paid.
- **Best when:** PCR < 0.8, IV rank < 50%, 7–15 days to expiry

#### Iron Condor (Option 3 in Basket, or press `I`)
- **Market view:** Range-bound (market will stay between two levels)
- **Structure:** 4 legs:
  - SELL CE 300 pts above ATM + BUY CE 500 pts above ATM (call spread)
  - SELL PE 300 pts below ATM + BUY PE 500 pts below ATM (put spread)
- **Cost:** Net Credit (you receive premium)
- **Profit:** If market stays between the two short strikes until expiry. Keep the full credit.
- **Risk:** Difference between strikes minus credit received.
- **Best when:** IV Rank > 30%, market in consolidation, 7–10 days to expiry, Max Pain near ATM
- Pressing `I` shows the Max Pain range and automatically sets strikes around it.

---

### Press `S` — Straddle / Strangle Builder

```
1  Short Straddle
2  Long  Straddle
3  Short Strangle
4  Long  Strangle
```

#### Short Straddle (Option 1)
- **Structure:** SELL ATM CE + SELL ATM PE
- **Cost:** Net Credit
- **Profit:** If market stays near ATM at expiry (within the two breakeven points)
- **Risk:** Unlimited. Use only with proper stop loss.
- **Best when:** IV Rank high (>60%), expecting flat market, Theta Clock shows large daily decay

#### Long Straddle (Option 2)
- **Structure:** BUY ATM CE + BUY ATM PE
- **Cost:** Net Debit
- **Profit:** If market makes a large move in either direction
- **Risk:** Total premium paid
- **Best when:** Big event coming (budget, RBI policy), IV Rank low (<30%), IV Skew neutral

#### Short Strangle (Option 3)
- **Structure:** SELL OTM CE + SELL OTM PE (200 pts away for NIFTY, 500 pts for BANKNIFTY)
- **Cost:** Net Credit (smaller than straddle but wider breakevens)
- **Profit:** Market stays within the two short strikes
- **Risk:** Unlimited. Safer than straddle because strikes are wider.
- **Best when:** IV elevated, expecting range-bound with some buffer

#### Long Strangle (Option 4)
- **Structure:** BUY OTM CE + BUY OTM PE
- **Cost:** Cheaper net debit than straddle
- **Profit:** Large directional move
- **Risk:** Full premium paid (less than straddle)

---

### After Selecting Any Strategy

The system shows you the full order summary:
```
──────────────────────────────────────────────────
  BULL CALL SPREAD — NIFTY
──────────────────────────────────────────────────
  BUY  CE 24000  x75  LTP: Rs148.5  Premium: Rs11,137 (+)
  SELL CE 24200  x75  LTP: Rs82.3   Premium: Rs6,172  (-)
──────────────────────────────────────────────────
  Net DEBIT: Rs4,965
──────────────────────────────────────────────────
  Charges — Brokerage: ₹40  STT: ₹5.57  Exchange: ₹3.12  GST: ₹7.78  Total: ₹56.47

  Execute this order? [y/n]
```

- Charges are calculated per-leg using actual Zerodha fee structure (₹20 brokerage flat + STT + Exchange + SEBI + GST + Stamp Duty)
- Type `y` to place or `n` to cancel
- After placement, the Trade ID and Kite Order IDs are shown

---

## 8. Risk Management — What It Monitors

Settings are in `config/settings.py` under the `RISK` section:

```python
RISK = {
    "max_capital_per_trade": 50000,   # Max Rs 50,000 net premium per trade
    "stop_loss_pct": 0.03,            # 3% stop loss (informational)
    "max_daily_loss": 10000,          # Alert if you lose more than Rs 10,000 today
    "max_open_positions": 3,          # Max concurrent open trades
}
```

**How to change these:** Open `config/settings.py` in Notepad and edit the numbers.

The system does NOT automatically close positions when limits are breached — it only alerts you. You must act manually.

---

## 9. P&L Reports — How to Generate

Press `X` in the dashboard at any time.

An Excel file is saved to `data/pnl_YYYYMMDD_HHMMSS.xlsx` with 3 sheets:

1. **Summary** — Today's total trades, win rate, gross P&L (green if positive, red if negative)
2. **Trade Log** — All trades ever placed: entry/exit time, premium, realised P&L, strategy
3. **Open Positions** — Currently open trades with all leg details

Requires `openpyxl` package. If not installed:
```
pip install openpyxl
```

---

## 10. Configuration — What You Can Change

File: `config\settings.py`

### Changing API credentials
```python
KITE_API_KEY    = "your_api_key"           # From kite.trade developer console
KITE_API_SECRET = "your_api_secret"        # From kite.trade developer console
```

### Adding more stocks to UOA scan
```python
UOA_CONFIG = {
    "scan_symbols": [
        "NIFTY", "BANKNIFTY",
        "RELIANCE", "TCS",           # Add any NSE F&O stock here
        "ADANIENT", "TATASTEEL",     # Example additions
    ],
    "min_multiplier": 5.0,           # Minimum 5x volume to trigger alert
    "fire_multiplier": 10.0,         # 10x+ = FIRE alert
}
```

### Changing PCR zones
```python
PCR_ZONES = {
    "EXTREME_BULL":  (1.5, float("inf")),   # PCR > 1.5
    "BULLISH":       (1.2, 1.5),
    "NEUTRAL":       (0.8, 1.2),
    "BEARISH":       (0.5, 0.8),
    "EXTREME_BEAR":  (0.0, 0.5),
}
```

### Changing Iron Condor strike gaps
```python
STRATEGIES = {
    "IRON_CONDOR": {
        "ce_otm_gap": 300,        # Sell CE this many points above ATM
        "pe_otm_gap": 300,        # Sell PE this many points below ATM
        "ce_hedge_gap": 500,      # Buy CE this many points beyond sold CE
        "pe_hedge_gap": 500,      # Buy PE this many points beyond sold PE
    },
}
```

---

## 11. Common Errors and Fixes

### "Token Expired" or "Invalid checksum"
**Cause:** Access token from yesterday. Kite tokens expire every day at midnight.
**Fix:** Run `python get_token.py` and get a fresh token.

### "Invalid request_token"
**Cause:** You either used the token already (each token works only once) or waited too long (>60 seconds).
**Fix:** Go back to browser, open the login URL again (`python get_token.py` prints it), log in fresh, paste the new token within 60 seconds.

### OI Chain showing "Loading..." (all dashes)
**Cause:** Market closed, or wrong expiry date, or API error.
**Check:** Open `logs/system.log` to see the exact error message.

**Cause:** Wrong expiry date entered at startup.
**Fix:** Restart `python main.py` and when it asks for the expiry date, press Enter to accept the auto-detected value.

### BANKNIFTY PCR showing "--"
**Cause:** Old bug (fixed in v2.0). Make sure you are running the latest `ui/dashboard.py`.

### Dashboard flickering / full screen clear on refresh
**Cause:** Old version bug. v2.0 uses `Rich Live` for in-place updates.

### "openpyxl not installed" when pressing X
**Fix:**
```
pip install openpyxl
```

### "kiteconnect not installed"
**Fix:**
```
pip install kiteconnect rich scipy openpyxl
```

Or install everything at once:
```
pip install -r requirements.txt
```

---

## 12. Trading Concepts Explained

### Max Pain
The strike price at which option **writers** (sellers) collectively lose the least money if the underlying expires there. Theory: since writers hedge their positions, the underlying tends to drift toward Max Pain as expiry approaches. Use it to estimate where the market may close on expiry day.

- **Max Pain > Spot** → Bulls may have edge (market could rise toward Max Pain)
- **Max Pain < Spot** → Bears may have edge (market could fall toward Max Pain)
- **Max Pain = Spot** → Market already at equilibrium

### Put-Call Ratio (PCR)
Total Put OI ÷ Total Call OI.
- **High PCR (>1.2)** = More put buying = more hedging = bullish (market participants are protected, so real direction is up)
- **Low PCR (<0.8)** = More call buying = complacency = can be bearish
- **Extreme values** can mean reversal (too much one-sided bets)

### IV Rank (IVR)
Measures where current Implied Volatility sits relative to the past 52-week range:
- **IVR > 70%** = IV is high historically → options are expensive → **SELL premium** (Iron Condor, Short Straddle)
- **IVR < 30%** = IV is low historically → options are cheap → **BUY options** (Long Straddle, directional buys)
- **IVR 30–70%** = Neutral → spreads work well

### IV Skew
Difference between OTM Put IV and OTM Call IV:
- **Positive skew (PE > CE)** = Fear in market. Puts cost more. Bearish sentiment, protective buying.
- **Negative skew (CE > PE)** = Greed. Calls cost more. Speculative call buying.
- **Near zero** = Market balanced, no strong directional bias.

### Theta (Time Decay)
Options lose value every day just due to the passage of time, even if the underlying doesn't move. This is Theta.
- **Short options** (seller): You earn Theta. Time works FOR you.
- **Long options** (buyer): You pay Theta. Time works AGAINST you.
- Theta accelerates exponentially in the last 7 days before expiry.

### OI Buildup Signals
| OI Change | Price Change | Signal | Meaning |
|-----------|-------------|--------|---------|
| OI ↑ | LTP ↑ | Fresh Long | New buyers entering. Bullish |
| OI ↑ | LTP ↓ | Fresh Short | New sellers entering. Bearish |
| OI ↓ | LTP ↑ | Short Covering | Shorts exiting, buying back. Can cause rally |
| OI ↓ | LTP ↓ | Long Unwinding | Longs exiting. Bearish |

### Lot Sizes (SEBI 2025–26)
| Symbol | Lot Size |
|--------|----------|
| NIFTY | 75 |
| BANKNIFTY | 30 |
| FINNIFTY | 40 |
| MIDCPNIFTY | 75 |

---

## Quick Reference Card

```
EVERY MORNING:
  1. python get_token.py   → get fresh Kite token (within 60 sec of browser URL)
  2. python main.py        → start dashboard

DASHBOARD KEYS:
  R = Refresh    T = Switch Symbol    Q = Quit
  B = Basket     S = Straddle         I = Iron Condor     X = Excel Report

WHEN TO USE WHICH STRATEGY:
  Market going UP mildly?           → Bull Call Spread [B → 1]
  Market going DOWN mildly?         → Bear Put Spread [B → 2]
  Market going SIDEWAYS?            → Iron Condor [I] or Short Straddle [S → 1]
  Big event, unsure direction?      → Long Straddle [S → 2]

READ IV RANK FIRST:
  IV Rank > 70% → sell premium (straddle/condor)
  IV Rank < 30% → buy options (long straddle/strangle)

READ PCR:
  PCR > 1.2 and rising → bullish
  PCR < 0.8 and falling → bearish
  PCR 0.8–1.2 → sideways → Iron Condor

LOGS: D:\HDFC\nse_fo_system\logs\system.log
DATA: D:\HDFC\nse_fo_system\data\
```

---

*System Version: 2.0 | Built on Zerodha Kite Connect API | NSE F&O*
