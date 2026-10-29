import hmac
from datetime import timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from .config import settings
from .db import REPORT_REASONS, Block, Invitation, Report, User, now
from .deps import current_user, get_db
from .notifications import tell as tell_author
from .serializers import utc_iso

REPORT_HIDE_THRESHOLD = 3
REPORTS_PER_DAY = 10

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


def admin_only(x_admin_key: str = Header(default="")) -> None:
    if not settings.admin_key:
        raise HTTPException(404, "Not Found")
    if not hmac.compare_digest(x_admin_key.encode(), settings.admin_key.encode()):
        raise HTTPException(401, "Неверный ключ")


class HideIn(BaseModel):
    reason: str = Field(default="", max_length=200)


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


def invitation_totals(db: Session, author_ids) -> dict[int, int]:
    if not author_ids:
        return {}
    q = select(Invitation.author_id, func.count()).where(Invitation.author_id.in_(author_ids)).group_by(Invitation.author_id)
    return dict(db.execute(q).all())


def resolve_reports(db: Session, inv_id: int) -> None:
    for r in db.scalars(select(Report).where(Report.invitation_id == inv_id, Report.resolved.is_(False))):
        r.resolved = True


def open_reports_by_invitation(db: Session) -> dict[int, list[Report]]:
    grouped: dict[int, list[Report]] = {}
    for r in db.scalars(select(Report).where(Report.resolved.is_(False)).order_by(Report.id)):
        grouped.setdefault(r.invitation_id, []).append(r)
    return grouped


def admin_items(db: Session, invitations: list[Invitation], open_reports: dict[int, list[Report]]) -> list[dict]:
    totals = invitation_totals(db, {inv.author_id for inv in invitations})
    return [
        {
            "id": inv.id,
            "title": inv.title,
            "description": inv.description,
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
            },
            "reports": [
                {"reason": REPORT_REASONS.get(r.reason, r.reason), "text": r.text, "at": utc_iso(r.created_at)}
                for r in open_reports.get(inv.id, [])
            ],
        }
        for inv in invitations
    ]


ADMIN_LOAD = (selectinload(Invitation.author), selectinload(Invitation.school), selectinload(Invitation.responses))


@admin.get("/reports", dependencies=[Depends(admin_only)])
def admin_reports(db: Session = Depends(get_db)):
    open_reports = open_reports_by_invitation(db)
    q = select(Invitation).where(or_(Invitation.hidden.is_(True), Invitation.id.in_(list(open_reports)))).options(*ADMIN_LOAD)
    items = admin_items(db, list(db.scalars(q)), open_reports)
    items.sort(key=lambda i: (-len(i["reports"]), -i["id"]))
    return {"items": items}


@admin.get("/invitations", dependencies=[Depends(admin_only)])
def admin_invitations(db: Session = Depends(get_db), limit: int = Query(200, ge=1, le=500)):
    q = select(Invitation).options(*ADMIN_LOAD).order_by(Invitation.id.desc()).limit(limit)
    return {"items": admin_items(db, list(db.scalars(q)), open_reports_by_invitation(db))}


@admin.get("/users", dependencies=[Depends(admin_only)])
def admin_users(db: Session = Depends(get_db), banned: bool = True):
    users = list(db.scalars(select(User).where(User.banned.is_(banned)).order_by(User.id.desc())))
    totals = invitation_totals(db, [u.id for u in users])
    return {"items": [{"id": u.id, "name": u.name, "username": u.username, "banned": u.banned, "invitations": totals.get(u.id, 0)} for u in users]}


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


@admin.post("/invitations/{inv_id}/hide", dependencies=[Depends(admin_only)])
def admin_hide(inv_id: int, body: HideIn, background: BackgroundTasks, db: Session = Depends(get_db)):
    inv = find_invitation(db, inv_id)
    inv.hidden, inv.hidden_reason = True, body.reason.strip() or "Решение модератора"
    resolve_reports(db, inv.id)
    db.commit()
    background.add_task(tell_author, inv.author_id, f"Ваше приглашение «{inv.title}» скрыто модератором: {inv.hidden_reason}.")
    return {"ok": True}


@admin.post("/invitations/{inv_id}/restore", dependencies=[Depends(admin_only)])
def admin_restore(inv_id: int, db: Session = Depends(get_db)):
    inv = find_invitation(db, inv_id)
    inv.hidden, inv.hidden_reason = False, ""
    resolve_reports(db, inv.id)
    db.commit()
    return {"ok": True}


@admin.post("/invitations/{inv_id}/dismiss", dependencies=[Depends(admin_only)])
def admin_dismiss(inv_id: int, db: Session = Depends(get_db)):
    resolve_reports(db, find_invitation(db, inv_id).id)
    db.commit()
    return {"ok": True}


@admin.post("/users/{user_id}/ban", dependencies=[Depends(admin_only)])
def admin_ban(user_id: int, db: Session = Depends(get_db)):
    user = find_user(db, user_id)
    user.banned = True
    for inv in db.scalars(select(Invitation).where(Invitation.author_id == user.id, Invitation.hidden.is_(False))):
        inv.hidden, inv.hidden_reason = True, "Автор заблокирован"
    db.commit()
    return {"ok": True}


@admin.post("/users/{user_id}/unban", dependencies=[Depends(admin_only)])
def admin_unban(user_id: int, db: Session = Depends(get_db)):
    find_user(db, user_id).banned = False
    db.commit()
    return {"ok": True}
