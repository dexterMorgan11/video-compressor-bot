import os
import asyncio
import subprocess
import time
from threading import Thread
from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- 1. جزء السيرفر الوهمي (إجباري لموقع Render) ---
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is Running!"

def run_web():
    # ريندر بيحدد البورت تلقائياً في البيئة بتاعته
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host='0.0.0.0', port=port)

# --- 2. بياناتك الشخصية (محطوطة جاهزة) ---
API_ID = 36568697
API_HASH = "19cea3f85b81f15d7ac8578f3b2d85a2"
BOT_TOKEN = "8449601484:AAGUVzbRk0behaw1iQYna75qywYLAc_DyhM"

# إنشاء كائن البوت
app = Client(
    "render_pro_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

queue = []
is_processing = False

def humanbytes(size):
    if not size: return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024: return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"

async def progress_bar(current, total, message, start_time, action):
    now = time.time()
    diff = now - start_time
    if round(diff % 4) == 0 or current == total:
        percentage = current * 100 / total
        speed = current / diff if diff > 0 else 0
        eta = round((total - current) / speed) if speed > 0 else 0
        filled_length = int(percentage / 10)
        bar = '🔹' * filled_length + '🔸' * (10 - filled_length)
        status = (
            f"⚙️ **{action}**\n\n"
            f"📊 التقدم: {bar} {percentage:.1f}%\n"
            f"🚀 السرعة: {humanbytes(speed)}/s\n"
            f"⏱️ المتبقي: {eta} ثانية"
        )
        try: await message.edit_text(status)
        except: pass

async def process_queue():
    global is_processing
    if is_processing or not queue: return
    is_processing = True
    task = queue.pop(0)
    try:
        await start_conversion(task['client'], task['message'], task['mode'], task['orig_msg'])
    except Exception as e:
        print(f"Error: {e}")
    is_processing = False
    asyncio.create_task(process_queue())

async def start_conversion(client, status_msg, mode, orig_msg):
    start_time = time.time()
    msg_id, chat_id = orig_msg.id, orig_msg.chat.id
    file_path, output_path, thumb_path = "", "", ""

    try:
        await status_msg.edit_text("📥 **جاري التحميل من تيليجرام...**")
        file_path = await client.download_media(orig_msg, progress=progress_bar, progress_args=(status_msg, start_time, "📥 جاري التحميل"))

        ext = "mp3" if mode == "audio" else "mp4"
        output_path = f"final_{msg_id}.{ext}"
        thumb_path = f"thumb_{msg_id}.jpg"

        await status_msg.edit_text("⚒ **جاري المعالجة والضغط الآن...**")

        # أوامر FFmpeg فائقة السرعة
        if mode == "360p":
            cmd = f'ffmpeg -i "{file_path}" -vf "scale=-2:360" -vcodec libx264 -crf 28 -preset ultrafast -threads 0 -movflags +faststart "{output_path}"'
        elif mode == "240p":
            cmd = f'ffmpeg -i "{file_path}" -vf "scale=-2:240" -vcodec libx264 -crf 30 -preset ultrafast -threads 0 -movflags +faststart "{output_path}"'
        elif mode == "audio":
            cmd = f'ffmpeg -i "{file_path}" -vn -acodec libmp3lame -q:a 4 "{output_path}"'

        process = await asyncio.create_subprocess_shell(cmd)
        await process.communicate()

        if mode != "audio":
            subprocess.run(f'ffmpeg -i "{file_path}" -ss 00:00:02 -vframes 1 "{thumb_path}"', shell=True)

        old_size, new_size = os.path.getsize(file_path), os.path.getsize(output_path)
        saving = (1 - (new_size / old_size)) * 100
        caption = f"✅ **تم الضغط بنجاح!**\n\n📁 الحجم الأصلي: `{humanbytes(old_size)}`\n📦 الحجم الجديد: `{humanbytes(new_size)}`\n📉 وفرت لك: `{saving:.1f}%`"

        await status_msg.edit_text("📤 **جاري الرفع...**")
        if mode == "audio":
            await client.send_audio(chat_id, audio=output_path, caption=caption)
        else:
            await client.send_video(chat_id, video=output_path, caption=caption, thumb=thumb_path if os.path.exists(thumb_path) else None, supports_streaming=True, progress=progress_bar, progress_args=(status_msg, time.time(), "📤 جاري الرفع"))

    except Exception as e:
        await client.send_message(chat_id, f"❌ **خطأ:** `{e}`")
    finally:
        for f in [file_path, output_path, thumb_path]:
            if f and os.path.exists(f): os.remove(f)
        await status_msg.delete()

@app.on_message(filters.video | filters.document)
async def handle_video(client, message):
    if message.document and "video" not in message.document.mime_type: return
    await message.reply_text(
        "🎬 **بوت الضغط الاحترافي جاهز للعمل!**\nاختار الجودة المطلوبة للضغط:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎬 جودة 360p", callback_data=f"360p_{message.id}"),
             InlineKeyboardButton("📱 جودة 240p", callback_data=f"240p_{message.id}")],
            [InlineKeyboardButton("🎵 استخراج الصوت MP3", callback_data=f"audio_{message.id}")]
        ])
    )

@app.on_callback_query()
async def on_click(client, callback_query):
    data = callback_query.data.split("_")
    mode, msg_id = data[0], int(data[1])
    orig_msg = await client.get_messages(callback_query.message.chat.id, msg_id)
    queue.append({'client': client, 'message': callback_query.message, 'mode': mode, 'orig_msg': orig_msg})
    if is_processing:
        await callback_query.message.edit_text(f"⏳ أنت في الطابور.. ترتيبك: `{len(queue)}`")
    else:
        asyncio.create_task(process_queue())

# --- 3. تشغيل السيرفر والبوت معاً ---
if __name__ == "__main__":
    # تشغيل Flask في سطر منفصل (Thread)
    Thread(target=run_web).start()
    
    # تشغيل البوت
    print("🚀 البوت يعمل الآن!")
    app.run()
