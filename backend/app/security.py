import hashlib
import hmac
import json
import time
from urllib.parse import unquote


def validate_init_data(init_data: str, bot_token: str, ttl: int = 86400) -> dict | None:
    if not init_data or not bot_token:
        return None
    pairs = [p.split("=", 1) for p in init_data.split("&") if "=" in p]
    hashes = [v for k, v in pairs if k == "hash"]
    if len(hashes) != 1:
        return None
    params = sorted((k, unquote(v)) for k, v in pairs if k != "hash")
    launch_params = "\n".join(f"{k}={v}" for k, v in params)
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret, launch_params.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, hashes[0]):
        return None
    data = dict(params)
    try:
        if ttl and time.time() - int(data["auth_date"]) > ttl:
            return None
        if "user" in data:
            data["user"] = json.loads(data["user"])
    except (KeyError, ValueError):
        return None
    return data
