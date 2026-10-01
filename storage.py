import os, asyncio, logging
from telegram import Bot
from telegram.error import TelegramError, TimedOut, NetworkError
from config import STORAGE_CHANNEL_ID, MAX_UPLOAD_MB

log = logging.getLogger(__name__)
MAX_RETRIES = 3
RETRY_DELAY = 5


async def upload_to_storage(bot, file_path, caption=""):
    if not STORAGE_CHANNEL_ID:
        return None, None

    fname = file_path.split("/")[-1]
    size_mb = os.path.getsize(file_path) / 1024 / 1024

    if size_mb > MAX_UPLOAD_MB:
        log.error(f"[storage] too large: {size_mb:.1f} MB")
        return None, None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with open(file_path, "rb") as f:
                msg = await bot.send_video(
                    chat_id=STORAGE_CHANNEL_ID,
                    video=f,
                    filename=fname,
                    caption=caption[:1024] if caption else None,
                    disable_notification=True,
                    supports_streaming=True,
                    read_timeout=900,
                    write_timeout=900,
                    connect_timeout=60,
                )
                return msg.video.file_id, msg.message_id
        except (TimedOut, NetworkError) as e:
            log.warning(f"[storage] {attempt} timeout: {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY * attempt)
        except TelegramError as e:
            log.error(f"[storage] {e}")
            return None, None
    return None, None


async def verify_storage_channel(bot):
    if not STORAGE_CHANNEL_ID:
        return {"ok": False, "error": "no channel"}
    try:
        chat = await bot.get_chat(STORAGE_CHANNEL_ID)
        me = await bot.get_me()
        m = await bot.get_chat_member(STORAGE_CHANNEL_ID, me.id)
        return {"ok": True, "title": chat.title, "id": chat.id,
                "is_admin": m.status in ("administrator", "creator")}
    except TelegramError as e:
        return {"ok": False, "error": str(e)}
