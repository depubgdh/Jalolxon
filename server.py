"""aiohttp veb-server: Mini App (index.html) va /api."""
import json
import pathlib

from aiohttp import web

import api
import db

ROOT = pathlib.Path(__file__).parent
NO_STORE = {"Cache-Control": "no-store"}


async def index(request):
    return web.Response(text=(ROOT / "index.html").read_text(encoding="utf-8"), content_type="text/html", headers=NO_STORE)


async def media(request):
    """Admin yuklagan rasm/GIF (o'yin kartalari, /start rasmi). ?v=<versiya> bilan keshlanadi."""
    key = request.match_info["key"]
    row = db.media_get(key) if key in db.MEDIA_KEYS else None
    if not row:
        return web.Response(status=404)
    return web.Response(body=bytes(row["data"]), content_type=row["mime"], headers={"Cache-Control": "public, max-age=31536000, immutable"})


async def handle_api(request):
    path = request.match_info["path"]
    try:
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
    except Exception:
        body = {}
    try:
        data = await api.dispatch(path, body)
        return web.json_response(data, headers=NO_STORE)
    except api.ApiError as e:
        return web.json_response({"error": e.code, "message": e.msg}, status=e.status, headers=NO_STORE)
    except Exception:
        import logging
        logging.exception("api xatosi: %s", path)
        return web.json_response({"error": "server", "message": "Server xatosi"}, status=500, headers=NO_STORE)


def make_app():
    app = web.Application(client_max_size=1024 * 1024 * 4)
    app.router.add_get("/", index)
    app.router.add_get("/health", lambda r: web.Response(text="ok"))
    app.router.add_get("/media/{key}", media)
    app.router.add_post("/api/{path:.*}", handle_api)
    return app
