from datetime import date, datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import UserActivity

LOCAL_OFFSET = timedelta(hours=3)

seen: set[tuple[int, date]] = set()


def today() -> date:
    return (datetime.now(timezone.utc) + LOCAL_OFFSET).date()


def record(db: Session, user_id: int) -> None:
    key = (user_id, today())
    if key in seen:
        return
    if any(day != key[1] for _, day in seen):
        seen.clear()
    try:
        with db.begin_nested():
            db.add(UserActivity(user_id=user_id, day=key[1]))
    except IntegrityError:
        pass
    seen.add(key)
