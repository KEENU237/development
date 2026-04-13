@echo off
chcp 65001 >nul 2>&1
title NSE FO Dashboard
cd /d D:\HDFC\nse_fo_system

echo.
echo  =============================================
echo   NSE F&O Web Dashboard  --  Browser Version
echo  =============================================
echo.

:: Python check
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python nahi mila!
    echo  python.org se install karo, "Add to PATH" tick karo.
    pause & exit
)

:: Packages
echo  [1/3] Packages check...
pip install streamlit kiteconnect scipy numpy pandas plotly --quiet 2>nul
echo  [OK] Packages ready
echo.

:: Token check
echo  [2/3] Token check...
python -c "
import pickle, os
from datetime import date
f = os.path.join('data','kite_token.pkl')
if not os.path.exists(f):
    print('  [WARN] Token nahi hai!')
    print('  Pehle chalao: python get_token.py')
    exit(1)
d = pickle.load(open(f,'rb'))
if d.get('date') != date.today().isoformat():
    print('  [WARN] Token expire ho gaya!')
    print('  Pehle chalao: python get_token.py')
    exit(1)
print('  [OK] Token valid -', d.get('date'))
" 2>nul
if errorlevel 1 (
    echo.
    echo  get_token.py chalana chahoge? [Y/N]
    set /p c=  :
    if /i "%c%"=="Y" (
        python get_token.py
        if errorlevel 1 ( pause & exit )
    ) else ( pause & exit )
)
echo.

:: Start
echo  [3/3] Dashboard start ho raha hai...
echo.
echo  Browser mein khulega : http://localhost:8501
echo  Band karne ke liye   : Ctrl+C
echo.
echo  NOTE: Agar koi aur dashboard chal raha hai to pehle us window ko band karo.
echo  =============================================
echo.

streamlit run web_dashboard.py --server.port 8501 --server.headless false --browser.gatherUsageStats false --theme.base dark

echo.
echo  Dashboard band ho gaya.
pause
