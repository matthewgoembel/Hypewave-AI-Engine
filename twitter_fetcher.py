# telegram_tracker.py
from telethon import TelegramClient, events
from datetime import datetime, timezone
from db import client
import os, asyncio
from telethon.errors import FloodWaitError
from dotenv import load_dotenv
from telethon.sessions import StringSession
from pathlib import Path
import faulthandler

# ⬇️ NEW: Cloudinary
import cloudinary, cloudinary.uploader

faulthandler.enable()
load_dotenv()

api_id = int(os.getenv("TELEGRAM_API_ID"))
api_hash = os.getenv("TELEGRAM_API_HASH")
session_string = os.getenv("TELEGRAM_SESSION")

# Cloudinary config (uses same env as your avatars)
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)

channel_usernames = [
    "WatcherGuru",
    "CryptoProUpdates",
    "TreeNewsFeed",
    "thekingsofsolana",
    "rektcapitalinsider"
]

collection = client["hypewave"]["telegram_news"]

# Local media dir (used only as a temp/fallback)
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

    # De-dupe
    if collection.find_one({"id": message.id, "source": canonical_username}):
        print("⚠️ Duplicate message — skipping")
        return

    media_url = None
    if message.media:
        file_path = None
        try:
            print("🟡 Media detected — downloading…")
            file_path = await tg_client.download_media(message.media, file=str(media_path))
            if file_path:
                print("☁️ Uploading to Cloudinary…")
                public_id = f"hypewave/news/{canonical_username}/{message.id}"
                up = cloudinary.uploader.upload(
                    file_path,
                    resource_type="auto",     # image, gif, video — auto-detect
                    public_id=public_id,
                    overwrite=True,
                    unique_filename=False,
                )
                media_url = up.get("secure_url")  # absolute https
                print(f"✅ Cloudinary uploaded: {media_url}")
            else:
                print("❌ download_media returned None")
        except Exception as e:
            print(f"❌ Cloudinary upload error: {e} — falling back to local /media")
            if file_path:
                try:
                    filename = Path(file_path).name
                    media_url = f"/media/{filename}"
                except Exception:
                    pass
        finally:
            # optional cleanup of temp file
            try:
                if file_path and Path(file_path).exists():
                    os.remove(file_path)
            except Exception:
                pass

    # Save to MongoDB
    doc = {
        "id": message.id,
        "text": message.text,
        "date": message.date.replace(tzinfo=timezone.utc),
        "link": f"https://t.me/{canonical_username}/{message.id}",
        "source": canonical_username,
        "display_name": display_name,
        "media_url": media_url,   # Cloudinary URL or /media/ fallback
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
