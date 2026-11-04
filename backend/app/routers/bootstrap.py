from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import Invitation, Response, User
from ..deps import current_user, get_db
from ..interests import interests_out
from ..serializers import user_out
from .invitations import FEED_PAGE_MAX, feed_page

FIRST_PAGE = 20

router = APIRouter()


def waiting_count(db: Session, me: User) -> int:
    q = (
        select(func.count())
        .select_from(Response)
        .join(Invitation, Response.invitation_id == Invitation.id)
        .where(Invitation.author_id == me.id, Invitation.status == "open", Response.status == "pending")
    )
    return db.scalar(q) or 0


@router.get("/api/bootstrap")
def bootstrap(
    interest: str = "",
    fmt: str | None = Query(None, pattern="^(offline|online)$"),
    has_spots: bool = False,
    sort: str = Query("new", pattern="^(new|old|spots|soon)$"),
    scope: str = Query("school", pattern="^(school|city)$"),
    q: str = Query("", max_length=80),
    limit: int = Query(FIRST_PAGE, ge=1, le=FEED_PAGE_MAX),
    db: Session = Depends(get_db),
    me: User = Depends(current_user),
):
    profile = user_out(me, db)
    feed = None
    if profile["onboarded"]:
        items, total = feed_page(db, me, interest, fmt, has_spots, sort, scope, q, limit, 0)
        feed = {"items": items, "total": total}
    return {"me": profile, "interests": interests_out(), "feed": feed, "waiting": waiting_count(db, me)}
