import hmac
import time

from fastapi import APIRouter, Header, HTTPException, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    GCCollector,
    Histogram,
    PlatformCollector,
    ProcessCollector,
    generate_latest,
)
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily
from sqlalchemy import func, select

from . import bot, notifications, reminders
from .config import settings
from .db import Invitation, ModerationLog, Report, Response as ResponseRow, SessionLocal, User, UserBan
from .max_client import max_client

LATENCY_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)
BOT_STATES = ("ok", "stale", "down", "off")

registry = CollectorRegistry()
ProcessCollector(registry=registry)
PlatformCollector(registry=registry)
GCCollector(registry=registry)

REQUESTS = Counter("kto_http_requests", "HTTP-запросы по маршрутам и кодам ответа", ["method", "route", "status"], registry=registry)
LATENCY = Histogram("kto_http_request_duration_seconds", "Время обработки HTTP-запроса", ["method", "route"], buckets=LATENCY_BUCKETS, registry=registry)
IN_PROGRESS = Gauge("kto_http_requests_in_progress", "Запросы, которые обрабатываются сейчас", registry=registry)

router = APIRouter()


def route_label(request: Request) -> str:
    route = request.scope.get("route")
    if route is None:
        return "unmatched"
    return route.path or "static"


async def track_requests(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)
    IN_PROGRESS.inc()
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        route = route_label(request)
        REQUESTS.labels(request.method, route, str(status)).inc()
        LATENCY.labels(request.method, route).observe(time.perf_counter() - started)
        IN_PROGRESS.dec()


def grouped(db, column, *where) -> dict:
    return dict(db.execute(select(column, func.count()).where(*where).group_by(column)).all())


def total(db, model, *where) -> int:
    return db.scalar(select(func.count()).select_from(model).where(*where)) or 0


def database_metrics(db) -> list:
    users = GaugeMetricFamily("kto_users", "Пользователи по состоянию", labels=["state"])
    users.add_metric(["registered"], total(db, User))
    users.add_metric(["onboarded"], total(db, User, User.onboarded.is_(True)))
    users.add_metric(["banned"], total(db, User, User.banned.is_(True)))

    by_status = grouped(db, Invitation.status)
    invitations = GaugeMetricFamily("kto_invitations", "Приглашения по статусу", labels=["status"])
    for status in ("open", "closed"):
        invitations.add_metric([status], by_status.get(status, 0))
    hidden = GaugeMetricFamily("kto_invitations_hidden", "Скрытые приглашения")
    hidden.add_metric([], total(db, Invitation, Invitation.hidden.is_(True)))
    created = CounterMetricFamily("kto_invitations_created", "Создано приглашений за всё время")
    created.add_metric([], sum(by_status.values()))

    answers = grouped(db, ResponseRow.status)
    responses = GaugeMetricFamily("kto_responses", "Отклики по статусу", labels=["status"])
    for status in ("pending", "accepted", "declined"):
        responses.add_metric([status], answers.get(status, 0))
    responded = CounterMetricFamily("kto_responses_created", "Создано откликов за всё время")
    responded.add_metric([], sum(answers.values()))

    reports_open = GaugeMetricFamily("kto_reports_open", "Жалобы, ждущие решения")
    reports_open.add_metric([], total(db, Report, Report.resolved.is_(False)))
    reported = CounterMetricFamily("kto_reports_created", "Подано жалоб за всё время")
    reported.add_metric([], total(db, Report))

    actions = CounterMetricFamily("kto_moderation_actions", "Действия модераторов", labels=["action"])
    for action, count in sorted(grouped(db, ModerationLog.action).items()):
        actions.add_metric([action], count)
    temporary = GaugeMetricFamily("kto_bans_temporary", "Блокировки со сроком")
    temporary.add_metric([], total(db, UserBan, UserBan.until.is_not(None)))

    outbox = GaugeMetricFamily("kto_notification_outbox", "Сообщения в очереди на отправку")
    outbox.add_metric([], notifications.queue_size(db))
    return [users, invitations, hidden, created, responses, responded, reports_open, reported, actions, temporary, outbox]


def process_metrics() -> list:
    delivery = CounterMetricFamily("kto_notifications", "Отправка сообщений ботом", labels=["result"])
    for result, key in (("sent", "sent"), ("failed", "failed"), ("retried", "retries")):
        delivery.add_metric([result], max_client.stats[key])

    reminded = CounterMetricFamily("kto_reminders", "Отправленные напоминания о встречах")
    reminded.add_metric([], reminders.status["sent"])
    last_run = GaugeMetricFamily("kto_reminders_last_run_timestamp_seconds", "Когда последний раз отработали напоминания")
    last_run.add_metric([], reminders.status["last_run"] or 0)

    state = bot.health_state()
    bot_state = GaugeMetricFamily("kto_bot_state", "Состояние бота (1 у текущего)", labels=["state"])
    for name in BOT_STATES:
        bot_state.add_metric([name], 1 if name == state else 0)
    return [delivery, reminded, last_run, bot_state]


class AppCollector:
    def collect(self):
        db_up = GaugeMetricFamily("kto_db_up", "База данных отвечает")
        try:
            with SessionLocal() as db:
                families = database_metrics(db)
            db_up.add_metric([], 1)
        except Exception:
            families = []
            db_up.add_metric([], 0)
        yield db_up
        yield from families
        yield from process_metrics()


registry.register(AppCollector())


@router.get("/metrics", include_in_schema=False)
def metrics(authorization: str = Header(default="")):
    if not settings.metrics_token:
        raise HTTPException(404, "Not Found")
    if not hmac.compare_digest(authorization.encode(), f"Bearer {settings.metrics_token}".encode()):
        raise HTTPException(401, "Неверный токен")
    return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
