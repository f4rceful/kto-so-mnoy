from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .db import Invitation, ModerationLog, User, UserBan

BAN_REASON = "Автор заблокирован"
MOSCOW = timedelta(hours=3)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def moscow_text(moment: datetime) -> str:
    return (as_utc(moment) + MOSCOW).strftime("%d.%m %H:%M")


def restore_hidden(db: Session, user_id: int) -> int:
    restored = 0
    q = select(Invitation).where(Invitation.author_id == user_id, Invitation.hidden.is_(True), Invitation.hidden_reason == BAN_REASON)
    for inv in db.scalars(q):
        inv.hidden, inv.hidden_reason = False, ""
        restored += 1
    return restored


def lift(db: Session, user: User) -> int:
    user.banned = False
    db.execute(delete(UserBan).where(UserBan.user_id == user.id))
    return restore_hidden(db, user.id)


def expire(db: Session, user: User) -> int:
    restored = lift(db, user)
    db.add(
        ModerationLog(
            action="unban",
            target_type="user",
            target_id=user.id,
            target_label=user.name[:160],
            detail=f"срок блокировки закончился; возвращено приглашений: {restored}",
            source="auto",
        )
    )
    return restored


def is_expired(ban: UserBan | None, at: datetime) -> bool:
    return ban is not None and ban.until is not None and as_utc(ban.until) <= at


def expire_if_due(db: Session, user: User, at: datetime | None = None) -> bool:
    if not user.banned or not is_expired(db.get(UserBan, user.id), at or utcnow()):
        return False
    expire(db, user)
    return True


def expire_due(db: Session, at: datetime) -> list[int]:
    lifted = []
    for ban in list(db.scalars(select(UserBan).where(UserBan.until.is_not(None), UserBan.until <= at))):
        user = db.get(User, ban.user_id)
        if user is not None and user.banned:
            expire(db, user)
            lifted.append(user.id)
        else:
            db.delete(ban)
    db.commit()
    return lifted


def denial(db: Session, user: User) -> str:
    ban = db.get(UserBan, user.id)
    if ban is not None and ban.until is not None:
        return f"Доступ к сервису ограничен до {moscow_text(ban.until)} (МСК) за нарушение правил"
    return "Доступ к сервису ограничен за нарушение правил"
