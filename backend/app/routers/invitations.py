import re
from datetime import date, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi import Response as HttpResponse
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload

from .. import ics, notifications
from ..blocks import blocked_pair_ids
from ..db import City, Invitation, Report, Response, User, now
from ..deps import consenting_user, current_user, get_db
from ..interests import INTERESTS
from ..notifications import EDIT_FIELDS, when_text
from ..serializers import accepted_count, inv_out

FEED_PAGE_MAX = 100
INVITATIONS_PER_HOUR = 10
DESCRIPTION_MAX = 1000
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
WHEN_FIELDS = {"when", "when_date", "when_time"}

router = APIRouter()


class InvitationIn(BaseModel):
    interest: str
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(default="", max_length=DESCRIPTION_MAX)
    when: str = Field(default="", max_length=80)
    when_date: date | None = None
    when_time: str = Field(default="", pattern=r"^(?:|(?:[01]\d|2[0-3]):[0-5]\d)$")
    fmt: str = Field(default="offline", pattern="^(offline|online)$")
    max_participants: int = Field(default=5, ge=1, le=30)


def clean_description(text: str) -> str:
    text = CONTROL_CHARS.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def check_when_date(day: date | None) -> None:
    if day is None:
        return
    today = date.today()
    if not today - timedelta(days=1) <= day <= today + timedelta(days=366):
        raise HTTPException(422, "Дата должна быть в ближайший год")


def check_interest(interest: str) -> None:
    if interest not in INTERESTS:
        raise HTTPException(422, "Неизвестный интерес")


def invitation_fields(body: InvitationIn) -> dict:
    return body.model_dump() | {
        "description": clean_description(body.description),
        "when_time": body.when_time if body.when_date else "",
    }


def fmt_label(fmt: str) -> str:
    return "онлайн" if fmt == "online" else "очно"


def load_invitation(db: Session, inv_id: int) -> Invitation:
    inv = db.scalar(
        select(Invitation)
        .where(Invitation.id == inv_id)
        .options(selectinload(Invitation.responses).selectinload(Response.user))
    )
    if not inv:
        raise HTTPException(404, "Приглашение не найдено")
    return inv


def feed_filters(me: User, hidden_authors: set[int], interest: str, fmt: str | None, scope: str) -> list:
    filters = [Invitation.status == "open", Invitation.hidden.is_(False)]
    if hidden_authors:
        filters.append(Invitation.author_id.not_in(hidden_authors))
    if scope == "school" and me.school_id:
        filters.append(Invitation.school_id == me.school_id)
    elif me.city_id:
        filters.append(Invitation.city_id == me.city_id)
    ids = [i for i in interest.split(",") if i]
    if ids:
        filters.append(Invitation.interest.in_(ids))
    if fmt:
        filters.append(Invitation.fmt == fmt)
    return filters


def title_filter(db: Session, filters: list, needle: str):
    if db.get_bind().dialect.name == "sqlite":
        rows = db.execute(select(Invitation.id, Invitation.title).where(*filters)).all()
        return Invitation.id.in_([i for i, title in rows if needle in title.lower()])
    return func.lower(Invitation.title).contains(needle, autoescape=True)


def accepted_counts():
    return (
        select(Response.invitation_id.label("invitation_id"), func.count().label("taken"))
        .where(Response.status == "accepted")
        .group_by(Response.invitation_id)
        .subquery()
    )


def date_order(since: date) -> list:
    upcoming = Invitation.when_date >= since
    return [
        case((Invitation.when_date.is_(None), 1), (upcoming, 0), else_=2),
        case((upcoming, Invitation.when_date), else_=None).asc().nulls_last(),
        case((upcoming, Invitation.when_time), else_=None).asc().nulls_last(),
        case((Invitation.when_date < since, Invitation.when_date), else_=None).desc().nulls_last(),
    ]


def feed_order(sort: str, taken) -> list:
    if sort == "old":
        return [Invitation.created_at.asc(), Invitation.id.asc()]
    newest = [Invitation.created_at.desc(), Invitation.id.desc()]
    if sort == "spots":
        return [(Invitation.max_participants - taken).desc(), *newest]
    if sort == "soon":
        return [*date_order(date.today() - timedelta(days=1)), *newest]
    return newest


def load_in_order(db: Session, ids: list[int]) -> list[Invitation]:
    if not ids:
        return []
    q = select(Invitation).where(Invitation.id.in_(ids)).options(selectinload(Invitation.responses), selectinload(Invitation.author), selectinload(Invitation.school))
    found = {i.id: i for i in db.scalars(q)}
    return [found[i] for i in ids if i in found]


@router.get("/api/invitations")
def feed(
    interest: str = "",
    fmt: str | None = Query(None, pattern="^(offline|online)$"),
    has_spots: bool = False,
    sort: str = Query("new", pattern="^(new|old|spots|soon)$"),
    scope: str = Query("school", pattern="^(school|city)$"),
    q: str = Query("", max_length=80),
    limit: int = Query(FEED_PAGE_MAX, ge=1, le=FEED_PAGE_MAX),
    offset: int = Query(0, ge=0),
    response: HttpResponse = None,
    db: Session = Depends(get_db),
    me: User = Depends(current_user),
):
    filters = feed_filters(me, blocked_pair_ids(db, me.id), interest, fmt, scope)
    needle = " ".join(q.lower().split())
    if needle:
        filters.append(title_filter(db, filters, needle))
    stmt = select(Invitation.id).where(*filters)
    taken = None
    if has_spots or sort == "spots":
        counts = accepted_counts()
        stmt = stmt.outerjoin(counts, counts.c.invitation_id == Invitation.id)
        taken = func.coalesce(counts.c.taken, 0)
        if has_spots:
            stmt = stmt.where(taken < Invitation.max_participants)
    if response is not None:
        response.headers["X-Total-Count"] = str(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    ids = list(db.scalars(stmt.order_by(*feed_order(sort, taken)).limit(limit).offset(offset)))
    return [inv_out(i, me, brief=True) for i in load_in_order(db, ids)]


@router.get("/api/invitations/mine")
def mine(db: Session = Depends(get_db), me: User = Depends(current_user)):
    q = (
        select(Invitation)
        .where(Invitation.author_id == me.id)
        .options(
            selectinload(Invitation.responses).selectinload(Response.user),
            selectinload(Invitation.author),
        )
        .order_by(Invitation.created_at.desc())
    )
    return [inv_out(i, me, with_responses=True, brief=True) for i in db.scalars(q)]


@router.get("/api/invitations/joined")
def joined(db: Session = Depends(get_db), me: User = Depends(current_user)):
    q = (
        select(Invitation)
        .join(Response, Response.invitation_id == Invitation.id)
        .where(Response.user_id == me.id, Invitation.hidden.is_(False))
        .options(selectinload(Invitation.responses), selectinload(Invitation.author))
        .order_by(Response.created_at.desc())
    )
    return [inv_out(i, me, brief=True) for i in db.scalars(q)]


def visible_to(db: Session, inv: Invitation, me: User) -> bool:
    if inv.hidden and inv.author_id != me.id:
        return False
    involved = inv.author_id == me.id or any(r.user_id == me.id for r in inv.responses)
    if involved:
        return True
    foreign = me.city_id and inv.city_id and inv.city_id != me.city_id
    return not foreign and inv.author_id not in blocked_pair_ids(db, me.id)


@router.get("/api/invitations/{inv_id}")
def detail(inv_id: int, db: Session = Depends(get_db), me: User = Depends(current_user)):
    inv = load_invitation(db, inv_id)
    if not visible_to(db, inv, me):
        raise HTTPException(404, "Приглашение не найдено")
    out = inv_out(inv, me, with_responses=True)
    out["reported"] = bool(db.scalar(select(Report.id).where(Report.invitation_id == inv.id, Report.reporter_id == me.id)))
    return out


def calendar_invitation(db: Session, inv_id: int, token: str) -> tuple[Invitation, int | None]:
    if not ics.verify(inv_id, token):
        raise HTTPException(404, "Приглашение не найдено")
    inv = load_invitation(db, inv_id)
    if inv.hidden or not inv.when_date:
        raise HTTPException(404, "Приглашение не найдено")
    offset = db.scalar(select(City.utc_offset).where(City.id == inv.city_id)) if inv.city_id else None
    return inv, offset


@router.get("/api/invitations/{inv_id}/calendar.ics")
def calendar_file(inv_id: int, t: str = "", db: Session = Depends(get_db)):
    inv, offset = calendar_invitation(db, inv_id, t)
    return HttpResponse(
        content=ics.build(inv, offset),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'inline; filename="{ics.FILENAME}"'},
    )


@router.get("/api/invitations/{inv_id}/google-calendar")
def google_calendar(inv_id: int, t: str = "", db: Session = Depends(get_db)):
    inv, offset = calendar_invitation(db, inv_id, t)
    return RedirectResponse(ics.google_link(inv, offset), status_code=302)


@router.post("/api/invitations", status_code=201)
def create(
    body: InvitationIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    me: User = Depends(consenting_user),
):
    check_interest(body.interest)
    check_when_date(body.when_date)
    recent = db.scalar(
        select(func.count()).select_from(Invitation).where(Invitation.author_id == me.id, Invitation.created_at >= now() - timedelta(hours=1))
    )
    if recent >= INVITATIONS_PER_HOUR:
        raise HTTPException(429, "Слишком много приглашений за час. Попробуйте чуть позже")
    inv = Invitation(author_id=me.id, city_id=me.city_id, school_id=me.school_id, **invitation_fields(body))
    db.add(inv)
    db.commit()
    background.add_task(notifications.new_invitation, inv.id)
    return inv_out(load_invitation(db, inv.id), me)


def change_lines(inv: Invitation, changed: set[str], old_when: str, old_fmt: str) -> list[str]:
    lines = []
    if changed & WHEN_FIELDS:
        lines.append(f"Когда: {when_text(inv.when_date, inv.when_time, inv.when)} (было: {old_when})")
    if "fmt" in changed:
        lines.append(f"Формат: {fmt_label(inv.fmt)} (было: {fmt_label(old_fmt)})")
    if "title" in changed:
        lines.append(f"Теперь называется «{inv.title}»")
    return lines


@router.put("/api/invitations/{inv_id}")
def update(
    inv_id: int,
    body: InvitationIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    me: User = Depends(consenting_user),
):
    inv = load_invitation(db, inv_id)
    if inv.author_id != me.id:
        raise HTTPException(403, "Изменить приглашение может только автор")
    if inv.status != "open":
        raise HTTPException(409, "Набор закрыт, изменить приглашение нельзя")
    check_interest(body.interest)
    if body.when_date != inv.when_date:
        check_when_date(body.when_date)
    taken = accepted_count(inv)
    if body.max_participants < taken:
        raise HTTPException(422, f"Уже принято {taken}, поставить меньше нельзя")

    new = invitation_fields(body)
    changed = {k for k in EDIT_FIELDS if getattr(inv, k) != new[k]}
    if not changed:
        return inv_out(inv, me, with_responses=True)
    old_when = when_text(inv.when_date, inv.when_time, inv.when)
    old_fmt = inv.fmt
    for key in EDIT_FIELDS:
        setattr(inv, key, new[key])
    inv.edited_at = now()
    db.commit()

    lines = change_lines(inv, changed, old_when, old_fmt)
    if lines:
        background.add_task(notifications.invitation_changed, inv.id, lines)
    return inv_out(load_invitation(db, inv.id), me, with_responses=True)


@router.post("/api/invitations/{inv_id}/respond", status_code=201)
def respond(
    inv_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    me: User = Depends(consenting_user),
):
    inv = load_invitation(db, inv_id)
    if inv.hidden:
        raise HTTPException(404, "Приглашение не найдено")
    if inv.status != "open":
        raise HTTPException(409, "Приглашение закрыто")
    if inv.author_id == me.id:
        raise HTTPException(409, "Нельзя откликнуться на своё приглашение")
    if inv.author_id in blocked_pair_ids(db, me.id):
        raise HTTPException(409, "Нельзя откликнуться на это приглашение")
    if any(r.user_id == me.id for r in inv.responses):
        raise HTTPException(409, "Вы уже откликнулись")
    resp = Response(invitation_id=inv.id, user_id=me.id)
    db.add(resp)
    db.commit()
    background.add_task(notifications.new_response, resp.id)
    return inv_out(load_invitation(db, inv_id), me)


def apply_decision(db: Session, response_id: int, me: User, accept: bool) -> tuple[Invitation, Response]:
    resp = db.get(Response, response_id)
    if not resp:
        raise HTTPException(404, "Отклик не найден")
    inv = load_invitation(db, resp.invitation_id)
    if inv.author_id != me.id:
        raise HTTPException(403, "Только автор может решать по откликам")
    if inv.status != "open" or resp.status != "pending":
        raise HTTPException(409, "Отклик уже обработан или приглашение закрыто")
    if accept and accepted_count(inv) >= inv.max_participants:
        raise HTTPException(409, "Набор участников уже полный")
    resp.status = "accepted" if accept else "declined"
    db.commit()
    return inv, resp


def decide(db: Session, background: BackgroundTasks, response_id: int, me: User, accept: bool) -> dict:
    inv, resp = apply_decision(db, response_id, me, accept)
    background.add_task(notifications.response_decided, resp.id)
    if accept:
        background.add_task(notifications.set_full, inv.id)
    return inv_out(load_invitation(db, inv.id), me, with_responses=True)


@router.post("/api/responses/{response_id}/accept")
def accept(
    response_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    me: User = Depends(consenting_user),
):
    return decide(db, background, response_id, me, True)


@router.post("/api/responses/{response_id}/decline")
def decline(
    response_id: int,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    me: User = Depends(consenting_user),
):
    return decide(db, background, response_id, me, False)


@router.post("/api/invitations/{inv_id}/close")
def close(inv_id: int, background: BackgroundTasks, db: Session = Depends(get_db), me: User = Depends(consenting_user)):
    inv = load_invitation(db, inv_id)
    if inv.author_id != me.id:
        raise HTTPException(403, "Закрыть может только автор")
    if inv.status == "open":
        inv.status = "closed"
        db.commit()
        background.add_task(notifications.set_closed, inv.id)
    return inv_out(inv, me, with_responses=True)
