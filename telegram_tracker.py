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
channel_usernames = ["hypewaveai", "WatcherGuru", "CryptoProUpdates", "TreeNewsFeed", "thekingsofsolana", "cryptocurrency_media"]
collection = client["hypewave"]["telegram_news"]

async def fetch_latest():
    async with TelegramClient("fresh_session.session", api_id, api_hash) as tg_client:
        for username in channel_usernames:
            # Fetch latest message ID from this channel already saved
            last_saved = collection.find_one({"source": username}, sort=[("id", -1)])
            last_id = last_saved["id"] if last_saved else 0

            async for message in tg_client.iter_messages(username):
                if message.id <= last_id:
                    break  # stop at already-seen messages

                if message.text and not collection.find_one({"id": message.id, "source": username}):
                    media_url = None
                    if message.media and message.photo:
                        path = await tg_client.download_media(message.media, file="media/")
                        if path:
                            media_url = f"/media/{os.path.basename(path)}"

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

        # Keep only most recent 100 messages
        recent_docs = list(collection.find().sort("date", -1).limit(100))
        if recent_docs:
            cutoff_date = recent_docs[-1]["date"]
            collection.delete_many({"date": {"$lt": cutoff_date}})

        try:
            if message.media and message.photo:
                path = await tg_client.download_media(message.media, file="media/")
                if path:
                    media_url = f"/media/{os.path.basename(path)}"
        except FloodWaitError as e:
            print(f"[Media download error]: A wait of {e.seconds} seconds is required (caused by {e.__class__.__name__})")
            media_url = None

async def loop_fetch():
    while True:
        await fetch_latest()
        await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(loop_fetch())
