import mimetypes
import os
import stat

import anyio
from starlette.datastructures import Headers
from starlette.responses import Response
from starlette.staticfiles import NotModifiedResponse, StaticFiles
from starlette.types import Scope

ENCODINGS = (("br", ".br"), ("gzip", ".gz"))
COMPRESSIBLE = {".js", ".css", ".svg", ".json", ".html"}


def accepted_encodings(scope: Scope) -> set[str]:
    header = Headers(scope=scope).get("accept-encoding", "")
    return {part.split(";")[0].strip().lower() for part in header.split(",") if part.strip()}


def content_type(path: str) -> str | None:
    media, _ = mimetypes.guess_type(path)
    if media and media.startswith("text/"):
        return f"{media}; charset=utf-8"
    return media


class PrecompressedFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        if scope["method"] in ("GET", "HEAD") and os.path.splitext(path)[1] in COMPRESSIBLE:
            packed = await self.precompressed(path, scope)
            if packed is not None:
                return packed
        return await super().get_response(path, scope)

    async def regular_file(self, path: str):
        try:
            full_path, stat_result = await anyio.to_thread.run_sync(self.lookup_path, path)
        except (OSError, ValueError):
            return None, None
        if stat_result is not None and stat.S_ISREG(stat_result.st_mode):
            return full_path, stat_result
        return None, None

    async def precompressed(self, path: str, scope: Scope) -> Response | None:
        accepted = accepted_encodings(scope)
        wanted = [(name, suffix) for name, suffix in ENCODINGS if name in accepted]
        if not wanted:
            return None
        original, _ = await self.regular_file(path)
        if original is None:
            return None
        for name, suffix in wanted:
            full_path, stat_result = await self.regular_file(path + suffix)
            if full_path is None:
                continue
            response = self.file_response(full_path, stat_result, scope)
            response.headers["vary"] = "Accept-Encoding"
            if not isinstance(response, NotModifiedResponse):
                response.headers["content-encoding"] = name
                response.headers["content-type"] = content_type(path) or "application/octet-stream"
            return response
        return None
