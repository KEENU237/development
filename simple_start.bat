@echo off
title NSE Dashboard
cd /d D:\HDFC\nse_fo_system

echo.
echo Checking Python...
python --version
if errorlevel 1 (
    echo ERROR: Python nahi mila. python.org se install karo.
    pause
    exit
)

echo.
echo Installing packages...
pip install streamlit kiteconnect --quiet

echo.
echo Checking token...
python -c "import pickle,os; d=pickle.load(open('data/kite_token.pkl','rb')); print('Token date:',d.get('date'))" 2>nul
if errorlevel 1 (
    echo.
    echo Token nahi mila! Pehle yeh chalao:
    echo    python get_token.py
    echo.
    pause
    exit
)

echo.
echo Starting dashboard at http://localhost:8501
echo Ctrl+C se band karo
echo.
streamlit run web_dashboard.py --server.port 8501

pause
