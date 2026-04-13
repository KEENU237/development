"""
NSE F&O Trading System — Configuration
Zerodha Kite Connect se data pull karta hai
"""

# ─── ZERODHA API CREDENTIALS ───────────────────────────────────────────────────
KITE_API_KEY    = "your_api_key_here"
KITE_API_SECRET = "your_api_secret_here"
KITE_ACCESS_TOKEN = ""   # Runtime mein set hoga (login ke baad)

# ─── UOA SCANNER SETTINGS ──────────────────────────────────────────────────────
UOA_CONFIG = {
    "min_multiplier": 5.0,        # 5x+ = unusual activity
    "fire_multiplier": 10.0,      # 10x+ = very unusual (🔥)
    "scan_symbols": [             # Jinhe scan karna hai
        "NIFTY", "BANKNIFTY",
        "RELIANCE", "TCS", "INFY",
        "ICICIBANK", "SBIN", "HDFC",
        "AXISBANK", "LT", "BAJFINANCE"
    ],
    "scan_interval_seconds": 60,  # Kitni baar scan kare
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

# ─── PATHS ─────────────────────────────────────────────────────────────────────
import os
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR  = os.path.join(BASE_DIR, "logs")
DATA_DIR = os.path.join(BASE_DIR, "data")
