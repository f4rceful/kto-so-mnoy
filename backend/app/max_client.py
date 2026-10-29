import asyncio
import logging
import ssl
from dataclasses import dataclass
from pathlib import Path

import certifi
import httpx

from .config import settings

log = logging.getLogger(__name__)

CERTS_DIR = Path(__file__).resolve().parents[1] / "certs"

ATTEMPTS = 3
BACKOFF = (0.5, 1.5)
MAX_RETRY_AFTER = 10
UPDATE_TYPES = ("message_created", "bot_started", "bot_stopped", "message_callback")
CONCURRENCY = 8


def ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=certifi.where())
    for pem in CERTS_DIR.glob("*.pem"):
        ctx.load_verify_locations(cafile=str(pem))
    return ctx


def message_body(text: str, buttons: list[list[dict]] | None) -> dict:
    body: dict = {"text": text}
    if buttons:
        body["attachments"] = [{"type": "inline_keyboard", "payload": {"buttons": buttons}}]
    return body


@dataclass
class SendResult:
    ok: bool
    permanent: bool = False


class MaxClient:
    def __init__(self, http: httpx.AsyncClient | None = None, sleep=asyncio.sleep) -> None:
        self._http = http or httpx.AsyncClient(
            base_url=settings.max_api_url,
            headers={"Authorization": settings.bot_token},
            timeout=15,
            verify=ssl_context(),
        )
        self._sleep = sleep
        self._gate = asyncio.Semaphore(CONCURRENCY)
        self.stats = {"sent": 0, "failed": 0, "retries": 0}
        self.last_error = ""

    async def get_updates(self, marker: int | None = None, timeout: int = 30) -> dict:
        params = {"timeout": timeout, "types": ",".join(UPDATE_TYPES)}
        if marker is not None:
            params["marker"] = marker
        r = await self._http.get(
            "/updates", params=params, timeout=httpx.Timeout(timeout + 30, connect=10)
        )
        r.raise_for_status()
        return r.json()

    @staticmethod
    def _retry_delay(attempt: int, response: httpx.Response | None) -> float:
        if response is not None:
            try:
                return min(float(response.headers["Retry-After"]), MAX_RETRY_AFTER)
            except (KeyError, ValueError):
                pass
        return BACKOFF[min(attempt - 1, len(BACKOFF) - 1)]

    async def send(
        self,
        user_id: int,
        text: str,
        buttons: list[list[dict]] | None = None,
        fallback_buttons: list[list[dict]] | None = None,
    ) -> SendResult:
        attempt = 1
        while True:
            response = None
            try:
                async with self._gate:
                    response = await self._http.post(
                        "/messages", params={"user_id": user_id}, json=message_body(text, buttons), timeout=httpx.Timeout(10, connect=5)
                    )
            except httpx.TransportError as e:
                reason = f"сеть: {type(e).__name__}"
            else:
                code = response.status_code
                if code < 300:
                    self.stats["sent"] += 1
                    return SendResult(True)
                reason = f"HTTP {code}"
                if code == 400 and fallback_buttons is not None and buttons != fallback_buttons:
                    log.warning("MAX не принял клавиатуру (%s), отправляю сообщение пользователю %s без неё", response.text[:120], user_id)
                    buttons = fallback_buttons
                    continue
                if code != 429 and code < 500:
                    self._give_up(user_id, reason, response.text[:200])
                    return SendResult(False, permanent=code != 401)
            if attempt == ATTEMPTS:
                self._give_up(user_id, reason, response.text[:200] if response is not None else "")
                return SendResult(False)
            self.stats["retries"] += 1
            await self._sleep(self._retry_delay(attempt, response))
            attempt += 1

    async def send_message(
        self, user_id: int, text: str, buttons: list[list[dict]] | None = None
    ) -> bool:
        return (await self.send(user_id, text, buttons)).ok

    async def answer_callback(self, callback_id: str, text: str) -> bool:
        try:
            r = await self._http.post(
                "/answers", params={"callback_id": callback_id}, json={"message": {"text": text, "attachments": []}}, timeout=10
            )
            r.raise_for_status()
            return True
        except httpx.HTTPError as e:
            log.warning("Не удалось ответить на нажатие кнопки: %s", type(e).__name__)
            return False

    async def subscribe(self, url: str, secret: str) -> None:
        r = await self._http.post(
            "/subscriptions", json={"url": url, "update_types": list(UPDATE_TYPES), "secret": secret}, timeout=15
        )
        r.raise_for_status()
        data = r.json()
        if not data.get("success", True):
            raise RuntimeError(data.get("message") or "MAX отказал в подписке")

    async def unsubscribe_all(self) -> int:
        try:
            r = await self._http.get("/subscriptions", timeout=10)
            r.raise_for_status()
            urls = [s["url"] for s in r.json().get("subscriptions", []) if s.get("url")]
            for url in urls:
                (await self._http.delete("/subscriptions", params={"url": url}, timeout=10)).raise_for_status()
            return len(urls)
        except httpx.HTTPError as e:
            log.warning("Не удалось снять подписку webhook: %s", type(e).__name__)
            return 0

    async def set_commands(self, commands: list[dict]) -> bool:
        try:
            r = await self._http.patch("/me/commands", json={"commands": commands}, timeout=10)
            r.raise_for_status()
            return True
        except httpx.HTTPError as e:
            log.warning("Не удалось зарегистрировать команды бота: %s", type(e).__name__)
            return False

    def _give_up(self, user_id: int, reason: str, detail: str) -> None:
        self.stats["failed"] += 1
        self.last_error = reason
        log.warning("Сообщение пользователю %s не доставлено (%s) %s", user_id, reason, detail)

    @staticmethod
    def bot_link() -> str:
        return f"https://max.ru/{settings.bot_username}"

    def app_link(self, payload: str = "") -> str:
        return f"https://max.ru/{settings.bot_username}?startapp" + (f"={payload}" if payload else "")

    @staticmethod
    def profile_link(username: str) -> str:
        return f"https://max.ru/{username}"

    def open_app_button(
        self, text: str = "Открыть «Кто со мной?»", payload: str = ""
    ) -> list[list[dict]]:
        return [[{"type": "link", "text": text, "url": self.app_link(payload)}]]

    async def close(self) -> None:
        await self._http.aclose()


max_client = MaxClient()
