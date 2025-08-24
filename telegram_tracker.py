# telegram_tracker.py  — PASTE OVER
from telethon import TelegramClient, events
from datetime import timezone
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

# Channels you want to ingest
channel_usernames = [
    "WatcherGuru",
    "CryptoProUpdates",
    "TreeNewsFeed",
    "thekingsofsolana",
    "rektcapitalinsider",
    "hypewaveai",
]

# Mongo collection
collection = client["hypewave"]["telegram_news"]

# Temp dirs for downloads
media_path = Path(__file__).resolve().parent / "media"
media_path.mkdir(exist_ok=True)
avatars_dir = media_path / "avatars"
avatars_dir.mkdir(exist_ok=True)

tg_client = TelegramClient(StringSession(session_string), api_id, api_hash)


def canonicalize_source_fields(entity, message_id: int):
    """
    Return a stable source key, display name, handle, and deep link.
    Works even if the chat has NO @username.
    """
    username = getattr(entity, "username", None)
    title = getattr(entity, "title", None) or getattr(entity, "first_name", None) or "Unknown"
    chat_id = int(getattr(entity, "id", 0) or 0)

    if username:
        source_key = username.lower()        # <- use as Mongo 'source'
        handle = username
        link = f"https://t.me/{username}/{message_id}"
    else:
        # for private/no-username chats, fall back to a stable id-based key
        source_key = f"id_{abs(chat_id)}"
        handle = None
        link = None

    return source_key, title, handle, link


# ---- Expo push helpers ----
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

def _chunk(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

def broadcast_news_push(
    title: str,
    body: str,
    link: str | None = None,
    logo_url: str | None = None,
    channel_id: str = "news",
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
        "channelId": channel_id,
        "priority": "high",
        "subtitle": "Hypewave AI",
        "imageUrl": logo_url or None,
        "mutableContent": True,
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


@tg_client.on(events.NewMessage(chats=channel_usernames))
async def handler(event):
    try:
        msg = event.message
        entity = await tg_client.get_entity(event.chat_id)

        # --- Stable source/display/link fields (never None) ---
        source_key, display_name, handle, deep_link = canonicalize_source_fields(entity, msg.id)

        # --- Log basic receipt ---
        preview = (msg.text or "").strip().replace("\n", " ")
        if len(preview) > 90:
            preview = preview[:90] + "…"
        print(f"📨 [{source_key}] {preview or '[no text]'}")

        # --- Avatar upload (best-effort) ---
        avatar_url = None
        tmp = None
        try:
            tmp = await tg_client.download_profile_photo(entity, file=str(avatars_dir / f"{source_key}.jpg"))
            if tmp:
                up = cloudinary.uploader.upload(
                    tmp,
                    public_id=f"hypewave/avatars/telegram/{source_key}",
                    overwrite=True,
                    unique_filename=False,
                    resource_type="image",
                )
                avatar_url = up.get("secure_url")
        except Exception as e:
            print("⚠️ avatar download/upload error:", e)
        finally:
            try:
                if tmp and Path(tmp).exists():
                    os.remove(tmp)
            except Exception:
                pass

        # --- Media upload (image/gif/video) ---
        media_item = None
        media_url = None
        file_path = None
        if msg.media:
            try:
                file_path = await tg_client.download_media(msg.media, file=str(media_path))
                if file_path:
                    public_id = f"hypewave/news/{source_key}/{getattr(msg, 'grouped_id', None) or msg.id}_{msg.id}"
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
                    media_url = media_item["url"]
                    print("✅ media uploaded:", media_url)
            except Exception as e:
                print("❌ Cloudinary upload error:", e)
            finally:
                try:
                    if file_path and Path(file_path).exists():
                        os.remove(file_path)
                except Exception:
                    pass

        album_id = getattr(msg, "grouped_id", None)

        # ---- Upsert key: merge parts of the same album, else by message id ----
        key = {"source": source_key}
        if album_id:
            key["album_id"] = album_id
        else:
            key["id"] = msg.id

        # ---- Build update with NO $set/$setOnInsert conflicts ----
        update = {
            "$setOnInsert": {
                "id": msg.id,
                "album_id": album_id,
                "date": msg.date.replace(tzinfo=timezone.utc),
                "source": source_key,
                "media": [],                    # init array on first create
            },
            "$set": {
                "display_name": display_name,   # keep fresh here only
                "handle": handle,
                "link": deep_link,
                "text": msg.text or None,
            },
        }
        if avatar_url:
            update["$set"]["avatar_url"] = avatar_url
        if media_item:
            update["$push"] = {"media": media_item}
            # set media_url for the preview on first create
            update["$setOnInsert"]["media_url"] = media_item["url"]

        # ---- Write & log exact result ----
        try:
            res = collection.update_one(key, update, upsert=True)
            print(
                "📥 upsert",
                {
                    "source": source_key,
                    "id": msg.id,
                    "album": album_id,
                    "matched": res.matched_count,
                    "modified": res.modified_count,
                    "upserted": bool(res.upserted_id),
                },
            )
        except Exception as e:
            print("❌ [tracker] upsert FAILED", {"err": str(e)})
            return  # bail

        # ensure media_url exists if we added media after first insert
        if media_url:
            collection.update_one(
                {**key, "media_url": {"$exists": False}},
                {"$set": {"media_url": media_url}},
            )

        # --- Push (only when first created) ---
        try:
            if getattr(res, "upserted_id", None):
                txt = (msg.text or "").strip()
                summary = (txt[:120] + "…") if txt and len(txt) > 120 else (txt or "New post")
                broadcast_news_push(
                    title=f"{display_name}",
                    body=summary,
                    link=deep_link,
                    logo_url="https://hypewave-ai-engine.onrender.com/static/main_logo.png",
                )
        except Exception as e:
            print("❌ [push] error:", e)

    except Exception as e:
        print("❌ handler error:", e)


async def main():
    print("[Telegram Tracker] Starting Telegram client...")
    await tg_client.start()
    print("[Telegram Tracker] Connected.")
    await tg_client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
