"""Telegram bot (aiogram 3): /start (admin belgilagan matn + rasm/GIF), Mini App tugmasi, yechib olishni bot ichidan tasdiqlash."""
from aiogram import Router, F
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

import api
import config
import db

router = Router()
CAPTION_MAX = 1000          # Telegram: rasm tagidagi matn 1024 belgidan oshmasin


def open_kb(text="🎮 O‘yinlarni ochish"):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, web_app=WebAppInfo(url=config.WEBAPP_URL))]])


def welcome_text(user) -> str:
    """Admin panel → Start bo'limida yozilgan matn. {name} — foydalanuvchi ismi."""
    text = db.get_text("start_text", "").strip() or db.START_TEXT_DEFAULT
    return text.replace("{name}", (user.first_name or user.username or "do‘st"))


async def send_welcome(m: Message):
    text, kb, media = welcome_text(m.from_user), open_kb(), db.media_get("start")
    if media:
        mime, ver, key = media["mime"], media["ver"], "start"
        anim = mime in ("image/gif", "video/mp4")
        ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif", "video/mp4": "mp4"}.get(mime, "bin")
        short = len(text) <= CAPTION_MAX
        for src in ([media["tg_file_id"]] if media["tg_file_id"] else []) + [BufferedInputFile(bytes(media["data"]), filename=f"start.{ext}")]:
            try:
                kw = dict(caption=text, reply_markup=kb) if short else {}
                sent = await (m.answer_animation(src, **kw) if anim else m.answer_photo(src, **kw))
            except Exception:
                continue                      # eski file_id ishlamasa — faylning o'zini yuboramiz
            fid = sent.animation.file_id if anim and sent.animation else (sent.photo[-1].file_id if sent.photo else "")
            if fid and not isinstance(src, str):
                db.media_set_file_id(key, ver, fid)
            if not short:
                await m.answer(text, reply_markup=kb)
            return
    await m.answer(text, reply_markup=kb)


@router.message(CommandStart())
async def start(m: Message, command: CommandObject):
    arg = (command.args or "").strip()
    ref = arg[4:] if arg.startswith("ref_") else None
    u = m.from_user
    _, is_new, inviter, paid = db.ensure_user(u.id, u.username or "", u.first_name or "", "", ref)
    if is_new and inviter and paid:
        try:
            await m.bot.send_message(inviter, f"🎉 Do‘stingiz qo‘shildi! +{db.usd(paid)} $ bonus.")
        except Exception:
            pass
    await send_welcome(m)


@router.message(Command("admin"))
async def admin(m: Message):
    if m.from_user.id not in config.ADMIN_IDS:
        return
    await m.answer("🛠 Admin panel Mini App ichida: ochib, yuqoridagi ⚙ tugmasini bosing.", reply_markup=open_kb("🛠 Admin panelni ochish"))


@router.callback_query(F.data.startswith("wd:"))
async def wd_cb(cb: CallbackQuery):
    if cb.from_user.id not in config.ADMIN_IDS:
        await cb.answer("Ruxsat yo‘q", show_alert=True)
        return
    _, act, wid = cb.data.split(":")
    try:
        await api.resolve_withdrawal(int(wid), act == "ok")
    except db.DbError as e:
        await cb.answer(e.msg, show_alert=True)
        return
    await cb.message.edit_text(cb.message.text + ("\n\n✅ To‘langan deb belgilandi" if act == "ok" else "\n\n❌ Rad etildi (balansga qaytarildi)"))
    await cb.answer("Bajarildi")
