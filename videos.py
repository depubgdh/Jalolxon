"""YouTube videolar kutubxonasi (alohida modul): havolani tekshirish, saqlash, tartib va "navbatdagi video" qoidasi.

O'yin kodi va pul hisobi bilan aloqasi yo'q. Har bir foydalanuvchining ijro holati mijozda (brauzerda) saqlanadi,
shuning uchun foydalanuvchilar bir-biriga xalaqit bermaydi; server faqat ro'yxatni beradi va "shundan keyin qaysi video" ni aytadi.
"""
import re
import time
from urllib.parse import parse_qs, quote, urlparse

import db

ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "www.youtu.be",
         "youtube-nocookie.com", "www.youtube-nocookie.com"}
TITLE_MAX = 150


def init():
    con = db.connect()
    try:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS videos(
            id INTEGER PRIMARY KEY AUTOINCREMENT, video_id TEXT NOT NULL, url TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '', sort INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL,
            active INTEGER NOT NULL DEFAULT 1);
        CREATE INDEX IF NOT EXISTS idx_videos_sort ON videos(sort, id);
        """)
    finally:
        con.close()


# ---------------- havola ----------------
def parse_id(text):
    """YouTube havolasidan (yoki 11 belgili ID dan) video ID sini ajratadi. Topilmasa None."""
    t = (text or "").strip()
    if ID_RE.match(t):
        return t
    if not re.match(r"^https?://", t, re.I):
        t = "https://" + t
    try:
        u = urlparse(t)
        host = (u.hostname or "").lower()
    except ValueError:
        return None
    if host not in HOSTS:
        return None
    if host.endswith("youtu.be"):
        cand = u.path.lstrip("/").split("/")[0]
    else:
        parts = [p for p in u.path.split("/") if p]
        if parts and parts[0] == "watch":
            cand = (parse_qs(u.query).get("v") or [""])[0]
        elif len(parts) >= 2 and parts[0] in ("embed", "shorts", "live", "v"):
            cand = parts[1]
        else:
            cand = ""
    return cand if ID_RE.match(cand) else None


async def check(video_id: str) -> dict:
    """YouTube oEmbed orqali tekshiradi. found: True (bor, nomi title) / False (yo'q, yopiq yoki joylashtirish taqiqlangan) / None (tekshirib bo'lmadi)."""
    import aiohttp
    url = "https://www.youtube.com/oembed?format=json&url=" + quote(f"https://www.youtube.com/watch?v={video_id}", safe="")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as s:
            async with s.get(url) as r:
                if r.status == 200:
                    j = await r.json(content_type=None)
                    return {"found": True, "title": str(j.get("title") or "")[:TITLE_MAX]}
                if r.status in (400, 401, 403, 404):
                    return {"found": False, "title": ""}
    except Exception:
        pass
    return {"found": None, "title": ""}


# ---------------- ro'yxat ----------------
def _row(r) -> dict:
    return {"id": r["id"], "vid": r["video_id"], "url": r["url"], "title": r["title"], "pos": r["sort"],
            "created_at": r["created_at"], "active": r["active"]}


def _all(con, only_active: bool):
    q = "SELECT * FROM videos" + (" WHERE active=1" if only_active else "") + " ORDER BY sort, id"
    return con.execute(q).fetchall()


def next_after(after_id=None, after_pos=None):
    """Foydalanuvchiga navbatdagi video. Argumentsiz — birinchi video. Ro'yxat tugasa — yana birinchisi (LOOP).
    Joriy video o'chirilgan bo'lsa ham ishlaydi: o'zining oldingi o'rni (after_pos) dan keyingisi olinadi."""
    con = db.connect()
    try:
        rows = _all(con, True)
        if not rows:
            return None, 0
        total = len(rows)
        if after_id is None and after_pos is None:
            return _row(rows[0]), total
        cur = None
        for r in rows:
            if r["id"] == after_id:
                cur = r["sort"]
        if cur is None:
            cur = db._int(after_pos, None)
        if cur is None:
            return _row(rows[0]), total
        for r in rows:
            if r["sort"] > cur:
                return _row(r), total
        return _row(rows[0]), total
    finally:
        con.close()


def admin_list() -> dict:
    con = db.connect()
    try:
        rows = _all(con, False)
        items = [_row(r) for r in rows]
        latest = max(items, key=lambda x: (x["created_at"], x["id"]))["id"] if items else None
        return {"items": items, "count": len(items), "active_count": sum(1 for i in items if i["active"]), "latest_id": latest}
    finally:
        con.close()


def add(video_id: str, url: str, title: str) -> int:
    title = (title or "").strip()[:TITLE_MAX] or video_id

    def run(con):
        if con.execute("SELECT 1 FROM videos WHERE video_id=?", (video_id,)).fetchone():
            raise db.DbError("dup", "Bu video ro‘yxatda allaqachon bor")
        pos = con.execute("SELECT COALESCE(MAX(sort),0)+1 AS p FROM videos").fetchone()["p"]     # har doim ro'yxat oxiriga
        return con.execute("INSERT INTO videos(video_id,url,title,sort,created_at,active) VALUES(?,?,?,?,?,1)",
                           (video_id, url[:300], title, pos, time.time())).lastrowid
    return db._tx(run)


def delete(vid: int):
    con = db.connect()
    try:
        con.execute("DELETE FROM videos WHERE id=?", (vid,))
    finally:
        con.close()


def save(vid: int, title=None, active=None):
    def run(con):
        if not con.execute("SELECT 1 FROM videos WHERE id=?", (vid,)).fetchone():
            raise db.DbError("no_video", "Video topilmadi")
        if title is not None:
            t = str(title).strip()[:TITLE_MAX]
            if not t:
                raise db.DbError("title", "Nom bo‘sh bo‘lmasin")
            con.execute("UPDATE videos SET title=? WHERE id=?", (t, vid))
        if active is not None:
            con.execute("UPDATE videos SET active=? WHERE id=?", (1 if active else 0, vid))
    db._tx(run)


def move(vid: int, direction: int):
    """direction: -1 — yuqoriga (oldinroq), +1 — pastga (keyinroq). Qo'shni bilan o'rin almashadi."""
    def run(con):
        rows = _all(con, False)
        idx = next((i for i, r in enumerate(rows) if r["id"] == vid), None)
        if idx is None:
            raise db.DbError("no_video", "Video topilmadi")
        j = idx + (-1 if direction < 0 else 1)
        if j < 0 or j >= len(rows):
            return
        a, b = rows[idx], rows[j]
        con.execute("UPDATE videos SET sort=? WHERE id=?", (b["sort"], a["id"]))
        con.execute("UPDATE videos SET sort=? WHERE id=?", (a["sort"], b["id"]))
    db._tx(run)
