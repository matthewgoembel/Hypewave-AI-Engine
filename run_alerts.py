# run_alerts.py
from alert_engine import run_alert_loop
from db import db

def run_alerts_for_watchlist():
    user_watchlists = db["watchlists"].find()  # Assuming each doc: { user_id, symbols: ["BTC", "ETH", ...] }

    for watchlist in user_watchlists:
        user_id = watchlist.get("user_id", "unknown")
        for symbol in watchlist.get("symbols", []):
            print(f"Scanning {symbol} for {user_id}")
            generate_alert(symbol.upper())  # Add user_id if you want user-specific logging


if __name__ == "__main__":
    run_alert_loop()
