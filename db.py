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

    # Define a unique signature for this signal (avoid exact duplicates)
    unique_filter = {
        "user_id": user_id,
        "input.symbol": input_data.get("symbol"),
        "output.result": output_data.get("result"),
        "output.timeframe": output_data.get("timeframe"),
        "created_at": entry["created_at"]
    }

    collection.update_one(unique_filter, {"$set": entry}, upsert=True)


def log_alert(user_id: str, input_data: dict, output_data: dict):
    entry = {
        "user_id": user_id,
        "input": input_data,
        "output": output_data,
        "created_at": datetime.now(timezone.utc)
    }
    result = alerts_coll.insert_one(entry)
    return str(result.inserted_id)

def get_latest_news(limit=10):
    coll = client["hypewave"]["telegram_news"]
    cursor = coll.find().sort("date", -1).limit(limit)
    return [
        {
            "text": doc.get("text"),
            "link": doc.get("link"),
            "timestamp": doc.get("date")
        }
        for doc in cursor
    ]

