import re
from datetime import date, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi import Response as HttpResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .. import notifications
from ..blocks import blocked_pair_ids
from ..db import Invitation, Report, Response, User, now
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


def feed_query(me: User, hidden_authors: set[int], interest: str, fmt: str | None, scope: str, sort: str):
    query = (
        select(Invitation)
        .where(Invitation.status == "open", Invitation.hidden.is_(False))
        .options(selectinload(Invitation.responses), selectinload(Invitation.author), selectinload(Invitation.school))
    )
    if hidden_authors:
        query = query.where(Invitation.author_id.not_in(hidden_authors))
    if scope == "school" and me.school_id:
        query = query.where(Invitation.school_id == me.school_id)
    elif me.city_id:
        query = query.where(Invitation.city_id == me.city_id)
    ids = [i for i in interest.split(",") if i]
    if ids:
        query = query.where(Invitation.interest.in_(ids))
    if fmt:
        query = query.where(Invitation.fmt == fmt)
    if sort == "old":
        return query.order_by(Invitation.created_at.asc(), Invitation.id.asc())
    return query.order_by(Invitation.created_at.desc(), Invitation.id.desc())


def sort_by_date(items: list[Invitation]) -> None:
    since = date.today() - timedelta(days=1)

    def key(i: Invitation):
        if i.when_date is None:
            return (1, 0, "")
        if i.when_date < since:
            return (2, -i.when_date.toordinal(), "")
        return (0, i.when_date.toordinal(), i.when_time)

    items.sort(key=key)


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
    query = feed_query(me, blocked_pair_ids(db, me.id), interest, fmt, scope, sort)
    items = list(db.scalars(query))
    needle = " ".join(q.lower().split())
    if needle:
        items = [i for i in items if needle in i.title.lower()]
    if has_spots:
        items = [i for i in items if accepted_count(i) < i.max_participants]
    if sort == "soon":
        sort_by_date(items)
    elif sort == "spots":
        items.sort(key=lambda i: i.max_participants - accepted_count(i), reverse=True)
    if response is not None:
        response.headers["X-Total-Count"] = str(len(items))
    return [inv_out(i, me) for i in items[offset : offset + limit]]


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
    return [inv_out(i, me, with_responses=True) for i in db.scalars(q)]


@router.get("/api/invitations/joined")
def joined(db: Session = Depends(get_db), me: User = Depends(current_user)):
    q = (
        select(Invitation)
        .join(Response, Response.invitation_id == Invitation.id)
        .where(Response.user_id == me.id, Invitation.hidden.is_(False))
        .options(selectinload(Invitation.responses), selectinload(Invitation.author))
        .order_by(Response.created_at.desc())
    )
    return [inv_out(i, me) for i in db.scalars(q)]


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
