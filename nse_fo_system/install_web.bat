@echo off
title Installing Web Dashboard Packages
color 0B
cls

echo.
echo  ============================================
echo   Web Dashboard — Package Installer
echo  ============================================
echo.

echo  Installing all required packages...
echo.

pip install streamlit
pip install kiteconnect
pip install rich
pip install scipy
pip install openpyxl
pip install pandas
pip install numpy

echo.
echo  ============================================
echo   Installation complete!
echo.
echo   Ab yeh steps follow karo:
echo   1. python get_token.py    (token generate karo)
echo   2. start_web.bat          (dashboard start karo)
echo  ============================================
echo.
pause
