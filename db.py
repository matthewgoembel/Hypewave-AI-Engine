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
    result = collection.insert_one(entry)
    return str(result.inserted_id)

def log_alert(user_id: str, input_data: dict, output_data: dict):
    entry = {
        "user_id": user_id,
        "input": input_data,
        "output": output_data,
        "created_at": datetime.now(timezone.utc)
    }
    result = alerts_coll.insert_one(entry)
    return str(result.inserted_id)
