from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from datetime import datetime, timezone
from dotenv import load_dotenv
import os

# Load .env
load_dotenv()

# Load URI from .env (or hardcode if debugging)
uri = os.getenv("MONGO_DB_URI")
client = MongoClient(uri, server_api=ServerApi('1'))

# Optional ping to confirm connection
try:
    client.admin.command('ping')
    print("MongoDB connected successfully.")
except Exception as e:
    print("MongoDB connection failed:", e)

# Collections
db = client["hypewave"]
collection = db["signals"]
alerts_coll = db["alerts"]

# Logging functions
def log_signal(user_id: str, input_data: dict, output_data: dict):
    entry = {
        "user_id": user_id,
        "input": input_data,
        "output": output_data,
        "created_at": datetime.now(timezone.utc)
    }

    # Remove created_at from filter to prevent duplication
    unique_filter = {
        "user_id": user_id,
        "input.symbol": input_data.get("symbol"),
        "output.result": output_data.get("result"),
        "output.timeframe": output_data.get("timeframe"),
        "output.source": output_data.get("source")  # ✅ include source if relevant
    }

    collection.update_one(unique_filter, {"$set": entry}, upsert=True)



def log_alert(user_id: str, input_data: dict, output_data: dict):
    entry = {
        "user_id": user_id,
        "input": input_data,
        "output": output_data,
        "created_at": datetime.now(timezone.utc)
    }

    unique_filter = {
        "user_id": user_id,
        "input.symbol": input_data.get("symbol"),
        "output.result": output_data.get("result"),
        "output.timeframe": output_data.get("timeframe"),
        "output.source": output_data.get("source")
    }

    alerts_coll.update_one(unique_filter, {"$setOnInsert": entry}, upsert=True)


def get_latest_news(limit=10):
    coll = client["hypewave"]["telegram_news"]
    cursor = coll.find().sort("date", -1).limit(limit)
    return [
        {
            "text": doc.get("text"),
            "link": doc.get("link"),
            "timestamp": doc.get("date").isoformat() if doc.get("date") else None,
            "source": doc.get("source"),
            "display_name": doc.get("display_name"),   # ✅ this line fixes it
            "media_url": doc.get("media_url")
        }
        for doc in cursor
    ]

def log_feedback(signal_id: str, feedback: str):
    from bson import ObjectId
    try:
        collection.update_one(
            {"_id": ObjectId(signal_id)},
            {"$push": {"feedback": feedback}}
        )
    except Exception as e:
        print(f"[❌ Feedback Logging Error] {e}")

