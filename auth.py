"""Telegram Mini App initData tekshiruvi (rasmiy usul: HMAC-SHA256)."""
import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

import config


def verify(init_data: str, token: str = None, max_age: int = None):
    """To'g'ri bo'lsa {'user': {...}, 'start_param': str} qaytaradi, bo'lmasa None."""
    token = token or config.BOT_TOKEN
    max_age = max_age or config.AUTH_MAX_AGE
    if not init_data or not token:
        return None
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        got = pairs.pop("hash", "")
        check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
        secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, got):
            return None
        if time.time() - int(pairs.get("auth_date", "0")) > max_age:
            return None
        user = json.loads(pairs.get("user", "{}"))
        if not user.get("id"):
            return None
        return {"user": user, "start_param": pairs.get("start_param", "")}
    except Exception:
        return None
