import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.orm import Session

from . import bot, notifications, reminders, safety
from .config import settings
from .db import init_db
from .deps import get_db
from .max_client import max_client
from .routers import invitations, profile

WEBAPP_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"
BOT_STALE_AFTER = 120

log = logging.getLogger(__name__)


def _start_background(name: str, coro) -> asyncio.Task:
    def report_crash(task: asyncio.Task) -> None:
        if not task.cancelled() and task.exception():
            log.error("Фоновая задача «%s» остановилась из-за ошибки", name, exc_info=task.exception())

    task = asyncio.create_task(coro)
    task.add_done_callback(report_crash)
    return task


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    tasks = []
    if settings.bot_token:
        await bot.register_commands()
        if settings.public_url:
            receiver = _start_background("подписка на webhook", bot.subscribe_forever())
        else:
            await max_client.unsubscribe_all()
            receiver = _start_background("бот", bot.poll_forever())
        tasks = [
            receiver,
            _start_background("напоминания", reminders.remind_forever()),
            _start_background("очередь уведомлений", notifications.drain_forever()),
        ]
    yield
    for task in tasks:
        task.cancel()
    await max_client.close()


app = FastAPI(title="Кто со мной?", lifespan=lifespan)


class GZipUnlessRange(GZipMiddleware):
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and any(k == b"range" for k, _ in scope["headers"]):
            await self.app(scope, receive, send)
        else:
            await super().__call__(scope, receive, send)


app.add_middleware(GZipUnlessRange, minimum_size=500)
app.include_router(profile.router)
app.include_router(invitations.router)
app.include_router(safety.router)
app.include_router(safety.admin)
app.include_router(bot.router)


@app.middleware("http")
async def cache_headers(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif not path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(Exception)
async def unexpected_error(request, exc: Exception):
    log.error("Необработанная ошибка в %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse({"detail": "Что-то пошло не так на сервере. Попробуйте ещё раз чуть позже."}, status_code=500)


def bot_state() -> str:
    if not settings.bot_token:
        return "off"
    if not bot.status["enabled"]:
        return "down"
    if bot.status.get("mode") == "webhook":
        return "ok"
    last = bot.status["last_ok"]
    return "ok" if last and time.time() - last < BOT_STALE_AFTER else "stale"


@app.get("/api/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        log.exception("Проверка состояния: база недоступна")
        return JSONResponse({"status": "down", "db": "error"}, status_code=503)
    bot_health = bot_state()
    return {
        "status": "ok" if bot_health in ("ok", "off") else "degraded",
        "db": "ok",
        "bot": bot_health,
        "notifications": max_client.stats | {"last_error": max_client.last_error, "queued": notifications.queue_size(db)},
        "reminders": {"last_run": reminders.status["last_run"], "sent": reminders.status["sent"]},
    }


@app.get("/admin", include_in_schema=False)
def admin_page():
    page = WEBAPP_DIR / "admin.html"
    if not page.exists():
        raise HTTPException(404, "Панель модератора не собрана: cd frontend && npm run build")
    return FileResponse(page)


if not WEBAPP_DIR.exists():
    log.warning("Нет %s: соберите фронтенд (cd frontend && npm run build)", WEBAPP_DIR)
app.mount("/", StaticFiles(directory=WEBAPP_DIR, html=True, check_dir=False), name="webapp")
