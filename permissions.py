from config import SUPER_ADMIN_ID, DEFAULT_PERMISSIONS
from state import get_user, get_daily_count, upsert_user


def is_super_admin(uid):
    return uid == SUPER_ADMIN_ID


def is_approved(uid):
    if is_super_admin(uid):
        return True
    u = get_user(uid)
    return bool(u and u["is_approved"] and not u["is_banned"])


def is_banned(uid):
    u = get_user(uid)
    return bool(u and u["is_banned"])


def check_quota(uid):
    if is_super_admin(uid):
        return True, ""
    u = get_user(uid)
    if not u:
        return False, "User မရှိပါ"
    mx = u["permissions"].get("max_jobs_per_day", 10)
    used = get_daily_count(uid)
    if used >= mx:
        return False, f"ယနေ့ {mx} ကြိမ် ပြည့်ပါပြီ"
    return True, ""


def can(uid, key):
    if is_super_admin(uid):
        return True
    u = get_user(uid)
    return bool(u and u["permissions"].get(key))


def register_user(user):
    upsert_user(user.id, user.username, user.first_name)
