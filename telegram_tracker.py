from telethon.sync import TelegramClient
from telethon.tl.types import Message
from datetime import datetime, timezone
from db import client
import os, asyncio
from dotenv import load_dotenv

load_dotenv()

api_id = int(os.getenv("TELEGRAM_API_ID"))
api_hash = os.getenv("TELEGRAM_API_HASH")
channel_usernames = ["hypewaveai", "WatcherGuru", "CryptoProUpdates", "TreeNewsFeed", "thekingsofsolana"]
collection = client["hypewave"]["telegram_news"]

async def fetch_latest():
    async with TelegramClient("news_session", api_id, api_hash) as tg_client:
        for username in channel_usernames:
            async for message in tg_client.iter_messages(username, limit=20):
                if message.text and not collection.find_one({"id": message.id, "source": username}):
                    media_url = None
                    if message.media:
                        media_url = f"https://t.me/{username}/{message.id}"

                    doc = {
                        "id": message.id,
                        "text": message.text,
                        "date": message.date.replace(tzinfo=timezone.utc),
                        "link": f"https://t.me/{username}/{message.id}",
                        "source": username,
                        "media_url": media_url
                    }
                    collection.insert_one(doc)
                    print(f"✅ [{username}] {doc['text'][:60]}...")

        # Keep only the 100 most recent messages
        recent_docs = list(collection.find().sort("date", -1).limit(100))
        if recent_docs:
            cutoff_date = recent_docs[-1]["date"]
            collection.delete_many({"date": {"$lt": cutoff_date}})

async def loop_fetch():
    while True:
        await fetch_latest()
        await asyncio.sleep(5)

if __name__ == "__main__":
    asyncio.run(loop_fetch())
