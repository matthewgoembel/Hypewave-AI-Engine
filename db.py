from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from datetime import datetime, timezone
from bson import ObjectId
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
chats_coll = db["chats"]  # ✅ NEW collection for chats
trades_review = db["trades_review"]  # ✅ NEW collection for chats
users_coll = db["users"]

# Logging functions
def log_signal(user_id: str, input_data: dict, output_data: dict, extra_meta: dict = None):
    entry = {
        "user_id": user_id,
        "input": input_data,
        "output": output_data,
        "created_at": datetime.now(timezone.utc)
    }

    if extra_meta:
        entry.update(extra_meta)

    unique_filter = {
        "user_id": user_id,
        "input.symbol": input_data.get("symbol"),
        "output.result": output_data.get("result"),
        "output.timeframe": output_data.get("timeframe"),
        "output.source": output_data.get("source")
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


def log_chat(user_id: str, input_data: dict, output_data: dict):
    """
    Logs plain chat interactions into their own collection.
    No deduplication filter—every chat is unique.
    """
    entry = {
        "user_id": user_id,
        "input": input_data,
        "output": output_data,
        "created_at": datetime.now(timezone.utc)
    }
    chats_coll.insert_one(entry)


def get_latest_news(limit=20):
    """
    Fetches the latest news from both Telegram and Truth Social.
    Returns a combined, sorted list.
    """
    # Fetch Telegram posts
    telegram_coll = client["hypewave"]["telegram_news"]
    telegram_cursor = telegram_coll.find().sort("date", -1).limit(limit)
    telegram_docs = list(telegram_cursor)

    # Fetch Truth Social posts
    truth_coll = client["hypewave"]["truthsocial_news"]
    truth_cursor = truth_coll.find().sort("date", -1).limit(limit)
    truth_docs = list(truth_cursor)

    # Combine and sort by date
    combined = telegram_docs + truth_docs
    combined.sort(key=lambda x: x["date"], reverse=True)

    # Build response list
    return [
        {
            "text": doc.get("text"),
            "link": doc.get("link"),
            "timestamp": doc.get("date").isoformat() if doc.get("date") else None,
            "source": doc.get("source"),
            "display_name": doc.get("display_name"),
            "media_url": doc.get("media_url")
        }
        for doc in combined[:limit]
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

def get_user_by_email(email: str):
    return users_coll.find_one({"email": email})

def create_user_in_db(email: str, password_hash: str, extra: dict = {}):
    user = {
        "email": email,
        "password_hash": password_hash,
        "created_at": datetime.now(timezone.utc),
        "preferences": {},
        "sessions": [],
        "login_method": extra.get("login_method", "email"),
        "username": extra.get("username", email.split("@")[0]),
        "avatar_url": extra.get("avatar_url", ""),
    }
    result = users_coll.insert_one(user)
    return str(result.inserted_id)

def get_user_by_id(user_id: str):
    from bson import ObjectId
    return users_coll.find_one({"_id": ObjectId(user_id)})

def update_user_last_seen(user_id: str):
    users_coll.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"last_seen": datetime.utcnow()}}
    )


