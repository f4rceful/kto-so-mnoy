import asyncio
import logging
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import notifications
from .db import City, Invitation, SessionLocal

log = logging.getLogger(__name__)

SOON = timedelta(hours=2)
MORNING_FROM, MORNING_TO = 8, 20
INTERVAL = 60

status = {"last_run": None, "sent": 0}


def as_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def local_moment_utc(day, at: time, offset: timedelta) -> datetime:
    return datetime.combine(day, at, tzinfo=timezone.utc) - offset


def city_offsets(db: Session, invitations: list[Invitation]) -> dict[int, int]:
    city_ids = {i.city_id for i in invitations if i.city_id}
    return {c.id: c.utc_offset for c in db.scalars(select(City).where(City.id.in_(city_ids)))}


def reminder_kind(inv: Invitation, offset: timedelta, at: datetime) -> bool | None:
    local_now = at + offset
    if inv.when_date != local_now.date():
        return None
    created = as_utc(inv.created_at)
    if inv.when_time:
        hour, minute = map(int, inv.when_time.split(":"))
        start = local_moment_utc(inv.when_date, time(hour, minute), offset)
        if start - SOON <= at < start and created <= start - SOON:
            return True
    elif MORNING_FROM <= local_now.hour < MORNING_TO:
        if created <= local_moment_utc(inv.when_date, time(MORNING_FROM), offset):
            return False
    return None


def due(db: Session, at: datetime) -> list[tuple[int, bool]]:
    candidates = db.scalars(
        select(Invitation).where(
            Invitation.status == "open",
            Invitation.hidden.is_(False),
            Invitation.when_date.between((at - timedelta(days=1)).date(), (at + timedelta(days=2)).date()),
        )
    ).all()
    offsets = city_offsets(db, candidates)
    result = []
    for inv in candidates:
        offset = timedelta(minutes=offsets.get(inv.city_id, notifications.DEFAULT_OFFSET))
        soon = reminder_kind(inv, offset, at)
        if soon is not None:
            result.append((inv.id, soon))
    return result


async def run_once() -> int:
    with SessionLocal() as db:
        pending = due(db, notifications.utcnow())
    for inv_id, soon in pending:
        await notifications.remind(inv_id, soon)
    status.update(last_run=notifications.utcnow().timestamp(), sent=status["sent"] + len(pending))
    return len(pending)


async def remind_forever(sleep=asyncio.sleep) -> None:
    while True:
        try:
            await run_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Сбой при отправке напоминаний")
        await sleep(INTERVAL)
