# auto_signal_runner.py

import threading
import time
from signal_engine import generate_alerts_for_symbol

TRACKED_SYMBOLS = ["BTC", "ETH", "XAU"]

def auto_signal_loop():
    while True:
        print("🔁 Scanning symbols for confluence alerts...")
        for symbol in TRACKED_SYMBOLS:
            generate_alerts_for_symbol(symbol)
        time.sleep(30)

def start_signal_engine():
    thread = threading.Thread(target=auto_signal_loop, daemon=True)
    thread.start()
    print("✅ Signal engine started.")
