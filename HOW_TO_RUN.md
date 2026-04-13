# NSE F&O Dashboard — How to Run
## Step-by-step guide (Roz follow karo)

---

## PEHLI BAAR SETUP (Sirf ek baar karna hai)

### Step 1 — Python Install Karo
1. https://www.python.org/downloads/ pe jao
2. Latest version download karo
3. Install karte waqt **"Add Python to PATH"** checkbox zaroor tick karo
4. Install complete karo

### Step 2 — Packages Install Karo
`D:\HDFC\nse_fo_system` folder mein jao aur double-click karo:
```
install_web.bat
```
Yeh automatically sab install kar dega. Ek baar karna hai.

### Step 3 — Zerodha Developer App Banana
1. https://developers.kite.trade/ pe login karo
2. **"Create new app"** click karo
3. Fill karo:
   - App Name: kuch bhi (e.g. `MyDashboard`)
   - Redirect URL: `http://127.0.0.1`
4. App create hone ke baad **API Key** aur **API Secret** copy karo

### Step 4 — API Key Settings Mein Daalo
File kholo: `D:\HDFC\nse_fo_system\config\settings.py`

Yahan dhundo aur apni details daalo:
```python
KITE_API_KEY    = "yahan_apni_api_key_daalo"
KITE_API_SECRET = "yahan_apna_api_secret_daalo"
```
Save karo (Ctrl+S).

---

## ROZ SUBAH KA ROUTINE (Market se pehle karna hai)

### Step 1 — Token Generate Karo
> **Kyun?** Zerodha ka token roz expire hota hai. Har subah fresh token chahiye.

Command Prompt (CMD) kholo aur type karo:
```
cd D:\HDFC\nse_fo_system
python get_token.py
```

**Kya hoga:**
1. Ek browser URL print hoga — usse browser mein kholo
2. Zerodha username/password se login karo
3. Login ke baad browser ka URL kuch aisa dikhega:
   ```
   http://127.0.0.1/?request_token=abc123xyz&action=login&status=success
   ```
4. `request_token=` ke baad wala part copy karo (e.g. `abc123xyz`)
5. CMD mein paste karo aur Enter dabaao
6. "Login successful" message aayega — ho gaya!

### Step 2 — Dashboard Start Karo
`D:\HDFC\nse_fo_system` folder mein double-click karo:
```
start_web.bat
```

**Ya CMD mein:**
```
cd D:\HDFC\nse_fo_system
streamlit run web_dashboard.py
```

### Step 3 — Browser Mein Kholo
Automatically browser mein khul jayega:
```
http://localhost:8501
```
Agar na khule toh browser mein manually yeh URL daalo.

---

## DASHBOARD USE KARNA

### Symbols Switch Karna
- Left side sidebar mein **Symbol dropdown** hai
- NIFTY / BANKNIFTY / FINNIFTY choose karo
- Click karte hi data switch ho jayega

### Data Refresh
- Data **automatically har 60 seconds** mein update hota hai
- Koi button press nahi karna
- Page reload nahi hoga — sirf numbers update honge

### Dashboard Band Karna
- CMD window mein **Ctrl + C** dabaao
- Ya CMD window close kar do

---

## COMMON ERRORS AUR FIX

### Error: "Token expired"
```
Fix: python get_token.py chalao (roz subah karna hai)
```

### Error: "Python nahi mila"
```
Fix: Python install karo aur PATH mein add karo
     python.org se download karo
```

### Error: "Module not found / streamlit not found"
```
Fix: install_web.bat double-click karke chalao
```

### Error: "Invalid API key"
```
Fix: config\settings.py mein API Key aur Secret check karo
     Zerodha developer console se copy karo
```

### Error: "Port 8501 already in use"
```
Fix: CMD mein yeh chalao:
     streamlit run web_dashboard.py --server.port 8502
     Phir browser mein: http://localhost:8502
```

### Dashboard browser mein nahi khula
```
Fix: Browser mein manually type karo: http://localhost:8501
```

### OI Chain blank dikh raha hai
```
Fix: Market hours ke baad hi OI data aata hai (9:15 AM - 3:30 PM)
     Token valid hai yeh check karo
```

---

## FILES KA MATLAB

| File | Kya Karta Hai |
|------|---------------|
| `start_web.bat` | Dashboard start karna — roz yahi double-click karo |
| `install_web.bat` | Packages install karna — sirf pehli baar |
| `get_token.py` | Daily token generate karna — roz subah |
| `web_dashboard.py` | Main dashboard code |
| `config\settings.py` | API Key/Secret settings |
| `data\kite_token.pkl` | Aaj ka saved token (auto-create hota hai) |
| `SYSTEM_GUIDE.md` | Detailed guide — har panel ka explanation |

---

## DAILY CHECKLIST

```
[ ] 1. get_token.py chalaya    (subah 9 baje se pehle)
[ ] 2. start_web.bat chalaya
[ ] 3. Browser mein dashboard khul gaya
[ ] 4. NIFTY/BANKNIFTY price dikh raha hai
[ ] 5. OI Chain load ho gayi
[ ] 6. PCR values aa rahi hain
```

---

## QUICK REFERENCE

| Kaam | Command/Action |
|------|---------------|
| Roz token lena | `python get_token.py` |
| Dashboard start | `start_web.bat` ya `streamlit run web_dashboard.py` |
| Browser URL | http://localhost:8501 |
| Dashboard band | Ctrl+C in CMD |
| Symbol change | Sidebar dropdown |
| Packages install | `install_web.bat` (sirf ek baar) |

---

*NSE F&O Dashboard v2.1 — Auto-refresh every 60 seconds*
