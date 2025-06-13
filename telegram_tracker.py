from telethon.sync import TelegramClient
from datetime import datetime, timezone
from db import client
import os, asyncio
from dotenv import load_dotenv

load_dotenv()

api_id = int(os.getenv("TELEGRAM_API_ID"))
api_hash = os.getenv("TELEGRAM_API_HASH")
channel_usernames = ["hypewaveai", "WatcherGuru", "CryptoProUpdates", "TreeNewsFeed", "thekingsofsolana", "cryptocurrency_media"]
collection = client["hypewave"]["telegram_news"]

async def fetch_latest():
    async with TelegramClient("news_session", api_id, api_hash) as tg_client:
        for username in channel_usernames:
            # 🧠 Get most recent saved message ID for this channel
            last_msg = collection.find_one({"source": username}, sort=[("id", -1)])
            min_id = last_msg["id"] if last_msg else 0

            # 📥 Fetch messages newer than min_id
            async for message in tg_client.iter_messages(username, limit=20, min_id=min_id):
                if message.text:
                    if collection.find_one({"id": message.id, "source": username}):
                        continue

                    media_url = None
                    if message.media and message.photo:
                        try:
                            path = await tg_client.download_media(message.media, file="media/")
                            if path:
                                media_url = f"/media/{os.path.basename(path)}"
                        except Exception as e:
                            print(f"[Media download error]: {e}")

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

        # 🧹 Keep only the 100 most recent messages
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
