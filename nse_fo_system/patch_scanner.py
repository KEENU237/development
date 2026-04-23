"""
Run this once to add Stock Scanner tab to web_dashboard.py
Usage: python patch_scanner.py
"""
import os, sys, shutil

dashboard = os.path.join(os.path.dirname(__file__), "web_dashboard.py")

if not os.path.exists(dashboard):
    print("ERROR: web_dashboard.py not found in current folder")
    sys.exit(1)

with open(dashboard, "r", encoding="utf-8") as f:
    content = f.read()

# Already patched?
if "stock_scanner_tab" in content:
    print("Already patched — Stock Scanner tab is already present.")
    sys.exit(0)

# Backup
shutil.copy(dashboard, dashboard + ".bak_scanner")
print("Backup created: web_dashboard.py.bak_scanner")

# Patch 1 — Import line (after last import block)
old_import = "from datetime import datetime"
new_import  = "from datetime import datetime\nfrom stock_scanner_tab import render_stock_scanner"
content = content.replace(old_import, new_import, 1)

# Patch 2 — Add to pages list
old_pages = '"🔬  Backtester"]'
new_pages  = '"🔬  Backtester",\n                 "📡  Stock Scanner"]'
content = content.replace(old_pages, new_pages, 1)

# Patch 3 — Add routing elif
old_route = '    elif "Backtester" in page:\n        render_backtester(symbol)'
new_route  = ('    elif "Backtester" in page:\n        render_backtester(symbol)\n\n'
              '    elif "Stock Scanner" in page:\n        render_stock_scanner(kite)')
content = content.replace(old_route, new_route, 1)

with open(dashboard, "w", encoding="utf-8") as f:
    f.write(content)

# Verify
if "stock_scanner_tab" in content and "Stock Scanner" in content:
    print("SUCCESS — Stock Scanner tab added to web_dashboard.py")
    print("Now restart: streamlit run web_dashboard.py")
else:
    print("FAILED — something went wrong, check web_dashboard.py manually")
