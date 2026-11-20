"""API yo'llari. Hammasi POST /api/<yo'l>, tanasida {init_data, ...}. Admin yo'llari faqat ADMIN_IDS uchun."""
import asyncio

import auth
import config
import db
import tgapi

ROUTES = {}
ADMIN_ROUTES = set()
_BROADCAST = {"running": False}


class ApiError(Exception):
    def __init__(self, status: int, code: str, msg: str = ""):
        super().__init__(code)
        self.status, self.code, self.msg = status, code, msg or code


def route(path, admin=False):
    def deco(fn):
        ROUTES[path] = fn
        if admin:
            ADMIN_ROUTES.add(path)
        return fn
    return deco


def _i(v, d=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return d


def link_for(uid: int) -> str:
    return f"https://t.me/{config.BOT_USERNAME}?start=ref_{uid}" if config.BOT_USERNAME else ""


async def dispatch(path: str, body: dict, dev_user: dict = None):
    fn = ROUTES.get(path)
    if not fn:
        raise ApiError(404, "not_found", "Yo‘l topilmadi")
    if dev_user:                                   # faqat dev_server.py uchun
        tg_user, start = dev_user, ""
    else:
        a = auth.verify(body.get("init_data", ""))
        if not a:
            raise ApiError(401, "auth", "Telegram orqali oching")
        tg_user, start = a["user"], a["start_param"]
    uid = int(tg_user["id"])
    ref = start[4:] if start.startswith("ref_") else None
    user, is_new, inviter, paid = db.ensure_user(uid, tg_user.get("username") or "", tg_user.get("first_name") or "", tg_user.get("photo_url") or "", ref)
    if is_new and inviter and paid:
        asyncio.ensure_future(tgapi.send_message(inviter, f"🎉 Do‘stingiz qo‘shildi! +{paid} so‘m bonus."))
    if user["banned"]:
        raise ApiError(403, "banned", "Hisobingiz bloklangan")
    is_admin = uid in config.ADMIN_IDS
    if path in ADMIN_ROUTES and not is_admin:
        raise ApiError(403, "forbidden", "Faqat admin uchun")
    ctx = {"uid": uid, "user": user, "is_admin": is_admin}
    try:
        return await fn(ctx, body)
    except db.DbError as e:
        raise ApiError(400, e.code, e.msg)


# ===================== foydalanuvchi =====================
@route("me")
async def api_me(c, d):
    uid = c["uid"]
    db.settle_stale(uid)
    u = db.get_user(uid)
    st = db.get_settings()
    return {
        "user": {"id": uid, "name": u["first_name"], "username": u["username"], "photo": u["photo"], "balance": u["balance"]},
        "stats": db.stats(uid, _i(d.get("days"), 7)),
        "settings": {k: st[k] for k in ("min_withdraw", "withdraw_on", "ref_join_bonus", "ref_active_bonus", "ref_active_minutes", "rate_per_min", "daily_cap", "tasks_on")},
        "is_admin": c["is_admin"], "play_secs": u["play_secs"],
    }


@route("stats")
async def api_stats(c, d):
    return db.stats(c["uid"], _i(d.get("days"), 7))


@route("game/start")
async def api_game_start(c, d):
    return {"sid": db.game_start(c["uid"], str(d.get("game", "")))}


@route("game/ping")
async def api_game_ping(c, d):
    return {"ok": db.game_ping(c["uid"], _i(d.get("sid")))}


@route("game/finish")
async def api_game_finish(c, d):
    r = db.game_finish(c["uid"], _i(d.get("sid")))
    if r.get("friend_bonus"):
        inv, amt = r["friend_bonus"]
        asyncio.ensure_future(tgapi.send_message(inv, f"✅ Do‘stingiz faol bo‘ldi! +{amt} so‘m bonus."))
    r["friend_bonus"] = None
    return r


@route("bonus")
async def api_bonus(c, d):
    uid = c["uid"]
    st = db.get_settings()
    return {"ref": db.referral_info(uid), "link": link_for(uid),
            "tasks": db.tasks_for(uid) if st["tasks_on"] else [],
            "rules": {k: st[k] for k in ("ref_join_bonus", "ref_active_bonus", "ref_active_minutes")}}


@route("task/open")
async def api_task_open(c, d):
    return {"url": db.task_open(c["uid"], _i(d.get("id")))}


@route("task/check")
async def api_task_check(c, d):
    uid, tid = c["uid"], _i(d.get("id"))
    t = db.task_get(tid)
    if not t or not t["active"]:
        raise ApiError(404, "no_task", "Vazifa topilmadi")
    s = db.task_state(uid, tid)
    if s and s["done_at"]:
        raise ApiError(400, "done", "Bu vazifa allaqachon bajarilgan")
    if t["kind"] == "telegram":
        stt = await tgapi.member_status(t["chat"], uid)
        if stt is None:
            raise ApiError(400, "check_fail", "Bot obunani tekshira olmadi. Admin botni kanal/guruhga admin qilishi kerak.")
        if stt not in ("member", "administrator", "creator"):
            raise ApiError(400, "not_member", "Avval kanal/guruhga obuna bo‘ling")
    else:
        if not s or not s["opened_at"]:
            raise ApiError(400, "not_opened", "Avval havolani oching")
        wait = db.get_settings()["link_wait_sec"]
        if db.now() - s["opened_at"] < wait:
            raise ApiError(400, "wait", f"Havolani ko‘rib chiqing, {wait} soniyadan keyin bosing")
    r = db.task_complete(uid, tid)
    if r["inviter"] and r["ref_bonus"]:
        asyncio.ensure_future(tgapi.send_message(r["inviter"], f"✅ Do‘stingiz vazifani bajardi! +{r['ref_bonus']} so‘m bonus."))
    return {"reward": r["reward"], "balance": db.get_user(uid)["balance"]}


@route("withdraw/create")
async def api_wd_create(c, d):
    r = db.withdraw_create(c["uid"], d.get("amount"), d.get("details", ""))
    u = c["user"]
    who = f"@{u['username']}" if u["username"] else (u["first_name"] or str(c["uid"]))
    kb = {"inline_keyboard": [[{"text": "✅ To‘landi", "callback_data": f"wd:ok:{r['id']}"}, {"text": "❌ Rad etish", "callback_data": f"wd:no:{r['id']}"}]]}
    for a in config.ADMIN_IDS:
        asyncio.ensure_future(tgapi.send_message(a, f"💸 Yangi yechib olish #{r['id']}\n{who} (ID {c['uid']})\nSumma: {r['amount']} so‘m\nRekvizit: {d.get('details', '').strip()}", reply_markup=kb))
    return r


@route("withdraw/list")
async def api_wd_list(c, d):
    return {"items": db.my_withdrawals(c["uid"])}


@route("history")
async def api_history(c, d):
    f = d.get("filter") if d.get("filter") in ("all", "withdraw", "bonus") else "all"
    return db.history(c["uid"], f)


# ===================== admin =====================
@route("admin/overview", admin=True)
async def api_a_overview(c, d):
    return db.admin_overview()


@route("admin/settings", admin=True)
async def api_a_settings(c, d):
    return {"settings": db.get_settings()}


@route("admin/settings/save", admin=True)
async def api_a_settings_save(c, d):
    return {"settings": db.set_settings(d.get("values") or {})}


@route("admin/tasks", admin=True)
async def api_a_tasks(c, d):
    return {"tasks": db.admin_tasks()}


@route("admin/task/save", admin=True)
async def api_a_task_save(c, d):
    db.admin_task_save(d)
    return {"tasks": db.admin_tasks()}


@route("admin/task/delete", admin=True)
async def api_a_task_del(c, d):
    db.admin_task_delete(_i(d.get("id")))
    return {"tasks": db.admin_tasks()}


@route("admin/withdrawals", admin=True)
async def api_a_wds(c, d):
    st = d.get("status") if d.get("status") in ("pending", "paid", "rejected") else "pending"
    return {"items": db.admin_withdrawals(st)}


async def resolve_withdrawal(wid: int, ok: bool, note: str = ""):
    """Admin panel ham, bot tugmalari ham shuni ishlatadi."""
    r = db.withdraw_resolve(wid, ok, note)
    msg = (f"✅ Yechib olish so‘rovingiz bajarildi: {r['amount']} so‘m." if ok
           else f"❌ Yechib olish so‘rovingiz rad etildi. {r['amount']} so‘m balansingizga qaytarildi." + (f"\nSabab: {note}" if note else ""))
    asyncio.ensure_future(tgapi.send_message(r["user_id"], msg))
    return r


@route("admin/withdraw/resolve", admin=True)
async def api_a_wd_resolve(c, d):
    await resolve_withdrawal(_i(d.get("id")), bool(d.get("ok")), str(d.get("note", ""))[:100])
    return {"items": db.admin_withdrawals("pending")}


@route("admin/user", admin=True)
async def api_a_user(c, d):
    u = db.admin_find_user(d.get("q", ""))
    if not u:
        raise ApiError(404, "no_user", "Foydalanuvchi topilmadi")
    return {"user": {k: u[k] for k in ("user_id", "username", "first_name", "balance", "play_secs", "ref_by", "banned", "referrals")}}


@route("admin/adjust", admin=True)
async def api_a_adjust(c, d):
    bal = db.admin_adjust(_i(d.get("user_id")), _i(d.get("amount")), "admin")
    return {"balance": bal}


@route("admin/ban", admin=True)
async def api_a_ban(c, d):
    db.admin_ban(_i(d.get("user_id")), bool(d.get("banned")))
    return {"ok": True}


@route("admin/broadcast", admin=True)
async def api_a_broadcast(c, d):
    text = str(d.get("text", "")).strip()[:3500]
    if not text:
        raise ApiError(400, "empty", "Matn bo‘sh")
    if _BROADCAST["running"]:
        raise ApiError(400, "busy", "Oldingi xabar yuborilmoqda")
    ids = db.all_user_ids()

    async def run():
        _BROADCAST["running"] = True
        try:
            await tgapi.broadcast(ids, text)
        finally:
            _BROADCAST["running"] = False
    asyncio.ensure_future(run())
    return {"total": len(ids)}
