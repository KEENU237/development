"""
NSE F&O Trading System — Entry Point
Run: python main.py
"""

import os
import sys

# Ensure project root is on sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.dashboard import main

if __name__ == "__main__":
    main()
