from collections.abc import Callable

from fastapi import HTTPException
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .db import City, School, User
from .names import clean_name, looks_like_name, norm_city, norm_school
from .regions import REGIONS

CITY_MAX, SCHOOL_MAX = 80, 120
CUSTOM_PLACES_LIMIT = 10
_MOSCOW_OFFSET = 180


def _word_match(column, norm_query: str):
    return and_(
        *(
            or_(column.startswith(w, autoescape=True), column.contains(f" {w}", autoescape=True))
            for w in norm_query.split()
        )
    )


def search_cities(db: Session, region: str, query: str, limit: int) -> list[dict]:
    if region not in REGIONS:
        raise HTTPException(422, "Выберите регион из списка")
    q = select(City).where(City.region == region)
    norm = norm_city(query)
    if norm:
        q = q.where(_word_match(City.name_norm, norm)).order_by(
            case((City.name_norm.startswith(norm, autoescape=True), 0), else_=1)
        )
    q = q.order_by(func.coalesce(City.population, 0).desc(), City.name).limit(limit)
    return [{"id": c.id, "name": c.name, "custom": c.custom} for c in db.scalars(q)]


def search_schools(db: Session, city_id: int, query: str, limit: int) -> list[dict]:
    q = select(School).where(School.city_id == city_id)
    norm = norm_school(query)
    if norm:
        q = q.where(_word_match(School.name_norm, norm))
    q = q.order_by(School.custom, School.name).limit(limit)
    schools = list(db.scalars(q))
    members = school_members(db, [s.id for s in schools])
    return [{"id": s.id, "name": s.name, "custom": s.custom, "members": members.get(s.id, 0)} for s in schools]


def school_members(db: Session, school_ids: list[int]) -> dict[int, int]:
    if not school_ids:
        return {}
    rows = db.execute(
        select(User.school_id, func.count()).where(User.school_id.in_(school_ids)).group_by(User.school_id)
    )
    return dict(rows.all())


def checked_name(text: str | None, label: str, max_len: int) -> str:
    name = clean_name(text or "")
    if not looks_like_name(name) or len(name) > max_len:
        raise HTTPException(422, f"Укажите {label}")
    return name


def region_offset(db: Session, region: str) -> int:
    found = db.scalar(
        select(City.utc_offset)
        .where(City.region == region, City.custom.is_(False))
        .order_by(func.coalesce(City.population, 0).desc())
        .limit(1)
    )
    return found if found is not None else _MOSCOW_OFFSET


def check_custom_quota(db: Session, user_id: int | None) -> None:
    if user_id is None:
        return
    made = db.scalar(select(func.count()).select_from(City).where(City.created_by == user_id)) + db.scalar(
        select(func.count()).select_from(School).where(School.created_by == user_id)
    )
    if made >= CUSTOM_PLACES_LIMIT:
        raise HTTPException(429, "Вы уже добавили много своих городов и школ. Выберите из списка или напишите нам")


def _get_or_create(db: Session, model, where: tuple, user_id: int | None, make: Callable):
    place = db.scalar(select(model).where(*where))
    if place:
        return place
    check_custom_quota(db, user_id)
    try:
        with db.begin_nested():
            place = make()
            db.add(place)
    except IntegrityError:
        place = db.scalar(select(model).where(*where))
    return place


def get_or_create_city(db: Session, region: str, name: str, user_id: int | None = None) -> City:
    norm = norm_city(name)
    return _get_or_create(
        db,
        City,
        (City.region == region, City.name_norm == norm),
        user_id,
        lambda: City(
            region=region, name=name, name_norm=norm, custom=True, created_by=user_id,
            utc_offset=region_offset(db, region),
        ),
    )


def get_or_create_school(db: Session, city_id: int, name: str, user_id: int | None = None) -> School:
    norm = norm_school(name)
    return _get_or_create(
        db,
        School,
        (School.city_id == city_id, School.name_norm == norm),
        user_id,
        lambda: School(city_id=city_id, name=name, name_norm=norm, custom=True, created_by=user_id),
    )


def resolve_city(db: Session, region: str, city_id: int | None, name: str | None, user_id: int | None = None) -> City:
    if city_id is not None:
        city = db.get(City, city_id)
        if not city or city.region != region:
            raise HTTPException(422, "Город не найден в выбранном регионе")
        return city
    return get_or_create_city(db, region, checked_name(name, "город", CITY_MAX), user_id)


def resolve_school(db: Session, city: City, school_id: int | None, name: str | None, user_id: int | None = None) -> School:
    if school_id is not None:
        school = db.get(School, school_id)
        if not school or school.city_id != city.id:
            raise HTTPException(422, "Школа не найдена в выбранном городе")
        return school
    return get_or_create_school(db, city.id, checked_name(name, "школу", SCHOOL_MAX), user_id)


def backfill_legacy_profiles(db: Session) -> None:
    users = db.scalars(
        select(User).where(User.city_id.is_(None), User.legacy_city != "", User.region.in_(REGIONS))
    ).all()
    for user in users:
        city_name = clean_name(user.legacy_city)
        if not looks_like_name(city_name):
            continue
        user.city = get_or_create_city(db, user.region, city_name)
        school_name = clean_name(user.legacy_school)
        if looks_like_name(school_name):
            db.flush()
            user.school = get_or_create_school(db, user.city.id, school_name)
    db.commit()
