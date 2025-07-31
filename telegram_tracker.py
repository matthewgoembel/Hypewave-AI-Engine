from telethon import TelegramClient, events
from datetime import datetime, timezone
from db import client
import os, asyncio
from telethon.errors import FloodWaitError
from dotenv import load_dotenv
from telethon.sessions import StringSession
from pathlib import Path
import faulthandler
faulthandler.enable()

load_dotenv()

api_id = int(os.getenv("TELEGRAM_API_ID"))
api_hash = os.getenv("TELEGRAM_API_HASH")
session_string = os.getenv("TELEGRAM_SESSION")

channel_usernames = [
    "WatcherGuru",
    "CryptoProUpdates",
    "TreeNewsFeed",
    "thekingsofsolana",
    "rektcapitalinsider"
]

collection = client["hypewave"]["telegram_news"]

# ✅ Define local media directory
media_path = Path(__file__).resolve().parent / "media"
media_path.mkdir(exist_ok=True)


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

    print(f"📨 New message from @{canonical_username}: {message.text[:60] if message.text else '[no text]'}")

    # Check for duplicate
    if collection.find_one({"id": message.id, "source": canonical_username}):
        print("⚠️ Duplicate message — skipping")
        return

    media_url = None
    if message.media:
        try:
            print("🟡 Media detected — attempting download...")
            file_path = await tg_client.download_media(message.media, file=str(media_path))
            if file_path:
                filename = Path(file_path).name
                media_url = f"/media/{filename}"
                print(f"✅ Media saved to: {file_path}")
            else:
                print("❌ `download_media` returned None")
        except Exception as e:
            print(f"❌ Media download error: {e}")

    # Save to MongoDB
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
    print(f"📥 Inserted message ID {message.id} into MongoDB.")


async def main():
    print("[Telegram Tracker] Starting Telegram client...")
    await tg_client.start()
    print("[Telegram Tracker] Connected.")
    await tg_client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
