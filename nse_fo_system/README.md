# NSE F&O Trading System — Zerodha Kite Connect

## Setup (3 steps)

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. API Key set karo
`config/settings.py` mein:
```python
KITE_API_KEY    = "your_actual_key"
KITE_API_SECRET = "your_actual_secret"
```

Zerodha developer portal: https://developers.kite.trade

### 3. Run karo
```bash
cd nse_fo_system
python ui/dashboard.py
```

---

## Features

| Module | Description |
|--------|-------------|
| **UOA Scanner** | Unusual Options Activity — 5x+ volume alerts |
| **PCR Tracker** | Put/Call ratio + OI chain live |
| **Basket Orders** | Bull Call Spread, Bear Put Spread, Iron Condor |
| **Dashboard** | Terminal-based live view |

## Project Structure

```
nse_fo_system/
├── config/
│   └── settings.py        # API keys + all configs
├── core/
│   ├── kite_manager.py    # Zerodha connection
│   ├── uoa_scanner.py     # Unusual activity scanner
│   └── pcr_tracker.py     # OI + PCR analysis
├── strategies/
│   └── basket_builder.py  # Multi-leg order builder
├── ui/
│   └── dashboard.py       # Terminal dashboard (entry point)
├── logs/                  # Auto-created
├── data/                  # Token cache
└── requirements.txt
```

## Important Notes

- **Paper trade pehle** — live orders se pehle logic verify karo
- Daily login required — Kite access token har din expire hota hai
- Market hours: 9:15 AM – 3:30 PM IST
- `logs/system.log` mein sab activity log hoti hai
