"""Sozlamalar (muhit o'zgaruvchilari). Boshqa hammasi — Mini App ichidagi admin panelda."""
import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x.strip().isdigit()}
WEBAPP_URL = os.getenv("WEBAPP_URL") or os.getenv("RENDER_EXTERNAL_URL", "")   # Render manzilni o'zi beradi
BOT_USERNAME = os.getenv("BOT_USERNAME", "")      # @siz, havola uchun (bo'sh bo'lsa bot o'zi aniqlaydi)
DB_PATH = os.getenv("DB_PATH", "bullplay.sqlite3")
PORT = int(os.getenv("PORT", "8080"))
AUTH_MAX_AGE = 3 * 24 * 3600
