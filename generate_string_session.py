from telethon.sync import TelegramClient
from telethon.sessions import StringSession

api_id = 24594733
api_hash = '3617efeb2604751e0041dd4b722774c4'

with TelegramClient(StringSession(), api_id, api_hash) as client:
    print("✅ String session generated below:\n")
    print(client.session.save())
