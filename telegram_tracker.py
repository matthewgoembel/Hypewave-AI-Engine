# telegram_tracker.py
from telethon import TelegramClient, events
from datetime import datetime, timezone
from db import client, get_all_news_push_tokens
import os, asyncio
from dotenv import load_dotenv
from telethon.sessions import StringSession
from pathlib import Path
import requests
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
    "hypewaveai",
]

collection = client["hypewave"]["telegram_news"]

# Temp dir (used only during upload)
media_path = Path(__file__).resolve().parent / "media"
media_path.mkdir(exist_ok=True)

avatars_dir = media_path / "avatars"
avatars_dir.mkdir(exist_ok=True)

tg_client = TelegramClient(StringSession(session_string), api_id, api_hash)

@tg_client.on(events.NewMessage(chats=channel_usernames))
async def handler(event):
    message = event.message
    canonical_username = event.chat.username

    avatar_url = None
    try:
        # download the channel's current profile photo to a temp file
        avatar_tmp = await tg_client.download_profile_photo(
            event.chat, file=str(avatars_dir / f"{canonical_username}.jpg")
        )
        if avatar_tmp:
            up = cloudinary.uploader.upload(
                avatar_tmp,
                public_id=f"hypewave/avatars/telegram/{canonical_username}",
                overwrite=True,
                unique_filename=False,
            )
            avatar_url = up["secure_url"]
    finally:
        try:
            if avatar_tmp and Path(avatar_tmp).exists():
                os.remove(avatar_tmp)
        except Exception:
            pass

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

    # ⬇️ backfill avatar across this channel if we managed to upload one
    if avatar_url:
        coll.update_many(
            {"source": canonical_username, "avatar_url": {"$exists": False}},
            {"$set": {"avatar_url": avatar_url}}
        )

    update = {
        "$setOnInsert": {
            "id": message.id,
            "album_id": album_id,
            "date": message.date.replace(tzinfo=timezone.utc),
            "link": f"https://t.me/{canonical_username}/{message.id}",
            "source": canonical_username,
            "display_name": display_name,
        }
    }

    # Keep the FIRST text we see; don’t overwrite later
    if message.text:
        update["$setOnInsert"]["text"] = message.text

    # ensure display_name stays fresh and attach avatar if we have one
    update.setdefault("$set", {})["display_name"] = display_name
    if avatar_url:
        update["$set"]["avatar_url"] = avatar_url    

    # Media handling:
    if media_item:
        # Push creates the array if missing — no conflict with $setOnInsert
        update["$push"] = {"media": media_item}
        # Set the first media_url only on insert (compat)
        update["$setOnInsert"]["media_url"] = media_item["url"]
    else:
        # No media in this part (e.g., first message is text) — initialize empty array on insert
        update["$setOnInsert"]["media"] = []

    res = coll.update_one(key, update, upsert=True)
    print(f"📥 Upserted {'album' if album_id else 'post'} {album_id or message.id}")

    # If this part had media and the doc still lacks media_url (e.g., first part was text),
    # set media_url now without touching existing ones.
    if media_item:
        coll.update_one({**key, "media_url": {"$exists": False}},
                        {"$set": {"media_url": media_item["url"]}})
    # If this part has text and the doc has no text yet, set it once.
        # If this part has text and the doc has no text yet, set it once.
    if message.text:
        coll.update_one({**key, "$or": [{"text": {"$exists": False}}, {"text": None}, {"text": ""}]},
                        {"$set": {"text": message.text}})

    # --- NEW: trigger push after upsert ---
    # --- trigger push only on first insert (prevents duplicates for albums) ---
    try:
        if res.upserted_id:  # only notify when this post/album is first created
            txt = (message.text or "").strip()
            summary = (txt[:120] + "…") if txt and len(txt) > 120 else (txt or "New post")
            post_link = f"https://t.me/{canonical_username}/{message.id}"
            broadcast_news_push(title=f"{display_name}", body=summary, link=post_link, logo_url="https://hypewave-ai-engine.onrender.com/static/main_logo.png")
    except Exception as e:
        print("❌ [push] broadcast error:", e)


# --- Expo push helpers ---
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

def _chunk(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

def broadcast_news_push(
    title: str,
    body: str,
    link: str | None = None,
    logo_url: str | None = None,        # NEW: accept logo
    channel_id: str = "news"            # NEW: default to your News channel
):
    tokens = get_all_news_push_tokens()
    if not tokens:
        print("ℹ️ [push] No tokens to notify.")
        return

    payloads = [{
        "to": t,
        "title": title,
        "body": body,
        "sound": "default",
        "data": {"type": "news", "link": link},
        "channelId": channel_id,        # ensure it routes to “news”
        "priority": "high",             # heads-up on Android
        "subtitle": "Hypewave AI",      # nice extra on iOS
        # Expo supports showing an image in many launchers:
        # this is ignored if the platform/launcher doesn’t support it.
        "imageUrl": logo_url or None,   # optional brand image
        "mutableContent": True,         # helps iOS render rich content
    } for t in tokens]

    sent = 0
    for batch in _chunk(payloads, 100):
        try:
            r = requests.post(EXPO_PUSH_URL, json=batch, headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            }, timeout=10)
            if r.status_code != 200:
                print(f"❌ [push] Expo error {r.status_code}: {r.text[:200]}")
            else:
                sent += len(batch)
        except Exception as e:
            print("❌ [push] send error:", e)

    print(f"📣 [push] Broadcast to {sent} devices.")

async def main():
    print("[Telegram Tracker] Starting Telegram client...")
    await tg_client.start()
    print("[Telegram Tracker] Connected.")
    await tg_client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
