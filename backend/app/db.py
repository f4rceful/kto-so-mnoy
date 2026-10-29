from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from .config import settings


engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class City(Base):
    __tablename__ = "cities"
    __table_args__ = (UniqueConstraint("region", "name_norm"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    region: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(80))
    name_norm: Mapped[str] = mapped_column(String(80))
    population: Mapped[int | None] = mapped_column(Integer, nullable=True)
    custom: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    utc_offset: Mapped[int] = mapped_column(Integer, default=180)


class School(Base):
    __tablename__ = "schools"
    __table_args__ = (UniqueConstraint("city_id", "name_norm"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    name_norm: Mapped[str] = mapped_column(String(120))
    custom: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    city: Mapped[City] = relationship()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(128), default="")
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    interests: Mapped[str] = mapped_column(String(500), default="")
    notify: Mapped[bool] = mapped_column(Boolean, default=True)
    onboarded: Mapped[bool] = mapped_column(Boolean, default=False)
    region: Mapped[str] = mapped_column(String(100), default="")
    city_id: Mapped[int | None] = mapped_column(ForeignKey("cities.id"), nullable=True)
    school_id: Mapped[int | None] = mapped_column(ForeignKey("schools.id"), nullable=True)
    grade: Mapped[int | None] = mapped_column(Integer, nullable=True)
    display_name: Mapped[str] = mapped_column(String(30), default="")
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terms_version: Mapped[str] = mapped_column(String(32), default="")
    banned: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_activity: Mapped[bool] = mapped_column(Boolean, default=True)
    bot_state: Mapped[str] = mapped_column(String(10), default="unknown")
    bot_fails: Mapped[int] = mapped_column(Integer, default=0)
    legacy_city: Mapped[str] = mapped_column("city", String(80), default="")
    legacy_school: Mapped[str] = mapped_column("school", String(120), default="")

    city: Mapped[City | None] = relationship()
    school: Mapped[School | None] = relationship()

    @property
    def public_name(self) -> str:
        return self.display_name or (self.name.split() or ["Участник"])[0]


class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    author_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    interest: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(120))
    when: Mapped[str] = mapped_column(String(80), default="")
    when_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    when_time: Mapped[str] = mapped_column(String(5), default="")
    description: Mapped[str] = mapped_column(String(1000), default="")
    fmt: Mapped[str] = mapped_column(String(16), default="offline")
    max_participants: Mapped[int] = mapped_column(Integer, default=5)
    status: Mapped[str] = mapped_column(String(16), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    hidden_reason: Mapped[str] = mapped_column(String(200), default="")
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    city_id: Mapped[int | None] = mapped_column(ForeignKey("cities.id"), nullable=True, index=True)
    school_id: Mapped[int | None] = mapped_column(ForeignKey("schools.id"), nullable=True, index=True)

    author: Mapped[User] = relationship()
    school: Mapped[School | None] = relationship()
    responses: Mapped[list["Response"]] = relationship(
        back_populates="invitation", cascade="all, delete-orphan"
    )


class Response(Base):
    __tablename__ = "responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invitation_id: Mapped[int] = mapped_column(ForeignKey("invitations.id"))
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    invitation: Mapped[Invitation] = relationship(back_populates="responses")
    user: Mapped[User] = relationship()


class NotificationLog(Base):
    __tablename__ = "notification_log"
    __table_args__ = (UniqueConstraint("user_id", "kind", "ref_id"), Index("ix_notification_log_user_kind_time", "user_id", "kind", "created_at"))

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(12))
    ref_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class QueuedMessage(Base):
    __tablename__ = "outbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    kind: Mapped[str] = mapped_column(String(12))
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    buttons: Mapped[list | None] = mapped_column(JSON, nullable=True)
    fallback: Mapped[list | None] = mapped_column(JSON, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


REPORT_REASONS = {
    "spam": "Спам или реклама",
    "abuse": "Оскорбления или неприемлемое содержание",
    "danger": "Опасное или противоправное",
    "personal": "Чужие личные данные",
    "other": "Другое",
}


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("invitation_id", "reporter_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invitation_id: Mapped[int] = mapped_column(ForeignKey("invitations.id"), index=True)
    reporter_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(String(300), default="")
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    invitation: Mapped[Invitation] = relationship()


class Block(Base):
    __tablename__ = "blocks"
    __table_args__ = (UniqueConstraint("blocker_id", "blocked_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    blocker_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    blocked_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

    blocked: Mapped[User] = relationship(foreign_keys=[blocked_id])


def init_db() -> None:
    from .citylist import seed_builtin
    from .places import backfill_legacy_profiles

    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        seed_builtin(session)
        backfill_legacy_profiles(session)
        backfill_invitation_places(session)


def backfill_invitation_places(session) -> None:
    q = (
        select(Invitation)
        .join(User, Invitation.author_id == User.id)
        .where(Invitation.city_id.is_(None), User.city_id.is_not(None))
    )
    for inv in session.scalars(q).all():
        inv.city_id, inv.school_id = inv.author.city_id, inv.author.school_id
    session.commit()
