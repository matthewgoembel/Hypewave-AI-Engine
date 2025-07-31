# trade_monitor.py

from pymongo import MongoClient
from datetime import datetime
from market_data_ws import get_latest_ohlc
from winrate_checker import update_winrate

# Connect to Mongo
client = MongoClient("mongodb+srv://HypewaveAI:hypewave123@hypwavecluster1.gx7dgib.mongodb.net/?retryWrites=true&w=majority&appName=HypwaveCluster1")  # Replace with your actual URI
signals = client["hypewave"]["signals"]

def monitor_open_trades():
    open_trades = signals.find({"status": "OPEN"})

    for trade in open_trades:
        try:
            symbol = trade.get("input", {}).get("symbol")
            entry = trade.get("output", {}).get("entry")
            tp = trade.get("output", {}).get("tp")
            sl = trade.get("output", {}).get("sl")
            trade_id = trade["_id"]

            if not all([symbol, entry, tp, sl]):
                continue

            candles = get_latest_ohlc(f"{symbol}USDT", "1m")
            if not candles:
                continue

            current_price = candles[-1]["close"]

            if current_price >= tp:
                finalize_trade(trade_id, "WIN")
            elif current_price <= sl:
                finalize_trade(trade_id, "LOSS")

        except Exception as e:
            print(f"[❌ Error checking trade {trade.get('_id')}] {e}")

def finalize_trade(trade_id, result):
    signals.update_one(
        {"_id": trade_id},
        {"$set": {"status": result, "resolved_at": datetime.utcnow()}}
    )
    update_winrate(result == "WIN")
    print(f"[📈 Trade Resolved] {trade_id} marked as {result}")
