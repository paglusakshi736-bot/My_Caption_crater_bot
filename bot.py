import os
import re
import json
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
TARGET_CHANNEL = int(os.environ.get("TARGET_CHANNEL"))
PORT = int(os.environ.get("PORT", 8080))

STATS_FILE = "stats.json"

CUSTOM_FOOTER = (
    "\n\n"
    "🍿 **Channel:** [Join Movie Zone](https://t.me/+nDKhro-O0mBiZTY1)\n"
    "🤖 **Movie Bot:** [Search More Movies](https://t.me/Movie_zone_1bot)\n"
    "⚡ _Fast Download & Clean Audio_"
)

app = Client(
    "CaptionCleanerBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Persistent Stats Handlers
def get_total_count():
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r") as f:
                return json.load(f).get("total_processed", 0)
        except Exception:
            return 0
    return 0

def add_to_total_count(added_number):
    current = get_total_count() + added_number
    with open(STATS_FILE, "w") as f:
        json.dump({"total_processed": current}, f)
    return current

def clean_caption_text(text):
    if not text:
        return f"🎬 **New Movie**{CUSTOM_FOOTER}"
    
    text = re.sub(r'\.(mkv|mp4|avi|webm|mov)$', '', text, flags=re.IGNORECASE)
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    first_line = lines[0] if lines else text

    year_match = re.search(r'(19\d\d|20\d\d)', first_line)
    year = f" ({year_match.group(1)})" if year_match else ""

    if year_match:
        name = first_line[:year_match.start()].strip()
    else:
        name = re.split(r'[\(\[\-#]', first_line)[0].strip()

    name = re.sub(r'[\(\)\[\]\.\-_#]', ' ', name).strip()
    name = re.sub(r'\s+', ' ', name)

    res_match = re.search(r'(\d{3,4}p|4K)', text, re.IGNORECASE)
    if res_match:
        quality = f" [{res_match.group(1).upper()}]"
    else:
        other_match = re.search(r'(HEVC|HDR)', text, re.IGNORECASE)
        quality = f" [{other_match.group(1).upper()}]" if other_match else ""

    return (
        f"┏━━━━━━━━━━━━━━━━━┓\n"
        f"🎬 **{name}{year}{quality}**\n"
        f"┗━━━━━━━━━━━━━━━━━┛"
        f"{CUSTOM_FOOTER}"
    )

# Bulk Batch Tracker
batch_queue = {}
batch_tasks = {}

async def wait_and_notify(user_id, client):
    # 5 सेकंड तक नई फाइल का इंतज़ार करेगा, फिर फाइनल समरी भेजेगा
    await asyncio.sleep(5)
    if user_id in batch_queue and batch_queue[user_id] > 0:
        batch_count = batch_queue[user_id]
        batch_queue[user_id] = 0
        total = add_to_total_count(batch_count)
        await client.send_message(
            chat_id=user_id,
            text=(
                f"✅ **Batch Processing Complete!**\n\n"
                f"📥 Is baar bheji gayi: **{batch_count} files**\n"
                f"📊 Channel me ab tak total: **{total} files**"
            )
        )

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    count = get_total_count()
    await message.reply_text(
        f"✅ **Bot Active Hai!**\n\n"
        f"📊 Ab tak total **{count}** files channel me bheji ja chuki hain.\n"
        f"Aap single ya bulk me movie files forward karein."
    )

@app.on_message(filters.command("stats") & filters.private)
async def stats_handler(client, message):
    count = get_total_count()
    await message.reply_text(f"📊 Total Posted Files: **{count}**")

@app.on_message(filters.media & filters.private)
async def process_media(client, message):
    user_id = message.from_user.id
    
    # अगर पिछला टाइमर चल रहा था, तो उसे कैंसिल करके नया बनाएगा
    if user_id in batch_tasks and not batch_tasks[user_id].done():
        batch_tasks[user_id].cancel()

    try:
        file_name = ""
        if message.document and message.document.file_name:
            file_name = message.document.file_name
        elif message.video and message.video.file_name:
            file_name = message.video.file_name

        original_text = message.caption or file_name or ""
        new_caption = clean_caption_text(original_text)
        
        await message.copy(
            chat_id=TARGET_CHANNEL,
            caption=new_caption,
            parse_mode=ParseMode.MARKDOWN
        )
        
        # बैच काउंट बढ़ाना
        batch_queue[user_id] = batch_queue.get(user_id, 0) + 1
        
        # अगर लगातार 50 फाइलें पूरी हो गईं:
        if batch_queue[user_id] >= 50:
            batch_count = batch_queue[user_id]
            batch_queue[user_id] = 0
            total = add_to_total_count(batch_count)
            await message.reply_text(
                f"✅ **50 Files Completed!**\n\n"
                f"📥 50 files successfully channel me bhej di gayi hain.\n"
                f"📊 Total Channel Files: **{total}**"
            )
        else:
            # 50 से कम होने पर टाइमर सेट करेगा
            batch_tasks[user_id] = asyncio.create_task(wait_and_notify(user_id, client))

        # Telegram limits ke liye safe delay
        await asyncio.sleep(2)
        
    except FloodWait as e:
        await asyncio.sleep(e.value)
        await message.copy(chat_id=TARGET_CHANNEL, caption=new_caption, parse_mode=ParseMode.MARKDOWN)
        batch_queue[user_id] = batch_queue.get(user_id, 0) + 1
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
    
