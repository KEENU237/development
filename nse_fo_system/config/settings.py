"""
NSE F&O Trading System — Configuration
Zerodha Kite Connect se data pull karta hai
"""

# ─── ZERODHA API CREDENTIALS ───────────────────────────────────────────────────
KITE_API_KEY    = "1llp18x99bahkfdu"
KITE_API_SECRET = "p9z6wtv2mvx8leiw4ykdg96hb95fx9di"
KITE_ACCESS_TOKEN = ""   # Runtime mein set hoga (login ke baad)

# ─── UOA SCANNER SETTINGS ──────────────────────────────────────────────────────
UOA_CONFIG = {
    "min_multiplier": 2.0,        # 2x+ = unusual activity (lowered from 5x)
    "fire_multiplier": 5.0,       # 5x+ = very unusual / fire (lowered from 10x)
    "scan_symbols": [             # Sirf index — stocks scan bahut slow karta hai
        "NIFTY", "BANKNIFTY",
    ],
    "scan_interval_seconds": 60,
    "lookback_days": 1,
}

# ─── BASKET ORDER STRATEGIES ───────────────────────────────────────────────────
STRATEGIES = {
    "BULL_CALL_SPREAD": {
        "description": "ATM CE buy + OTM CE sell | Mild bullish",
        "otm_gap": 200,          # Nifty ke liye 200 points OTM
        "iv_max": 16,            # IV 16% se zyada ho toh mat lo
        "days_to_expiry": (7, 15),
    },
    "BEAR_PUT_SPREAD": {
        "description": "ATM PE buy + OTM PE sell | Mild bearish",
        "otm_gap": 500,          # BankNifty ke liye 500 points OTM
        "pcr_max": 0.8,
    },
    "IRON_CONDOR": {
        "description": "4-leg range-bound strategy | Net credit",
        "ce_otm_gap": 300,
        "pe_otm_gap": 300,
        "ce_hedge_gap": 500,
        "pe_hedge_gap": 500,
        "iv_rank_min": 30,       # IV Rank 30%+ chahiye
        "days_to_expiry": (7, 10),
    },
}

# ─── PCR THRESHOLDS ────────────────────────────────────────────────────────────
PCR_ZONES = {
    "EXTREME_BULL":  (1.5, float("inf")),
    "BULLISH":       (1.2, 1.5),
    "NEUTRAL":       (0.8, 1.2),
    "BEARISH":       (0.5, 0.8),
    "EXTREME_BEAR":  (0.0, 0.5),
}

# ─── RISK MANAGEMENT ───────────────────────────────────────────────────────────
RISK = {
    "max_capital_per_trade": 50000,   # Rs 50,000 per trade
    "stop_loss_pct": 0.03,            # 3% stop loss
    "max_daily_loss": 10000,          # Rs 10,000 daily max loss
    "max_open_positions": 3,
}

# ─── TELEGRAM ALERT BOT ────────────────────────────────────────────────────────
# Setup kaise karo:
#   Step 1: Telegram pe @BotFather ko message karo → /newbot → token milega
#   Step 2: Apne bot ko ek message bhejo (koi bhi text)
#   Step 3: https://api.telegram.org/bot<TOKEN>/getUpdates open karo
#           "chat":{"id": XXXXXXX} — yahi tumhara CHAT_ID hai
#   Step 4: Neeche fill karo aur ENABLED = True karo
TELEGRAM_CONFIG = {
    "bot_token": "8762123584:AAH0jJ8l5y6XDdcCOlS7H78vLbcW6GUcu2w",
    "chat_id":   "2136453340",
    "enabled":   True,
}

# ─── PATHS ─────────────────────────────────────────────────────────────────────
import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR  = os.path.join(BASE_DIR, "logs")
DATA_DIR = os.path.join(BASE_DIR, "data")
