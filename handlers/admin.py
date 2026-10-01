import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler
from permissions import is_super_admin
from state import (list_users, approve_user, ban_user, unban_user,
                   get_user, set_permission, get_audit_logs, log_action)

log = logging.getLogger(__name__)


def admin_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Users", callback_data="adm_users"),
         InlineKeyboardButton("⏳ Pending", callback_data="adm_pending")],
        [InlineKeyboardButton("🚫 Banned", callback_data="adm_banned"),
         InlineKeyboardButton("📊 Stats", callback_data="adm_stats")],
        [InlineKeyboardButton("📜 Audit", callback_data="adm_log")],
    ])


def user_actions_kb(uid):
    u = get_user(uid)
    if not u: return None
    p = u["permissions"]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"{'✅ Approved' if u['is_approved'] else '⏳ Approve'}",
            callback_data=f"adm_approve:{uid}")],
        [InlineKeyboardButton(
            "🎬 Generate — " + ("ON" if p.get("can_generate") else "OFF"),
            callback_data=f"adm_perm:{uid}:can_generate")],
        [InlineKeyboardButton("🚫 Ban", callback_data=f"adm_ban:{uid}"),
         InlineKeyboardButton("♻️ Unban", callback_data=f"adm_unban:{uid}")],
        [InlineKeyboardButton("◀️ Users", callback_data="adm_users")],
    ])


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_super_admin(update.effective_user.id):
        await update.message.reply_text("⛔")
        return
    await update.message.reply_text("👑 <b>Admin</b>", parse_mode="HTML",
                                    reply_markup=admin_kb())


async def id_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🆔 <code>{update.effective_user.id}</code>", parse_mode="HTML")


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    if not is_super_admin(uid):
        await q.answer("⛔", show_alert=True)
        return
    await q.answer()
    d = q.data

    try:
        if d == "adm_users":
            users = list_users("all")
            kb = []
            for u in users[:20]:
                tag = "✅" if u["is_approved"] else ("🚫" if u["is_banned"] else "⏳")
                n = u["first_name"] or u["username"] or str(u["user_id"])
                kb.append([InlineKeyboardButton(f"{tag} {n}",
                          callback_data=f"adm_view:{u['user_id']}")])
            kb.append([InlineKeyboardButton("◀️ Back", callback_data="adm_back")])
            await q.message.edit_text("👥 <b>Users</b>", parse_mode="HTML",
                                      reply_markup=InlineKeyboardMarkup(kb))
            return

        if d == "adm_pending":
            users = list_users("pending")
            kb = [[InlineKeyboardButton(f"⏳ {u['first_name'] or u['username'] or u['user_id']}",
                  callback_data=f"adm_view:{u['user_id']}")] for u in users[:20]]
            kb.append([InlineKeyboardButton("◀️ Back", callback_data="adm_back")])
            await q.message.edit_text(f"⏳ <b>Pending ({len(users)})</b>",
                                      parse_mode="HTML",
                                      reply_markup=InlineKeyboardMarkup(kb))
            return

        if d == "adm_banned":
            users = list_users("banned")
            kb = [[InlineKeyboardButton(f"🚫 {u['first_name'] or u['username'] or u['user_id']}",
                  callback_data=f"adm_view:{u['user_id']}")] for u in users[:20]]
            kb.append([InlineKeyboardButton("◀️ Back", callback_data="adm_back")])
            await q.message.edit_text(f"🚫 <b>Banned ({len(users)})</b>",
                                      parse_mode="HTML",
                                      reply_markup=InlineKeyboardMarkup(kb))
            return

        if d == "adm_stats":
            users = list_users("all")
            ap = sum(1 for u in users if u["is_approved"])
            bn = sum(1 for u in users if u["is_banned"])
            await q.message.edit_text(
                f"📊 Total — {len(users)}\n✅ Approved — {ap}\n"
                f"⏳ Pending — {len(users) - ap - bn}\n🚫 Banned — {bn}",
                reply_markup=admin_kb())
            return

        if d == "adm_log":
            rows = get_audit_logs(15)
            if not rows:
                await q.message.edit_text("📭 No log", reply_markup=admin_kb())
                return
            txt = "📜 <b>Recent</b>\n\n" + "\n".join(
                f"<code>{str(r['created_at'])[:16]}</code> — {r['actor_id']} {r['action']}"
                for r in rows)
            await q.message.edit_text(txt, parse_mode="HTML", reply_markup=admin_kb())
            return

        if d == "adm_back":
            await q.message.edit_text("👑 <b>Admin</b>", parse_mode="HTML",
                                      reply_markup=admin_kb())
            return

        if d.startswith("adm_view:"):
            t = int(d.split(":")[1])
            u = get_user(t)
            if not u:
                await q.answer("No user", show_alert=True)
                return
            p = u["permissions"]
            txt = (f"👤 <code>{t}</code>\n\n"
                   f"Name — {u['first_name'] or '-'}\n"
                   f"@{(u['username'] or '-')}\n"
                   f"Approved — {bool(u['is_approved'])}\n"
                   f"Banned — {bool(u['is_banned'])}\n\n"
                   f"🎬 Generate — {p.get('can_generate')}\n"
                   f"📅 Jobs/Day — {p.get('max_jobs_per_day', 10)}")
            await q.message.edit_text(txt, parse_mode="HTML",
                                      reply_markup=user_actions_kb(t))
            return

        if d.startswith("adm_approve:"):
            t = int(d.split(":")[1])
            approve_user(t); log_action(uid, "approve", t)
            await q.answer("✅")
            try: await q.message.edit_reply_markup(reply_markup=user_actions_kb(t))
            except Exception: pass
            try:
                await q.get_bot().send_message(t, "✅ <b>Approved!</b>\n\n/start နှိပ်ပါ",
                                               parse_mode="HTML")
            except Exception: pass
            return

        if d.startswith("adm_ban:"):
            t = int(d.split(":")[1])
            ban_user(t); log_action(uid, "ban", t)
            await q.answer("🚫")
            try: await q.message.edit_reply_markup(reply_markup=user_actions_kb(t))
            except Exception: pass
            return

        if d.startswith("adm_unban:"):
            t = int(d.split(":")[1])
            unban_user(t); log_action(uid, "unban", t)
            await q.answer("♻️")
            try: await q.message.edit_reply_markup(reply_markup=user_actions_kb(t))
            except Exception: pass
            return

        if d.startswith("adm_perm:"):
            _, t_s, key = d.split(":")
            t = int(t_s)
            u = get_user(t)
            cur = u["permissions"].get(key, False)
            set_permission(t, key, not cur)
            log_action(uid, "perm", t, f"{key}={not cur}")
            await q.answer("✅")
            try: await q.message.edit_reply_markup(reply_markup=user_actions_kb(t))
            except Exception: pass
            return

    except Exception as e:
        log.exception("admin callback")
        try: await q.answer(f"⚠️ {str(e)[:50]}", show_alert=True)
        except Exception: pass


def register_admin(app):
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("id", id_cmd))
