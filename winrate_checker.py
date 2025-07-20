# winrate_checker.py
from datetime import datetime, timezone
from db import client  # ✅ Use the shared MongoDB client from .env
import random

stats_coll = client["hypewave"]["stats"]

# Ensure winrate stats doc exists
def init_winrate_doc():
    if not stats_coll.find_one({"_id": "winrate"}):
        stats_coll.insert_one({
            "_id": "winrate",
            "wins": 0,
            "total_trades": 0,
            "winrate": 0.0,
            "last_updated": datetime.now(timezone.utc)
        })

# Update with result (True = win, False = loss)
def update_winrate(is_win: bool):
    init_winrate_doc()
    update = {
        "$inc": {"total_trades": 1},
        "$set": {"last_updated": datetime.now(timezone.utc)}
    }
    if is_win:
        update["$inc"]["wins"] = 1

    stats_coll.update_one({"_id": "winrate"}, update)

    doc = stats_coll.find_one({"_id": "winrate"})
    if doc and doc["total_trades"] > 0:
        winrate = round((doc["wins"] / doc["total_trades"]) * 100, 2)
        stats_coll.update_one({"_id": "winrate"}, {"$set": {"winrate": winrate}})

# Get current stats
def get_winrate():
    doc = stats_coll.find_one({"_id": "winrate"})
    if not doc:
        return {"total_trades": 0, "wins": 0, "winrate": 0.0}
    return {
        "total_trades": doc.get("total_trades", 0),
        "wins": doc.get("wins", 0),
        "winrate": doc.get("winrate", 0.0)
    }

""" === Bulk Simulation ===
def simulate_bulk_winrate_tests(total: int = 50, win_ratio: float = 0.6):
    win_count = int(total * win_ratio)
    loss_count = total - win_count

    print(f"\n[🧪] Simulating {total} trades with ~{int(win_ratio * 100)}% winrate...")

    for _ in range(win_count):
        update_winrate(True)
    for _ in range(loss_count):
        update_winrate(False)

    final_stats = get_winrate()
    print("\n📊 Final Winrate Stats:")
    print(f"Total Trades: {final_stats['total_trades']}")
    print(f"Wins: {final_stats['wins']}")
    print(f"Winrate: {final_stats['winrate']}%")
"""