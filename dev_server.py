"""Mahalliy sinov serveri (aiohttp va Telegram kerak emas): python dev_server.py  →  http://localhost:8770/?dev=1
Foydalanuvchi: DEV_UID (standart 7, u admin). Boshqa foydalanuvchi sifatida kirish: ?dev=1&as=123 emas — sarlavha X-Dev-User ishlatiladi."""
import asyncio
import json
import os
import pathlib
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault("DB_PATH", tempfile.mkdtemp() + "/dev.sqlite3")
os.environ.setdefault("ADMIN_IDS", "7")
os.environ.setdefault("BOT_USERNAME", "bullplay_bot")
import api, config, db, tgapi  # noqa: E402

SENT = []


async def fake_send(chat_id, text, **kw):
    SENT.append((chat_id, text)); return True


async def fake_member(chat, uid):
    return "member" if str(chat).endswith("ok") else "left"

tgapi.send_message, tgapi.member_status = fake_send, fake_member
db.init_db()
ROOT = pathlib.Path(__file__).parent


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith("/sent"):
            return self._send(200, json.dumps(SENT))
        self._send(200, (ROOT / "index.html").read_text(encoding="utf-8"), "text/html; charset=utf-8")

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); body = json.loads(self.rfile.read(n) or b"{}")
        uid = int(self.headers.get("X-Dev-User", os.environ.get("DEV_UID", "7")))
        user = {"id": uid, "first_name": "Test" if uid == 7 else f"User{uid}", "username": "testuser" if uid == 7 else f"user{uid}"}
        ref = self.headers.get("X-Dev-Ref")
        if ref:
            body["__ref"] = ref
        try:
            if ref and not db.get_user(uid):
                db.ensure_user(uid, user["username"], user["first_name"], "", ref)
            res = asyncio.run(api.dispatch(self.path[5:], body, dev_user=user))
            self._send(200, json.dumps(res))
        except api.ApiError as e:
            self._send(e.status, json.dumps({"error": e.code, "message": e.msg}))


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8770
    print("dev server", port, "DB", config.DB_PATH)
    ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
