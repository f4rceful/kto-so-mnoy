import hmac
import time
from datetime import timedelta

from fastapi import APIRouter, Header, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily, HistogramMetricFamily
from sqlalchemy import func, select

from . import activity, bans, bot, notifications, reminders
from .config import settings
from .db import Invitation, ModerationLog, QueuedMessage, Report, Response as ResponseRow, SessionLocal, User, UserActivity, UserBan
from .instruments import IN_PROGRESS, LATENCY, REQUESTS, registry
from .max_client import max_client

BOT_STATES = ("ok", "stale", "down", "off")
ACTIVE_PERIODS = (("1d", 1), ("7d", 7), ("30d", 30))
FIRST_RESPONSE_BOUNDS = (300, 900, 3600, 10800, 43200, 86400, 259200)
STARTED_AT = time.time()

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


def distinct(db, column, *joins_where) -> int:
    return db.scalar(select(func.count(func.distinct(column))).where(*joins_where)) or 0


def gauge(name: str, doc: str, value: float, labels: dict | None = None) -> GaugeMetricFamily:
    family = GaugeMetricFamily(name, doc, labels=list(labels or {}))
    family.add_metric(list((labels or {}).values()), value)
    return family


def labelled(name: str, doc: str, label: str, values: dict, family=GaugeMetricFamily):
    out = family(name, doc, labels=[label])
    for key, value in values.items():
        out.add_metric([key], value)
    return out


def product_metrics(db) -> list:
    users = labelled(
        "kto_users",
        "Пользователи по состоянию",
        "state",
        {"registered": total(db, User), "onboarded": total(db, User, User.onboarded.is_(True)), "banned": total(db, User, User.banned.is_(True))},
    )
    by_status = grouped(db, Invitation.status)
    invitations = labelled("kto_invitations", "Приглашения по статусу", "status", {s: by_status.get(s, 0) for s in ("open", "closed")})
    created = CounterMetricFamily("kto_invitations_created", "Создано приглашений за всё время")
    created.add_metric([], sum(by_status.values()))

    answers = grouped(db, ResponseRow.status)
    responses = labelled("kto_responses", "Отклики по статусу", "status", {s: answers.get(s, 0) for s in ("pending", "accepted", "declined")})
    responded = CounterMetricFamily("kto_responses_created", "Создано откликов за всё время")
    responded.add_metric([], sum(answers.values()))

    reported = CounterMetricFamily("kto_reports_created", "Подано жалоб за всё время")
    reported.add_metric([], total(db, Report))
    actions = labelled("kto_moderation_actions", "Действия модераторов", "action", dict(sorted(grouped(db, ModerationLog.action).items())), CounterMetricFamily)
    return [
        users,
        invitations,
        gauge("kto_invitations_hidden", "Скрытые приглашения", total(db, Invitation, Invitation.hidden.is_(True))),
        created,
        responses,
        responded,
        gauge("kto_reports_open", "Жалобы, ждущие решения", total(db, Report, Report.resolved.is_(False))),
        reported,
        actions,
        gauge("kto_bans_temporary", "Блокировки со сроком", total(db, UserBan, UserBan.until.is_not(None))),
    ]


def activity_metrics(db) -> list:
    today = activity.today()
    active = {label: distinct(db, UserActivity.user_id, UserActivity.day >= today - timedelta(days=days - 1)) for label, days in ACTIVE_PERIODS}
    accepted = ResponseRow.status == "accepted"
    on_invitation = ResponseRow.invitation_id == Invitation.id
    funnel = {
        "registered": total(db, User),
        "onboarded": total(db, User, User.onboarded.is_(True)),
        "created_invitation": distinct(db, Invitation.author_id),
        "got_response": db.scalar(select(func.count(func.distinct(Invitation.author_id))).join(ResponseRow, on_invitation)) or 0,
        "accepted_response": db.scalar(select(func.count(func.distinct(Invitation.author_id))).join(ResponseRow, on_invitation).where(accepted)) or 0,
        "responded": distinct(db, ResponseRow.user_id),
    }
    full = (
        select(Invitation.id)
        .join(ResponseRow, on_invitation)
        .where(accepted)
        .group_by(Invitation.id)
        .having(func.count(ResponseRow.id) >= func.max(Invitation.max_participants))
    )
    held = (
        select(func.count(func.distinct(Invitation.id)))
        .join(ResponseRow, on_invitation)
        .where(accepted, Invitation.hidden.is_(False), Invitation.when_date < today)
    )
    return [
        labelled("kto_active_users", "Пользователи, открывавшие сервис за период", "period", active),
        labelled("kto_funnel_users", "Воронка: сколько пользователей дошло до шага", "stage", funnel),
        gauge("kto_invitations_filled", "Приглашения, где набрано нужное число участников", db.scalar(select(func.count()).select_from(full.subquery())) or 0),
        gauge("kto_meetups_held", "Состоявшиеся занятия", db.scalar(held) or 0),
        first_response_histogram(db),
    ]


def first_response_histogram(db) -> HistogramMetricFamily:
    rows = db.execute(
        select(Invitation.created_at, func.min(ResponseRow.created_at))
        .join(ResponseRow, ResponseRow.invitation_id == Invitation.id)
        .group_by(Invitation.id, Invitation.created_at)
    ).all()
    delays = [max(0.0, (bans.as_utc(first) - bans.as_utc(made)).total_seconds()) for made, first in rows]
    buckets = [(str(float(bound)), sum(1 for d in delays if d <= bound)) for bound in FIRST_RESPONSE_BOUNDS]
    buckets.append(("+Inf", len(delays)))
    return HistogramMetricFamily("kto_first_response_seconds", "Через сколько приглашение получило первый отклик", buckets=buckets, sum_value=sum(delays))


def queue_metrics(db) -> list:
    oldest = db.scalar(select(func.min(QueuedMessage.created_at)))
    age = max(0.0, (bans.utcnow() - bans.as_utc(oldest)).total_seconds()) if oldest else 0.0
    return [
        gauge("kto_notification_outbox", "Сообщения в очереди на отправку", notifications.queue_size(db)),
        gauge("kto_notification_outbox_oldest_age_seconds", "Сколько ждёт самое старое сообщение в очереди", age),
    ]


def database_metrics(db) -> list:
    return product_metrics(db) + activity_metrics(db) + queue_metrics(db)


def process_metrics() -> list:
    delivery = CounterMetricFamily("kto_notifications", "Отправка сообщений ботом", labels=["result"])
    for result, key in (("sent", "sent"), ("failed", "failed"), ("retried", "retries")):
        delivery.add_metric([result], max_client.stats[key])

    reminded = CounterMetricFamily("kto_reminders", "Отправленные напоминания о встречах")
    reminded.add_metric([], reminders.status["sent"])

    state = bot.health_state()
    info = gauge("kto_build_info", "Версия запущенного сервиса", 1, {"version": settings.app_version})
    return [
        delivery,
        reminded,
        gauge("kto_reminders_last_run_timestamp_seconds", "Когда последний раз отработали напоминания", reminders.status["last_run"] or 0),
        labelled("kto_bot_state", "Состояние бота (1 у текущего)", "state", {name: 1 if name == state else 0 for name in BOT_STATES}),
        gauge("kto_bot_failures", "Подряд идущие сбои получения событий", bot.status["failures"]),
        info,
        gauge("kto_start_time_seconds", "Когда запущен сервис", STARTED_AT),
    ]


class AppCollector:
    def collect(self):
        db_up = gauge("kto_db_up", "База данных отвечает", 0)
        try:
            with SessionLocal() as db:
                families = database_metrics(db)
            db_up = gauge("kto_db_up", "База данных отвечает", 1)
        except Exception:
            families = []
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
