import os
import re
import asyncio
from pyrogram import Client, filters
from pyrogram.errors import FloodWait

# सर्वर से वैल्यूज लोड होंगी
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
TARGET_CHANNEL = int(os.environ.get("TARGET_CHANNEL"))

# अगर आपको कोई अपना लिंक या टेक्स्ट जोड़ना हो तो यहाँ बदल सकते हैं
CUSTOM_FOOTER = "\n\n🎬 Join: @your_channel"

bot = Client(
    "CaptionCleanerBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

def clean_caption_text(text):
    if not text:
        return ""
    # मूवी नाम, साल और क्वालिटी निकालने का पैटर्न
    pattern = r"([a-zA-Z0-9\s\.\-_]+?)(19\d\d|20\d\d).*?(\d{3,4}p|HEVC|HDR|HD)"
    match = re.search(pattern, text, re.IGNORECASE)
    
    if match:
        name = match.group(1).replace('.', ' ').strip()
        year = match.group(2)
        quality = match.group(3).upper()
        return f"🎬 **{name} ({year}) [{quality}]**{CUSTOM_FOOTER}"
    
    # अगर साल/क्वालिटी न मिले तो लिंक्स हटाकर साफ टेक्स्ट रखेगा
    clean_text = re.sub(r'http\S+|@\S+', '', text).strip()
    return f"{clean_text}{CUSTOM_FOOTER}"

@bot.on_message(filters.media & filters.private)
async def process_media(client, message):
    try:
        # ओरिजिनल कैप्शन या फाइलनेम उठाएगा
        original_caption = message.caption or (message.document.file_name if message.document else "")
        new_caption = clean_caption_text(original_caption)
        
        # टारगेट चैनल में कॉपी करके सेंड करेगा (फॉरवर्ड टैग नहीं आएगा)
        await message.copy(
            chat_id=TARGET_CHANNEL,
            caption=new_caption
        )
        await asyncio.sleep(2) # FloodWait से बचने के लिए छोटा गैप
        
    except FloodWait as e:
        await asyncio.sleep(e.value)
        await message.copy(chat_id=TARGET_CHANNEL, caption=new_caption)
    except Exception as e:
        print(f"Error: {e}")

print("Bot Start Ho Gaya...")
bot.run()
