from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import places, terms
from ..db import School, User, now
from ..deps import current_user, get_db
from ..interests import INTERESTS, interests_out
from ..regions import GRADES, REGIONS
from ..serializers import profile_complete, user_out

DISPLAY_NAME_MAX = 30

router = APIRouter()


class ProfileIn(BaseModel):
    interests: list[str] | None = Field(default=None, max_length=len(INTERESTS))
    notify: bool | None = None
    notify_activity: bool | None = None
    region: str | None = None
    city_id: int | None = Field(default=None, ge=1)
    city: str | None = Field(default=None, max_length=places.CITY_MAX)
    school_id: int | None = Field(default=None, ge=1)
    school: str | None = Field(default=None, max_length=places.SCHOOL_MAX)
    grade: int | None = None
    display_name: str | None = Field(default=None, max_length=DISPLAY_NAME_MAX)
    accept_terms: bool | None = None


@router.get("/api/interests")
def interests():
    return interests_out()


@router.get("/api/regions")
def regions():
    return REGIONS


@router.get("/api/cities")
def cities(
    region: str,
    q: str = Query("", max_length=80),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    return places.search_cities(db, region, q, limit)


@router.get("/api/schools")
def schools(
    city_id: int,
    q: str = Query("", max_length=120),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    _: User = Depends(current_user),
):
    return places.search_schools(db, city_id, q, limit)


@router.get("/api/schools/{school_id}")
def school(school_id: int, db: Session = Depends(get_db), _: User = Depends(current_user)):
    found = db.get(School, school_id)
    if not found:
        raise HTTPException(404, "Школа не найдена")
    return {
        "id": found.id,
        "name": found.name,
        "city_id": found.city_id,
        "city": found.city.name,
        "region": found.city.region,
        "members": places.school_members(db, [found.id]).get(found.id, 0),
    }


@router.get("/api/terms")
def get_terms():
    return {"version": terms.TERMS_VERSION, "documents": terms.DOCUMENTS}


@router.get("/api/me")
def get_me(db: Session = Depends(get_db), me: User = Depends(current_user)):
    return user_out(me, db)


def update_place(db: Session, me: User, body: ProfileIn) -> None:
    if body.region is not None:
        if body.region not in REGIONS:
            raise HTTPException(422, "Выберите регион из списка")
        if body.region != me.region:
            me.city = me.school = None
        me.region = body.region
    if body.city_id is not None or body.city is not None:
        if not me.region:
            raise HTTPException(422, "Сначала выберите регион")
        city = places.resolve_city(db, me.region, body.city_id, body.city, me.id)
        if city != me.city:
            me.school = None
        me.city = city
    if body.school_id is not None or body.school is not None:
        if not me.city:
            raise HTTPException(422, "Сначала выберите город")
        me.school = places.resolve_school(db, me.city, body.school_id, body.school, me.id)


@router.put("/api/me")
def update_me(body: ProfileIn, db: Session = Depends(get_db), me: User = Depends(current_user)):
    if body.interests is not None:
        if set(body.interests) - set(INTERESTS):
            raise HTTPException(422, "Неизвестный интерес")
        me.interests = ",".join(dict.fromkeys(body.interests))
    if body.notify is not None:
        me.notify = body.notify
    if body.notify_activity is not None:
        me.notify_activity = body.notify_activity
    update_place(db, me, body)
    if body.grade is not None:
        if body.grade not in GRADES:
            raise HTTPException(422, "Класс — от 5 до 11")
        me.grade = body.grade
    if body.display_name is not None:
        me.display_name = places.checked_name(body.display_name, "имя", DISPLAY_NAME_MAX)
    if body.accept_terms and me.terms_version != terms.TERMS_VERSION:
        me.terms_version, me.consented_at = terms.TERMS_VERSION, now()
    me.onboarded = profile_complete(me)
    db.add(me)
    db.commit()
    return user_out(me, db)
