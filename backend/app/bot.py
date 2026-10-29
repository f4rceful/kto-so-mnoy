import asyncio
import hashlib
import hmac
import logging
import re
import time

import httpx
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from . import botcmd, notifications, terms
from .config import settings
from .db import SessionLocal, User
from .max_client import max_client
from .routers.invitations import apply_decision

log = logging.getLogger(__name__)

DECISION_PAYLOAD = re.compile(r"(acc|dec):(\d{1,9})")
RETRY_BASE, RETRY_MAX = 5, 60
WEBHOOK_PATH = "/api/bot/webhook"

status = {"enabled": False, "mode": "polling", "last_ok": None, "failures": 0, "last_error": ""}

router = APIRouter()


def mark_reachable(user_id: int, state: str, name: str = "") -> None:
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None:
            user = User(id=user_id, name=name[:128])
            db.add(user)
        user.bot_state = state
        user.bot_fails = 0
        db.commit()


def sender_of(update: dict) -> tuple[int | None, str]:
    user = update.get("user") or (update.get("message") or {}).get("sender") or (update.get("callback") or {}).get("user") or {}
    return user.get("user_id"), user.get("name") or user.get("first_name") or ""


async def on_started(update: dict) -> None:
    user_id, name = sender_of(update)
    if user_id is None:
        return
    mark_reachable(user_id, "ok", name)
    reply = botcmd.start_reply(update.get("payload") or "")
    await max_client.send_message(user_id, reply.text, reply.buttons)


async def on_stopped(update: dict) -> None:
    user_id, name = sender_of(update)
    if user_id is not None:
        mark_reachable(user_id, "blocked", name)


async def on_message(update: dict) -> None:
    message = update.get("message") or {}
    user_id, name = sender_of(update)
    if user_id is None:
        return
    mark_reachable(user_id, "ok", name)
    text = (message.get("body") or {}).get("text") or ""
    with SessionLocal() as db:
        reply = botcmd.reply_to(db, user_id, text)
    if reply:
        await max_client.send_message(user_id, reply.text, reply.buttons)


async def on_callback(update: dict) -> None:
    if not settings.bot_quick_actions:
        return
    callback = update.get("callback") or {}
    callback_id, payload = callback.get("callback_id"), callback.get("payload") or ""
    user_id, _ = sender_of(update)
    match = DECISION_PAYLOAD.fullmatch(payload)
    if not (callback_id and user_id and match):
        return
    accept, resp_id = match.group(1) == "acc", int(match.group(2))
    with SessionLocal() as db:
        user = db.get(User, user_id)
        try:
            if user is None:
                raise HTTPException(403, "Сначала откройте приложение")
            if user.terms_version != terms.TERMS_VERSION:
                raise HTTPException(403, "Сначала откройте приложение и примите условия")
            inv, resp = apply_decision(db, resp_id, user, accept)
            who = db.get(User, resp.user_id).public_name
            answer = (
                f"Принято: {who} в списке участников ({notifications.accepted(inv)} из {inv.max_participants})"
                if accept
                else f"Отклонено: {who}"
            )
        except HTTPException as e:
            refusal = str(e.detail)
        else:
            refusal = None
    if refusal is not None:
        await max_client.answer_callback(callback_id, refusal)
        return
    await max_client.answer_callback(callback_id, answer)
    await notifications.response_decided(resp.id)
    if accept:
        await notifications.set_full(inv.id)


async def register_commands() -> None:
    await max_client.set_commands(botcmd.COMMANDS)


HANDLERS = {
    "bot_started": on_started,
    "bot_stopped": on_stopped,
    "message_created": on_message,
    "message_callback": on_callback,
}


async def handle_update(update: dict) -> None:
    handler = HANDLERS.get(update.get("update_type"))
    if handler:
        await handler(update)


async def handle_updates(updates: list[dict]) -> None:
    for update in updates:
        try:
            await handle_update(update)
        except Exception:
            log.exception("Ошибка обработки обновления %s", update)


async def poll_forever(sleep=asyncio.sleep) -> None:
    marker: int | None = None
    status["enabled"] = True
    while True:
        try:
            data = await max_client.get_updates(marker)
            marker = data.get("marker", marker)
            await handle_updates(data.get("updates", []))
            status.update(last_ok=time.time(), failures=0, last_error="")
        except asyncio.CancelledError:
            status["enabled"] = False
            raise
        except Exception as e:
            if isinstance(e, httpx.ReadTimeout):
                continue
            error = type(e).__name__
            failures = status["failures"] + 1
            status.update(failures=failures, last_error=error)
            delay = min(RETRY_BASE * 2 ** (failures - 1), RETRY_MAX)
            log.warning("Long polling: %s (%s). Повтор через %s с", error, e or "без текста", delay)
            await sleep(delay)


def webhook_secret() -> str:
    return settings.webhook_secret or hashlib.sha256(f"webhook:{settings.bot_token}".encode()).hexdigest()


def webhook_url() -> str:
    return settings.public_url.rstrip("/") + WEBHOOK_PATH


async def subscribe_forever(sleep=asyncio.sleep) -> None:
    status.update(mode="webhook", enabled=False)
    while True:
        try:
            await max_client.subscribe(webhook_url(), webhook_secret())
        except asyncio.CancelledError:
            raise
        except Exception as e:
            error = type(e).__name__
            failures = status["failures"] + 1
            status.update(failures=failures, last_error=error)
            delay = min(RETRY_BASE * 2 ** (failures - 1), RETRY_MAX)
            log.warning("Подписка на webhook: %s (%s). Повтор через %s с", error, e or "без текста", delay)
            await sleep(delay)
        else:
            status.update(enabled=True, last_ok=time.time(), failures=0, last_error="")
            log.info("Бот получает события через webhook %s", webhook_url())
            return


@router.post(WEBHOOK_PATH, include_in_schema=False)
async def webhook(request: Request, background: BackgroundTasks, x_max_bot_api_secret: str = Header(default="")):
    if not (settings.bot_token and settings.public_url):
        raise HTTPException(404)
    if not hmac.compare_digest(x_max_bot_api_secret.encode(), webhook_secret().encode()):
        raise HTTPException(401)
    try:
        update = await request.json()
    except ValueError:
        raise HTTPException(400) from None
    if not isinstance(update, dict):
        raise HTTPException(400)
    status["last_ok"] = time.time()
    background.add_task(handle_updates, [update])
    return {"ok": True}
