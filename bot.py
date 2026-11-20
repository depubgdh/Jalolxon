"""Telegram bot (aiogram 3): /start, Mini App tugmasi, yechib olishni bot ichidan tasdiqlash."""
from aiogram import Router, F
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

import api
import config
import db

router = Router()


def open_kb(text="🎮 O‘yinlarni ochish"):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, web_app=WebAppInfo(url=config.WEBAPP_URL))]])


@router.message(CommandStart())
async def start(m: Message, command: CommandObject):
    arg = (command.args or "").strip()
    ref = arg[4:] if arg.startswith("ref_") else None
    u = m.from_user
    _, is_new, inviter, paid = db.ensure_user(u.id, u.username or "", u.first_name or "", "", ref)
    if is_new and inviter and paid:
        try:
            await m.bot.send_message(inviter, f"🎉 Do‘stingiz qo‘shildi! +{paid} so‘m bonus.")
        except Exception:
            pass
    await m.answer("Salom! 🎮 Paper.io va Slither o‘yinlarini tekin o‘ynang, vaqtingiz uchun so‘m yig‘ing va do‘stlaringizni taklif qiling.", reply_markup=open_kb())


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
