"""Telegram Bot API (faqat kerakli qismi). aiohttp ixtiyoriy import — testlarda almashtiriladi."""
import asyncio

import config

_BASE = "https://api.telegram.org/bot{}/{}"


async def call(method: str, **params):
    import aiohttp
    url = _BASE.format(config.BOT_TOKEN, method)
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
        async with s.post(url, json=params) as r:
            return await r.json()


async def member_status(chat, user_id: int):
    """'member' / 'administrator' / 'creator' / 'left' / ... yoki None (bot tekshira olmasa)."""
    try:
        d = await call("getChatMember", chat_id=chat, user_id=user_id)
        if d.get("ok"):
            return d["result"]["status"]
    except Exception:
        pass
    return None


async def send_message(chat_id: int, text: str, **kw):
    try:
        d = await call("sendMessage", chat_id=chat_id, text=text, **kw)
        return bool(d.get("ok"))
    except Exception:
        return False


async def broadcast(user_ids, text: str, delay: float = 0.05):
    ok = 0
    for uid in user_ids:
        if await send_message(uid, text):
            ok += 1
        await asyncio.sleep(delay)
    return ok
