"""aiohttp veb-server: Mini App (index.html) va /api."""
import json
import pathlib

import re

from aiohttp import web

import api
import db

ROOT = pathlib.Path(__file__).parent
NO_STORE = {"Cache-Control": "no-store"}


async def index(request):
    return web.Response(text=(ROOT / "index.html").read_text(encoding="utf-8"), content_type="text/html", headers=NO_STORE)


async def video_js(request):
    """YouTube video moduli (alohida fayl): index.html uni <script src="/video.js"> bilan ulaydi."""
    return web.Response(text=(ROOT / "video.js").read_text(encoding="utf-8"), content_type="application/javascript", headers=NO_STORE)


async def media(request):
    """Admin yuklagan rasm/GIF/video (o'yin kartalari, /start rasmi, reklamalar). ?v=<versiya> bilan keshlanadi. Video uchun Range (iOS talab qiladi)."""
    key = request.match_info["key"]
    row = db.media_get(key) if key in db.MEDIA_KEYS else None
    if not row:
        return web.Response(status=404)
    data = bytes(row["data"])
    hdr = {"Cache-Control": "public, max-age=31536000, immutable", "Accept-Ranges": "bytes"}
    rng = request.headers.get("Range", "")
    m = re.match(r"bytes=(\d*)-(\d*)$", rng.strip()) if rng else None
    if m and (m.group(1) or m.group(2)):
        n = len(data)
        if m.group(1):
            lo = int(m.group(1)); hi = int(m.group(2)) if m.group(2) else n - 1
        else:
            lo = max(0, n - int(m.group(2))); hi = n - 1
        hi = min(hi, n - 1)
        if lo > hi or lo >= n:
            return web.Response(status=416, headers={"Content-Range": f"bytes */{n}"})
        hdr["Content-Range"] = f"bytes {lo}-{hi}/{n}"
        return web.Response(status=206, body=data[lo:hi + 1], content_type=row["mime"], headers=hdr)
    return web.Response(body=data, content_type=row["mime"], headers=hdr)


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
    app = web.Application(client_max_size=1024 * 1024 * 12)
    app.router.add_get("/", index)
    app.router.add_get("/health", lambda r: web.Response(text="ok"))
    app.router.add_get("/video.js", video_js)
    app.router.add_get("/media/{key}", media)
    app.router.add_post("/api/{path:.*}", handle_api)
    return app
