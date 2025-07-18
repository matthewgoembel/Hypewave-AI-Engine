import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv()

api_id = int(os.getenv("TELEGRAM_API_ID"))
api_hash = os.getenv("TELEGRAM_API_HASH")
session_string = os.getenv("TELEGRAM_SESSION")

media_path = Path(__file__).resolve().parent / "media"
media_path.mkdir(exist_ok=True)

client = TelegramClient(StringSession(session_string), api_id, api_hash)

async def run():
    await client.start()
    msg = await client.get_messages("thekingsofsolana", limit=1)
    print(f"📥 Downloading media from: {msg[0].id}")
    path = await client.download_media(msg[0].media, file=str(media_path))
    print("✅ Saved to:", path)

asyncio.run(run())
