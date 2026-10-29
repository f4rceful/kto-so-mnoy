import re

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from . import terms
from .config import settings
from .db import SessionLocal, User
from .security import validate_init_data

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.]{3,64}$")


def get_db():
    with SessionLocal() as db:
        yield db


def clean_username(raw) -> str | None:
    return raw if isinstance(raw, str) and USERNAME_RE.fullmatch(raw) else None


def _identity(x_init_data: str, x_dev_user: str, x_dev_username: str) -> tuple[int, str, str | None]:
    if settings.dev_mode and x_dev_user:
        if not x_dev_user.isdigit():
            raise HTTPException(401, "Неверные данные авторизации")
        return int(x_dev_user), f"Тест {x_dev_user}", clean_username(x_dev_username)
    data = validate_init_data(x_init_data, settings.bot_token, settings.init_data_ttl)
    info = data and data.get("user")
    if not info:
        raise HTTPException(401, "Неверные данные авторизации")
    name = " ".join(filter(None, [info.get("first_name"), info.get("last_name")])) or info.get("name", "")
    return int(info["id"]), name, clean_username(info.get("username"))


def current_user(
    db: Session = Depends(get_db),
    x_init_data: str = Header(default=""),
    x_dev_user: str = Header(default=""),
    x_dev_username: str = Header(default=""),
) -> User:
    uid, name, username = _identity(x_init_data, x_dev_user, x_dev_username)
    user = db.get(User, uid) or User(id=uid)
    if user.banned:
        raise HTTPException(403, "Доступ к сервису ограничен за нарушение правил")
    user.name = name[:128] or user.name
    user.username = username
    db.add(user)
    db.commit()
    return user


def consenting_user(me: User = Depends(current_user)) -> User:
    if me.terms_version != terms.TERMS_VERSION:
        raise HTTPException(403, "Сначала примите условия использования")
    return me
