"""ALPHA X ACADEMY web server (Python standard library only).  Run:  python server.py"""
import hashlib, hmac, json, mimetypes, os, re, secrets, threading, time
from datetime import date, datetime, timedelta
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse
import database as db

BASE = os.path.dirname(os.path.abspath(__file__))
STATIC, TPL = os.path.realpath(os.path.join(BASE, "static")), os.path.join(BASE, "templates")
SECURE = os.environ.get("AX_SECURE_COOKIES") == "1"  # set to 1 when served over HTTPS
SESSION_HOURS = 8
STATUSES = ("New", "Contacted", "Admitted", "Closed")
CSP = "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
MIME = {".js": "application/javascript", ".css": "text/css", ".html": "text/html", ".svg": "image/svg+xml",
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".ico": "image/x-icon"}
CONTENT_KEYS = {"announcement": 300, "hero_title": 120, "hero_subtitle": 300, "about_text": 1200,
                "address": 200, "opening_hours": 100, "phone": 30, "email": 120}
CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
hits, lock = {}, threading.Lock()


def exceeded(key, limit, window):
    now = time.time()
    with lock:
        hits[key] = [t for t in hits.get(key, []) if now - t < window]
        return len(hits[key]) >= limit


def record(key):
    with lock:
        hits.setdefault(key, []).append(time.time())


def clean(v):
    return CTRL.sub("", str(v if v is not None else "")).strip()


def sha(t):
    return hashlib.sha256(t.encode()).hexdigest()


def cookie_str(name, val, max_age, samesite="Strict"):
    s = f"{name}={val}; Path=/; HttpOnly; SameSite={samesite}; Max-Age={max_age}"
    return s + "; Secure" if SECURE else s


class Handler(BaseHTTPRequestHandler):
    server_version = "AlphaX"

    def log_message(self, fmt, *a):  # log method + path only (no query strings, no personal data)
        print(self.command, self.path.split("?")[0])

    # ---------- response helpers ----------
    def send(self, status, body=b"", ctype="text/plain; charset=utf-8", extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Cache-Control", "no-store" if ctype.startswith("application/json") else "no-cache")
        for k, v in extra or []:
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def js(self, status, obj, extra=None):
        self.send(status, json.dumps(obj).encode(), "application/json; charset=utf-8", extra)

    def err(self, status, msg, details=None):
        self.js(status, {"error": msg, "details": details})

    def file(self, full):
        ct = MIME.get(os.path.splitext(full)[1].lower()) or mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ct.startswith("text/") or ct == "application/javascript":
            ct += "; charset=utf-8"
        with open(full, "rb") as f:
            self.send(200, f.read(), ct)

    def cookie(self, name):
        try:
            m = SimpleCookie(self.headers.get("Cookie", "")).get(name)
            return m.value if m else None
        except Exception:
            return None

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not 0 < n <= 32768 or "application/json" not in self.headers.get("Content-Type", ""):
            return None
        try:
            d = json.loads(self.rfile.read(n))
            return d if isinstance(d, dict) else None
        except ValueError:
            return None

    def admin(self):
        t = self.cookie("axsid")
        if not t:
            return None
        with db.conn() as c:
            r = c.execute("SELECT s.admin_id,s.csrf,s.expires_at,u.username FROM admin_sessions s "
                          "JOIN admin_users u ON u.id=s.admin_id WHERE s.token_hash=?", (sha(t),)).fetchone()
            if r and r["expires_at"] < db.now():
                c.execute("DELETE FROM admin_sessions WHERE token_hash=?", (sha(t),))
                return None
        return r

    # ---------- routing ----------
    def route(self):
        u = urlparse(self.path)
        p, q, m = unquote(u.path), parse_qs(u.query), self.command
        try:
            if m in ("POST", "PATCH", "PUT", "DELETE"):
                o = self.headers.get("Origin")
                if o and urlparse(o).netloc != self.headers.get("Host"):
                    return self.err(403, "Cross-origin request blocked.")
            if p.startswith("/api/"):
                return self.api(m, p[5:].strip("/").split("/"), q)
            if m not in ("GET", "HEAD"):
                return self.err(405, "Method not allowed.")
            return self.page(p)
        except Exception as e:
            print("ERROR", type(e).__name__, e)
            self.err(500, "Server error.")

    do_GET = do_POST = do_PATCH = do_PUT = do_DELETE = do_HEAD = route

    def page(self, p):
        pages = {"/": "index.html", "/index.html": "index.html", "/admin/login": "admin-login.html"}
        if p == "/admin":
            if not self.admin():
                return self.send(302, b"", extra=[("Location", "/admin/login")])
            return self.file(os.path.join(TPL, "admin-dashboard.html"))
        if p in pages:
            return self.file(os.path.join(TPL, pages[p]))
        if p.startswith("/static/") and "\x00" not in p:
            full = os.path.realpath(os.path.join(STATIC, p[8:]))
            if full.startswith(STATIC + os.sep) and os.path.isfile(full):
                return self.file(full)
        self.send(404, b"Not found")

    def api(self, m, r, q):
        if r == ["courses"] and m == "GET":
            with db.conn() as c:
                rows = c.execute("SELECT id,title,category,class_or_exam,description FROM courses WHERE is_active=1 "
                                 "ORDER BY CASE category WHEN 'school' THEN 0 ELSE 1 END,id").fetchall()
            return self.js(200, [dict(x) for x in rows])
        if r == ["content"] and m == "GET":
            with db.conn() as c:
                return self.js(200, {x["key"]: x["value"] for x in c.execute("SELECT key,value FROM site_content")})
        if r == ["enquiries"] and m == "POST":
            return self.new_enquiry()
        if r == ["pageview"] and m == "POST":
            return self.pageview()
        if r[0] == "admin":
            return self.admin_api(m, r[1:], q)
        self.err(404, "Not found.")

    # ---------- public endpoints ----------
    def new_enquiry(self):
        ip = self.client_address[0]
        if exceeded("enq:" + ip, 5, 600):
            return self.err(429, "Too many enquiries. Please try again later.")
        d = self.body()
        if d is None:
            return self.err(400, "JSON body required.")
        name, guard, cls = clean(d.get("student_name")), clean(d.get("guardian_name")), clean(d.get("class_or_exam"))
        phone, email, msg = re.sub(r"[\s\-()]", "", clean(d.get("phone"))), clean(d.get("email")), clean(d.get("message"))
        e = {}
        if not 2 <= len(name) <= 100: e["student_name"] = "Enter the student's name (2-100 characters)."
        if not 2 <= len(guard) <= 100: e["guardian_name"] = "Enter the parent or guardian's name."
        if not re.fullmatch(r"\+?\d{10,13}", phone): e["phone"] = "Enter a valid phone number (10-13 digits)."
        if email and not (len(email) <= 254 and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)): e["email"] = "Enter a valid email or leave it blank."
        if len(msg) > 1000: e["message"] = "Message is too long (max 1000 characters)."
        with db.conn() as c:
            if not c.execute("SELECT 1 FROM courses WHERE title=? AND is_active=1", (cls,)).fetchone():
                e["class_or_exam"] = "Please choose an available class or exam."
            if e:
                return self.err(422, "Please correct the highlighted fields.", e)
            since = (datetime.now() - timedelta(minutes=10)).isoformat(timespec="seconds")
            dup = c.execute("SELECT id FROM enquiries WHERE phone=? AND class_or_exam=? AND created_at>?", (phone, cls, since)).fetchone()
            if dup:
                return self.js(200, {"ok": True, "id": dup["id"], "duplicate": True})
            cur = c.execute("INSERT INTO enquiries(student_name,guardian_name,class_or_exam,phone,email,message,created_at) "
                            "VALUES(?,?,?,?,?,?,?)", (name, guard, cls, phone, email or None, msg or None, db.now()))
        record("enq:" + ip)
        self.js(201, {"ok": True, "id": cur.lastrowid})

    def pageview(self):
        ip = self.client_address[0]
        d = self.body()
        path = clean(d.get("path")) if d else ""
        if exceeded("pv:" + ip, 60, 60) or not re.fullmatch(r"/[A-Za-z0-9/_\-.]{0,100}", path) \
                or re.search(r"bot|spider|crawl", self.headers.get("User-Agent", "").lower()):
            return self.send(204)
        vid, extra = self.cookie("axv"), []
        if not vid or not re.fullmatch(r"[A-Za-z0-9_\-]{20,64}", vid):
            vid = secrets.token_urlsafe(24)
            extra = [("Set-Cookie", cookie_str("axv", vid, 180 * 86400, "Lax"))]
        n = db.now()
        with db.conn() as c:
            c.execute("INSERT INTO sessions VALUES(?,?,?) ON CONFLICT(visitor_id) DO UPDATE SET last_seen=excluded.last_seen", (vid, n, n))
            c.execute("INSERT INTO page_views(path,visitor_id,day,viewed_at) VALUES(?,?,?,?)", (path, vid, db.today(), n))
        record("pv:" + ip)
        self.send(204, extra=extra)

    # ---------- admin endpoints ----------
    def admin_api(self, m, r, q):
        if r == ["login"] and m == "POST":
            return self.login()
        a = self.admin()
        if not a:
            return self.err(401, "Login required.")
        if m != "GET" and not hmac.compare_digest(self.headers.get("X-CSRF-Token", ""), a["csrf"]):
            return self.err(403, "Invalid CSRF token.")
        if r == ["me"] and m == "GET":
            return self.js(200, {"username": a["username"], "csrf": a["csrf"]})
        if r == ["logout"] and m == "POST":
            with db.conn() as c:
                c.execute("DELETE FROM admin_sessions WHERE token_hash=?", (sha(self.cookie("axsid")),))
            return self.js(200, {"ok": True}, [("Set-Cookie", cookie_str("axsid", "", 0))])
        if r == ["stats"] and m == "GET":
            return self.stats()
        if r == ["enquiries"] and m == "GET":
            return self.list_enquiries(q)
        if len(r) == 2 and r[0] in ("enquiries", "courses") and r[1].isdigit():
            return self.item(m, r[0], int(r[1]))
        if r == ["courses"]:
            return self.courses(m)
        if r == ["content"]:
            return self.content(m)
        self.err(404, "Not found.")

    def login(self):
        key = "login:" + self.client_address[0]
        if exceeded(key, 5, 900):
            return self.err(429, "Too many failed attempts. Try again in 15 minutes.")
        d = self.body()
        if d is None:
            return self.err(400, "JSON body required.")
        u, pw = str(d.get("username", ""))[:60], str(d.get("password", ""))[:200]
        with db.conn() as c:
            row = c.execute("SELECT id,password_hash FROM admin_users WHERE username=?", (u,)).fetchone()
            good = db.verify_password(pw, row["password_hash"] if row else db.DUMMY)
            if not (row and good):
                record(key)
                return self.err(401, "Invalid username or password.")
            tok, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
            exp = (datetime.now() + timedelta(hours=SESSION_HOURS)).isoformat(timespec="seconds")
            c.execute("DELETE FROM admin_sessions WHERE expires_at<?", (db.now(),))
            c.execute("INSERT INTO admin_sessions VALUES(?,?,?,?)", (sha(tok), row["id"], csrf, exp))
        self.js(200, {"ok": True}, [("Set-Cookie", cookie_str("axsid", tok, SESSION_HOURS * 3600))])

    def stats(self):
        td = db.today()
        with db.conn() as c:
            one = lambda sql, *a: c.execute(sql, a).fetchone()[0]
            start = (date.today() - timedelta(days=13)).isoformat()
            by = {x["day"]: (x["v"], x["u"]) for x in c.execute(
                "SELECT day,COUNT(*) v,COUNT(DISTINCT visitor_id) u FROM page_views WHERE day>=? GROUP BY day", (start,))}
            days = [(date.today() - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
            return self.js(200, {
                "total_enquiries": one("SELECT COUNT(*) FROM enquiries"),
                "today_enquiries": one("SELECT COUNT(*) FROM enquiries WHERE substr(created_at,1,10)=?", td),
                "total_views": one("SELECT COUNT(*) FROM page_views"),
                "today_views": one("SELECT COUNT(*) FROM page_views WHERE day=?", td),
                "unique_visitors": one("SELECT COUNT(DISTINCT visitor_id) FROM page_views"),
                "unique_today": one("SELECT COUNT(DISTINCT visitor_id) FROM page_views WHERE day=?", td),
                "by_day": [{"day": d, "views": by.get(d, (0, 0))[0], "visitors": by.get(d, (0, 0))[1]} for d in days]})

    def list_enquiries(self, q):
        sql, args = "SELECT * FROM enquiries WHERE 1=1", []
        st = (q.get("status") or [""])[0]
        if st in STATUSES:
            sql += " AND status=?"; args.append(st)
        s = clean((q.get("q") or [""])[0])[:60]
        if s:
            like = "%" + s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            sql += " AND (student_name LIKE ? ESCAPE '\\' OR guardian_name LIKE ? ESCAPE '\\' OR phone LIKE ? ESCAPE '\\' OR class_or_exam LIKE ? ESCAPE '\\')"
            args += [like] * 4
        with db.conn() as c:
            rows = c.execute(sql + " ORDER BY id DESC LIMIT 300", args).fetchall()
        self.js(200, [dict(x) for x in rows])

    def item(self, m, kind, i):
        d = self.body() if m == "PATCH" else {}
        if d is None:
            return self.err(400, "JSON body required.")
        with db.conn() as c:
            if kind == "enquiries":
                if m == "DELETE":
                    n = c.execute("DELETE FROM enquiries WHERE id=?", (i,)).rowcount
                elif m == "PATCH" and d.get("status") in STATUSES:
                    n = c.execute("UPDATE enquiries SET status=? WHERE id=?", (d["status"], i)).rowcount
                else:
                    return self.err(422, "Invalid request.")
            elif m == "PATCH":
                cur = c.execute("SELECT * FROM courses WHERE id=?", (i,)).fetchone()
                if not cur:
                    return self.err(404, "Not found.")
                v, e = self.course_values(d, dict(cur))
                if e:
                    return self.err(422, "Invalid course.", e)
                try:
                    n = c.execute("UPDATE courses SET title=?,category=?,class_or_exam=?,description=?,is_active=? WHERE id=?",
                                  (v["title"], v["category"], v["class_or_exam"], v["description"], v["is_active"], i)).rowcount
                except Exception:
                    return self.err(409, "A course with that title already exists.")
            else:
                return self.err(405, "Method not allowed.")
        self.js(200, {"ok": True}) if n else self.err(404, "Not found.")

    def course_values(self, d, base):
        v, e = dict(base), {}
        for k, mx in (("title", 120), ("class_or_exam", 60), ("description", 500)):
            if k in d:
                v[k] = clean(d[k])
        if "category" in d: v["category"] = d["category"]
        if "is_active" in d: v["is_active"] = 1 if d["is_active"] is True else 0
        if not 2 <= len(v["title"]) <= 120: e["title"] = "2-120 characters."
        if v["category"] not in ("school", "competitive"): e["category"] = "Choose school or competitive."
        if not 1 <= len(v["class_or_exam"]) <= 60: e["class_or_exam"] = "Required (max 60 characters)."
        if len(v["description"]) > 500: e["description"] = "Max 500 characters."
        if v["category"] == "school" and v["class_or_exam"] in ("Class 11", "Class 12") and "science" not in v["title"].lower():
            e["title"] = "Classes 11 and 12 are Science stream only; include 'Science' in the title."
        return v, e

    def courses(self, m):
        with db.conn() as c:
            if m == "GET":
                return self.js(200, [dict(x) for x in c.execute("SELECT * FROM courses ORDER BY id")])
            if m != "POST":
                return self.err(405, "Method not allowed.")
            d = self.body()
            if d is None:
                return self.err(400, "JSON body required.")
            v, e = self.course_values(d, {"title": "", "category": "", "class_or_exam": "", "description": "", "is_active": 1})
            if e:
                return self.err(422, "Invalid course.", e)
            try:
                cur = c.execute("INSERT INTO courses(title,category,class_or_exam,description,is_active,created_at) VALUES(?,?,?,?,?,?)",
                                (v["title"], v["category"], v["class_or_exam"], v["description"], v["is_active"], db.now()))
            except Exception:
                return self.err(409, "A course with that title already exists.")
        self.js(201, {"ok": True, "id": cur.lastrowid})

    def content(self, m):
        with db.conn() as c:
            if m == "GET":
                return self.js(200, {x["key"]: x["value"] for x in c.execute("SELECT key,value FROM site_content")})
            if m != "PUT":
                return self.err(405, "Method not allowed.")
            d = self.body()
            if d is None:
                return self.err(400, "JSON body required.")
            e, vals = {}, {}
            for k, v in d.items():
                v = clean(v)
                if k not in CONTENT_KEYS or len(v) > CONTENT_KEYS[k]: e[k] = "Unknown field or too long."
                elif k == "phone" and v and not re.fullmatch(r"[0-9+\-\s()]{7,30}", v): e[k] = "Invalid phone number."
                elif k == "email" and v and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v): e[k] = "Invalid email."
                else: vals[k] = v
            if e:
                return self.err(422, "Invalid content.", e)
            for k, v in vals.items():
                c.execute("INSERT INTO site_content(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))
        self.js(200, {"ok": True})


def main():
    db.init_db()
    host, port = os.environ.get("AX_HOST", "127.0.0.1"), int(os.environ.get("AX_PORT", "8000"))
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"ALPHA X ACADEMY running at http://{host}:{port}  (admin: /admin/login)  Ctrl+C to stop")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
