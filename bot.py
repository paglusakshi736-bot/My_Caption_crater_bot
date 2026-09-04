import os
import re
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pyrogram import Client, filters
from pyrogram.errors import FloodWait

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
TARGET_CHANNEL = int(os.environ.get("TARGET_CHANNEL"))
PORT = int(os.environ.get("PORT", 8080))

CUSTOM_FOOTER = (
    "\n\n"
    "🤖 Bot: @Movie_zone_1bot\n"
    "🍿 Join Channel: https://t.me/+nDKhro-O0mBiZTY1"
)

app = Client(
    "CaptionCleanerBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

def clean_caption_text(text):
    if not text:
        return f"🎬 **New Movie**{CUSTOM_FOOTER}"
    
    # फाइल एक्सटेंशन (.mkv, .mp4, etc.) पहले ही हटा लें
    text = re.sub(r'\.(mkv|mp4|avi|webm|mov)$', '', text, flags=re.IGNORECASE)
    
    # पहली लाइन उठाएं
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    first_line = lines[0] if lines else text

    # साल (19xx या 20xx) निकालना
    year_match = re.search(r'(19\d\d|20\d\d)', first_line)
    year = f" ({year_match.group(1)})" if year_match else ""

    # मूवी का नाम अलग करना
    if year_match:
        name = first_line[:year_match.start()].strip()
    else:
        # अगर साल न मिले तो ब्रैकेट्स या स्पेशल सिंबल से पहले का नाम
        name = re.split(r'[\(\[\-#]', first_line)[0].strip()

    # नाम से डॉट्स, अंडरस्कोर और फालतू चीजें साफ करना
    name = re.sub(r'[\.\-_]', ' ', name).strip()

    # क्वालिटी निकालना (480p, 720p, 1080p, 2160p, 4k, HEVC, HDTC आदि)
    quality_match = re.search(r'(\d{3,4}p|4K|HEVC|HDR|HDTC)', text, re.IGNORECASE)
    quality = f" [{quality_match.group(1).upper()}]" if quality_match else ""

    return f"🎬 **{name}{year}{quality}**{CUSTOM_FOOTER}"

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    await message.reply_text("✅ Bot active hai! Koi bhi movie file send karo (with ya without caption).")

@app.on_message(filters.media & filters.private)
async def process_media(client, message):
    try:
        # 1. पहले कैप्शन चेक करेगा
        # 2. अगर कैप्शन नहीं है, तो Document का नाम देखेगा
        # 3. अगर Video है, तो Video का फाइलनेम उठाएगा
        file_name = ""
        if message.document and message.document.file_name:
            file_name = message.document.file_name
        elif message.video and message.video.file_name:
            file_name = message.video.file_name

        original_text = message.caption or file_name or ""
        new_caption = clean_caption_text(original_text)
        
        await message.copy(
            chat_id=TARGET_CHANNEL,
            caption=new_caption
        )
        await asyncio.sleep(2)
        
    except FloodWait as e:
        await asyncio.sleep(e.value)
        await message.copy(chat_id=TARGET_CHANNEL, caption=new_caption)
    except Exception as e:
        await message.reply_text(f"❌ Error: {e}")

class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_web():
    httpd = HTTPServer(("0.0.0.0", PORT), SimpleHandler)
    httpd.serve_forever()

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    print("Bot starting via app.run()...")
    app.run()
