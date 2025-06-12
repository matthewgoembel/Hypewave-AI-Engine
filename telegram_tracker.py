from telethon.sync import TelegramClient
from telethon.tl.types import Message
from datetime import datetime, timezone
from db import client
import os, asyncio
from dotenv import load_dotenv

load_dotenv()

api_id = int(os.getenv("TELEGRAM_API_ID"))
api_hash = os.getenv("TELEGRAM_API_HASH")
channel_username = "hypewaveai", "WatcherGuru", "CryptoProUpdates"  # no @ symbol
collection = client["hypewave"]["telegram_news"]

async def fetch_latest():
    async with TelegramClient("news_session", api_id, api_hash) as client:
        async for message in client.iter_messages(channel_username, limit=20):
            if message.text and not collection.find_one({"id": message.id}):
                doc = {
                    "id": message.id,
                    "text": message.text,
                    "date": message.date.replace(tzinfo=timezone.utc),
                    "link": f"https://t.me/{channel_username}/{message.id}"
                }
                collection.insert_one(doc)
                print(f"✅ New message saved: {doc['text'][:60]}...")

if __name__ == "__main__":
    asyncio.run(fetch_latest())
