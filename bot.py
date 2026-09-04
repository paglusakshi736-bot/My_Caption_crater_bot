import os
import re
import asyncio
from pyrogram import Client, filters
from pyrogram.errors import FloodWait

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
TARGET_CHANNEL = int(os.environ.get("TARGET_CHANNEL"))

CUSTOM_FOOTER = "\n\n🎬 Join: @your_channel"

app = Client(
    "CaptionCleanerBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

def clean_caption_text(text):
    if not text:
        return ""
    pattern = r"([a-zA-Z0-9\s\.\-_]+?)(19\d\d|20\d\d).*?(\d{3,4}p|HEVC|HDR|HD)"
    match = re.search(pattern, text, re.IGNORECASE)
    
    if match:
        name = match.group(1).replace('.', ' ').strip()
        year = match.group(2)
        quality = match.group(3).upper()
        return f"🎬 **{name} ({year}) [{quality}]**{CUSTOM_FOOTER}"
    
    clean_text = re.sub(r'http\S+|@\S+', '', text).strip()
    return f"{clean_text}{CUSTOM_FOOTER}"

@app.on_message(filters.media & filters.private)
async def process_media(client, message):
    try:
        original_caption = message.caption or (message.document.file_name if message.document else "")
        new_caption = clean_caption_text(original_caption)
        
        await message.copy(
            chat_id=TARGET_CHANNEL,
            caption=new_caption
        )
        await asyncio.sleep(2)
        
    except FloodWait as e:
        await asyncio.sleep(e.value)
        await message.copy(chat_id=TARGET_CHANNEL, caption=new_caption)
    except Exception as e:
        print(f"Error: {e}")

async def main():
    async with app:
        print("Bot Start Ho Gaya...")
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
    
