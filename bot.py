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
INDEX_FILE = "index_data.json"

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

def load_index_data():
    if os.path.exists(INDEX_FILE):
        try:
            with open(INDEX_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"message_ids": [], "movies": {}}

def save_index_data(data):
    with open(INDEX_FILE, "w") as f:
        json.dump(data, f)

def get_clean_channel_id(channel_id):
    s = str(channel_id)
    if s.startswith("-100"):
        return s[4:]
    elif s.startswith("-"):
        return s[1:]
    return s

def clean_caption_text(text, fallback_id=None):
    if not text or not text.strip():
        tag = f" #ID_{fallback_id}" if fallback_id else ""
        caption = f"┏━━━━━━━━━━━━━━━━━┓\n🎬 **Update Name{tag}**\n┗━━━━━━━━━━━━━━━━━┛{CUSTOM_FOOTER}"
        return caption, f"Update Name{tag}"
    
    text = re.sub(r'\.(mkv|mp4|avi|webm|mov)$', '', text, flags=re.IGNORECASE)
    text = re.sub(r'https?://\S+|www\.\S+|t\.me/\S+', ' ', text)
    text = re.sub(r'@[\w_]+', ' ', text)
    text = re.sub(r'join\s+us\s+on\s+telegram', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'join\s+telegram', ' ', text, flags=re.IGNORECASE)

    lines = [l.strip() for l in text.split('\n') if l.strip()]
    raw_title = lines[0] if lines else text
    raw_title = re.sub(r'[\._]', ' ', raw_title)

    year_match = re.search(r'\b(19[5-9]\d|20[0-3]\d)\b', raw_title)
    year = f" ({year_match.group(1)})" if year_match else ""

    res_match = re.search(r'(\d{3,4}p|4K)', raw_title, re.IGNORECASE)
    quality = f" [{res_match.group(1).upper()}]" if res_match else ""

    if year_match:
        name = raw_title[:year_match.start()].strip()
    elif res_match:
        name = raw_title[:res_match.start()].strip()
    else:
        name = re.split(r'[\(\[\-#]', raw_title)[0].strip()

    name = re.sub(r'[\(\)\[\]\-_#|~★❤✔➔➜•:]+', ' ', name).strip()
    name = re.sub(r'\s+', ' ', name)

    if not name:
        tag = f" #ID_{fallback_id}" if fallback_id else ""
        name = f"Update Name{tag}"

    display_title = f"{name}{year}".strip()
    full_caption = (
        f"┏━━━━━━━━━━━━━━━━━┓\n"
        f"🎬 **{name}{year}{quality}**\n"
        f"┗━━━━━━━━━━━━━━━━━┛"
        f"{CUSTOM_FOOTER}"
    )
    return full_caption, display_title

async def render_index_messages(data):
    sorted_movies = sorted(data["movies"].items(), key=lambda x: x[0].lower())
    
    chunks = []
    lines = [f"• [{title}]({link})\n" for title, link in sorted_movies]
    
    current_chunk = ""
    for line in lines:
        if len(current_chunk) + len(line) > 3500:
            chunks.append(current_chunk)
            current_chunk = line
        else:
            current_chunk += line
    if current_chunk:
        chunks.append(current_chunk)

    total_parts = len(chunks) or 1
    formatted_chunks = []
    for idx, content in enumerate(chunks, 1):
        header = f"📑 **Master Movies Index — Part {idx}/{total_parts}**\n\n"
        formatted_chunks.append(header + content)

    for idx, chunk_text in enumerate(formatted_chunks):
        if idx < len(data["message_ids"]):
            try:
                await app.edit_message_text(
                    chat_id=TARGET_CHANNEL,
                    message_id=data["message_ids"][idx],
                    text=chunk_text,
                    disable_web_page_preview=True,
                    parse_mode=ParseMode.MARKDOWN
                )
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
            except Exception:
                pass
        else:
            try:
                sent = await app.send_message(
                    chat_id=TARGET_CHANNEL,
                    text=chunk_text,
                    disable_web_page_preview=True,
                    parse_mode=ParseMode.MARKDOWN
                )
                data["message_ids"].append(sent.id)
                if idx == 0:
                    try:
                        await sent.pin(disable_notification=True)
                    except Exception:
                        pass
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
            except Exception:
                pass

    save_index_data(data)

async def update_master_index(display_title, post_id):
    data = load_index_data()
    clean_id = get_clean_channel_id(TARGET_CHANNEL)
    post_link = f"https://t.me/c/{clean_id}/{post_id}"

    if display_title in data["movies"]:
        return
    data["movies"][display_title] = post_link
    await render_index_messages(data)

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

        original_text = msg.caption or ""
        if not original_text:
            if msg.document:
                original_text = msg.document.file_name or ""
            elif msg.video:
                original_text = getattr(msg.video, 'file_name', None) or getattr(msg.video, 'file_name', '')

        new_caption, display_title = clean_caption_text(original_text, fallback_id=msg.id)

        success = False
        while not success:
            try:
                copied_msg = await msg.copy(
                    chat_id=TARGET_CHANNEL,
                    caption=new_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
                success = True
                batch_count += 1
                await update_master_index(display_title, copied_msg.id)
            except FloodWait as e:
                await asyncio.sleep(e.value + 2)
            except Exception as e:
                print(f"Skipping file due to error: {e}")
                break

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
        f"📑 Master Index Feature Active Hai!\n"
        f"👉 Purani files ka index banane ke liye **/build_index** bhejein.\n"
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

@app.on_message(filters.command("build_index") & filters.private)
async def build_index_handler(client, message):
    status_msg = await message.reply_text("⏳ **Channel scan shuru ho gaya hai... Kripya 1-2 minute wait karein.**")
    clean_id = get_clean_channel_id(TARGET_CHANNEL)
    data = load_index_data()

    try:
        temp_msg = await app.send_message(TARGET_CHANNEL, "🔍 Checking index...")
        latest_id = temp_msg.id
        await temp_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"❌ Channel send permission check karein: {e}")
        return

    scanned = 0
    added = 0
    batch_size = 100

    try:
        for i in range(1, latest_id + 1, batch_size):
            msg_ids = list(range(i, min(i + batch_size, latest_id + 1)))
            try:
                messages = await app.get_messages(TARGET_CHANNEL, msg_ids)
            except FloodWait as e:
                await asyncio.sleep(e.value + 2)
                messages = await app.get_messages(TARGET_CHANNEL, msg_ids)
            except Exception:
                continue

            for post in messages:
                if not post or post.empty:
                    continue
                scanned += 1
                if post.document or post.video:
                    raw = post.caption or ""
                    if not raw:
                        if post.document and post.document.file_name:
                            raw = post.document.file_name
                        elif post.video and post.video.file_name:
                            raw = post.video.file_name

                    _, display_title = clean_caption_text(raw, fallback_id=post.id)
                    if display_title not in data["movies"]:
                        data["movies"][display_title] = f"https://t.me/c/{clean_id}/{post.id}"
                        added += 1

            await asyncio.sleep(0.5)

        await render_index_messages(data)
        await status_msg.edit_text(
            f"✅ **Master Index Taiyar Ho Gaya Hai!**\n\n"
            f"🔍 Total Messages Scanned: **{scanned}**\n"
            f"🎬 Unique Movies in Index: **{len(data['movies'])}**\n"
            f"📌 Channel me Master Index update aur pin ho chuka hai."
        )
    except FloodWait as e:
        await asyncio.sleep(e.value + 2)
    except Exception as e:
        await status_msg.edit_text(f"❌ Index banane me error: {e}")

@app.on_message(filters.media & filters.private)
async def process_media(client, message):
    await task_queue.put((message.chat.id, message.id))

# HEAD & GET dono handle karega taaki 501 error na aaye
class SimpleHandler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

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
