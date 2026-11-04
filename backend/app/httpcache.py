import hashlib
import json

from fastapi import Request, Response


def cached_json(request: Request, payload, max_age: int | None = None) -> Response:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    etag = f'"{hashlib.sha1(body).hexdigest()[:16]}"'
    control = f"public, max-age={max_age}" if max_age else "no-cache"
    headers = {"ETag": etag, "Cache-Control": control}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(body, media_type="application/json", headers=headers)
