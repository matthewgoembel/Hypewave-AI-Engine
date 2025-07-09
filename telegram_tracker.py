from telethon import TelegramClient, events
from datetime import datetime, timezone
from db import client
import os, asyncio
from telethon.errors import FloodWaitError
from dotenv import load_dotenv
from telethon.sessions import StringSession
from pathlib import Path

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

@tg_client.on(events.NewMessage(chats=channel_usernames))
async def handler(event):
    message = event.message
    canonical_username = event.chat.username
    display_name = event.chat.title or canonical_username

    # Check if already saved (very unlikely since it's a new event)
    if collection.find_one({"id": message.id, "source": canonical_username}):
        return

    media_url = None
    if message.media and message.photo:
        try:
            path = await tg_client.download_media(message.media, file="/mnt/data/")
            if path:
                media_url = f"/media/{os.path.basename(path)}"
        except FloodWaitError as e:
            print(f"[Media download error]: Wait {e.seconds} seconds (from {canonical_username})")
            return

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

async def main():
    print("[Telegram Tracker] Starting Telegram client...")
    await tg_client.start()
    print("[Telegram Tracker] Connected to Telegram.")
    await tg_client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
