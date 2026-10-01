"""
User Flow: MP3 → Title → Episode → Split/Single → Video
"""
import os
import time
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler,
)
from telegram.constants import ChatAction

from permissions import is_approved, is_banned, register_user, check_quota, is_super_admin
from state import increment_daily, create_job
from config import (
    TEMP_DIR, MAX_DURATION_SEC, MAX_UPLOAD_MB,
    PROMO_CUSTOM, STORAGE_CHANNEL_ID, PART_DURATION_SEC,
)
from modules.cleanup import clean_dir
from modules.video_maker import build_video, get_audio_duration, split_audio
from storage import upload_to_storage

log = logging.getLogger(__name__)

SESSIONS = {}
AUDIO_EXTS = (".mp3", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".flac")


def get_session(uid):
    return SESSIONS.setdefault(uid, {})


def main_kb(uid):
    kb = [[InlineKeyboardButton("📖 Help", callback_data="help")]]
    if is_super_admin(uid):
        kb.insert(0, [InlineKeyboardButton("📸 Upload Promo Photo", callback_data="adm_promo")])
    return InlineKeyboardMarkup(kb)


# ============================================================
# /start
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    register_user(u)

    if is_banned(u.id):
        await update.message.reply_text("🚫 သင့်ကို ban ထားပါသည်")
        return
    if not is_approved(u.id):
        await update.message.reply_text(
            f"⏳ <b>Approval စောင့်နေသည်</b>\n\nID — <code>{u.id}</code>",
            parse_mode="HTML")
        return

    await update.message.reply_text(
        f"🎬 <b>Voice → Video Bot</b>\n\n"
        f"📤 MP3 File ပို့ပါ။\n"
        f"Bot က Photo + Title + Episode နဲ့ 720p Video ဖန်တီးပေးမည်။\n\n"
        f"• 📦 Split Mode — 15-min Parts (YouTube အတွက်)\n"
        f"• 🎬 Single Mode — Video တစ်ခုတည်း\n"
        f"• Max Duration — <code>60 min</code>\n"
        f"• Max Size — <code>50 MB</code>",
        parse_mode="HTML",
        reply_markup=main_kb(u.id))


# ============================================================
# MP3 Handler
# ============================================================
async def on_mp3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    register_user(u)
    if is_banned(u.id) or not is_approved(u.id):
        return

    msg = update.message
    audio = msg.audio or msg.voice or msg.document
    if not audio:
        return

    if msg.document:
        fname = msg.document.file_name or ""
        ext = os.path.splitext(fname)[1].lower()
        if ext not in AUDIO_EXTS:
            await msg.reply_text(
                f"⚠️ Audio Format မမှန်ပါ\nလက်ခံသည် — {', '.join(AUDIO_EXTS)}")
            return

    file_id = audio.file_id
    fname = getattr(audio, "file_name", None) or "audio"
    size_mb = (getattr(audio, "file_size", 0) or 0) / 1024 / 1024

    if size_mb > 200:
        await msg.reply_text(f"⚠️ File ကြီးလွန်းသည် ({size_mb:.0f} MB)")
        return

    s = get_session(u.id)
    s["audio_file_id"] = file_id
    s["audio_name"] = fname
    s["audio_size_mb"] = size_mb
    s["state"] = "waiting_title"
    s.pop("title", None)
    s.pop("episode", None)
    s.pop("split_mode", None)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Set Title + Episode", callback_data="set_title")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
    ])

    await msg.reply_text(
        f"🎵 <b>Audio လက်ခံပြီ</b>\n\n"
        f"📁 <code>{fname}</code>\n"
        f"📦 <code>{size_mb:.1f} MB</code>\n\n"
        f"📖 Title + 🎬 Episode ထည့်ရန် အောက်က Button နှိပ်ပါ",
        parse_mode="HTML",
        reply_markup=kb)


# ============================================================
# Text Handler
# ============================================================
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    register_user(u)
    if is_banned(u.id) or not is_approved(u.id):
        return

    s = get_session(u.id)
    state = s.get("state")
    text = update.message.text.strip()

    if state == "waiting_title":
        if not (2 <= len(text) <= 100):
            await update.message.reply_text("⚠️ Title 2-100 characters")
            return
        s["title"] = text
        s["state"] = "waiting_episode"
        await update.message.reply_text(
            f"✅ Title — <b>{text}</b>\n\n"
            f"🎬 Episode နံပါတ် ရိုက်ပါ (ဥပမာ — <code>1</code>)",
            parse_mode="HTML")
        return

    if state == "waiting_episode":
        clean = text.replace(" ", "").replace("-", "")
        if len(clean) > 20 or not clean.isalnum():
            await update.message.reply_text("⚠️ Episode — နံပါတ်/စာလုံး (20 char အောက်)")
            return
        s["episode"] = text
        s["state"] = "choose_mode"

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 Split 15-min Parts", callback_data="mode_split")],
            [InlineKeyboardButton("🎬 Single Video", callback_data="mode_single")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
        ])
        await update.message.reply_text(
            f"✅ <b>Title + Episode ရပြီ</b>\n\n"
            f"📖 {s['title']}\n"
            f"🎬 Episode {text}\n\n"
            f"🎯 <b>Video Mode ရွေးပါ</b>\n\n"
            f"📦 <b>Split 15-min</b> — Part 1, 2, 3... (YouTube 15 min limit)\n"
            f"🎬 <b>Single</b> — Video တစ်ခုတည်း",
            parse_mode="HTML",
            reply_markup=kb)
        return


# ============================================================
# Callback Router
# ============================================================
async def user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    u = q.from_user
    register_user(u)

    if not is_approved(u.id):
        await q.answer("⏳", show_alert=True)
        return

    if q.data.startswith("adm_"):
        return

    await q.answer()
    s = get_session(u.id)
    data = q.data

    try:
        if data == "help":
            await q.message.edit_text(
                f"📖 <b>Help</b>\n\n"
                f"1. MP3 File ကို Bot ဆီ ပို့ပါ\n"
                f"2. <b>📝 Set Title + Episode</b> နှိပ်ပါ\n"
                f"3. Title ရိုက်ပါ\n"
                f"4. Episode ရိုက်ပါ\n"
                f"5. Mode ရွေးပါ (Split / Single)\n"
                f"6. Video Generate ပါ\n\n"
                f"⏱️ Max — 60 min | 📦 Max — 50 MB",
                parse_mode="HTML")
            return

        if data == "set_title":
            if not s.get("audio_file_id"):
                await q.answer("⚠️ MP3 ပြန်ပို့ပါ", show_alert=True)
                return
            s["state"] = "waiting_title"
            await q.message.edit_text(
                "📖 <b>Title ရိုက်ထည့်ပါ</b>\n\n"
                "ဥပမာ — <code>ရန်ကြွေးသစ္စာ</code>",
                parse_mode="HTML")
            return

        if data == "cancel":
            SESSIONS.pop(u.id, None)
            await q.message.edit_text("❌ Cancel လုပ်လိုက်သည်")
            return

        if data in ("mode_split", "mode_single"):
            if not s.get("audio_file_id") or not s.get("title"):
                await q.answer("⚠️ Data မပြည့်ပါ", show_alert=True)
                return

            ok, msg = check_quota(u.id)
            if not ok:
                await q.answer(f"⚠️ {msg}", show_alert=True)
                return

            if not os.path.exists(PROMO_CUSTOM):
                await q.message.edit_text("⚠️ Promo Photo မရှိပါ")
                return

            s["split_mode"] = (data == "mode_split")
            increment_daily(u.id)

            mode_text = "📦 Split 15-min Parts" if s["split_mode"] else "🎬 Single Video"
            await q.message.edit_text(
                f"🚀 <b>Video စတင်နေသည်</b>\n\n"
                f"📖 {s['title']}\n"
                f"🎬 Episode {s['episode']}\n"
                f"🎯 {mode_text}\n\n"
                f"⏳ ခန့်မှန်း — 10-25 မိနစ်",
                parse_mode="HTML")

            asyncio.create_task(_build_job(context.bot, u.id, dict(s)))
            return

    except Exception as e:
        log.exception("callback")
        try:
            await q.answer(f"⚠️ {str(e)[:50]}", show_alert=True)
        except Exception:
            pass


# ============================================================
# Channel Link
# ============================================================
def _channel_link(msg_id):
    cid = str(STORAGE_CHANNEL_ID).lstrip("-")
    if cid.startswith("100"):
        cid = cid[3:]
    return f"https://t.me/c/{cid}/{msg_id}"


# ============================================================
# Video Build Job
# ============================================================
async def _build_job(bot, uid, session):
    job_dir = os.path.join(TEMP_DIR, f"job_{uid}_{int(time.time())}")
    clean_dir(job_dir)

    try:
        await bot.send_chat_action(uid, ChatAction.TYPING)

        audio_path = os.path.join(job_dir, "audio.bin")
        tg_file = await bot.get_file(session["audio_file_id"], read_timeout=600)
        await tg_file.download_to_drive(
            custom_path=audio_path,
            read_timeout=600, write_timeout=600)

        if not os.path.exists(audio_path) or os.path.getsize(audio_path) < 1000:
            await bot.send_message(uid, "❌ Audio File မမှန်ပါ")
            return

        try:
            duration = get_audio_duration(audio_path)
        except Exception:
            log.exception("audio read fail")
            await bot.send_message(uid, "❌ Audio ဖတ်လို့မရပါ")
            return

        title = session["title"]
        episode = session.get("episode", "")
        split_mode = session.get("split_mode", False)

        videos = []

        if split_mode and duration > PART_DURATION_SEC:
            await bot.send_message(uid,
                f"📦 <b>15-min Parts ခွဲနေသည်...</b>\n\n⏱️ {duration / 60:.1f} min",
                parse_mode="HTML")

            parts_dir = os.path.join(job_dir, "parts")
            parts = split_audio(audio_path, PART_DURATION_SEC, parts_dir)

            if not parts:
                await bot.send_message(uid, "❌ Split Fail")
                return

            await bot.send_message(uid,
                f"✅ Parts — <b>{len(parts)}</b> ခု\n\n🎬 Video ဖန်တီးစတင်နေသည်...",
                parse_mode="HTML")

            for i, part_path in enumerate(parts, 1):
                out_path = os.path.join(job_dir, f"part_{i:02d}.mp4")

                await bot.send_message(uid,
                    f"🎬 <b>Part {i}/{len(parts)}</b> ဖန်တီးနေသည်...",
                    parse_mode="HTML")

                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, lambda p=part_path, o=out_path:
                    build_video(
                        photo_path=PROMO_CUSTOM,
                        audio_path=p,
                        out_path=o,
                        title=title,
                        episode=f"{episode} · Part {i}",
                        work_dir=job_dir))

                part_dur = get_audio_duration(part_path)
                part_mb = os.path.getsize(out_path) / 1024 / 1024
                videos.append({
                    "path": out_path,
                    "title": f"{title} — Episode {episode} · Part {i}",
                    "duration": part_dur,
                    "size_mb": part_mb,
                    "part": i,
                })
        else:
            if duration > MAX_DURATION_SEC:
                await bot.send_message(uid,
                    f"❌ Audio ရှည်လွန်းသည် ({duration / 60:.1f} min)")
                return

            out_path = os.path.join(job_dir, "final.mp4")
            await bot.send_message(uid,
                f"🎬 <b>Video Build နေသည်...</b>\n\n⏱️ {duration / 60:.1f} min",
                parse_mode="HTML")

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: build_video(
                photo_path=PROMO_CUSTOM,
                audio_path=audio_path,
                out_path=out_path,
                title=title,
                episode=episode,
                work_dir=job_dir))

            videos = [{
                "path": out_path,
                "title": f"{title} — Episode {episode}",
                "duration": duration,
                "size_mb": os.path.getsize(out_path) / 1024 / 1024,
                "part": 1,
            }]

        results = []
        for v in videos:
            if v["size_mb"] > MAX_UPLOAD_MB:
                results.append({**v, "error": f"{v['size_mb']:.1f} MB > {MAX_UPLOAD_MB} MB"})
                continue

            await bot.send_message(uid,
                f"📤 <b>Upload — Part {v['part']}</b>\n📦 {v['size_mb']:.1f} MB",
                parse_mode="HTML")

            file_id, msg_id = await upload_to_storage(
                bot, v["path"], caption=v["title"])

            if file_id:
                create_job(uid, v["title"], episode, v["duration"], file_id)
                link = _channel_link(msg_id) if msg_id else "—"
                results.append({**v, "file_id": file_id, "link": link})
            else:
                results.append({**v, "error": "Upload Fail"})

        summary = [f"✅ <b>{len([r for r in results if not r.get('error')])}/{len(results)} Video ပြီးပါပြီ</b>\n"]
        for r in results:
            if r.get("error"):
                summary.append(f"❌ <b>Part {r['part']}</b> — {r['error']}")
            else:
                summary.append(
                    f"🎬 <b>Part {r['part']}</b> — {r['size_mb']:.1f} MB\n"
                    f"   🔗 {r['link']}")

        summary.append(f"\n📖 {title} · Episode {episode}")
        await bot.send_message(uid, "\n".join(summary),
            parse_mode="HTML", disable_web_page_preview=True)

        SESSIONS.pop(uid, None)

    except Exception as e:
        log.exception("build job fail")
        try:
            await bot.send_message(uid, f"❌ Error — {str(e)[:200]}")
        except Exception:
            pass
    finally:
        clean_dir(job_dir)


# ============================================================
# /cancel
# ============================================================
async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    SESSIONS.pop(update.effective_user.id, None)
    await update.message.reply_text("❌ Cancel")


# ============================================================
# Photo — Admin Promo Upload
# ============================================================
async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    register_user(u)
    if not is_super_admin(u.id):
        return

    s = get_session(u.id)
    if s.get("state") != "waiting_promo":
        return

    msg = update.message
    photo_obj = None
    if msg.photo:
        photo_obj = msg.photo[-1]
    elif msg.document and (msg.document.mime_type or "").startswith("image/"):
        photo_obj = msg.document

    if not photo_obj:
        return

    status = await msg.reply_text("📥 Photo Save နေသည်...")
    try:
        os.makedirs(os.path.dirname(PROMO_CUSTOM), exist_ok=True)
        tg_file = await photo_obj.get_file()
        tmp = PROMO_CUSTOM + ".tmp"
        await tg_file.download_to_drive(custom_path=tmp)

        from PIL import Image
        img = Image.open(tmp).convert("RGB")
        iw, ih = img.size
        scale = max(1920 / iw, 1080 / ih)
        img = img.resize((int(iw * scale), int(ih * scale)), Image.LANCZOS)
        iw, ih = img.size
        left = (iw - 1920) // 2
        top = (ih - 1080) // 2
        img = img.crop((left, top, left + 1920, top + 1080))
        img.save(PROMO_CUSTOM, quality=95, optimize=True, subsampling=0)

        try:
            os.remove(tmp)
        except Exception:
            pass

        s.pop("state", None)
        await status.edit_text(
            f"✅ <b>Promo Photo Save ပြီ</b>\n\n📁 <code>{PROMO_CUSTOM}</code>",
            parse_mode="HTML")
    except Exception as e:
        log.exception("promo upload")
        await status.edit_text(f"❌ Error — {str(e)[:150]}")


# ============================================================
# Admin Promo callback
# ============================================================
async def adm_promo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    u = q.from_user
    register_user(u)

    if not is_super_admin(u.id):
        await q.answer("⛔", show_alert=True)
        return
    await q.answer()

    s = get_session(u.id)
    s["state"] = "waiting_promo"
    await q.message.edit_text(
        "📸 <b>Promo Photo Upload</b>\n\n"
        "Photo တစ်ပုံ ပို့ပါ — Auto 1920×1080 Crop လုပ်မည်။\n\n"
        "ရပ်ရန် /cancel",
        parse_mode="HTML")


# ============================================================
# Register
# ============================================================
def register_user_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel_cmd))

    from handlers.admin import admin_callback
    app.add_handler(CallbackQueryHandler(adm_promo_callback, pattern=r"^adm_promo$"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern=r"^adm_(?!promo)"))

    app.add_handler(CallbackQueryHandler(user_callback))

    app.add_handler(MessageHandler(
        filters.AUDIO | filters.VOICE | filters.Document.AUDIO |
        filters.Document.FileExtension("mp3") |
        filters.Document.FileExtension("m4a") |
        filters.Document.FileExtension("opus"),
        on_mp3))

    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, on_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
