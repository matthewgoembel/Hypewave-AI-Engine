from telethon.sync import TelegramClient
from telethon.tl.types import Message
from telethon.errors import FloodWaitError
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
            try:
                # Get latest known message ID for this channel
                last = collection.find_one({"source": username}, sort=[("id", -1)])
                min_id = last["id"] if last else 0

                async for message in tg_client.iter_messages(username, min_id=min_id):
                    if not message.text:
                        continue

                    media_url = None

                    # Double-check against duplicates
                    if not collection.find_one({"id": message.id, "source": username}):
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

            except FloodWaitError as e:
                print(f"🌊 FloodWaitError from {username}: sleeping for {e.seconds} seconds")
                await asyncio.sleep(e.seconds + 2)
            except Exception as e:
                print(f"[Error fetching {username}]: {e}")

        # Keep only the 100 most recent messages
        recent_docs = list(collection.find().sort("date", -1).limit(100))
        if recent_docs:
            cutoff_date = recent_docs[-1]["date"]
            collection.delete_many({"date": {"$lt": cutoff_date}})

async def loop_fetch():
    while True:
        try:
            await fetch_latest()
        except Exception as e:
            print(f"[loop_fetch error]: {e}")
        await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(loop_fetch())
