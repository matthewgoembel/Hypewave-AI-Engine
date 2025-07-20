# mock_signal_test.py
from winrate_checker import get_winrate, update_winrate
from datetime import datetime, timezone
from bson import ObjectId
from db import client  # ✅ Use correct MongoDB client from .env
from winrate_checker import simulate_bulk_winrate_tests



signals = client["hypewave"]["signals"]

print("\n[🧪] Inserting 2 mock trades manually...")

# === Local insert version of log_signal ===
def log_signal_direct(user_id: str, input_data: dict, output_data: dict, extra_meta: dict = None):
    entry = {
        "user_id": user_id,
        "input": input_data,
        "output": output_data,
        "created_at": datetime.now(timezone.utc)
    }
    if extra_meta:
        entry.update(extra_meta)
    signals.insert_one(entry)

# Trade 1: WIN
trade_1 = {
    "input": {"symbol": "MOCK_WIN"},
    "output": {
        "trade": "LONG",
        "entry": 10000,
        "sl": 9900,
        "tp": 10200,
        "timeframe": "1h",
        "confidence": 95,
        "thesis": "This is a mock winning long trade.",
        "source": "mock-signal-test",
        "result": "MOCK_WIN | LONG | 1h | Entry: 10000 | Conf: 95"
    }
}

# Trade 2: LOSS
trade_2 = {
    "input": {"symbol": "MOCK_LOSS"},
    "output": {
        "trade": "SHORT",
        "entry": 10000,
        "sl": 10100,
        "tp": 9800,
        "timeframe": "1h",
        "confidence": 85,
        "thesis": "This is a mock losing short trade.",
        "source": "mock-signal-test",
        "result": "MOCK_LOSS | SHORT | 1h | Entry: 10000 | Conf: 85"
    }
}

log_signal_direct("test", trade_1["input"], trade_1["output"], extra_meta={"status": "WIN", "resolved_at": datetime.now(timezone.utc)})
log_signal_direct("test", trade_2["input"], trade_2["output"], extra_meta={"status": "LOSS", "resolved_at": datetime.now(timezone.utc)})

# Fake finalize for test purposes
update_winrate(True)   # WIN
update_winrate(False)  # LOSS

# === Winrate Summary ===
print("\n📊 Current Winrate Stats:")
winrate = get_winrate()
print(f"Total Trades: {winrate['total_trades']}")
print(f"Wins: {winrate['wins']}")
print(f"Winrate: {winrate['winrate']}%")

# === Optional Bulk Simulation ===
simulate_bulk_winrate_tests(50, 0.6)
