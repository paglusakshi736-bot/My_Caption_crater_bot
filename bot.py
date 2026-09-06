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
DEFAULT_TARGET_CHANNEL = int(os.environ.get("TARGET_CHANNEL"))
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
PORT = int(os.environ.get("PORT", 8080))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

STATS_FILE = "stats.json"
INDEX_FILE = "index_data.json"
CONFIG_FILE = "config.json"
USERS_FILE = "users.json"

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

def get_target_channel():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f).get("target_channel", DEFAULT_TARGET_CHANNEL)
        except Exception:
            return DEFAULT_TARGET_CHANNEL
    return DEFAULT_TARGET_CHANNEL

def set_target_channel_id(new_id):
    with open(CONFIG_FILE, "w") as f:
        json.dump({"target_channel": new_id}, f)

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

def load_users():
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_user(user_id):
    users = load_users()
    if user_id not in users:
        users.add(user_id)
        with open(USERS_FILE, "w") as f:
            json.dump(list(users), f)

def load_index_data():
    if os.path.exists(INDEX_FILE):
        try:
            with open(INDEX_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"message_ids": [], "movies": {}, "existing_signatures": []}

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

def is_admin(_, __, message):
    if not ADMIN_ID:
        return True
    return message.from_user and message.from_user.id == ADMIN_ID

admin_filter = filters.create(is_admin)

async def extract_real_file_name(msg):
    if not msg:
        return ""

    if msg.caption and msg.caption.strip():
        return msg.caption

    if msg.document and msg.document.file_name:
        return msg.document.file_name

    if msg.video:
        if getattr(msg.video, 'file_name', None):
            return msg.video.file_name
        if hasattr(msg.video, 'attributes') and msg.video.attributes:
            for attr in msg.video.attributes:
                fn = getattr(attr, 'file_name', None)
                if fn:
                    return fn

    try:
        media = getattr(msg, 'video', None) or getattr(msg, 'document', None)
        if media:
            for key in ['attributes', 'raw']:
                obj = getattr(media, key, None)
                if obj and isinstance(obj, list):
                    for item in obj:
                        fn = getattr(item, 'file_name', None)
                        if fn:
                            return fn
    except Exception:
        pass

    if msg.forward_from_chat and msg.forward_from_message_id:
        try:
            fwd = await app.get_messages(msg.forward_from_chat.id, msg.forward_from_message_id)
            if fwd:
                fwd_name = await extract_real_file_name(fwd)
                if fwd_name:
                    return fwd_name
        except Exception:
            pass

    return ""

def clean_caption_text(text, fallback_id=None):
    if not text or not text.strip():
        tag = f" #ID_{fallback_id}" if fallback_id else ""
        caption = f"┏━━━━━━━━━━━━━━━━━┓\n🎬 **Update Name{tag}**\n┗━━━━━━━━━━━━━━━━━┛{CUSTOM_FOOTER}"
        return caption, f"Update Name{tag}", f"update_name_{fallback_id}"

    movie_line_match = re.search(r'🎬\s*\**([^\*\n\r]+)', text)
    if movie_line_match:
        raw_title = movie_line_match.group(1).strip()
    else:
        text_clean = re.sub(r'\.(mkv|mp4|avi|webm|mov)$', '', text, flags=re.IGNORECASE)
        text_clean = re.sub(r'https?://\S+|www\.\S+|t\.me/\S+', ' ', text_clean)
        text_clean = re.sub(r'@[\w_]+', ' ', text_clean)
        text_clean = re.sub(r'(?i)\bjoin\s+us\s+on\s+telegram\b', ' ', text_clean)
        text_clean = re.sub(r'(?i)\bjoin\s+telegram\b', ' ', text_clean)

        valid_lines = []
        for l in text_clean.split('\n'):
            line_str = re.sub(r'^[┏┗━\s\[\]\(\)\-_#|~★❤✔➔➜•:]+', '', l.strip()).strip()
            if line_str and re.search(r'[a-zA-Z0-9]', line_str):
                valid_lines.append(line_str)

        raw_title = valid_lines[0] if valid_lines else text_clean

    raw_title = re.sub(r'[\._]', ' ', raw_title)

    year_match = re.search(r'\b(19[5-9]\d|20[0-3]\d)\b', raw_title)
    year = f" ({year_match.group(1)})" if year_match else ""

    res_match = re.search(r'\b(\d{3,4}p|4K|DS4K|HDRip|WEB-?DL|HD)\b', raw_title, re.IGNORECASE)
    quality = f" [{res_match.group(1).upper()}]" if res_match else ""
    quality_tag = res_match.group(1).upper() if res_match else "DEFAULT"

    cut_pos = len(raw_title)
    if year_match:
        cut_pos = min(cut_pos, year_match.start())
    if res_match:
        cut_pos = min(cut_pos, res_match.start())

    name = raw_title[:cut_pos].strip()
    name = re.sub(r'[\(\)\[\]\-_#|~★❤✔➔➜•:┏┗━*]+', ' ', name).strip()
    name = re.sub(r'\s+', ' ', name)

    if not name or name.lower() == "movie":
        tag = f" #ID_{fallback_id}" if fallback_id else ""
        name = f"Movie{tag}"

    display_title = f"{name}{year}".strip()
    full_caption = (
        f"┏━━━━━━━━━━━━━━━━━┓\n"
        f"🎬 **{name}{year}{quality}**\n"
        f"┗━━━━━━━━━━━━━━━━━┛"
        f"{CUSTOM_FOOTER}"
    )
    signature = f"{display_title}_{quality_tag}".lower().strip()
    return full_caption, display_title, signature

async def render_index_messages(data):
    target = get_target_channel()
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
                    chat_id=target,
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
                    chat_id=target,
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

task_queue = asyncio.Queue()
batch_count = 0
duplicate_skipped_count = 0
active_user_id = None

async def worker():
    global batch_count, duplicate_skipped_count, active_user_id
    pending_index_updates = 0

    while True:
        chat_id, msg_id = await task_queue.get()
        active_user_id = chat_id
        target = get_target_channel()

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

        original_text = await extract_real_file_name(msg)
        new_caption, display_title, signature = clean_caption_text(original_text, fallback_id=msg.id)

        data = load_index_data()
        existing_sigs = set(data.get("existing_signatures", []))

        if signature in existing_sigs and not signature.startswith("update_name_"):
            duplicate_skipped_count += 1
            task_queue.task_done()
            await asyncio.sleep(0.1)
            continue

        success = False
        while not success:
            try:
                copied_msg = await msg.copy(
                    chat_id=target,
                    caption=new_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
                success = True
                batch_count += 1

                clean_id = get_clean_channel_id(target)
                post_link = f"https://t.me/c/{clean_id}/{copied_msg.id}"

                if display_title not in data["movies"]:
                    data["movies"][display_title] = post_link

                if "existing_signatures" not in data:
                    data["existing_signatures"] = []
                data["existing_signatures"].append(signature)
                save_index_data(data)
                pending_index_updates += 1

                if pending_index_updates >= 10:
                    await render_index_messages(data)
                    pending_index_updates = 0

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
                        f"🚀 **50 Files Processed!**\n\n"
                        f"✅ New Uploaded: **50 files**\n"
                        f"🚫 Duplicate Skipped: **{duplicate_skipped_count} files**\n"
                        f"📊 Total Channel Files: **{total}**\n"
                        f"⏳ Remaining in Queue: **{task_queue.qsize()} files**"
                    )
                )
            except Exception:
                pass
            batch_count = 0

        task_queue.task_done()
        await asyncio.sleep(0.8)

        if task_queue.empty():
            if pending_index_updates > 0:
                data = load_index_data()
                await render_index_messages(data)
                pending_index_updates = 0

            if batch_count > 0 or duplicate_skipped_count > 0:
                total = add_to_total_count(batch_count)
                try:
                    await app.send_message(
                        chat_id=active_user_id,
                        text=(
                            f"🎉 **Batch Complete Ho Gaya!**\n\n"
                            f"✅ **New Files Uploaded:** {batch_count}\n"
                            f"🚫 **Duplicate Skipped:** {duplicate_skipped_count}\n"
                            f"📊 **Total Channel Files:** {total}\n"
                            f"✨ Sabhi files successfully process ho chuki hain."
                        )
                    )
                except Exception:
                    pass
                batch_count = 0
                duplicate_skipped_count = 0

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    save_user(message.from_user.id)
    if not is_admin(None, None, message):
        await message.reply_text("⛔ **Access Denied!**\nYeh bot private hai aur sirf Admin use kar sakta hai.")
        return

    count = get_total_count()
    cur_ch = get_target_channel()
    await message.reply_text(
        f"🤖 **Caption Cleaner Bot Active Hai!**\n\n"
        f"🎯 Current Channel: `{cur_ch}`\n"
        f"📊 Channel Total Files: **{count}**\n\n"
        f"⚙️ **Admin Commands:**\n"
        f"• `/set_channel <id>` - Target channel badlein\n"
        f"• `/users` - Total Bot Users check karein\n"
        f"• `/stats` - Live Queue & Files check karein\n"
        f"• `/remove_duplicates` - Duplicate files clean karein\n"
        f"• `/build_index` - Master Index refresh karein\n"
        f"• `/fix_captions` - Corrupt caption theek karein"
    )

@app.on_message(filters.command("set_channel") & filters.private & admin_filter)
async def set_channel_handler(client, message):
    if len(message.command) < 2:
        cur = get_target_channel()
        await message.reply_text(f"ℹ️ **Current Channel:** `{cur}`\n\nChannel badalne ke liye aise likhein:\n`/set_channel -100xxxxxxxxxx`")
        return

    new_channel_str = message.command[1].strip()
    try:
        new_channel_id = int(new_channel_str)
        set_target_channel_id(new_channel_id)
        await message.reply_text(
            f"✅ **Target Channel Updated!**\n\n"
            f"Ab sabhi files is channel me post hongi: `{new_channel_id}`\n\n"
            f"⚠️ *Dhyan rahe:* Bot is naye channel me Admin hona chahiye!"
        )
    except ValueError:
        await message.reply_text("❌ Galat Channel ID! ID number me honi chahiye (jaise `-1001234567890`).")

@app.on_message(filters.command("users") & filters.private & admin_filter)
async def users_handler(client, message):
    users = load_users()
    await message.reply_text(f"👥 **Total Bot Users:** **{len(users)}** logo ne bot start kiya hai.")

@app.on_message(filters.command("stats") & filters.private & admin_filter)
async def stats_handler(client, message):
    count = get_total_count()
    q_size = task_queue.qsize()
    cur_ch = get_target_channel()
    await message.reply_text(
        f"📊 **Live Status:**\n"
        f"• Target Channel: `{cur_ch}`\n"
        f"• Total Channel Files: **{count}**\n"
        f"• Queue me bachi files: **{q_size}**"
    )

@app.on_message(filters.command("remove_duplicates") & filters.private & admin_filter)
async def remove_duplicates_handler(client, message):
    target = get_target_channel()
    status_msg = await message.reply_text("🔍 **Channel me duplicate files check ho rahi hain...**")

    try:
        temp_msg = await app.send_message(target, "🔍 Scanning...")
        latest_id = temp_msg.id
        await temp_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {e}")
        return

    seen_signatures = {}
    duplicates_to_delete = []
    scanned = 0
    batch_size = 100

    for i in range(1, latest_id + 1, batch_size):
        msg_ids = list(range(i, min(i + batch_size, latest_id + 1)))
        try:
            messages = await app.get_messages(target, msg_ids)
        except FloodWait as e:
            await asyncio.sleep(e.value + 2)
            messages = await app.get_messages(target, msg_ids)
        except Exception:
            continue

        for post in messages:
            if not post or post.empty:
                continue
            scanned += 1
            if post.document or post.video:
                raw = await extract_real_file_name(post)
                _, _, sig = clean_caption_text(raw, fallback_id=post.id)
                if not sig or sig.startswith("update_name_"):
                    continue

                if sig in seen_signatures:
                    duplicates_to_delete.append(post.id)
                else:
                    seen_signatures[sig] = post.id

    deleted_count = 0
    for del_id in duplicates_to_delete:
        try:
            await app.delete_messages(chat_id=target, message_ids=del_id)
            deleted_count += 1
            await asyncio.sleep(0.5)
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
            try:
                await app.delete_messages(chat_id=target, message_ids=del_id)
                deleted_count += 1
            except Exception:
                pass
        except Exception:
            pass

    data = load_index_data()
    data["existing_signatures"] = list(seen_signatures.keys())
    save_index_data(data)

    await status_msg.edit_text(
        f"🗑️ **Duplicate Clean-up Complete!**\n\n"
        f"🔍 Messages Scanned: **{scanned}**\n"
        f"🗑️ Duplicates Removed: **{deleted_count} files**\n"
        f"✅ Unique Files Safe: **{len(seen_signatures)} files**\n\n"
        f"👉 Ek baar **/build_index** bhej dein."
    )

@app.on_message(filters.command("fix_captions") & filters.private & admin_filter)
async def fix_captions_handler(client, message):
    target = get_target_channel()
    status_msg = await message.reply_text("🛠️ **Channel scan ho raha hai... ID wali files theek ki ja rahi hain...**")
    fixed_count = 0

    try:
        temp_msg = await app.send_message(target, "🔍 Checking...")
        latest_id = temp_msg.id
        await temp_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {e}")
        return

    batch_size = 100
    for i in range(1, latest_id + 1, batch_size):
        msg_ids = list(range(i, min(i + batch_size, latest_id + 1)))
        try:
            messages = await app.get_messages(target, msg_ids)
        except FloodWait as e:
            await asyncio.sleep(e.value + 2)
            messages = await app.get_messages(target, msg_ids)
        except Exception:
            continue

        for post in messages:
            if not post or post.empty:
                continue

            caption = post.caption or ""
            if ("Movie #ID_" in caption) or ("Update Name" in caption) or (re.search(r'🎬\s*\*\*Movie\*\*', caption)):
                real_file_name = await extract_real_file_name(post)
                if real_file_name:
                    new_caption, _, _ = clean_caption_text(real_file_name, fallback_id=post.id)
                    try:
                        await post.edit_caption(new_caption, parse_mode=ParseMode.MARKDOWN)
                        fixed_count += 1
                        await asyncio.sleep(1.0)
                    except FloodWait as e:
                        await asyncio.sleep(e.value + 2)
                        await post.edit_caption(new_caption, parse_mode=ParseMode.MARKDOWN)
                        fixed_count += 1
                    except Exception:
                        pass

    await status_msg.edit_text(
        f"🎉 **Kaam Ho Gaya!**\n\n"
        f"✅ Total **{fixed_count}** files theek kar di gayi hain!\n"
        f"👉 Ab ek baar **/build_index** bhej dein."
    )

@app.on_message(filters.command("build_index") & filters.private & admin_filter)
async def build_index_handler(client, message):
    target = get_target_channel()
    status_msg = await message.reply_text("⏳ **Channel scan shuru ho gaya hai... Kripya 1-2 minute wait karein.**")
    clean_id = get_clean_channel_id(target)
    data = {"message_ids": [], "movies": {}, "existing_signatures": []}

    try:
        temp_msg = await app.send_message(target, "🔍 Checking index...")
        latest_id = temp_msg.id
        await temp_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"❌ Channel send permission check karein: {e}")
        return

    scanned = 0
    batch_size = 100

    try:
        for i in range(1, latest_id + 1, batch_size):
            msg_ids = list(range(i, min(i + batch_size, latest_id + 1)))
            try:
                messages = await app.get_messages(target, msg_ids)
            except FloodWait as e:
                await asyncio.sleep(e.value + 2)
                messages = await app.get_messages(target, msg_ids)
            except Exception:
                continue

            for post in messages:
                if not post or post.empty:
                    continue
                scanned += 1
                if post.document or post.video:
                    raw = await extract_real_file_name(post)
                    _, display_title, sig = clean_caption_text(raw, fallback_id=post.id)
                    if display_title not in data["movies"]:
                        data["movies"][display_title] = f"https://t.me/c/{clean_id}/{post.id}"
                    if sig and sig not in data["existing_signatures"]:
                        data["existing_signatures"].append(sig)

            await asyncio.sleep(0.5)

        old_data = load_index_data()
        data["message_ids"] = old_data.get("message_ids", [])
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

@app.on_message(filters.media & filters.private & admin_filter)
async def process_media(client, message):
    await task_queue.put((message.chat.id, message.id))

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
