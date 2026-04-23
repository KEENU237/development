"""
Run from: D:\\HDFC\\nse_fo_system\\nse_fo_system\\
This patches the OUTER web_dashboard.py (one folder up) where user actually runs the dashboard.
"""
import os, sys, shutil

this_dir   = os.path.dirname(os.path.abspath(__file__))
outer_dir  = os.path.dirname(this_dir)

# web_dashboard.py jo actually use hoti hai
dashboard = os.path.join(outer_dir, "web_dashboard.py")

# Agar outer mein nahi mila — same folder mein try karo
if not os.path.exists(dashboard):
    dashboard = os.path.join(this_dir, "web_dashboard.py")

if not os.path.exists(dashboard):
    print("ERROR: web_dashboard.py nahi mili.")
    sys.exit(1)

print(f"Patching: {dashboard}")

with open(dashboard, "r", encoding="utf-8") as f:
    content = f.read()

if "stock_scanner_tab" in content:
    print("Already patched — Stock Scanner tab already present.")
else:
    shutil.copy(dashboard, dashboard + ".bak_scanner")

    content = content.replace(
        "from datetime import datetime",
        "from datetime import datetime\nfrom stock_scanner_tab import render_stock_scanner",
        1
    )
    content = content.replace(
        '"🔬  Backtester"]',
        '"🔬  Backtester",\n                 "📡  Stock Scanner"]',
        1
    )
    content = content.replace(
        '    elif "Backtester" in page:\n        render_backtester(symbol)',
        '    elif "Backtester" in page:\n        render_backtester(symbol)\n\n    elif "Stock Scanner" in page:\n        render_stock_scanner(kite)',
        1
    )

    with open(dashboard, "w", encoding="utf-8") as f:
        f.write(content)
    print("web_dashboard.py patched successfully.")

# stock_scanner_tab.py bhi outer folder mein copy karo
src_scanner = os.path.join(this_dir, "stock_scanner_tab.py")
dst_scanner = os.path.join(outer_dir, "stock_scanner_tab.py")

if os.path.exists(src_scanner):
    if not os.path.exists(os.path.join(outer_dir, "web_dashboard.py")):
        dst_scanner = os.path.join(this_dir, "stock_scanner_tab.py")
    else:
        shutil.copy(src_scanner, dst_scanner)
        print(f"stock_scanner_tab.py copied to: {dst_scanner}")
else:
    print("WARNING: stock_scanner_tab.py not found in this folder.")

print("\nDone! Now run:")
print(f"  cd {outer_dir if os.path.exists(os.path.join(outer_dir, 'web_dashboard.py')) else this_dir}")
print("  streamlit run web_dashboard.py")
