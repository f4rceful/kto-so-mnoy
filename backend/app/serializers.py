from datetime import timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import terms
from .config import settings
from .db import Invitation, Response, User
from .max_client import max_client


def accepted_terms(user: User) -> bool:
    return user.terms_version == terms.TERMS_VERSION


def profile_complete(user: User) -> bool:
    return bool(user.region and user.city and user.school and user.grade and accepted_terms(user))


def _name_of(place) -> str:
    return place.name if place else ""


def _app_link(payload: str) -> str | None:
    return max_client.app_link(payload) if settings.bot_username else None


def user_stats(db: Session, user: User) -> dict:
    accepted = Response.status == "accepted"
    created = db.scalar(select(func.count()).select_from(Invitation).where(Invitation.author_id == user.id))
    joined = db.scalar(select(func.count()).select_from(Response).where(Response.user_id == user.id, accepted))
    gathered = db.scalar(
        select(func.count())
        .select_from(Response)
        .join(Invitation, Response.invitation_id == Invitation.id)
        .where(Invitation.author_id == user.id, accepted)
    )
    return {"created": created, "joined": joined, "gathered": gathered}


def school_invite_link(user: User) -> str | None:
    return _app_link(f"school_{user.school_id}") if user.school_id else None


def user_out(user: User, db: Session | None = None) -> dict:
    out = {
        "id": user.id,
        "name": user.name,
        "display_name": user.public_name,
        "accepted_terms": accepted_terms(user),
        "school_invite": school_invite_link(user),
        "interests": [i for i in user.interests.split(",") if i],
        "notify": user.notify,
        "notify_activity": user.notify_activity,
        "bot": {"state": user.bot_state, "link": max_client.bot_link() if settings.bot_username else None},
        "onboarded": user.onboarded and profile_complete(user),
        "region": user.region,
        "city_id": user.city_id,
        "city": _name_of(user.city),
        "school_id": user.school_id,
        "school": _name_of(user.school),
        "grade": user.grade,
    }
    if db is not None:
        out["stats"] = user_stats(db, user)
    return out


def utc_iso(moment) -> str | None:
    if moment is None:
        return None
    return (moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)).isoformat()


def accepted_count(inv: Invitation) -> int:
    return sum(1 for r in inv.responses if r.status == "accepted")


def inv_out(inv: Invitation, me: User, with_responses: bool = False) -> dict:
    mine = next((r for r in inv.responses if r.user_id == me.id), None)
    is_mine = inv.author_id == me.id
    out = {
        "id": inv.id,
        "interest": inv.interest,
        "title": inv.title,
        "description": inv.description,
        "when": inv.when,
        "when_date": inv.when_date.isoformat() if inv.when_date else None,
        "when_time": inv.when_time,
        "fmt": inv.fmt,
        "max_participants": inv.max_participants,
        "accepted": accepted_count(inv),
        "status": inv.status,
        "author": inv.author.public_name,
        "school": _name_of(inv.school),
        "my_school": inv.school_id is not None and inv.school_id == me.school_id,
        "edited": inv.edited_at is not None,
        "edited_at": utc_iso(inv.edited_at),
        "link": _app_link(f"inv_{inv.id}"),
        "is_mine": is_mine,
        "hidden": inv.hidden if is_mine else False,
        "hidden_reason": inv.hidden_reason if is_mine else "",
        "my_response": mine.status if mine else None,
        "author_contact": inv.author.username if mine and mine.status == "accepted" else None,
    }
    if with_responses and is_mine:
        out["responses"] = [response_out(r, me) for r in inv.responses]
    return out


def response_out(resp: Response, author: User) -> dict:
    person = resp.user
    return {
        "id": resp.id,
        "user": person.public_name,
        "status": resp.status,
        "contact": person.username if resp.status == "accepted" else None,
        "created_at": utc_iso(resp.created_at),
        "grade": person.grade,
        "school": _name_of(person.school),
        "same_school": bool(person.school_id and person.school_id == author.school_id),
    }
