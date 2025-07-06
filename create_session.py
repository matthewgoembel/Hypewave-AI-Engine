from telethon.sync import TelegramClient

api_id = 24594733
api_hash = '3617efeb2604751e0041dd4b722774c4'

client = TelegramClient("fresh_session", api_id, api_hash)
client.start()  # This is what prompts for your phone and code
