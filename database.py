"""SQLite layer for ALPHA X ACADEMY: schema, seed data, password hashing. Standard library only."""
import base64, hashlib, hmac, os, sqlite3
from contextlib import contextmanager
from datetime import date, datetime

DB_PATH = os.environ.get("AX_DB") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "alpha_x_academy.db")
ITERATIONS = 310_000

SCHEMA = """
CREATE TABLE IF NOT EXISTS courses(
 id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL UNIQUE,
 category TEXT NOT NULL CHECK(category IN('school','competitive')),
 class_or_exam TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
 is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN(0,1)), created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS enquiries(
 id INTEGER PRIMARY KEY AUTOINCREMENT, student_name TEXT NOT NULL, guardian_name TEXT NOT NULL,
 class_or_exam TEXT NOT NULL, phone TEXT NOT NULL, email TEXT, message TEXT,
 status TEXT NOT NULL DEFAULT 'New' CHECK(status IN('New','Contacted','Admitted','Closed')),
 created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_enq_created ON enquiries(created_at);
CREATE TABLE IF NOT EXISTS admin_users(
 id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE,
 password_hash TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS admin_sessions(
 token_hash TEXT PRIMARY KEY, admin_id INTEGER NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
 csrf TEXT NOT NULL, expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS site_content(key TEXT PRIMARY KEY, value TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS sessions(
 visitor_id TEXT PRIMARY KEY, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS page_views(
 id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT NOT NULL, visitor_id TEXT, day TEXT NOT NULL, viewed_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS ix_pv_day ON page_views(day);
"""

CATALOG = [(f"Class {c} Tuition", "school", f"Class {c}", f"Tuition for Class {c}.") for c in range(6, 11)] + [
    ("Class 11 Science", "school", "Class 11", "Science stream only."),
    ("Class 12 Science", "school", "Class 12", "Science stream only."),
    ("Railway Clerk", "competitive", "Railway Clerk", "Structured preparation for Railway Clerk examinations. Selection is not guaranteed."),
    ("Police Recruitment", "competitive", "Police", "Structured preparation for police recruitment examinations. Selection is not guaranteed."),
    ("Army Recruitment", "competitive", "Army", "Structured preparation for army recruitment examinations. Selection is not guaranteed."),
    ("Patwari Exam", "competitive", "Patwari", "Structured preparation for the Patwari examination. Selection is not guaranteed."),
]
CONTENT_DEFAULTS = {
    "announcement": "",
    "hero_title": "Learn smarter. Aim higher.",
    "hero_subtitle": "School tuition for Classes 6–12 and competitive exam preparation on the Ambala–Chandigarh Highway.",
    "about_text": "ALPHA X ACADEMY offers school tuition for Classes 6 to 12 (Science stream for Classes 11 and 12) and preparation for Railway Clerk, Police, Army and Patwari examinations.",
    "address": "Ambala–Chandigarh Highway, below Peter's Gym",
    "opening_hours": "10:00 AM – 7:00 PM",
    "phone": "", "email": "",
}


def now():
    return datetime.now().isoformat(timespec="seconds")


def today():
    return date.today().isoformat()


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def init_db():
    """Create the database file, tables and starter content if missing (safe to call repeatedly)."""
    with conn() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript(SCHEMA)
        if not c.execute("SELECT 1 FROM courses LIMIT 1").fetchone():
            c.executemany("INSERT INTO courses(title,category,class_or_exam,description,created_at) VALUES(?,?,?,?,?)",
                          [(*x, now()) for x in CATALOG])
        c.executemany("INSERT OR IGNORE INTO site_content(key,value) VALUES(?,?)", list(CONTENT_DEFAULTS.items()))


def hash_password(pw, salt=None, iterations=ITERATIONS):
    salt = salt or os.urandom(16)
    d = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(d).decode()}"


def verify_password(pw, stored):
    try:
        _, it, s, h = stored.split("$")
        d = hashlib.pbkdf2_hmac("sha256", pw.encode(), base64.b64decode(s), int(it))
        return hmac.compare_digest(d, base64.b64decode(h))
    except Exception:
        return False


DUMMY = hash_password("not-a-real-password")  # used to equalise timing for unknown usernames


def create_admin(username, password):
    with conn() as c:
        c.execute("INSERT INTO admin_users(username,password_hash,created_at) VALUES(?,?,?)",
                  (username, hash_password(password), now()))


def set_admin_password(username, password):
    with conn() as c:
        c.execute("UPDATE admin_users SET password_hash=? WHERE username=?", (hash_password(password), username))
        c.execute("DELETE FROM admin_sessions WHERE admin_id=(SELECT id FROM admin_users WHERE username=?)", (username,))
