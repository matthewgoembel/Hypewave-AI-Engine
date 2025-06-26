from telethon.sync import TelegramClient

api_id = 24594733
api_hash = '3617efeb2604751e0041dd4b722774c4'

with TelegramClient("fresh_session", api_id, api_hash) as client:
    print("Session created")