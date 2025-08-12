# telegram_tracker.py
from telethon import TelegramClient, events
from datetime import datetime, timezone
from db import client
import os, asyncio
from dotenv import load_dotenv
from telethon.sessions import StringSession
from pathlib import Path
import faulthandler

# Cloudinary
import cloudinary, cloudinary.uploader

faulthandler.enable()
load_dotenv()

api_id = int(os.getenv("TELEGRAM_API_ID"))
api_hash = os.getenv("TELEGRAM_API_HASH")
session_string = os.getenv("TELEGRAM_SESSION")

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
    "rektcapitalinsider",
]

collection = client["hypewave"]["telegram_news"]

# Temp dir (used only during upload)
media_path = Path(__file__).resolve().parent / "media"
media_path.mkdir(exist_ok=True)

tg_client = TelegramClient(StringSession(session_string), api_id, api_hash)

@tg_client.on(events.NewMessage(chats=channel_usernames))
async def handler(event):
    message = event.message
    canonical_username = event.chat.username
    display_name = event.chat.title or canonical_username
    album_id = getattr(message, "grouped_id", None)  # albums share this id

    print(f"📨 @{canonical_username}: {message.text[:60] if message.text else '[no text]'}")

    # ---- Upload media (image/gif/video) to Cloudinary ----
    media_item = None
    file_path = None
    if message.media:
        try:
            file_path = await tg_client.download_media(message.media, file=str(media_path))
            if file_path:
                public_id = f"hypewave/news/{canonical_username}/{album_id or message.id}_{message.id}"
                up = cloudinary.uploader.upload(
                    file_path,
                    resource_type="auto",
                    public_id=public_id,
                    overwrite=True,
                    unique_filename=False,
                )
                rtype = up.get("resource_type", "image")
                fmt = (up.get("format") or "").lower()
                media_item = {
                    "type": "video" if rtype == "video" else ("gif" if fmt == "gif" else "image"),
                    "url": up["secure_url"],
                    "mime_type": fmt,
                    "width": up.get("width"),
                    "height": up.get("height"),
                    "duration_ms": int(up.get("duration") * 1000) if up.get("duration") else None,
                }
                print("✅ Uploaded:", media_item["url"])
        except Exception as e:
            print("❌ Cloudinary upload error:", e)
        finally:
            try:
                if file_path and Path(file_path).exists():
                    os.remove(file_path)
            except Exception:
                pass

    # ---- Merge posts by album_id (or insert single) ----
    coll = collection
    key = {"source": canonical_username}
    if album_id:
        key["album_id"] = album_id
    else:
        key["id"] = message.id

    update = {
        "$setOnInsert": {
            "id": message.id,
            "album_id": album_id,
            "date": message.date.replace(tzinfo=timezone.utc),
            "link": f"https://t.me/{canonical_username}/{message.id}",
            "source": canonical_username,
            "display_name": display_name,
            "media": [],  
        }
    }

    # carry/refresh text if present
    if message.text:
        update.setdefault("$set", {})["text"] = message.text

    # push media into the array; keep media_url = first item (compat)
    if media_item:
        update.setdefault("$push", {})["media"] = media_item
        update.setdefault("$setOnInsert", {})["media_url"] = media_item["url"]

    coll.update_one(key, update, upsert=True)
    print(f"📥 Upserted {'album' if album_id else 'post'} {album_id or message.id}")

async def main():
    print("[Telegram Tracker] Starting Telegram client...")
    await tg_client.start()
    print("[Telegram Tracker] Connected.")
    await tg_client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
