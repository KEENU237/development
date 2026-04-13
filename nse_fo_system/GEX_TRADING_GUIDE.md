# GEX Trading Guide — Gamma Exposure se Option Buy/Sell Kaise Karein
## Complete Beginner to Advanced Guide

---

## PART 1 — GEX Kya Hai (Simple Language Mein)

### Ek Real Life Example:

```
Soch ek bada dam (dam = big player / market maker) hai.
Usne tumse 1000 options kharide.

Ab agar market upar jaaye →
Dam ko nuksaan hoga →
Isliye dam futures BECHEGA (hedge ke liye)

Agar market neeche jaaye →
Dam ko nuksaan hoga →
Isliye dam futures KHARIDEGA (hedge ke liye)

Yeh buying/selling itni badi hoti hai ki
MARKET KI DIRECTION CHANGE HO JAATI HAI!

GEX = Yeh estimate karta hai ki dam kab kitna buy/sell karega
```

### Formula (Samajhne ke liye):
```
GEX = Gamma × OI × Lot Size × Spot Price

Positive GEX → Dams stabilize karte hain market
Negative GEX → Dams volatile banate hain market
```

---

## PART 2 — Dashboard Mein GEX Kaise Padhein

### Dashboard pe yeh dikhega:

```
⚡ GEX — Gamma Exposure
┌──────────────────────────────────────┐
│ 📦 RANGE BOUND      Net GEX: +4.28Cr│
│                                      │
│ Gamma Wall  Flip Level  Spot         │
│   22900       22750     22950        │
└──────────────────────────────────────┘
```

### 3 Important Values:

```
1. NET GEX VALUE
   +4.28 Cr = Positive = Range Bound
   -3.15 Cr = Negative = Volatile

2. GAMMA WALL
   22900 = Sabse bada magnet
   Price yahan aati rehti hai
   Strong support AND resistance dono

3. FLIP LEVEL
   22750 = Danger zone
   Price isse neeche gayi = Volatile market shuru
   Price isse upar = Stable market
```

---

## PART 3 — GEX Regime samjho

### REGIME 1: RANGE BOUND (Positive GEX)

```
Dashboard dikhata hai:
📦 RANGE BOUND   Net GEX: +4.28Cr

Matlab:
Market makers (dams) apni position hedge karte hain
Aisa karte hain ki market EK RANGE MEIN REHTI HAI

Price upar jaaye → Dam bechega → Price neeche aayegi
Price neeche jaaye → Dam kharidega → Price upar aayegi

RESULT: Market sideways/range-bound chalti hai
```

### REGIME 2: VOLATILE / TRENDING (Negative GEX)

```
Dashboard dikhata hai:
🌊 VOLATILE / TRENDING   Net GEX: -3.15Cr

Matlab:
Market makers ki hedging market ko
AUR ZYADA MOVE KARATI HAI

Price upar gayi → Dam bhi kharidega → Aur upar jayegi
Price neeche gayi → Dam bhi bechega → Aur neeche jayegi

RESULT: Bade directional moves possible
```

### REGIME 3: NEUTRAL

```
Dashboard dikhata hai:
⚖️ NEUTRAL   Net GEX: +0.12Cr

Matlab:
Balanced positioning
Koi strong signal nahi
Wait karo
```

---

## PART 4 — GEX se OPTION BUYING Strategy

### Strategy 1: Negative GEX + Direction Confirm = Strong Buy

```
SETUP:
GEX Negative (Volatile regime)   ← Check dashboard
PCR trend ▲ (Bullish)            ← Check dashboard
BUILD = FL (Fresh Long at ATM)   ← Check dashboard
Price > Flip Level               ← Check dashboard

ACTION: BUY ATM CE

WHY:
Negative GEX = Market volatile hogi
PCR + FL = Bulls dominant hain
= Strong upside move expected

ENTRY  : ATM CE @ market price
TARGET : +40% to +50% premium
SL     : -25% premium

EXAMPLE:
GEX = -2.8 Cr (Volatile)
PCR = 1.35 ▲ (Bullish)
BUILD = FL at 22950
Flip Level = 22750, Spot = 22980 (above flip)

BUY: 22950 CE @ ₹180
TARGET: ₹252 (+40%)
SL:     ₹135 (-25%)
```

### Strategy 2: Negative GEX + Bearish Setup = Buy PE

```
SETUP:
GEX Negative (Volatile regime)
PCR trend ▼ (Bearish)
BUILD = FS (Fresh Short at ATM)
Price < Flip Level ← DANGER ZONE

ACTION: BUY ATM PE

EXAMPLE:
GEX = -3.5 Cr (Volatile)
PCR = 0.72 ▼ (Bearish)
BUILD = FS at 22900
Spot = 22680 (below flip level 22750)

BUY: 22900 PE @ ₹220
TARGET: ₹308 (+40%)
SL:     ₹165 (-25%)
```

### Strategy 3: Gamma Wall Breakout Buy

```
SETUP:
Price Gamma Wall ke bilkul upar hai
Volume spike aaya
PCR Bullish

Gamma Wall = 22900
Price = 22950 (above wall)
Volume = 2x average

ACTION: BUY CE (next strike above wall)

WHY: Gamma Wall toot gaya = Dam ki hedging
     ek direction mein ho jayegi
     = Accelerated move expected

ENTRY  : 23000 CE (strike above wall)
TARGET : +50% to +60%
SL     : Agar price gamma wall ke neeche aaye
```

---

## PART 5 — GEX se OPTION SELLING Strategy

### Strategy 4: Positive GEX = Sell Premium (Best Strategy)

```
SETUP:
GEX Positive (Range Bound regime)    ← Dashboard
IV Rank > 50% (Options mehngi hain)  ← Dashboard
PCR Neutral (0.8 to 1.2)             ← Dashboard
VIX > 15                             ← Dashboard

ACTION: SELL IRON CONDOR

SELL CE: At/above Gamma Wall (resistance)
SELL PE: Below Flip Level (support)

EXAMPLE:
GEX = +5.2 Cr (Range Bound)
Gamma Wall = 22900
Flip Level = 22700
IV Rank = 65%

SELL: 23000 CE @ ₹90 (above gamma wall)
SELL: 22600 PE @ ₹85 (below flip level)
Total Premium = ₹175
Max Profit = ₹175 × lot size
SL Rule = Agar koi bhi side 2x ho jaye → exit
```

### Strategy 5: Positive GEX + One Side Bias = Bear Call or Bull Put Spread

```
POSITIVE GEX + PCR BEARISH:
SELL: CE at Gamma Wall (strong resistance)
BUY:  CE 200 points upar (hedge)
= Bear Call Spread

Net Credit = Sell premium - Buy premium
Profit = Market gamma wall se neeche rahe

POSITIVE GEX + PCR BULLISH:
SELL: PE at Flip Level (strong support)
BUY:  PE 200 points neeche (hedge)
= Bull Put Spread

Net Credit collected
Profit = Market flip level ke upar rahe
```

### Strategy 6: Gamma Wall ke Paas Sell

```
Gamma Wall = Price ka MAGNET

RULE:
Price Gamma Wall se 50-100 points upar → SELL CE at wall
Price Gamma Wall se 50-100 points neeche → SELL PE at wall

WHY: Price wall ke aaspaas oscillate karti hai
     Sellers ko fayda milta hai

EXAMPLE:
Gamma Wall = 22900
Price = 22980 (+80 from wall)

SELL: 22900 CE @ ₹145
SL: Agar price 23100 ke upar jaaye
TARGET: CE premium 50% decay pe exit
```

---

## PART 6 — Flip Level ka Use

```
Flip Level = Line of Control

ABOVE Flip Level (SAFE ZONE):
Market stable hai
Selling strategies work karti hain
Iron Condor, Short Strangle safe

BELOW Flip Level (DANGER ZONE):
Market volatile ho sakti hai
Avoid selling naked options
Agar already sell ki hai → SL tight rakho
Buying strategies better yahan

TRADING RULE:
Spot > Flip Level = Sell premium (safer)
Spot < Flip Level = Buy options (directional)
```

---

## PART 7 — Complete Decision Tree

```
STEP 1: GEX Regime dekho
│
├── RANGE BOUND (Positive GEX)
│   │
│   ├── IV Rank > 50%
│   │   └── SELL Iron Condor
│   │       CE at Gamma Wall
│   │       PE at Flip Level
│   │
│   └── IV Rank < 50%
│       └── Wait ya small spread
│
├── VOLATILE (Negative GEX)
│   │
│   ├── PCR > 1.2 + BUILD = FL
│   │   └── BUY CE
│   │       ATM strike
│   │       Target +40%
│   │
│   ├── PCR < 0.8 + BUILD = FS
│   │   └── BUY PE
│   │       ATM strike
│   │       Target +40%
│   │
│   └── Mixed signals
│       └── NO TRADE
│
└── NEUTRAL
    └── Wait for regime change
```

---

## PART 8 — Risk Management with GEX

```
BUYING OPTIONS (Negative GEX):
Max loss per trade  : 2% of capital = ₹2,000 (on ₹1L)
Lot size            : Calculate karo SL pe
Entry timing        : GEX confirm ho phir enter karo
Exit rule           : SL -25% OR GEX regime change ho

SELLING OPTIONS (Positive GEX):
Max loss per trade  : 3% of capital = ₹3,000
Stop Loss           : Premium 2x ho jaye
Entry timing        : IV Rank > 50% confirm karo
Exit rule           : 40-50% profit OR 2x loss
```

---

## PART 9 — Real Examples

### Example 1: NIFTY Intraday — Buy CE

```
Time      : 10:15 AM
GEX       : -3.8 Cr (VOLATILE)        ✅ Negative
Flip Level: 22750
Spot      : 22920 (above flip)         ✅ Safe zone
PCR       : 1.28 ▲                     ✅ Bullish
BUILD     : FL at 22900               ✅ Fresh Long
IV Rank   : 25%                        ✅ Options cheap
VIX       : 13.5                       ✅ Low fear

TRADE:
BUY 22900 CE @ ₹185
TARGET : ₹259 (+40%)
SL     : ₹139 (-25%)
Lots   : 2 lots (max loss ₹2,300)

RESULT:
GEX negative → Market moved up
11:30 AM → CE ₹261 → EXIT ✅
Profit: ₹76 × 50 qty = ₹3,800
```

### Example 2: BANKNIFTY Weekly — Sell Iron Condor

```
Day       : Monday (5 days to expiry)
GEX       : +8.2 Cr (RANGE BOUND)     ✅ Positive
Gamma Wall: 52500
Flip Level: 51800
Spot      : 52150 (between wall & flip)✅
PCR       : 1.05 → (Neutral)           ✅
IV Rank   : 68%                        ✅ Sell premium
VIX       : 18.5

TRADE:
SELL 52700 CE @ ₹120
SELL 51500 PE @ ₹110
Total Premium = ₹230

MAX PROFIT = ₹230 × 15 = ₹3,450
SL RULE    = Exit agar koi bhi side ₹460 ho jaye (2x)

RESULT:
GEX positive → Market ranged 52000-52400 all week
Expiry → Both expire worthless
Profit: ₹3,450 ✅
```

---

## PART 10 — Quick Reference Card

```
┌─────────────────────────────────────────────────────┐
│               GEX QUICK REFERENCE                   │
├─────────────────────────────────────────────────────┤
│ GEX POSITIVE → Range Bound → SELL OPTIONS          │
│ GEX NEGATIVE → Volatile   → BUY OPTIONS            │
├─────────────────────────────────────────────────────┤
│ GAMMA WALL = Strongest support/resistance           │
│ FLIP LEVEL = Line between safe and danger zone      │
├─────────────────────────────────────────────────────┤
│ Spot > Flip Level = Safe, sell premium              │
│ Spot < Flip Level = Danger, buy options/tight SL    │
├─────────────────────────────────────────────────────┤
│ BEST BUY SETUP:                                     │
│ GEX Negative + PCR ▲ + FL signal + Price > Flip    │
│                                                     │
│ BEST SELL SETUP:                                    │
│ GEX Positive + IV Rank >50% + PCR Neutral          │
└─────────────────────────────────────────────────────┘
```

---

## PART 11 — Common Mistakes

```
MISTAKE 1: Sirf GEX dekh ke trade lena
FIX: GEX + PCR + BUILD sab confirm karo

MISTAKE 2: Positive GEX mein options kharidna
FIX: Positive GEX = Range bound = Options value kho deti hain

MISTAKE 3: Flip Level se neeche options sell karna
FIX: Flip Level ke neeche = Volatile = Selling risky hai

MISTAKE 4: GEX ke against trade lena
FIX: Hamesha GEX ke direction mein trade karo

MISTAKE 5: SL nahi lagana GEX trade mein
FIX: Regime change hote hi exit karo
```

---

## Summary

```
GEX ek institutional-grade tool hai.
Sensibull, Opstra mein yeh NAHI hai.
Tera dashboard mein hai — FREE mein.

Yaad rakho:
POSITIVE GEX = Dams range mein rakhenge = SELL
NEGATIVE GEX = Dams moves amplify karenge = BUY
GAMMA WALL   = Sabse bada price magnet
FLIP LEVEL   = Safe zone ki boundary

GEX + PCR + OI Build = Complete picture
Yeh combination 90% retail traders ke paas NAHI hai
```

---

*Dashboard: NSE F&O Live Dashboard v2.1*
*GEX Panel: web_dashboard.py → render_gex()*
*Data Source: Live Zerodha Kite API*
