from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
from dotenv import load_dotenv
import os


# Load URI from your .env
load_dotenv()
uri = "mongodb+srv://HypewaveAI:test1234@hypwavecluster1.gx7dgib.mongodb.net/hypewave?retryWrites=true&w=majority"

try:
    # Use stable Server API version
    client = MongoClient(uri, server_api=ServerApi('1'))
    client.admin.command('ping')
    print("MongoDB connection successful.")
except Exception as e:
    print("MongoDB connection failed:", e)
