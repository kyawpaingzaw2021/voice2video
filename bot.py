"""
Voice → Video Bot — Main Entry
"""
import asyncio
import logging
import sys
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes

from config import BOT_TOKEN, TEMP_DIR, STORAGE_CHANNEL_ID, SUPER_ADMIN_ID
from state import init_db
from modules.cleanup import clean_dir
from handlers.admin import register_admin
from handlers.user import register_user_handlers

logging.basicConfig(
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
)
for n in ("httpx", "httpcore", "telegram.ext.Updater", "telegram.ext.Application",
          "moviepy", "PIL", "edge_tts"):
    logging.getLogger(n).setLevel(logging.WARNING)

log = logging.getLogger("v2v-bot")


def startup_checks():
    err = []
    if not BOT_TOKEN or BOT_TOKEN in ("REPLACE_WITH_YOUR_BOT_TOKEN", ""):
        err.append("❌ BOT_TOKEN မရှိ")
    if not SUPER_ADMIN_ID or SUPER_ADMIN_ID == 0:
        err.append("❌ SUPER_ADMIN_ID မရှိ")
    if err:
        for e in err:
            log.error(e)
        sys.exit(1)
    log.info(f"✅ Admin — {SUPER_ADMIN_ID}")
    log.info(f"✅ Channel — {STORAGE_CHANNEL_ID}")


async def post_init(app):
    log.info("=" * 55)
    log.info("🎬 Voice → Video Bot — Online")
    log.info("=" * 55)

    try:
        await app.bot.send_message(
            chat_id=SUPER_ADMIN_ID,
            text="🎬 <b>Voice → Video Bot Online</b>\n\n/admin\n/id",
            parse_mode="HTML")
    except Exception as e:
        log.warning(f"admin notify: {e}")

    try:
        from storage import verify_storage_channel
        r = await verify_storage_channel(app.bot)
        if r.get("ok"):
            log.info(f"✅ Channel — {r.get('title')} (Admin: {r.get('is_admin')})")
        else:
            log.warning(f"⚠️ Channel — {r.get('error')}")
    except Exception as e:
        log.warning(f"channel verify: {e}")


async def post_shutdown(app):
    log.info("🛑 Shutdown")


async def error_handler(update, context):
    err = context.error
    es = str(err).lower()
    if "message is not modified" in es or "query is too old" in es:
        return
    log.error(f"❌ {type(err).__name__}: {err}", exc_info=err)
    try:
        if isinstance(update, Update):
            cid = None
            if update.effective_chat:
                cid = update.effective_chat.id
            elif update.callback_query and update.callback_query.message:
                cid = update.callback_query.message.chat_id
            if cid:
                try:
                    await context.bot.send_message(cid, "⚠️ Error ဖြစ်သွားပါတယ်")
                except Exception:
                    pass
    except Exception:
        pass


def main():
    log.info("🎬 Voice → Video Bot — Starting")

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    startup_checks()
    init_db()
    clean_dir(TEMP_DIR)

    app = (ApplicationBuilder()
           .token(BOT_TOKEN)
           .concurrent_updates(True)
           .post_init(post_init)
           .post_shutdown(post_shutdown)
           .build())

    register_admin(app)
    register_user_handlers(app)
    app.add_error_handler(error_handler)

    log.info("🚀 Bot running...")
    app.run_polling(
        drop_pending_updates=True,
        allowed_updates=["message", "callback_query"],
        close_loop=False,
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("👋 Stopped")
    except Exception as e:
        log.exception(f"💥 {e}")
        sys.exit(1)
