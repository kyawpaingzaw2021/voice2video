import sqlite3, json, os
from contextlib import contextmanager
from datetime import date
from config import DB_PATH, DEFAULT_PERMISSIONS

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            is_approved INTEGER DEFAULT 0,
            is_banned INTEGER DEFAULT 0,
            permissions TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT,
            episode TEXT,
            duration REAL,
            file_id TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS daily_usage (
            user_id INTEGER, date TEXT, jobs_count INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, date)
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_id INTEGER, action TEXT, target_id INTEGER,
            detail TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)


def get_user(uid):
    with db() as c:
        r = c.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
        if not r: return None
        d = dict(r)
        d["permissions"] = json.loads(d["permissions"]) if d["permissions"] else dict(DEFAULT_PERMISSIONS)
        return d


def upsert_user(uid, username=None, first_name=None):
    with db() as c:
        e = c.execute("SELECT user_id FROM users WHERE user_id=?", (uid,)).fetchone()
        if e:
            c.execute("UPDATE users SET username=?, first_name=?, last_seen=CURRENT_TIMESTAMP WHERE user_id=?",
                      (username, first_name, uid))
        else:
            c.execute("INSERT INTO users (user_id, username, first_name, permissions, last_seen) VALUES (?,?,?,?,CURRENT_TIMESTAMP)",
                      (uid, username, first_name, json.dumps(DEFAULT_PERMISSIONS)))


def approve_user(uid):
    with db() as c: c.execute("UPDATE users SET is_approved=1 WHERE user_id=?", (uid,))

def ban_user(uid):
    with db() as c: c.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (uid,))

def unban_user(uid):
    with db() as c: c.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (uid,))


def list_users(status="all"):
    with db() as c:
        q = {"approved": "WHERE is_approved=1 AND is_banned=0",
             "pending": "WHERE is_approved=0 AND is_banned=0",
             "banned": "WHERE is_banned=1"}.get(status, "")
        return [dict(r) for r in c.execute(f"SELECT * FROM users {q} ORDER BY last_seen DESC").fetchall()]


def set_permission(uid, key, val):
    u = get_user(uid)
    if not u: return False
    p = u["permissions"]; p[key] = val
    with db() as c:
        c.execute("UPDATE users SET permissions=? WHERE user_id=?", (json.dumps(p), uid))
    return True


def increment_daily(uid):
    today = date.today().isoformat()
    with db() as c:
        c.execute("""INSERT INTO daily_usage (user_id, date, jobs_count) VALUES (?,?,1)
                     ON CONFLICT(user_id, date) DO UPDATE SET jobs_count = jobs_count + 1""",
                  (uid, today))


def get_daily_count(uid):
    today = date.today().isoformat()
    with db() as c:
        r = c.execute("SELECT jobs_count FROM daily_usage WHERE user_id=? AND date=?",
                      (uid, today)).fetchone()
        return r["jobs_count"] if r else 0


def create_job(uid, title, episode, duration, file_id):
    with db() as c:
        cur = c.execute("INSERT INTO jobs (user_id, title, episode, duration, file_id, status) VALUES (?,?,?,?,?,'done')",
                        (uid, title, episode, duration, file_id))
        return cur.lastrowid


def list_active_jobs(uid):
    with db() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM jobs WHERE user_id=? ORDER BY id DESC LIMIT 10", (uid,)
        ).fetchall()]


def log_action(actor, action, target=None, detail=""):
    with db() as c:
        c.execute("INSERT INTO audit_log (actor_id, action, target_id, detail) VALUES (?,?,?,?)",
                  (actor, action, target, detail))


def get_audit_logs(limit=15):
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]
