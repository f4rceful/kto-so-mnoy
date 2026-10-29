import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .blocks import blocked_pair_ids
from .config import settings
from .db import Invitation, NotificationLog, QueuedMessage, Response, SessionLocal, User
from .interests import INTERESTS
from .max_client import SendResult, max_client

log = logging.getLogger(__name__)

MAX_NOTIFY_RECIPIENTS = 200
NEW_PER_DAY = 5
NEW_SEND_CONCURRENCY = 10
QUIET_FROM, QUIET_TO = 22, 8
BOT_FAILS_TO_BLOCK = 3
DEFAULT_OFFSET = 180

MONTHS_SHORT = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
EDIT_FIELDS = ("interest", "title", "description", "when", "when_date", "when_time", "fmt", "max_participants")

QUEUE_RETRY = (60, 300, 900, 3600, 3 * 3600)
QUEUE_LOCK = timedelta(minutes=2)
QUEUE_TTL = {"new": timedelta(hours=6)}
QUEUE_TTL_DEFAULT = timedelta(hours=24)
QUEUE_BATCH = 100
QUEUE_INTERVAL = 30

ACTIVITY = {"response", "decision", "change", "full", "closed", "remind"}
ONCE = {"new", "full", "closed", "remind"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def when_text(when_date, when_time: str, note: str) -> str:
    if when_date:
        head = f"{when_date.day} {MONTHS_SHORT[when_date.month - 1]}" + (f", {when_time}" if when_time else "")
        return f"{head} · {note}" if note else head
    return note or "договоримся в чате"


def local_hour(offset_minutes: int, at: datetime) -> int:
    return (at + timedelta(minutes=offset_minutes)).hour


def is_quiet(offset_minutes: int, at: datetime) -> bool:
    hour = local_hour(offset_minutes, at)
    return hour >= QUIET_FROM or hour < QUIET_TO


def user_offset(user: User) -> int:
    return user.city.utc_offset if user.city else DEFAULT_OFFSET


def is_once(kind: str, ref: int | None) -> bool:
    return kind in ONCE and ref is not None


def new_sent_today(db: Session, user_id: int) -> int:
    since = utcnow() - timedelta(days=1)
    return db.scalar(
        select(func.count())
        .select_from(NotificationLog)
        .where(NotificationLog.user_id == user_id, NotificationLog.kind == "new", NotificationLog.created_at >= since)
    )


def already_sent(db: Session, user_id: int, kind: str, ref: int) -> bool:
    return bool(
        db.scalar(
            select(NotificationLog.id).where(
                NotificationLog.user_id == user_id, NotificationLog.kind == kind, NotificationLog.ref_id == ref
            )
        )
    )


def already_queued(db: Session, user_id: int, kind: str, ref: int) -> bool:
    return bool(
        db.scalar(
            select(QueuedMessage.id).where(
                QueuedMessage.user_id == user_id, QueuedMessage.kind == kind, QueuedMessage.ref_id == ref
            )
        )
    )


def allowed(db: Session, user: User, kind: str, ref: int | None) -> bool:
    if user.banned:
        return False
    if kind == "system":
        return True
    if kind == "new":
        if not user.notify or user.bot_state == "blocked":
            return False
        if is_quiet(user_offset(user), utcnow()):
            return False
        if new_sent_today(db, user.id) >= NEW_PER_DAY:
            return False
    elif kind in ACTIVITY and not user.notify_activity:
        return False
    if is_once(kind, ref) and (already_sent(db, user.id, kind, ref) or already_queued(db, user.id, kind, ref)):
        return False
    return True


def remember_result(user: User, result: SendResult) -> None:
    if result.ok:
        user.bot_state, user.bot_fails = "ok", 0
    elif result.permanent:
        user.bot_fails += 1
        if user.bot_fails >= BOT_FAILS_TO_BLOCK:
            user.bot_state = "blocked"


def log_sent(db: Session, user_id: int, kind: str, ref: int) -> None:
    try:
        with db.begin_nested():
            db.add(NotificationLog(user_id=user_id, kind=kind, ref_id=ref, created_at=utcnow()))
    except IntegrityError:
        pass


def enqueue(db: Session, user_id: int, kind: str, text: str, buttons, ref: int | None, fallback) -> int:
    at = utcnow()
    msg = QueuedMessage(
        user_id=user_id, kind=kind, ref_id=ref, text=text, buttons=buttons, fallback=fallback,
        next_at=at, locked_until=at + QUEUE_LOCK, created_at=at,
    )
    db.add(msg)
    db.commit()
    return msg.id


def claim(db: Session, msg_id: int) -> bool:
    at = utcnow()
    claimed = db.execute(
        update(QueuedMessage)
        .where(QueuedMessage.id == msg_id, or_(QueuedMessage.locked_until.is_(None), QueuedMessage.locked_until < at))
        .values(locked_until=at + QUEUE_LOCK)
    ).rowcount
    db.commit()
    return claimed == 1


def settle(db: Session, msg: QueuedMessage, result: SendResult) -> None:
    if result.ok or result.permanent:
        db.delete(msg)
    elif msg.attempts >= len(QUEUE_RETRY):
        log.warning("Сообщение пользователю %s снято с очереди после %s повторов", msg.user_id, msg.attempts)
        db.delete(msg)
    else:
        msg.next_at = utcnow() + timedelta(seconds=QUEUE_RETRY[msg.attempts])
        msg.attempts += 1
        msg.locked_until = None


async def send_queued(msg_id: int) -> bool:
    with SessionLocal() as db:
        msg = db.get(QueuedMessage, msg_id)
        if msg is None:
            return False
        if is_once(msg.kind, msg.ref_id) and already_sent(db, msg.user_id, msg.kind, msg.ref_id):
            db.delete(msg)
            db.commit()
            return False
        user_id, kind, ref = msg.user_id, msg.kind, msg.ref_id
        text, buttons, fallback = msg.text, msg.buttons, msg.fallback
    result = await max_client.send(user_id, text, buttons, fallback)
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is not None:
            remember_result(user, result)
        if result.ok and is_once(kind, ref):
            log_sent(db, user_id, kind, ref)
        msg = db.get(QueuedMessage, msg_id)
        if msg is not None:
            settle(db, msg, result)
        db.commit()
    return result.ok


async def deliver(user_id: int, kind: str, text: str, buttons=None, *, ref: int | None = None, fallback=None) -> bool:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.id == user_id).options(selectinload(User.city)))
        if user is None or not allowed(db, user, kind, ref):
            return False
        msg_id = enqueue(db, user_id, kind, text, buttons, ref, fallback)
    return await send_queued(msg_id)


def drop_stale(db: Session, at: datetime) -> int:
    dropped = 0
    for kind, ttl in QUEUE_TTL.items():
        dropped += db.execute(delete(QueuedMessage).where(QueuedMessage.kind == kind, QueuedMessage.created_at < at - ttl)).rowcount
    dropped += db.execute(
        delete(QueuedMessage).where(QueuedMessage.kind.not_in(QUEUE_TTL), QueuedMessage.created_at < at - QUEUE_TTL_DEFAULT)
    ).rowcount
    db.commit()
    return dropped


def due_messages(db: Session, at: datetime) -> list[int]:
    return list(
        db.scalars(
            select(QueuedMessage.id)
            .where(QueuedMessage.next_at <= at, or_(QueuedMessage.locked_until.is_(None), QueuedMessage.locked_until < at))
            .order_by(QueuedMessage.id)
            .limit(QUEUE_BATCH)
        )
    )


def queue_size(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(QueuedMessage))


async def drain_once() -> int:
    with SessionLocal() as db:
        at = utcnow()
        dropped = drop_stale(db, at)
        if dropped:
            log.warning("Из очереди убрано %s устаревших сообщений", dropped)
        ids = [i for i in due_messages(db, at) if claim(db, i)]
    sent = 0
    for msg_id in ids:
        sent += await send_queued(msg_id)
    return sent


async def drain_forever(sleep=asyncio.sleep) -> None:
    while True:
        try:
            await drain_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Сбой при разборе очереди уведомлений")
        await sleep(QUEUE_INTERVAL)


def open_button(inv_id: int, label: str = "Открыть приглашение"):
    return max_client.open_app_button(label, f"inv_{inv_id}")


def load_invitation(db: Session, inv_id: int) -> Invitation | None:
    return db.scalar(
        select(Invitation)
        .where(Invitation.id == inv_id)
        .options(selectinload(Invitation.author), selectinload(Invitation.responses).selectinload(Response.user))
    )


def accepted(inv: Invitation) -> int:
    return sum(1 for r in inv.responses if r.status == "accepted")


async def tell(user_id: int, text: str) -> None:
    await deliver(user_id, "system", text)


def new_invitation_recipients(db: Session, inv: Invitation) -> list[int]:
    q = select(User).where(User.notify.is_(True), User.banned.is_(False), User.id != inv.author_id, User.bot_state != "blocked")
    if inv.city_id:
        q = q.where(User.city_id == inv.city_id)
    skip = blocked_pair_ids(db, inv.author_id)
    interested = (u.id for u in db.scalars(q.order_by(User.id)) if inv.interest in u.interests.split(",") and u.id not in skip)
    return list(interested)[:MAX_NOTIFY_RECIPIENTS]


def new_invitation_text(inv: Invitation) -> str:
    left = inv.max_participants - accepted(inv)
    fmt = "онлайн" if inv.fmt == "online" else "очно"
    return (
        f"Новое приглашение · {INTERESTS[inv.interest]}\n«{inv.title}»\n"
        f"{when_text(inv.when_date, inv.when_time, inv.when)} · {fmt} · мест: {left}\n"
        f"Автор: {inv.author.public_name}"
    )


async def new_invitation(inv_id: int) -> None:
    with SessionLocal() as db:
        inv = load_invitation(db, inv_id)
        if inv is None or inv.hidden or inv.status != "open":
            return
        recipients = new_invitation_recipients(db, inv)
        text = new_invitation_text(inv)
    buttons = open_button(inv_id, "Посмотреть")
    gate = asyncio.Semaphore(NEW_SEND_CONCURRENCY)

    async def send(uid: int) -> None:
        async with gate:
            await deliver(uid, "new", text, buttons, ref=inv_id)

    await asyncio.gather(*(send(uid) for uid in recipients))


def quick_buttons(resp_id: int, inv_id: int):
    plain = open_button(inv_id)
    if not settings.bot_quick_actions:
        return plain, None
    quick = [
        [
            {"type": "callback", "text": "Принять", "payload": f"acc:{resp_id}", "intent": "positive"},
            {"type": "callback", "text": "Отклонить", "payload": f"dec:{resp_id}", "intent": "negative"},
        ],
        *plain,
    ]
    return quick, plain


async def new_response(resp_id: int) -> None:
    with SessionLocal() as db:
        resp = db.get(Response, resp_id)
        inv = load_invitation(db, resp.invitation_id) if resp else None
        if inv is None:
            return
        who = resp.user.public_name
        text = f"{who} откликнулся(ась) на «{inv.title}» (принято {accepted(inv)} из {inv.max_participants}).\nПримите или отклоните отклик."
        author_id, inv_id = inv.author_id, inv.id
    buttons, fallback = quick_buttons(resp_id, inv_id)
    await deliver(author_id, "response", text, buttons, fallback=fallback)


async def response_decided(resp_id: int) -> None:
    with SessionLocal() as db:
        resp = db.get(Response, resp_id)
        inv = load_invitation(db, resp.invitation_id) if resp else None
        if inv is None or resp.status == "pending":
            return
        user_id, inv_id, title = resp.user_id, inv.id, inv.title
        buttons = open_button(inv_id)
        if resp.status == "accepted":
            text = f"{inv.author.public_name} принял(а) ваш отклик на «{title}». Договоритесь о деталях в MAX."
            if inv.author.username:
                buttons = buttons + [[{"type": "link", "text": "Написать автору", "url": max_client.profile_link(inv.author.username)}]]
        else:
            text = f"К сожалению, ваш отклик на «{title}» не принят."
    await deliver(user_id, "decision", text, buttons)


async def invitation_changed(inv_id: int, lines: list[str]) -> None:
    with SessionLocal() as db:
        inv = load_invitation(db, inv_id)
        if inv is None or not lines:
            return
        text = f"Автор изменил приглашение «{inv.title}».\n" + "\n".join(lines)
        recipients = [r.user_id for r in inv.responses if r.status != "declined"]
    buttons = open_button(inv_id)
    await asyncio.gather(*(deliver(uid, "change", text, buttons) for uid in recipients))


async def set_full(inv_id: int) -> None:
    with SessionLocal() as db:
        inv = load_invitation(db, inv_id)
        if inv is None or inv.status != "open":
            return
        taken = accepted(inv)
        if taken < inv.max_participants:
            return
        author_id = inv.author_id
        text = f"Набор на «{inv.title}» собран: {taken} из {inv.max_participants}. Можно закрыть набор, чтобы больше не получать отклики."
    await deliver(author_id, "full", text, open_button(inv_id), ref=inv_id)


async def set_closed(inv_id: int) -> None:
    with SessionLocal() as db:
        inv = load_invitation(db, inv_id)
        if inv is None:
            return
        title = inv.title
        mail = [(r.user_id, r.status) for r in inv.responses if r.status != "declined"]
    buttons = open_button(inv_id)

    async def one(uid: int, status: str) -> None:
        text = (
            f"Автор закрыл набор на «{title}». Вы в списке участников, до встречи!"
            if status == "accepted"
            else f"Набор на «{title}» закрыт, ваш отклик не был принят."
        )
        await deliver(uid, "closed", text, buttons, ref=inv_id)

    await asyncio.gather(*(one(uid, status) for uid, status in mail))


async def remind(inv_id: int, soon: bool) -> None:
    with SessionLocal() as db:
        inv = load_invitation(db, inv_id)
        if inv is None or inv.hidden or inv.status != "open":
            return
        people = accepted(inv)
        start = f"сегодня в {inv.when_time}" if soon and inv.when_time else "сегодня"
        note = f" · {inv.when}" if inv.when else ""
        text = f"Напоминаем: {start} «{inv.title}»{note}."
        if people:
            text += f"\nУчастников: {people}."
        recipients = [inv.author_id] + [r.user_id for r in inv.responses if r.status == "accepted"]
    buttons = open_button(inv_id)
    await asyncio.gather(*(deliver(uid, "remind", text, buttons, ref=inv_id) for uid in recipients))
