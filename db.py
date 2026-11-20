"""Ma'lumotlar bazasi va barcha hisob-kitob qoidalari (SQLite).

Pul birligi — butun so'm. Balans faqat shu yerdagi funksiyalar orqali, bitta tranzaksiyada o'zgaradi va har bir o'zgarish `tx` jadvaliga yoziladi.
O'yindan daromad — FAQAT serverdagi vaqtga qarab (mijoz yuborgan natijaga emas), kunlik chegara bilan.
"""
import sqlite3
import time
from datetime import datetime, timedelta

import config

DEFAULTS = {
    "min_withdraw": 20000,       # eng kam yechib olish (so'm)
    "withdraw_on": 1,            # yechib olish yoqilgan (1) / o'chiq (0)
    "rate_per_min": 60,          # o'yinda har daqiqa uchun so'm
    "daily_cap": 3000,           # bir kunda o'yindan olinadigan eng ko'p so'm
    "max_session_min": 20,       # bir o'yin seansida hisoblanadigan eng ko'p daqiqa
    "ref_join_bonus": 300,       # do'st qo'shilganda taklif qilganga (so'm)
    "ref_active_bonus": 700,     # do'st "faol" bo'lganda taklif qilganga (so'm)
    "ref_active_minutes": 10,    # do'st shuncha daqiqa o'ynasa — faol hisoblanadi
    "tasks_on": 1,               # reklama/vazifalar bo'limi yoqilgan
    "link_wait_sec": 8,          # YouTube/Instagram havolasi ochilgach tekshirishgacha kutish
}
KINDS_BONUS = ("ref_join", "ref_active", "ref_task")
KINDS_FRIENDS = KINDS_BONUS
MAX_SECS_PING_GAP = 90          # ping shu vaqtdan ko'p uzilsa — oradagi vaqt hisoblanmaydi


class DbError(Exception):
    def __init__(self, code: str, msg: str = ""):
        super().__init__(code)
        self.code, self.msg = code, msg or code


def connect():
    con = sqlite3.connect(config.DB_PATH, timeout=15, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def today() -> str:
    return (datetime.utcnow() + timedelta(hours=5)).strftime("%Y-%m-%d")      # Toshkent vaqti


def now() -> float:
    return time.time()


def _tx(fn):
    con = connect()
    try:
        con.execute("BEGIN IMMEDIATE")
        res = fn(con)
        con.execute("COMMIT")
        return res
    except Exception:
        try:
            con.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        con.close()


def init_db():
    con = connect()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY, username TEXT DEFAULT '', first_name TEXT DEFAULT '', photo TEXT DEFAULT '',
        balance INTEGER NOT NULL DEFAULT 0, play_secs INTEGER NOT NULL DEFAULT 0,
        ref_by INTEGER, active_paid INTEGER NOT NULL DEFAULT 0, banned INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL DEFAULT 0);
    CREATE INDEX IF NOT EXISTS idx_users_ref ON users(ref_by);
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS tx(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, kind TEXT NOT NULL, amount INTEGER NOT NULL,
        note TEXT DEFAULT '', other INTEGER, created_at REAL NOT NULL);
    CREATE INDEX IF NOT EXISTS idx_tx_user ON tx(user_id, id);
    CREATE TABLE IF NOT EXISTS sessions(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, game TEXT NOT NULL,
        started REAL NOT NULL, last_ping REAL NOT NULL, status TEXT NOT NULL DEFAULT 'active', secs INTEGER DEFAULT 0, earned INTEGER DEFAULT 0);
    CREATE INDEX IF NOT EXISTS idx_sess_user ON sessions(user_id, status);
    CREATE TABLE IF NOT EXISTS daily(user_id INTEGER NOT NULL, day TEXT NOT NULL, secs INTEGER NOT NULL DEFAULT 0,
        earned INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id, day));
    CREATE TABLE IF NOT EXISTS tasks(
        id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL DEFAULT 'link', title TEXT NOT NULL, url TEXT NOT NULL DEFAULT '',
        chat TEXT NOT NULL DEFAULT '', reward INTEGER NOT NULL DEFAULT 0, ref_bonus INTEGER NOT NULL DEFAULT 0,
        active INTEGER NOT NULL DEFAULT 1, sort INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS task_done(user_id INTEGER NOT NULL, task_id INTEGER NOT NULL, opened_at REAL, done_at REAL,
        PRIMARY KEY(user_id, task_id));
    CREATE TABLE IF NOT EXISTS withdrawals(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, amount INTEGER NOT NULL, details TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending', note TEXT DEFAULT '', created_at REAL NOT NULL, resolved_at REAL);
    CREATE INDEX IF NOT EXISTS idx_wd_user ON withdrawals(user_id, id);
    """)
    con.close()


# ---------------- sozlamalar ----------------
def get_settings() -> dict:
    out = dict(DEFAULTS)
    con = connect()
    try:
        for r in con.execute("SELECT key, value FROM settings"):
            if r["key"] in DEFAULTS:
                try:
                    out[r["key"]] = int(r["value"])
                except ValueError:
                    pass
    finally:
        con.close()
    return out


def set_settings(values: dict) -> dict:
    con = connect()
    try:
        for k, v in values.items():
            if k not in DEFAULTS:
                continue
            v = int(v)
            if v < 0 or v > 10_000_000_000:
                raise DbError("bad_value", f"{k}: noto‘g‘ri qiymat")
            con.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(v)))
    finally:
        con.close()
    return get_settings()


# ---------------- foydalanuvchi ----------------
def _credit(con, uid: int, amount: int, kind: str, note: str = "", other=None):
    con.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, uid))
    con.execute("INSERT INTO tx(user_id,kind,amount,note,other,created_at) VALUES(?,?,?,?,?,?)", (uid, kind, amount, note, other, now()))


def ensure_user(uid: int, username: str = "", first_name: str = "", photo: str = "", ref=None):
    """Foydalanuvchini yaratadi/yangilaydi. Yangi bo'lsa va ref to'g'ri bo'lsa — taklif qilganga qo'shilish bonusi beriladi.
    Qaytaradi: (user_row, is_new, inviter_id_or_None, bonus_paid)"""
    st = get_settings()

    def run(con):
        row = con.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
        if row:
            con.execute("UPDATE users SET username=?, first_name=?, photo=? WHERE user_id=?",
                        (username or row["username"], first_name or row["first_name"], photo or row["photo"], uid))
            return con.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone(), False, None, 0
        inviter, paid = None, 0
        try:
            rid = int(ref) if ref else None
        except (TypeError, ValueError):
            rid = None
        if rid and rid != uid:
            r = con.execute("SELECT user_id, banned FROM users WHERE user_id=?", (rid,)).fetchone()
            if r and not r["banned"]:
                inviter = rid
        con.execute("INSERT INTO users(user_id,username,first_name,photo,ref_by,created_at) VALUES(?,?,?,?,?,?)",
                    (uid, username, first_name, photo, inviter, now()))
        if inviter and st["ref_join_bonus"] > 0:
            _credit(con, inviter, st["ref_join_bonus"], "ref_join", first_name or username or str(uid), uid)
            paid = st["ref_join_bonus"]
        return con.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone(), True, inviter, paid

    return _tx(run)


def get_user(uid: int):
    con = connect()
    try:
        return con.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
    finally:
        con.close()


# ---------------- o'yin seanslari ----------------
def _settle(con, sess, st, end_ts: float):
    """Seansni yopadi: vaqt = (end_ts - start), serverdagi soat bo'yicha; kunlik/seans chegarasi bilan so'm hisoblanadi."""
    secs = int(max(0, min(end_ts, now()) - sess["started"]))
    secs = min(secs, st["max_session_min"] * 60)
    uid = sess["user_id"]
    day = today()
    d = con.execute("SELECT earned FROM daily WHERE user_id=? AND day=?", (uid, day)).fetchone()
    got = d["earned"] if d else 0
    earn = max(0, min(secs * st["rate_per_min"] // 60, st["daily_cap"] - got))
    con.execute("UPDATE sessions SET status='done', secs=?, earned=? WHERE id=?", (secs, earn, sess["id"]))
    con.execute("INSERT INTO daily(user_id,day,secs,earned) VALUES(?,?,?,?) ON CONFLICT(user_id,day) DO UPDATE SET secs=secs+excluded.secs, earned=earned+excluded.earned",
                (uid, day, secs, earn))
    con.execute("UPDATE users SET play_secs = play_secs + ? WHERE user_id=?", (secs, uid))
    if earn > 0:
        _credit(con, uid, earn, "game", sess["game"])
    # do'st faol bo'ldimi?
    u = con.execute("SELECT play_secs, ref_by, active_paid FROM users WHERE user_id=?", (uid,)).fetchone()
    bonus_to = None
    if u["ref_by"] and not u["active_paid"] and u["play_secs"] >= st["ref_active_minutes"] * 60:
        con.execute("UPDATE users SET active_paid=1 WHERE user_id=?", (uid,))
        if st["ref_active_bonus"] > 0:
            _credit(con, u["ref_by"], st["ref_active_bonus"], "ref_active", "faol do‘st", uid)
            bonus_to = (u["ref_by"], st["ref_active_bonus"])
    return secs, earn, bonus_to


def game_start(uid: int, game: str) -> int:
    if game not in ("paperio", "slither"):
        raise DbError("bad_game", "Noma’lum o‘yin")
    st = get_settings()

    def run(con):
        u = con.execute("SELECT banned FROM users WHERE user_id=?", (uid,)).fetchone()
        if not u or u["banned"]:
            raise DbError("banned", "Hisob bloklangan")
        for s in con.execute("SELECT * FROM sessions WHERE user_id=? AND status='active'", (uid,)).fetchall():
            _settle(con, s, st, s["last_ping"])
        cur = con.execute("INSERT INTO sessions(user_id,game,started,last_ping) VALUES(?,?,?,?)", (uid, game, now(), now()))
        return cur.lastrowid

    return _tx(run)


def game_ping(uid: int, sid: int) -> bool:
    con = connect()
    try:
        con.execute("UPDATE sessions SET last_ping=? WHERE id=? AND user_id=? AND status='active'", (now(), sid, uid))
        return True
    finally:
        con.close()


def game_finish(uid: int, sid: int):
    """Seansni tugatadi. Qaytaradi: dict(secs, earned, balance, capped, friend_bonus)"""
    st = get_settings()

    def run(con):
        s = con.execute("SELECT * FROM sessions WHERE id=? AND user_id=?", (sid, uid)).fetchone()
        if not s:
            raise DbError("no_session", "Seans topilmadi")
        if s["status"] != "active":
            bal = con.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()["balance"]
            return {"secs": s["secs"], "earned": s["earned"], "balance": bal, "capped": False, "friend_bonus": None}
        # oxirgi ping uzoq bo'lsa (ilova yopilgan) — faqat ping vaqtigacha
        end = now() if now() - s["last_ping"] <= MAX_SECS_PING_GAP else s["last_ping"]
        secs, earn, bonus_to = _settle(con, s, st, end)
        bal = con.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()["balance"]
        capped = secs * st["rate_per_min"] // 60 > earn
        return {"secs": secs, "earned": earn, "balance": bal, "capped": capped, "friend_bonus": bonus_to}

    return _tx(run)


def settle_stale(uid: int):
    """Ilova ochilganda: yopilmay qolgan seanslarni oxirgi ping bo'yicha hisoblaydi."""
    st = get_settings()

    def run(con):
        for s in con.execute("SELECT * FROM sessions WHERE user_id=? AND status='active' AND ?-last_ping>?", (uid, now(), MAX_SECS_PING_GAP)).fetchall():
            _settle(con, s, st, s["last_ping"])

    _tx(run)


# ---------------- statistika ----------------
def stats(uid: int, days: int = 7) -> dict:
    days = 14 if days >= 14 else 7
    con = connect()
    try:
        base = datetime.utcnow() + timedelta(hours=5)
        rows = {r["day"]: r for r in con.execute("SELECT * FROM daily WHERE user_id=? AND day>=?", (uid, (base - timedelta(days=days - 1)).strftime("%Y-%m-%d")))}
        series = []
        for i in range(days - 1, -1, -1):
            d = (base - timedelta(days=i)).strftime("%Y-%m-%d")
            r = rows.get(d)
            series.append({"day": d, "earned": r["earned"] if r else 0, "secs": r["secs"] if r else 0})
        t = series[-1]
        return {"series": series, "today_earned": t["earned"], "today_secs": t["secs"]}
    finally:
        con.close()


# ---------------- referal ----------------
def referral_info(uid: int) -> dict:
    con = connect()
    try:
        joined = con.execute("SELECT COUNT(*) c FROM users WHERE ref_by=?", (uid,)).fetchone()["c"]
        active = con.execute("SELECT COUNT(*) c FROM users WHERE ref_by=? AND active_paid=1", (uid,)).fetchone()["c"]
        earned = con.execute("SELECT COALESCE(SUM(amount),0) s FROM tx WHERE user_id=? AND kind IN ('ref_join','ref_active','ref_task')", (uid,)).fetchone()["s"]
        return {"joined": joined, "active": active, "earned": earned}
    finally:
        con.close()


# ---------------- vazifalar ----------------
def tasks_for(uid: int) -> list:
    con = connect()
    try:
        done = {r["task_id"]: r for r in con.execute("SELECT * FROM task_done WHERE user_id=?", (uid,))}
        out = []
        for t in con.execute("SELECT * FROM tasks WHERE active=1 ORDER BY sort, id"):
            d = done.get(t["id"])
            out.append({"id": t["id"], "kind": t["kind"], "title": t["title"], "reward": t["reward"],
                        "done": bool(d and d["done_at"]), "opened": bool(d and d["opened_at"])})
        return out
    finally:
        con.close()


def task_open(uid: int, task_id: int) -> str:
    def run(con):
        t = con.execute("SELECT * FROM tasks WHERE id=? AND active=1", (task_id,)).fetchone()
        if not t:
            raise DbError("no_task", "Vazifa topilmadi")
        con.execute("INSERT INTO task_done(user_id,task_id,opened_at) VALUES(?,?,?) ON CONFLICT(user_id,task_id) DO UPDATE SET opened_at=COALESCE(opened_at, excluded.opened_at)", (uid, task_id, now()))
        return t["url"]
    return _tx(run)


def task_get(task_id: int):
    con = connect()
    try:
        return con.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    finally:
        con.close()


def task_state(uid: int, task_id: int):
    con = connect()
    try:
        return con.execute("SELECT * FROM task_done WHERE user_id=? AND task_id=?", (uid, task_id)).fetchone()
    finally:
        con.close()


def task_complete(uid: int, task_id: int) -> dict:
    """Vazifani bajarilgan deb belgilaydi (bir marta) va mukofotlarni beradi."""
    def run(con):
        t = con.execute("SELECT * FROM tasks WHERE id=? AND active=1", (task_id,)).fetchone()
        if not t:
            raise DbError("no_task", "Vazifa topilmadi")
        d = con.execute("SELECT * FROM task_done WHERE user_id=? AND task_id=?", (uid, task_id)).fetchone()
        if d and d["done_at"]:
            return {"reward": 0, "already": True, "inviter": None, "ref_bonus": 0}
        con.execute("INSERT INTO task_done(user_id,task_id,opened_at,done_at) VALUES(?,?,?,?) ON CONFLICT(user_id,task_id) DO UPDATE SET done_at=excluded.done_at", (uid, task_id, now(), now()))
        if t["reward"] > 0:
            _credit(con, uid, t["reward"], "task", t["title"], task_id)
        inviter, rb = None, 0
        u = con.execute("SELECT ref_by FROM users WHERE user_id=?", (uid,)).fetchone()
        if u and u["ref_by"] and t["ref_bonus"] > 0:
            inviter, rb = u["ref_by"], t["ref_bonus"]
            _credit(con, inviter, rb, "ref_task", t["title"], uid)
        return {"reward": t["reward"], "already": False, "inviter": inviter, "ref_bonus": rb}
    return _tx(run)


# ---------------- yechib olish ----------------
def withdraw_create(uid: int, amount, details: str) -> dict:
    st = get_settings()
    try:
        amount = int(amount)
    except (TypeError, ValueError):
        raise DbError("bad_amount", "Summani to‘g‘ri kiriting")
    details = (details or "").strip()
    if not st["withdraw_on"]:
        raise DbError("off", "Yechib olish vaqtincha o‘chiq")
    if amount < st["min_withdraw"]:
        raise DbError("min", f"Eng kam summa: {st['min_withdraw']}")
    if len(details) < 5 or len(details) > 120:
        raise DbError("details", "Karta yoki hamyon rekvizitini kiriting")

    def run(con):
        u = con.execute("SELECT balance, banned FROM users WHERE user_id=?", (uid,)).fetchone()
        if not u or u["banned"]:
            raise DbError("banned", "Hisob bloklangan")
        if con.execute("SELECT 1 FROM withdrawals WHERE user_id=? AND status='pending'", (uid,)).fetchone():
            raise DbError("pending", "Avvalgi so‘rovingiz hali ko‘rib chiqilmoqda")
        if amount > u["balance"]:
            raise DbError("funds", "Balans yetarli emas")
        cur = con.execute("INSERT INTO withdrawals(user_id,amount,details,created_at) VALUES(?,?,?,?)", (uid, amount, details, now()))
        _credit(con, uid, -amount, "withdraw", details[:40], cur.lastrowid)
        bal = con.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()["balance"]
        return {"id": cur.lastrowid, "balance": bal, "amount": amount}

    return _tx(run)


def withdraw_resolve(wid: int, ok: bool, note: str = "") -> dict:
    def run(con):
        w = con.execute("SELECT * FROM withdrawals WHERE id=?", (wid,)).fetchone()
        if not w:
            raise DbError("no_wd", "So‘rov topilmadi")
        if w["status"] != "pending":
            raise DbError("done", "Bu so‘rov allaqachon ko‘rib chiqilgan")
        con.execute("UPDATE withdrawals SET status=?, note=?, resolved_at=? WHERE id=?", ("paid" if ok else "rejected", note, now(), wid))
        if not ok:
            _credit(con, w["user_id"], w["amount"], "withdraw_refund", "rad etildi", wid)
        return {"user_id": w["user_id"], "amount": w["amount"], "ok": ok}
    return _tx(run)


def history(uid: int, flt: str = "all", limit: int = 60) -> dict:
    con = connect()
    try:
        sums = {r["k"]: r["s"] for r in con.execute("SELECT kind k, SUM(amount) s FROM tx WHERE user_id=? GROUP BY kind", (uid,))}
        totals = {"games": sums.get("game", 0), "friends": sum(sums.get(k, 0) for k in KINDS_FRIENDS), "tasks": sums.get("task", 0)}
        if flt == "withdraw":
            kinds = ("withdraw", "withdraw_refund")
        elif flt == "bonus":
            kinds = ("game", "ref_join", "ref_active", "ref_task", "task")
        else:
            kinds = None
        q = "SELECT id,kind,amount,note,other,created_at FROM tx WHERE user_id=?"
        args = [uid]
        if kinds:
            q += " AND kind IN (%s)" % ",".join("?" * len(kinds))
            args += list(kinds)
        q += " ORDER BY id DESC LIMIT ?"
        items = [dict(r) for r in con.execute(q, args + [limit])]
        wds = {r["id"]: r["status"] for r in con.execute("SELECT id,status FROM withdrawals WHERE user_id=?", (uid,))}
        for it in items:
            it["status"] = wds.get(it["other"]) if it["kind"] == "withdraw" else None
        return {"items": items, "totals": totals}
    finally:
        con.close()


def my_withdrawals(uid: int, limit: int = 30) -> list:
    con = connect()
    try:
        return [dict(r) for r in con.execute("SELECT id,amount,status,created_at,note FROM withdrawals WHERE user_id=? ORDER BY id DESC LIMIT ?", (uid, limit))]
    finally:
        con.close()


# ---------------- admin ----------------
def admin_overview() -> dict:
    con = connect()
    try:
        day_start = (datetime.utcnow() + timedelta(hours=5)).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=5)
        ts = (day_start - datetime(1970, 1, 1)).total_seconds()
        users = con.execute("SELECT COUNT(*) c, COALESCE(SUM(balance),0) b, COALESCE(SUM(play_secs),0) p FROM users").fetchone()
        new = con.execute("SELECT COUNT(*) c FROM users WHERE created_at>=?", (ts,)).fetchone()["c"]
        act = con.execute("SELECT COUNT(DISTINCT user_id) c FROM daily WHERE day=?", (today(),)).fetchone()["c"]
        pend = con.execute("SELECT COUNT(*) c, COALESCE(SUM(amount),0) s FROM withdrawals WHERE status='pending'").fetchone()
        paid = con.execute("SELECT COALESCE(SUM(amount),0) s FROM withdrawals WHERE status='paid'").fetchone()["s"]
        earned = con.execute("SELECT COALESCE(SUM(earned),0) s FROM daily WHERE day=?", (today(),)).fetchone()["s"]
        refs = con.execute("SELECT COUNT(*) c FROM users WHERE ref_by IS NOT NULL").fetchone()["c"]
        return {"users": users["c"], "new_today": new, "active_today": act, "balances": users["b"], "play_hours": round(users["p"] / 3600, 1),
                "pending_count": pend["c"], "pending_sum": pend["s"], "paid_total": paid, "earned_today": earned, "referred": refs}
    finally:
        con.close()


def admin_withdrawals(status: str = "pending", limit: int = 50) -> list:
    con = connect()
    try:
        q = ("SELECT w.*, u.username, u.first_name FROM withdrawals w LEFT JOIN users u ON u.user_id=w.user_id "
             "WHERE w.status=? ORDER BY w.id DESC LIMIT ?")
        return [dict(r) for r in con.execute(q, (status, limit))]
    finally:
        con.close()


def admin_find_user(q: str):
    q = (q or "").strip().lstrip("@")
    con = connect()
    try:
        if q.isdigit():
            r = con.execute("SELECT * FROM users WHERE user_id=?", (int(q),)).fetchone()
        else:
            r = con.execute("SELECT * FROM users WHERE LOWER(username)=LOWER(?)", (q,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["referrals"] = con.execute("SELECT COUNT(*) c FROM users WHERE ref_by=?", (r["user_id"],)).fetchone()["c"]
        return d
    finally:
        con.close()


def admin_adjust(uid: int, amount: int, note: str = "admin") -> int:
    def run(con):
        u = con.execute("SELECT balance FROM users WHERE user_id=?", (uid,)).fetchone()
        if not u:
            raise DbError("no_user", "Foydalanuvchi topilmadi")
        if u["balance"] + amount < 0:
            raise DbError("funds", "Balans manfiy bo‘lib qoladi")
        _credit(con, uid, amount, "admin", note)
        return u["balance"] + amount
    return _tx(run)


def admin_ban(uid: int, banned: bool):
    con = connect()
    try:
        con.execute("UPDATE users SET banned=? WHERE user_id=?", (1 if banned else 0, uid))
    finally:
        con.close()


def admin_tasks() -> list:
    con = connect()
    try:
        return [dict(r) for r in con.execute("SELECT * FROM tasks ORDER BY sort, id")]
    finally:
        con.close()


def admin_task_save(d: dict) -> int:
    kind = d.get("kind") if d.get("kind") in ("telegram", "youtube", "instagram", "link") else "link"
    title = (d.get("title") or "").strip()[:60]
    if not title:
        raise DbError("title", "Nomini kiriting")
    url = (d.get("url") or "").strip()[:300]
    if not url.startswith("http"):
        raise DbError("url", "Havola https:// bilan boshlansin")
    chat = (d.get("chat") or "").strip()[:80]
    if kind == "telegram" and not chat:
        raise DbError("chat", "Telegram vazifasi uchun kanal/guruh (@username yoki ID) kerak")
    vals = (kind, title, url, chat, max(0, int(d.get("reward") or 0)), max(0, int(d.get("ref_bonus") or 0)), 1 if d.get("active", True) else 0, int(d.get("sort") or 0))
    con = connect()
    try:
        if d.get("id"):
            con.execute("UPDATE tasks SET kind=?,title=?,url=?,chat=?,reward=?,ref_bonus=?,active=?,sort=? WHERE id=?", vals + (int(d["id"]),))
            return int(d["id"])
        return con.execute("INSERT INTO tasks(kind,title,url,chat,reward,ref_bonus,active,sort) VALUES(?,?,?,?,?,?,?,?)", vals).lastrowid
    finally:
        con.close()


def admin_task_delete(tid: int):
    con = connect()
    try:
        con.execute("DELETE FROM tasks WHERE id=?", (tid,))
        con.execute("DELETE FROM task_done WHERE task_id=?", (tid,))
    finally:
        con.close()


def all_user_ids() -> list:
    con = connect()
    try:
        return [r["user_id"] for r in con.execute("SELECT user_id FROM users WHERE banned=0")]
    finally:
        con.close()
