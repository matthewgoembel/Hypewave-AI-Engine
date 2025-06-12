from pymongo import MongoClient
from datetime import datetime

# Connect to MongoDB
client = MongoClient("mongodb://localhost:27017")  # adjust if needed
db = client["hypewave"]
collection = db["signals"]

# Step 1: Group all unique combinations of (symbol, result, source, timeframe)
pipeline = [
    {
        "$group": {
            "_id": {
                "symbol": "$input.symbol",
                "result": "$output.result",
                "source": "$output.source",
                "timeframe": "$output.timeframe"
            },
            "latest_id": { "$max": "$_id" },
            "ids": { "$push": "$_id" }
        }
    }
]

groups = list(collection.aggregate(pipeline))

# Step 2: Delete all but the latest for each group
deleted_count = 0
for group in groups:
    ids_to_delete = [id for id in group["ids"] if id != group["latest_id"]]
    if ids_to_delete:
        result = collection.delete_many({ "_id": { "$in": ids_to_delete } })
        deleted_count += result.deleted_count

print(f"✅ Deduplication complete. Removed {deleted_count} duplicates.")
