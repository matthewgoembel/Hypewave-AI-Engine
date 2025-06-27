from telethon.sync import TelegramClient
from telethon.tl.types import Message
from datetime import datetime, timezone
from db import client
import os, asyncio
from telethon.errors import FloodWaitError
from dotenv import load_dotenv

load_dotenv()

api_id = int(os.getenv("TELEGRAM_API_ID"))
api_hash = os.getenv("TELEGRAM_API_HASH")
channel_usernames = [
    "hypewaveai",
    "WatcherGuru",
    "CryptoProUpdates",
    "TreeNewsFeed",
    "thekingsofsolana",
    "cryptocurrency_media",
    "rektcapitalinsider"
]
collection = client["hypewave"]["telegram_news"]

async def fetch_latest():
    async with TelegramClient("sessions/fresh_session", api_id, api_hash) as tg_client:
        for username in channel_usernames:
            # 🟢 Fetch the full channel entity once
            entity = await tg_client.get_entity(username)

            display_name = entity.title if hasattr(entity, "title") else username
            canonical_username = entity.username if hasattr(entity, "username") else username

            last_saved = collection.find_one({"source": canonical_username}, sort=[("id", -1)])
            last_id = last_saved["id"] if last_saved else 0

            try:
                async for message in tg_client.iter_messages(username, limit=10):
                    if message.id <= last_id:
                        break

                    media_url = None
                    if message.media and message.photo:
                        try:
                            path = await tg_client.download_media(message.media, file="media/")
                            if path:
                                media_url = f"/media/{os.path.basename(path)}"
                        except FloodWaitError as e:
                            print(f"[Media download error]: Wait {e.seconds} seconds (from {username})")

                    if message.text and not collection.find_one({"id": message.id, "source": canonical_username}):
                        doc = {
                            "id": message.id,
                            "text": message.text,
                            "date": message.date.replace(tzinfo=timezone.utc),
                            "link": f"https://t.me/{canonical_username}/{message.id}",
                            "source": canonical_username,
                            "display_name": display_name,
                            "media_url": media_url
                        }
                        collection.insert_one(doc)
                        print(f"✅ [{canonical_username}] {doc['text'][:60]}...")

            except Exception as e:
                print(f"[{username}] ❌ Failed to fetch messages: {e}")

        # Clean old messages
        recent_docs = list(collection.find().sort("date", -1).limit(100))
        if recent_docs:
            cutoff_date = recent_docs[-1]["date"]
            collection.delete_many({"date": {"$lt": cutoff_date}})

async def loop_fetch():
    while True:
        await fetch_latest()
        await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(loop_fetch())
