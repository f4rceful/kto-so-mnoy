import hmac
import math
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from . import bans, places
from .config import settings
from .db import REPORT_REASONS, Block, Invitation, ModerationLog, Report, Response, School, User, UserBan, now
from .deps import current_user, get_db
from .interests import INTERESTS
from .names import norm_school
from .notifications import tell as tell_author
from .regions import GRADES
from .routers.invitations import DESCRIPTION_MAX, clean_description
from .routers.profile import DISPLAY_NAME_MAX
from .serializers import profile_complete, utc_iso

REPORT_HIDE_THRESHOLD = 3
REPORTS_PER_DAY = 10
ADMIN_MAX_FAILURES = 5
ADMIN_LOCK_SECONDS = 300
ADMIN_PAGE_MAX = 200
BAN_REASON = bans.BAN_REASON
DEFAULT_BAN_REASON = "Нарушение правил"
METRICS_DAYS = 7
METRICS_RANGES = (7, 14, 30)
METRICS_UTC_OFFSET = timedelta(hours=3)

clock = time.monotonic
failures: dict[str, list[float]] = {}

router = APIRouter(prefix="/api")
admin = APIRouter(prefix="/api/admin")


class ReportIn(BaseModel):
    reason: str
    text: str = Field(default="", max_length=300)


@router.get("/report-reasons")
def report_reasons():
    return [{"id": k, "name": v} for k, v in REPORT_REASONS.items()]


def visible_invitation(db: Session, inv_id: int, me: User) -> Invitation:
    inv = db.get(Invitation, inv_id)
    if not inv or (inv.hidden and inv.author_id != me.id):
        raise HTTPException(404, "Приглашение не найдено")
    return inv


@router.post("/invitations/{inv_id}/report", status_code=201)
def report(
    inv_id: int,
    body: ReportIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    me: User = Depends(current_user),
):
    if body.reason not in REPORT_REASONS:
        raise HTTPException(422, "Выберите причину из списка")
    inv = visible_invitation(db, inv_id, me)
    if inv.author_id == me.id:
        raise HTTPException(409, "Нельзя пожаловаться на своё приглашение")
    if db.scalar(select(Report.id).where(Report.invitation_id == inv.id, Report.reporter_id == me.id)):
        raise HTTPException(409, "Вы уже отправили жалобу на это приглашение")
    recent = db.scalar(
        select(func.count()).select_from(Report).where(Report.reporter_id == me.id, Report.created_at >= now() - timedelta(days=1))
    )
    if recent >= REPORTS_PER_DAY:
        raise HTTPException(429, "Слишком много жалоб за сутки. Попробуйте завтра")
    db.add(Report(invitation_id=inv.id, reporter_id=me.id, reason=body.reason, text=" ".join(body.text.split())))
    db.commit()

    reporters = db.scalar(
        select(func.count(func.distinct(Report.reporter_id))).where(Report.invitation_id == inv.id, Report.resolved.is_(False))
    )
    if reporters >= REPORT_HIDE_THRESHOLD and not inv.hidden:
        inv.hidden, inv.hidden_reason = True, "Жалобы пользователей"
        db.commit()
        background.add_task(tell_author, inv.author_id, f"Ваше приглашение «{inv.title}» скрыто до проверки: на него пожаловались. Если это ошибка, мы разберёмся.")
    return {"ok": True}


@router.post("/invitations/{inv_id}/block-author")
def block_author(inv_id: int, db: Session = Depends(get_db), me: User = Depends(current_user)):
    inv = visible_invitation(db, inv_id, me)
    if inv.author_id == me.id:
        raise HTTPException(409, "Нельзя скрыть самого себя")
    if not db.scalar(select(Block.id).where(Block.blocker_id == me.id, Block.blocked_id == inv.author_id)):
        db.add(Block(blocker_id=me.id, blocked_id=inv.author_id))
        db.commit()
    return {"ok": True}


@router.get("/blocks")
def my_blocks(db: Session = Depends(get_db), me: User = Depends(current_user)):
    rows = db.scalars(select(Block).where(Block.blocker_id == me.id).options(selectinload(Block.blocked)).order_by(Block.id.desc()))
    return [{"id": b.id, "name": b.blocked.public_name} for b in rows]


@router.delete("/blocks/{block_id}")
def unblock(block_id: int, db: Session = Depends(get_db), me: User = Depends(current_user)):
    block = db.get(Block, block_id)
    if not block or block.blocker_id != me.id:
        raise HTTPException(404, "Не найдено")
    db.delete(block)
    db.commit()
    return {"ok": True}


def lock_remaining(source: str) -> int:
    at = clock()
    recent = [t for t in failures.get(source, []) if at - t < ADMIN_LOCK_SECONDS]
    if recent:
        failures[source] = recent
    else:
        failures.pop(source, None)
    if len(recent) < ADMIN_MAX_FAILURES:
        return 0
    return math.ceil(recent[0] + ADMIN_LOCK_SECONDS - at)


def admin_only(request: Request, x_admin_key: str = Header(default="")) -> str:
    if not settings.admin_key:
        raise HTTPException(404, "Not Found")
    source = request.client.host if request.client else "-"
    wait = lock_remaining(source)
    if wait:
        raise HTTPException(
            429,
            f"Слишком много попыток. Повторите через {math.ceil(wait / 60)} мин.",
            headers={"Retry-After": str(wait)},
        )
    if not hmac.compare_digest(x_admin_key.encode(), settings.admin_key.encode()):
        failures.setdefault(source, []).append(clock())
        raise HTTPException(401, "Неверный ключ")
    failures.pop(source, None)
    return source


class HideIn(BaseModel):
    reason: str = Field(default="", max_length=200)


class BanIn(BaseModel):
    reason: str = Field(default="", max_length=200)
    days: int | None = Field(default=None, ge=1, le=365)


class UserEditIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=DISPLAY_NAME_MAX)
    grade: int | None = None
    school_id: int | None = Field(default=None, ge=1)


class SchoolEditIn(BaseModel):
    name: str = Field(min_length=2, max_length=places.SCHOOL_MAX)


class InvitationEditIn(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=120)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX)
    when: str | None = Field(default=None, max_length=80)


def find_invitation(db: Session, inv_id: int) -> Invitation:
    inv = db.get(Invitation, inv_id)
    if not inv:
        raise HTTPException(404, "Приглашение не найдено")
    return inv


def find_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    return user


def log_action(db: Session, source: str, action: str, target_type: str, target_id: int, label: str = "", detail: str = "") -> None:
    db.add(
        ModerationLog(
            action=action,
            target_type=target_type,
            target_id=target_id,
            target_label=label[:160],
            detail=detail[:300],
            source=source[:64],
        )
    )


def invitation_totals(db: Session, author_ids) -> dict[int, int]:
    if not author_ids:
        return {}
    q = select(Invitation.author_id, func.count()).where(Invitation.author_id.in_(author_ids)).group_by(Invitation.author_id)
    return dict(db.execute(q).all())


def report_totals(db: Session, author_ids) -> dict[int, int]:
    if not author_ids:
        return {}
    q = (
        select(Invitation.author_id, func.count(Report.id))
        .join(Invitation, Report.invitation_id == Invitation.id)
        .where(Invitation.author_id.in_(author_ids))
        .group_by(Invitation.author_id)
    )
    return dict(db.execute(q).all())


def ban_details(db: Session, user_ids) -> dict[int, UserBan]:
    if not user_ids:
        return {}
    return {b.user_id: b for b in db.scalars(select(UserBan).where(UserBan.user_id.in_(user_ids)))}


def resolve_reports(db: Session, inv_id: int) -> int:
    resolved = 0
    for r in db.scalars(select(Report).where(Report.invitation_id == inv_id, Report.resolved.is_(False))):
        r.resolved = True
        resolved += 1
    return resolved


def open_reports_by_invitation(db: Session) -> dict[int, list[Report]]:
    grouped: dict[int, list[Report]] = {}
    for r in db.scalars(select(Report).where(Report.resolved.is_(False)).order_by(Report.id)):
        grouped.setdefault(r.invitation_id, []).append(r)
    return grouped


def normalized(value) -> str:
    return " ".join(str(value).lower().replace("ё", "е").split())


def matches(query: str, *fields) -> bool:
    needle = normalized(query)
    return not needle or any(needle in normalized(f) for f in fields if f not in (None, ""))


def as_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def until_iso(ban: UserBan | None) -> str | None:
    return utc_iso(ban.until) if ban is not None and ban.until is not None else None


def admin_items(db: Session, invitations: list[Invitation], open_reports: dict[int, list[Report]]) -> list[dict]:
    author_ids = {inv.author_id for inv in invitations}
    totals = invitation_totals(db, author_ids)
    complaints = report_totals(db, author_ids)
    return [
        {
            "id": inv.id,
            "title": inv.title,
            "description": inv.description,
            "when": inv.when,
            "status": inv.status,
            "hidden": inv.hidden,
            "hidden_reason": inv.hidden_reason,
            "created_at": utc_iso(inv.created_at),
            "school": inv.school.name if inv.school else "",
            "responses": len(inv.responses),
            "author": {
                "id": inv.author.id,
                "name": inv.author.name,
                "username": inv.author.username,
                "banned": inv.author.banned,
                "invitations": totals.get(inv.author_id, 0),
                "reports": complaints.get(inv.author_id, 0),
            },
            "reports": [
                {"reason": REPORT_REASONS.get(r.reason, r.reason), "text": r.text, "at": utc_iso(r.created_at)}
                for r in open_reports.get(inv.id, [])
            ],
        }
        for inv in invitations
    ]


ADMIN_LOAD = (selectinload(Invitation.author), selectinload(Invitation.school), selectinload(Invitation.responses))


def load_invitations(db: Session, ids: list[int]) -> list[Invitation]:
    if not ids:
        return []
    found = {inv.id: inv for inv in db.scalars(select(Invitation).where(Invitation.id.in_(ids)).options(*ADMIN_LOAD))}
    return [found[i] for i in ids if i in found]


@admin.get("/reports", dependencies=[Depends(admin_only)])
def admin_reports(db: Session = Depends(get_db)):
    open_reports = open_reports_by_invitation(db)
    q = select(Invitation).where(or_(Invitation.hidden.is_(True), Invitation.id.in_(list(open_reports)))).options(*ADMIN_LOAD)
    items = admin_items(db, list(db.scalars(q)), open_reports)
    items.sort(key=lambda i: (-len(i["reports"]), -i["id"]))
    return {"items": items}


@admin.get("/invitations", dependencies=[Depends(admin_only)])
def admin_invitations(
    db: Session = Depends(get_db),
    q: str = Query("", max_length=80),
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=ADMIN_PAGE_MAX),
):
    if normalized(q):
        rows = db.scalars(select(Invitation).options(selectinload(Invitation.author), selectinload(Invitation.school)).order_by(Invitation.id.desc()))
        found = [
            inv.id
            for inv in rows
            if matches(q, inv.id, inv.title, inv.description, inv.author.name, inv.author.username, inv.school.name if inv.school else "")
        ]
        total, ids = len(found), found[offset : offset + limit]
    else:
        total = db.scalar(select(func.count()).select_from(Invitation)) or 0
        ids = list(db.scalars(select(Invitation.id).order_by(Invitation.id.desc()).offset(offset).limit(limit)))
    return {"items": admin_items(db, load_invitations(db, ids), open_reports_by_invitation(db)), "total": total}


@admin.get("/users", dependencies=[Depends(admin_only)])
def admin_users(
    db: Session = Depends(get_db),
    q: str = Query("", max_length=80),
    banned: bool | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=ADMIN_PAGE_MAX),
):
    query = select(User).order_by(User.id.desc())
    if banned is not None:
        query = query.where(User.banned.is_(banned))
    users = [u for u in db.scalars(query) if matches(q, u.id, u.name, u.display_name, u.username)]
    chunk = users[offset : offset + limit]
    ids = [u.id for u in chunk]
    totals, complaints, bans_by_user = invitation_totals(db, ids), report_totals(db, ids), ban_details(db, ids)
    return {
        "items": [
            {
                "id": u.id,
                "name": u.name,
                "username": u.username,
                "banned": u.banned,
                "invitations": totals.get(u.id, 0),
                "reports": complaints.get(u.id, 0),
                "ban_reason": bans_by_user[u.id].reason if u.banned and u.id in bans_by_user else "",
                "ban_until": until_iso(bans_by_user.get(u.id)) if u.banned else None,
            }
            for u in chunk
        ],
        "total": len(users),
    }


@admin.get("/log", dependencies=[Depends(admin_only)])
def admin_log(db: Session = Depends(get_db), offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=ADMIN_PAGE_MAX)):
    total = db.scalar(select(func.count()).select_from(ModerationLog)) or 0
    rows = db.scalars(select(ModerationLog).order_by(ModerationLog.id.desc()).offset(offset).limit(limit))
    return {
        "items": [
            {
                "id": r.id,
                "at": utc_iso(r.created_at),
                "action": r.action,
                "target_type": r.target_type,
                "target_id": r.target_id,
                "target_label": r.target_label,
                "detail": r.detail,
                "source": r.source,
            }
            for r in rows
        ],
        "total": total,
    }


@admin.get("/links", dependencies=[Depends(admin_only)])
def admin_links():
    return {"grafana": settings.grafana_url.strip()}


@admin.get("/stats", dependencies=[Depends(admin_only)])
def admin_stats(db: Session = Depends(get_db)):
    scalar = lambda q: db.scalar(q) or 0
    return {
        "reports": scalar(select(func.count()).select_from(Report).where(Report.resolved.is_(False))),
        "reported_invitations": scalar(select(func.count(func.distinct(Report.invitation_id))).where(Report.resolved.is_(False))),
        "hidden": scalar(select(func.count()).select_from(Invitation).where(Invitation.hidden.is_(True))),
        "banned": scalar(select(func.count()).select_from(User).where(User.banned.is_(True))),
        "invitations": scalar(select(func.count()).select_from(Invitation)),
        "users": scalar(select(func.count()).select_from(User)),
    }


@admin.get("/metrics", dependencies=[Depends(admin_only)])
def admin_metrics(db: Session = Depends(get_db), days: int = METRICS_DAYS):
    if days not in METRICS_RANGES:
        raise HTTPException(422, "Период — 7, 14 или 30 дней")
    today = (now() + METRICS_UTC_OFFSET).date()
    first = today - timedelta(days=days - 1)
    since = datetime(first.year, first.month, first.day, tzinfo=timezone.utc) - METRICS_UTC_OFFSET

    def per_day(column, *conditions) -> Counter:
        counts: Counter = Counter()
        for moment in db.scalars(select(column).where(column >= since, *conditions)):
            counts[(as_utc(moment) + METRICS_UTC_OFFSET).date()] += 1
        return counts

    created, responded = per_day(Invitation.created_at), per_day(Response.created_at)
    accepted = per_day(Response.created_at, Response.status == "accepted")
    scalar = lambda q: db.scalar(q) or 0
    held = select(func.count(func.distinct(Invitation.id))).select_from(Invitation).join(Response, Response.invitation_id == Invitation.id)
    return {
        "days": [
            {"date": day.isoformat(), "invitations": created[day], "responses": responded[day], "accepted": accepted[day]}
            for day in (first + timedelta(days=i) for i in range(days))
        ],
        "totals": {
            "invitations": scalar(select(func.count()).select_from(Invitation)),
            "responses": scalar(select(func.count()).select_from(Response)),
            "accepted": scalar(select(func.count()).select_from(Response).where(Response.status == "accepted")),
            "held": scalar(held.where(Response.status == "accepted", Invitation.hidden.is_(False), Invitation.when_date < today)),
        },
    }


@admin.post("/invitations/{inv_id}/hide")
def admin_hide(inv_id: int, body: HideIn, background: BackgroundTasks, db: Session = Depends(get_db), source: str = Depends(admin_only)):
    inv = find_invitation(db, inv_id)
    inv.hidden, inv.hidden_reason = True, body.reason.strip() or "Решение модератора"
    resolve_reports(db, inv.id)
    log_action(db, source, "hide", "invitation", inv.id, inv.title, inv.hidden_reason)
    db.commit()
    background.add_task(tell_author, inv.author_id, f"Ваше приглашение «{inv.title}» скрыто модератором: {inv.hidden_reason}.")
    return {"ok": True}


@admin.post("/invitations/{inv_id}/restore")
def admin_restore(inv_id: int, db: Session = Depends(get_db), source: str = Depends(admin_only)):
    inv = find_invitation(db, inv_id)
    inv.hidden, inv.hidden_reason = False, ""
    resolve_reports(db, inv.id)
    log_action(db, source, "restore", "invitation", inv.id, inv.title)
    db.commit()
    return {"ok": True}


@admin.post("/invitations/{inv_id}/dismiss")
def admin_dismiss(inv_id: int, db: Session = Depends(get_db), source: str = Depends(admin_only)):
    inv = find_invitation(db, inv_id)
    resolved = resolve_reports(db, inv.id)
    log_action(db, source, "dismiss", "invitation", inv.id, inv.title, f"закрыто жалоб: {resolved}")
    db.commit()
    return {"ok": True}


@admin.post("/users/{user_id}/ban")
def admin_ban(
    user_id: int,
    background: BackgroundTasks,
    body: BanIn | None = None,
    db: Session = Depends(get_db),
    source: str = Depends(admin_only),
):
    user = find_user(db, user_id)
    reason = (body.reason.strip() if body else "") or DEFAULT_BAN_REASON
    until = now() + timedelta(days=body.days) if body and body.days else None
    previous = db.get(UserBan, user.id) if user.banned else None
    unchanged = previous is not None and until is None and previous.until is None and previous.reason == reason
    user.banned = True
    for inv in db.scalars(select(Invitation).where(Invitation.author_id == user.id, Invitation.hidden.is_(False))):
        inv.hidden, inv.hidden_reason = True, BAN_REASON
    if not unchanged:
        existing = db.get(UserBan, user.id)
        if existing:
            existing.reason, existing.until, existing.created_at = reason, until, now()
        else:
            db.add(UserBan(user_id=user.id, reason=reason, until=until))
        detail = f"{reason} (до {bans.moscow_text(until)} МСК)" if until else reason
        log_action(db, source, "ban", "user", user.id, user.name, detail)
    db.commit()
    if not unchanged:
        span = f" до {bans.moscow_text(until)} (МСК)" if until else ""
        background.add_task(tell_author, user.id, f"Ваш доступ к «Кто со мной?» ограничен модератором{span}: {reason}.", True)
    return {"ok": True}


@admin.post("/users/{user_id}/unban")
def admin_unban(user_id: int, background: BackgroundTasks, db: Session = Depends(get_db), source: str = Depends(admin_only)):
    user = find_user(db, user_id)
    was_banned = user.banned
    restored = bans.lift(db, user)
    if was_banned:
        log_action(db, source, "unban", "user", user.id, user.name, f"возвращено приглашений: {restored}")
    db.commit()
    if was_banned:
        background.add_task(tell_author, user.id, "Доступ к «Кто со мной?» восстановлен модератором.")
    return {"ok": True, "restored": restored}


def user_profile(db: Session, user: User) -> dict:
    ban = db.get(UserBan, user.id) if user.banned else None
    invitations = list(db.scalars(select(Invitation).where(Invitation.author_id == user.id).order_by(Invitation.id.desc()).limit(50)))
    joined = db.scalar(select(func.count()).select_from(Response).where(Response.user_id == user.id)) or 0
    return {
        "id": user.id,
        "name": user.name,
        "display_name": user.display_name,
        "public_name": user.public_name,
        "username": user.username,
        "grade": user.grade,
        "region": user.region,
        "city": user.city.name if user.city else "",
        "school": user.school.name if user.school else "",
        "school_id": user.school_id,
        "school_custom": bool(user.school and user.school.custom),
        "interests": [INTERESTS[i] for i in user.interests.split(",") if i in INTERESTS],
        "notify": user.notify,
        "notify_activity": user.notify_activity,
        "bot_state": user.bot_state,
        "onboarded": user.onboarded,
        "terms_version": user.terms_version,
        "consented_at": utc_iso(user.consented_at),
        "banned": user.banned,
        "ban_reason": ban.reason if ban else "",
        "ban_until": until_iso(ban),
        "reports": report_totals(db, [user.id]).get(user.id, 0),
        "responses": joined,
        "invitations": [
            {
                "id": inv.id,
                "title": inv.title,
                "description": inv.description,
                "when": inv.when,
                "status": inv.status,
                "hidden": inv.hidden,
                "created_at": utc_iso(inv.created_at),
            }
            for inv in invitations
        ],
    }


@admin.get("/users/{user_id}", dependencies=[Depends(admin_only)])
def admin_user(user_id: int, db: Session = Depends(get_db)):
    return user_profile(db, find_user(db, user_id))


@admin.patch("/users/{user_id}")
def admin_edit_user(
    user_id: int,
    body: UserEditIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    source: str = Depends(admin_only),
):
    user = find_user(db, user_id)
    changes: list[tuple[str, object, object]] = []
    if body.display_name is not None:
        new = places.checked_name(body.display_name, "имя", DISPLAY_NAME_MAX) if body.display_name.strip() else ""
        if new != user.display_name:
            changes.append(("публичное имя", user.display_name or "—", new or "—"))
            user.display_name = new
    if body.grade is not None:
        if body.grade not in GRADES:
            raise HTTPException(422, "Класс — от 5 до 11")
        if body.grade != user.grade:
            changes.append(("класс", user.grade or "—", body.grade))
            user.grade = body.grade
    if body.school_id is not None:
        school = db.get(School, body.school_id)
        if school is None:
            raise HTTPException(404, "Школа не найдена")
        if school.id != user.school_id:
            changes.append(("школа", user.school.name if user.school else "—", school.name))
            user.school, user.city, user.region = school, school.city, school.city.region
    if changes:
        user.onboarded = profile_complete(user)
        log_action(db, source, "edit_user", "user", user.id, user.name, "; ".join(f"{label}: {old} → {new}" for label, old, new in changes))
        db.commit()
        background.add_task(tell_author, user.id, "Модератор исправил данные вашего профиля: " + ", ".join(label for label, _, _ in changes) + ".")
    return user_profile(db, user)


@admin.get("/schools", dependencies=[Depends(admin_only)])
def admin_schools(db: Session = Depends(get_db), q: str = Query("", max_length=120), limit: int = Query(20, ge=1, le=50)):
    found = places.find_schools(db, q, limit)
    members = places.school_members(db, [s.id for s in found])
    return {
        "items": [
            {"id": s.id, "name": s.name, "custom": s.custom, "city": s.city.name, "region": s.city.region, "members": members.get(s.id, 0)}
            for s in found
        ]
    }


@admin.patch("/schools/{school_id}")
def admin_rename_school(school_id: int, body: SchoolEditIn, db: Session = Depends(get_db), source: str = Depends(admin_only)):
    school = db.get(School, school_id)
    if school is None:
        raise HTTPException(404, "Школа не найдена")
    if not school.custom:
        raise HTTPException(409, "Названия школ из справочника не меняются")
    name = places.checked_name(body.name, "название школы", places.SCHOOL_MAX)
    norm = norm_school(name)
    clash = db.scalar(select(School.id).where(School.city_id == school.city_id, School.name_norm == norm, School.id != school.id))
    if clash:
        raise HTTPException(409, "Такая школа в этом городе уже есть. Лучше перенести учеников в неё")
    old = school.name
    school.name, school.name_norm = name, norm
    log_action(db, source, "rename_school", "school", school.id, name, f"{old} → {name}")
    db.commit()
    return {"id": school.id, "name": school.name}


@admin.patch("/invitations/{inv_id}")
def admin_edit_invitation(
    inv_id: int,
    body: InvitationEditIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    source: str = Depends(admin_only),
):
    inv = find_invitation(db, inv_id)
    old_title = inv.title
    changes: list[tuple[str, str, str]] = []
    if body.title is not None:
        new = " ".join(body.title.split())
        if len(new) < 3:
            raise HTTPException(422, "Название — от 3 символов")
        if new != inv.title:
            changes.append(("название", inv.title, new))
            inv.title = new
    if body.description is not None:
        new = clean_description(body.description)
        if new != inv.description:
            changes.append(("описание", inv.description or "—", new or "—"))
            inv.description = new
    if body.when is not None:
        new = " ".join(body.when.split())
        if new != inv.when:
            changes.append(("заметка о времени", inv.when or "—", new or "—"))
            inv.when = new
    if changes:
        inv.edited_at = now()
        shorten = lambda text: text if len(text) <= 40 else text[:39] + "…"
        log_action(db, source, "edit_inv", "invitation", inv.id, old_title, "; ".join(f"{label}: «{shorten(old)}» → «{shorten(new)}»" for label, old, new in changes))
        db.commit()
        background.add_task(tell_author, inv.author_id, f"Модератор исправил ваше приглашение «{inv.title}»: " + ", ".join(label for label, _, _ in changes) + ".")
    return admin_items(db, load_invitations(db, [inv.id]), open_reports_by_invitation(db))[0]
