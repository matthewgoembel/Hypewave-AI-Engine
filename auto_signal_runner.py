import threading
import time
from signal_engine import generate_alerts_for_symbol

TRACKED_SYMBOLS = ["BTC", "ETH", "SPX", "NASDAQ", "XAU"]

# Loop to scan and generate alerts automatically
def auto_signal_loop():
    while True:
        print("🔁 Scanning symbols for alerts...")
        for symbol in TRACKED_SYMBOLS:
            generate_alerts_for_symbol(symbol)
        time.sleep(30)  # Run every 30 seconds

# Hook to run on FastAPI startup
def start_signal_engine():
    thread = threading.Thread(target=auto_signal_loop, daemon=True)
    thread.start()
    print("✅ Signal engine started.")
