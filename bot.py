import os
import re
import json
import asyncio
import threading
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
TARGET_CHANNEL = int(os.environ.get("TARGET_CHANNEL"))
PORT = int(os.environ.get("PORT", 8080))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

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
        return f"┏━━━━━━━━━━━━━━━━━┓\n🎬 **New Movie**\n┗━━━━━━━━━━━━━━━━━┛{CUSTOM_FOOTER}"
    
    # 1. पहली लाइन उठाना
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    first_line = lines[0] if lines else text

    # 2. फ़ाइल एक्सटेंशन (.mkv, .mp4 आदि) हटाना
    first_line = re.sub(r'\.(mkv|mp4|avi|webm|mov)$', '', first_line, flags=re.IGNORECASE)

    # 3. सिर्फ लिंक्स और @usernames को हटाना
    first_line = re.sub(r'https?://\S+|www\.\S+|t\.me/\S+', '', first_line)
    first_line = re.sub(r'@[\w_]+', '', first_line)

    # 4. एक्स्ट्रा स्पेसेस साफ़ करना (नाम को बिना काटे सुरक्षित रखना)
    cleaned_title = re.sub(r'\s+', ' ', first_line).strip()

    if not cleaned_title:
        cleaned_title = "New Movie"

    return (
        f"┏━━━━━━━━━━━━━━━━━┓\n"
        f"🎬 **{cleaned_title}**\n"
        f"┗━━━━━━━━━━━━━━━━━┛"
        f"{CUSTOM_FOOTER}"
    )

task_queue = asyncio.Queue()
batch_count = 0
active_user_id = None

async def worker():
    global batch_count, active_user_id
    while True:
        chat_id, msg_id = await task_queue.get()
        active_user_id = chat_id
        
        try:
            msg = await app.get_messages(chat_id=chat_id, message_ids=msg_id)
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
            msg = await app.get_messages(chat_id=chat_id, message_ids=msg_id)
        except Exception:
            task_queue.task_done()
            continue

        if not msg or msg.empty:
            task_queue.task_done()
            continue

        file_name = ""
        if msg.document and msg.document.file_name:
            file_name = msg.document.file_name
        elif msg.video and msg.video.file_name:
            file_name = msg.video.file_name

        original_text = msg.caption or file_name or ""
        new_caption = clean_caption_text(original_text)

        success = False
        while not success:
            try:
                await msg.copy(
                    chat_id=TARGET_CHANNEL,
                    caption=new_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
                success = True
                batch_count += 1
            except FloodWait as e:
                await asyncio.sleep(e.value + 2)
            except Exception as e:
                print(f"Skipping file due to error: {e}")
                break

        # हर 50 फाइल्स पर अपडेट
        if batch_count >= 50:
            total = add_to_total_count(batch_count)
            try:
                await app.send_message(
                    chat_id=active_user_id,
                    text=(
                        f"🚀 **50 Files Done!**\n\n"
                        f"✅ 50 files successfully post ho gayi hain.\n"
                        f"📊 Total Channel Files: **{total}**\n"
                        f"⏳ Remaining in Queue: **{task_queue.qsize()} files**"
                    )
                )
            except Exception:
                pass
            batch_count = 0

        task_queue.task_done()
        await asyncio.sleep(2.5)

        # पूरी कतार खाली होने पर मैसेज
        if task_queue.empty() and batch_count > 0:
            total = add_to_total_count(batch_count)
            try:
                await app.send_message(
                    chat_id=active_user_id,
                    text=(
                        f"🎉 **Sabhi Files Complete Ho Gayi Hain!**\n\n"
                        f"📥 Last Batch: **{batch_count} files**\n"
                        f"📊 Total Files in Channel: **{total}**\n"
                        f"✨ Queue bilkul khali ho chuki hai."
                    )
                )
            except Exception:
                pass
            batch_count = 0

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    count = get_total_count()
    await message.reply_text(
        f"🤖 **Caption Cleaner Bot Active Hai!**\n\n"
        f"📊 Channel me ab tak total: **{count} files**\n"
        f"⚡ Bulk me files bhejiye, bot queue me sambhal lega."
    )

@app.on_message(filters.command("stats") & filters.private)
async def stats_handler(client, message):
    count = get_total_count()
    q_size = task_queue.qsize()
    await message.reply_text(
        f"📊 **Live Status:**\n"
        f"• Total Channel Files: **{count}**\n"
        f"• Queue me bachi files: **{q_size}**"
    )

@app.on_message(filters.media & filters.private)
async def process_media(client, message):
    await task_queue.put((message.chat.id, message.id))

class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is alive!")

def run_web():
    httpd = HTTPServer(("0.0.0.0", PORT), SimpleHandler)
    httpd.serve_forever()

async def keep_alive_pinger():
    await asyncio.sleep(30)
    while True:
        if RENDER_EXTERNAL_URL:
            try:
                urllib.request.urlopen(RENDER_EXTERNAL_URL)
            except Exception:
                pass
        await asyncio.sleep(600)

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    
    loop = asyncio.get_event_loop()
    loop.create_task(worker())
    loop.create_task(keep_alive_pinger())
    
    app.run()
