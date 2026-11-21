"""Ishga tushirish: bot (polling) + veb-server bitta jarayonda."""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiohttp import web

import bot as bot_mod
import config
import db
import server
import videos


async def main():
    logging.basicConfig(level=logging.INFO)
    if not config.BOT_TOKEN or not config.WEBAPP_URL:
        raise SystemExit("BOT_TOKEN va WEBAPP_URL ni sozlang (.env.example ga qarang)")
    db.init_db()
    videos.init()
    bot = Bot(config.BOT_TOKEN)
    if not config.BOT_USERNAME:
        config.BOT_USERNAME = (await bot.get_me()).username
    runner = web.AppRunner(server.make_app())
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", config.PORT).start()
    dp = Dispatcher()
    dp.include_router(bot_mod.router)
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
