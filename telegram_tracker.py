from telethon import TelegramClient
from datetime import datetime, timezone
from db import client
import os, asyncio
from telethon.errors import FloodWaitError
from dotenv import load_dotenv
from telethon.sessions import StringSession

load_dotenv()

api_id = int(os.getenv("TELEGRAM_API_ID"))
api_hash = os.getenv("TELEGRAM_API_HASH")
session_string = os.getenv("TELEGRAM_SESSION")

channel_usernames = [
    "WatcherGuru",
    "CryptoProUpdates",
    "TreeNewsFeed",
    "thekingsofsolana",
    "cryptocurrency_media",
    "rektcapitalinsider"
]

collection = client["hypewave"]["telegram_news"]

tg_client = TelegramClient(StringSession(session_string), api_id, api_hash)

def get_display_name(entity):
    if hasattr(entity, "title") and entity.title:
        return entity.title
    if hasattr(entity, "first_name") and entity.first_name:
        if hasattr(entity, "last_name") and entity.last_name:
            return f"{entity.first_name} {entity.last_name}"
        return entity.first_name
    if hasattr(entity, "username") and entity.username:
        return entity.username
    return "Unnamed"

async def fetch_latest():
    print("[Telegram Tracker] Fetching latest messages...")
    for username in channel_usernames:
        try:
            entity = await tg_client.get_entity(username)
            display_name = get_display_name(entity)
            canonical_username = entity.username if hasattr(entity, "username") else username

            # 🟢 Check if we have any stored messages
            last_saved = collection.find_one({"source": canonical_username}, sort=[("id", -1)])

            if last_saved:
                last_id = last_saved["id"]
            else:
                # No saved messages—get the latest message ID to avoid fetching everything
                latest = await tg_client.get_messages(username, limit=1)
                if latest:
                    last_id = latest[0].id
                    print(f"[{canonical_username}] 🆕 Starting from latest message ID {last_id}")
                else:
                    last_id = 0
                    print(f"[{canonical_username}] ⚠️ No messages found in channel.")

            async for message in tg_client.iter_messages(username, min_id=last_id):
                media_url = None
                if message.media and message.photo:
                    try:
                        path = await tg_client.download_media(message.media, file="/mnt/data/")
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
                        "media_url": media_url,
                        "forwarded_to": "@hypewaveai"
                    }
                    collection.insert_one(doc)
                    print(f"✅ [{canonical_username}] {doc['text'][:60]}...")

                    await tg_client.forward_messages(
                        entity="@hypewaveai",
                        messages=message
                    )

        except Exception as e:
            print(f"[{username}] ❌ Failed to fetch messages: {e}")

    now = datetime.now(timezone.utc)
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

    deleted = collection.delete_many({"date": {"$lt": start_of_day}})
    print(f"[Cleanup] Deleted {deleted.deleted_count} old records.")

    from pathlib import Path

    media_folder = Path("/mnt/data")
    deleted_count = 0
    for file in media_folder.iterdir():
        if file.is_file():
            mtime = datetime.fromtimestamp(file.stat().st_mtime, tz=timezone.utc)
            if mtime < start_of_day:
                file.unlink()
                deleted_count += 1

    print(f"[Cleanup] Deleted {deleted_count} old media files.")

async def loop_fetch():
    print("[Telegram Tracker] Starting Telegram client...")
    await tg_client.start()
    print("[Telegram Tracker] Connected to Telegram.")
    while True:
        await fetch_latest()
        await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(loop_fetch())
