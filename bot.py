import os
import re
import json
import asyncio
import threading
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
DEFAULT_TARGET_CHANNEL = int(os.environ.get("TARGET_CHANNEL", "0"))
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
PORT = int(os.environ.get("PORT", 8080))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

STATS_FILE = "stats.json"
INDEX_FILE = "index_data.json"
CONFIG_FILE = "config.json"
USERS_FILE = "users.json"
PENDING_DUPLICATES_FILE = "pending_duplicates.json"

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

def load_config():
    default_cfg = {
        "main_channel": DEFAULT_TARGET_CHANNEL,
        "review_channel": DEFAULT_TARGET_CHANNEL
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)
                return {
                    "main_channel": data.get("main_channel", data.get("target_channel", DEFAULT_TARGET_CHANNEL)),
                    "review_channel": data.get("review_channel", DEFAULT_TARGET_CHANNEL)
                }
        except Exception:
            return default_cfg
    return default_cfg

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f)

def get_main_channel():
    return load_config()["main_channel"]

def get_review_channel():
    return load_config()["review_channel"]

def set_main_channel_id(new_id):
    cfg = load_config()
    cfg["main_channel"] = new_id
    save_config(cfg)

def set_review_channel_id(new_id):
    cfg = load_config()
    cfg["review_channel"] = new_id
    save_config(cfg)

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

async def get_raw_media_filename(msg):
    if not msg:
        return ""
    if msg.document and getattr(msg.document, 'file_name', None):
        return msg.document.file_name
    if msg.video and getattr(msg.video, 'file_name', None):
        return msg.video.file_name
    try:
        media = getattr(msg, 'video', None) or getattr(msg, 'document', None)
        if media:
            attrs = getattr(media, 'attributes', None) or []
            for attr in attrs:
                fn = getattr(attr, 'file_name', None)
                if fn:
                    return fn
        raw = getattr(msg, '_raw', None) or getattr(msg, 'raw', None)
        if raw and hasattr(raw, 'media'):
            doc = getattr(raw.media, 'document', None)
            if doc and hasattr(doc, 'attributes'):
                for attr in doc.attributes:
                    fn = getattr(attr, 'file_name', None)
                    if fn:
                        return fn
    except Exception:
        pass
    return ""

def parse_movie_details(text):
    if not text or not text.strip():
        return None, None, None, "DEFAULT"

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
    year_str = f" ({year_match.group(1)})" if year_match else None

    res_match = re.search(r'\b(\d{3,4}p|4K|DS4K|HDRip|WEB-?DL|HD)\b', raw_title, re.IGNORECASE)
    quality_str = f" [{res_match.group(1).upper()}]" if res_match else ""
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
        return None, None, None, "DEFAULT"

    return name, year_str, quality_str, quality_tag

async def get_final_movie_caption(msg, fallback_id=None):
    caption_text = msg.caption or ""
    file_name_text = await get_raw_media_filename(msg)

    name, year, quality, q_tag = None, None, "", "DEFAULT"
    if caption_text.strip():
        p_name, p_year, p_qual, p_tag = parse_movie_details(caption_text)
        if p_name and p_year:
            name, year, quality, q_tag = p_name, p_year, p_qual, p_tag

    if not name or not year:
        if file_name_text.strip():
            p_name, p_year, p_qual, p_tag = parse_movie_details(file_name_text)
            if p_name:
                name, year, quality, q_tag = p_name, p_year, p_qual, p_tag

    is_unnamed = False
    if not name:
        is_unnamed = True
        tag = f" #ID_{fallback_id}" if fallback_id else ""
        name = f"Movie{tag}"
        year = ""
        quality = ""
        q_tag = "DEFAULT"

    year = year or ""
    display_title = f"{name}{year}".strip()
    full_caption = (
        f"┏━━━━━━━━━━━━━━━━━┓\n"
        f"🎬 **{name}{year}{quality}**\n"
        f"┗━━━━━━━━━━━━━━━━━┛"
        f"{CUSTOM_FOOTER}"
    )
    signature = f"{display_title}_{q_tag}".lower().strip()
    return full_caption, display_title, signature, is_unnamed

async def render_index_messages(data):
    target = get_main_channel()
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
review_count = 0
active_user_id = None

async def worker():
    global batch_count, review_count, active_user_id
    pending_index_updates = 0

    while True:
        chat_id, msg_id = await task_queue.get()
        active_user_id = chat_id
        main_ch = get_main_channel()
        review_ch = get_review_channel()

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

        new_caption, display_title, signature, is_unnamed = await get_final_movie_caption(msg, fallback_id=msg.id)
        target = review_ch if is_unnamed else main_ch

        success = False
        while not success:
            try:
                copied_msg = await msg.copy(
                    chat_id=target,
                    caption=new_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
                success = True

                if is_unnamed:
                    review_count += 1
                else:
                    batch_count += 1
                    data = load_index_data()
                    clean_id = get_clean_channel_id(main_ch)
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

        if (batch_count + review_count) >= 50:
            total = add_to_total_count(batch_count)
            try:
                await app.send_message(
                    chat_id=active_user_id,
                    text=(
                        f"🚀 **50 Files Processed!**\n\n"
                        f"✅ Main Channel (Safe): **{batch_count} files**\n"
                        f"⚠️ Review Channel (ID): **{review_count} files**\n"
                        f"📊 Total Main Files: **{total}**\n"
                        f"⏳ Remaining in Queue: **{task_queue.qsize()} files**"
                    )
                )
            except Exception:
                pass
            batch_count = 0
            review_count = 0

        task_queue.task_done()
        await asyncio.sleep(0.8)

        if task_queue.empty():
            if pending_index_updates > 0:
                data = load_index_data()
                await render_index_messages(data)
                pending_index_updates = 0

            if batch_count > 0 or review_count > 0:
                total = add_to_total_count(batch_count)
                try:
                    await app.send_message(
                        chat_id=active_user_id,
                        text=(
                            f"🎉 **Batch Complete Ho Gaya!**\n\n"
                            f"✅ **Main Channel Me Gai:** {batch_count}\n"
                            f"⚠️ **Review Channel Me Gai:** {review_count}\n"
                            f"📊 **Total Main Channel Files:** {total}\n"
                            f"✨ Processing successfully poori ho chuki hai."
                        )
                    )
                except Exception:
                    pass
                batch_count = 0
                review_count = 0

@app.on_message(filters.command("start") & filters.private)
async def start_handler(client, message):
    save_user(message.from_user.id)
    if not is_admin(None, None, message):
        await message.reply_text("⛔ **Access Denied!**\nYeh bot private hai aur sirf Admin use kar sakta hai.")
        return

    count = get_total_count()
    main_ch = get_main_channel()
    rev_ch = get_review_channel()
    await message.reply_text(
        f"🤖 **Caption Cleaner & Dual-Channel Bot Active Hai!**\n\n"
        f"🎯 **Main Channel:** `{main_ch}` (Saaf movies)\n"
        f"🛠️ **Review Channel:** `{rev_ch}` (Bina name / #ID files)\n"
        f"📊 Main Channel Total Files: **{count}**\n\n"
        f"⚙️ **Admin Commands:**\n"
        f"• `/set_main <id>` - Main channel badlein\n"
        f"• `/set_review <id>` - Review channel badlein\n"
        f"• `/move_id_files` - Purani ID files Review Channel me bhejein\n"
        f"• `/remove_duplicates` - Main channel duplicates review & delete karein\n"
        f"• `/build_index` - Master Index refresh karein\n"
        f"• `/fix_captions` - Main channel captions theek karein\n"
        f"• `/users` - Total Bot Users check karein\n"
        f"• `/stats` - Live Queue & Status check karein"
    )

@app.on_message(filters.command("set_main") & filters.private & admin_filter)
async def set_main_handler(client, message):
    if len(message.command) < 2:
        cur = get_main_channel()
        await message.reply_text(f"ℹ️ **Current Main Channel:** `{cur}`\n\nAise likhein:\n`/set_main -100xxxxxxxxxx`")
        return
    try:
        new_id = int(message.command[1].strip())
        set_main_channel_id(new_id)
        await message.reply_text(f"✅ **Main Channel Set:** `{new_id}`\nAb sahi naam wali files yahan aayengi!")
    except ValueError:
        await message.reply_text("❌ Galat Channel ID! ID number me honi chahiye (jaise `-1001234567890`).")

@app.on_message(filters.command("set_review") & filters.private & admin_filter)
async def set_review_handler(client, message):
    if len(message.command) < 2:
        cur = get_review_channel()
        await message.reply_text(f"ℹ️ **Current Review Channel:** `{cur}`\n\nAise likhein:\n`/set_review -100xxxxxxxxxx`")
        return
    try:
        new_id = int(message.command[1].strip())
        set_review_channel_id(new_id)
        await message.reply_text(f"✅ **Review Channel Set:** `{new_id}`\nAb bina naam / #ID wali files yahan aayengi!")
    except ValueError:
        await message.reply_text("❌ Galat Channel ID! ID number me honi chahiye (jaise `-1001234567890`).")

@app.on_message(filters.command("move_id_files") & filters.private & admin_filter)
async def move_id_files_handler(client, message):
    main_ch = get_main_channel()
    review_ch = get_review_channel()

    if main_ch == review_ch:
        await message.reply_text("❌ Main Channel aur Review Channel alag-alag hone chahiye! Pehle `/set_review <id>` karein.")
        return

    status_msg = await message.reply_text("🔍 **Main Channel scan ho raha hai... ID wali files dhoondi ja rahi hain...**")

    try:
        temp_msg = await app.send_message(main_ch, "🔍 Checking...")
        latest_id = temp_msg.id
        await temp_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {e}")
        return

    moved_count = 0
    batch_size = 100

    for i in range(1, latest_id + 1, batch_size):
        msg_ids = list(range(i, min(i + batch_size, latest_id + 1)))
        try:
            messages = await app.get_messages(main_ch, msg_ids)
        except FloodWait as e:
            await asyncio.sleep(e.value + 2)
            messages = await app.get_messages(main_ch, msg_ids)
        except Exception:
            continue

        for post in messages:
            if not post or post.empty:
                continue

            caption = post.caption or ""
            if ("#ID_" in caption) or ("Update Name" in caption):
                try:
                    await post.copy(chat_id=review_ch)
                    await post.delete()
                    moved_count += 1
                    await asyncio.sleep(0.8)
                except FloodWait as e:
                    await asyncio.sleep(e.value + 2)
                    try:
                        await post.copy(chat_id=review_ch)
                        await post.delete()
                        moved_count += 1
                    except Exception:
                        pass
                except Exception:
                    pass

    await status_msg.edit_text(
        f"📦 **Transfer Complete!**\n\n"
        f"🚚 Total **{moved_count} files** Review Channel me bhej di gayi hain aur Main Channel se hata di gayi hain!\n"
        f"👉 Ab ek baar **/build_index** bhej dein taaki Main Channel ka Index refresh ho jaye."
    )

@app.on_message(filters.command("users") & filters.private & admin_filter)
async def users_handler(client, message):
    users = load_users()
    await message.reply_text(f"👥 **Total Bot Users:** **{len(users)}** logo ne bot start kiya hai.")

@app.on_message(filters.command("stats") & filters.private & admin_filter)
async def stats_handler(client, message):
    count = get_total_count()
    q_size = task_queue.qsize()
    main_ch = get_main_channel()
    rev_ch = get_review_channel()
    await message.reply_text(
        f"📊 **Live Status:**\n"
        f"• Main Channel: `{main_ch}`\n"
        f"• Review Channel: `{rev_ch}`\n"
        f"• Main Channel Files: **{count}**\n"
        f"• Queue me bachi files: **{q_size}**"
    )

@app.on_message(filters.command("remove_duplicates") & filters.private & admin_filter)
async def remove_duplicates_handler(client, message):
    target = get_main_channel()
    clean_id = get_clean_channel_id(target)
    status_msg = await message.reply_text("🔍 **Main Channel me duplicate files scan ho rahi hain...**")

    try:
        temp_msg = await app.send_message(target, "🔍 Scanning...")
        latest_id = temp_msg.id
        await temp_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {e}")
        return

    seen_signatures = {}
    duplicates_to_mark = []
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
                _, title, sig, is_unnamed = await get_final_movie_caption(post, fallback_id=post.id)
                if not sig or is_unnamed:
                    continue

                if sig in seen_signatures:
                    orig_id = seen_signatures[sig]
                    duplicates_to_mark.append({
                        "dup_id": post.id,
                        "orig_id": orig_id,
                        "title": title,
                        "old_caption": post.caption or ""
                    })
                else:
                    seen_signatures[sig] = post.id

    if not duplicates_to_mark:
        await status_msg.edit_text(f"✅ **Koi Duplicate File Nahi Mili!**\n\n🔍 Messages Scanned: **{scanned}**\n✨ Main Channel ki sabhi files unique hain.")
        return

    await status_msg.edit_text(f"⚠️ **{len(duplicates_to_mark)} Duplicates mili hain!**\nUn par Tag lagaya ja raha hai...")

    for item in duplicates_to_mark:
        dup_id = item["dup_id"]
        orig_id = item["orig_id"]
        cur_cap = item["old_caption"]

        if "DUPLICATE_FILE" not in cur_cap:
            marked_caption = f"⚠️ **#DUPLICATE_FILE** (Original Post: `#ID_{orig_id}`)\n\n" + cur_cap
            try:
                await app.edit_message_caption(
                    chat_id=target,
                    message_id=dup_id,
                    caption=marked_caption,
                    parse_mode=ParseMode.MARKDOWN
                )
                await asyncio.sleep(0.8)
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
                try:
                    await app.edit_message_caption(
                        chat_id=target,
                        message_id=dup_id,
                        caption=marked_caption,
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception:
                    pass
            except Exception:
                pass

    with open(PENDING_DUPLICATES_FILE, "w") as f:
        json.dump([d["dup_id"] for d in duplicates_to_mark], f)

    report_lines = []
    for idx, d in enumerate(duplicates_to_mark[:10], 1):
        report_lines.append(
            f"{idx}. 🎬 **{d['title']}**\n"
            f"   • Original: [Post #{d['orig_id']}](https://t.me/c/{clean_id}/{d['orig_id']})\n"
            f"   • Duplicate: [Post #{d['dup_id']}](https://t.me/c/{clean_id}/{d['dup_id']})"
        )

    more_text = f"\n...aur **{len(duplicates_to_mark) - 10}** aur files." if len(duplicates_to_mark) > 10 else ""
    report_text = (
        f"📋 **Duplicate Files Review List (Main Channel):**\n\n"
        + "\n\n".join(report_lines)
        + more_text + "\n\n"
        f"⚠️ Sabhi {len(duplicates_to_mark)} duplicate posts par `#DUPLICATE_FILE` tag laga diya gaya hai.\n"
        f"Agar aap in sabhi duplicates ko ek sath channel se delete karna chahte hain, to niche diye gaye button par click karein:"
    )

    btn = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑️ Confirm Delete All Duplicates", callback_data="delete_all_duplicates")]
    ])
    await message.reply_text(report_text, reply_markup=btn, disable_web_page_preview=True)

@app.on_callback_query(filters.regex("^delete_all_duplicates$"))
async def handle_delete_duplicates_callback(client, callback_query: CallbackQuery):
    if not is_admin(None, None, callback_query):
        await callback_query.answer("⛔ Sirf Admin yeh action le sakta hai!", show_alert=True)
        return

    if not os.path.exists(PENDING_DUPLICATES_FILE):
        await callback_query.answer("❌ Koi pending duplicates nahi mile!", show_alert=True)
        return

    with open(PENDING_DUPLICATES_FILE, "r") as f:
        del_ids = json.load(f)

    if not del_ids:
        await callback_query.answer("❌ List pehle se empty hai!", show_alert=True)
        return

    await callback_query.message.edit_reply_markup(reply_markup=None)
    await callback_query.message.reply_text(f"⏳ **{len(del_ids)} duplicates Main Channel se delete ho rahe hain...**")

    target = get_main_channel()
    deleted_count = 0

    for d_id in del_ids:
        try:
            await app.delete_messages(chat_id=target, message_ids=d_id)
            deleted_count += 1
            await asyncio.sleep(0.5)
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
            try:
                await app.delete_messages(chat_id=target, message_ids=d_id)
                deleted_count += 1
            except Exception:
                pass
        except Exception:
            pass

    if os.path.exists(PENDING_DUPLICATES_FILE):
        os.remove(PENDING_DUPLICATES_FILE)

    await callback_query.message.reply_text(
        f"🎉 **Clean-up Successful!**\n\n"
        f"🗑️ Total **{deleted_count} duplicate files** delete ho chuki hain!\n"
        f"👉 Ab ek baar **/build_index** bhej dein."
    )

@app.on_message(filters.command("fix_captions") & filters.private & admin_filter)
async def fix_captions_handler(client, message):
    target = get_main_channel()
    status_msg = await message.reply_text("🛠️ **Main Channel scan ho raha hai... ID wali files theek ki ja rahi hain...**")
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
                new_caption, _, _, is_unnamed = await get_final_movie_caption(post, fallback_id=post.id)
                if not is_unnamed:
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
    target = get_main_channel()
    status_msg = await message.reply_text("⏳ **Main Channel scan shuru ho gaya hai... Kripya 1-2 minute wait karein.**")
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
                    _, display_title, sig, is_unnamed = await get_final_movie_caption(post, fallback_id=post.id)
                    if not is_unnamed:
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
            f"📌 Main Channel me Master Index update aur pin ho chuka hai."
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
