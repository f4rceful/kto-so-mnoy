import re
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .db import Invitation, Response, User
from .max_client import max_client

WELCOME = (
    "Привет! «Кто со мной?» помогает найти компанию для занятий вне уроков: "
    "спорт, музыка, игры, творчество, совместные проекты.\n\n"
    "Предложи своё занятие или откликнись на чужое."
)

HELP = (
    "«Кто со мной?» — приглашения для занятий вне уроков: создавайте своё или откликайтесь на чужие. "
    "Всё делается в приложении, а здесь я пишу, когда что-то происходит.\n\n"
    "Команды:\n"
    "/my — мои приглашения и отклики\n"
    "/notify — уведомления (/notify off — выключить, /notify on — включить)\n"
    "/help — эта справка"
)

COMMANDS = [
    {"name": "my", "description": "Мои приглашения и отклики"},
    {"name": "notify", "description": "Уведомления: включить или выключить"},
    {"name": "help", "description": "Как это работает"},
]

ALIASES = {
    "start": "start", "старт": "start", "привет": "start", "здравствуйте": "start", "hi": "start", "hello": "start",
    "help": "help", "помощь": "help", "справка": "help", "?": "help", "что ты умеешь": "help",
    "my": "my", "мои": "my", "мои приглашения": "my",
    "notify": "notify", "уведомления": "notify",
    "stop": "off", "стоп": "off",
}
ON_WORDS, OFF_WORDS = {"on", "вкл", "включить", "включи"}, {"off", "выкл", "выключить", "выключи"}

START_PAYLOAD = re.compile(r"(inv|school)_\d{1,9}")
HINT_EVERY = 600
MY_LIMIT = 5


@dataclass
class Reply:
    text: str
    buttons: list[list[dict]] | None = None


def parse(text: str) -> tuple[str, str]:
    t = " ".join((text or "").strip().lower().split()).lstrip("/")
    if not t:
        return "", ""
    if t in ALIASES:
        return ALIASES[t], ""
    first, _, rest = t.partition(" ")
    first = first.split("@")[0]
    first = first.rstrip(".,!?…:;") or first
    return ALIASES.get(first, first), rest.strip()


def open_app(label: str = "Открыть «Кто со мной?»", payload: str = ""):
    return max_client.open_app_button(label, payload)


def start_reply(payload: str = "") -> Reply:
    if payload and START_PAYLOAD.fullmatch(payload):
        label = "Открыть приглашение" if payload.startswith("inv_") else "Открыть приложение"
        return Reply(WELCOME, open_app(label, payload))
    return Reply(WELCOME, open_app())


def invitation_line(inv: Invitation) -> str:
    waiting = sum(1 for r in inv.responses if r.status == "pending")
    taken = sum(1 for r in inv.responses if r.status == "accepted")
    return f"• «{inv.title}» — {taken} из {inv.max_participants}" + (f", ждут ответа: {waiting}" if waiting else "")


def my_reply(db: Session, user: User | None) -> Reply:
    if user is None or not user.onboarded:
        return Reply("Чтобы я мог показать ваши приглашения, откройте приложение и зарегистрируйтесь.", open_app())
    mine = db.scalars(
        select(Invitation)
        .where(Invitation.author_id == user.id, Invitation.status == "open", Invitation.hidden.is_(False))
        .options(selectinload(Invitation.responses))
        .order_by(Invitation.id.desc())
    ).all()
    joined = db.scalar(
        select(Response.id).join(Invitation, Invitation.id == Response.invitation_id).where(
            Response.user_id == user.id, Response.status == "accepted", Invitation.status == "open", Invitation.hidden.is_(False)
        ).limit(1)
    )
    lines = [invitation_line(inv) for inv in mine[:MY_LIMIT]]
    if len(mine) > MY_LIMIT:
        lines.append(f"…и ещё {len(mine) - MY_LIMIT}")
    if not lines and not joined:
        return Reply("У вас пока нет открытых приглашений и участий. Предложите занятие или откликнитесь на чужое!", open_app())
    text = ("Ваши открытые приглашения:\n" + "\n".join(lines)) if lines else "Своих открытых приглашений у вас нет."
    if joined:
        text += "\n\nВы участвуете в чужих приглашениях — они в профиле приложения."
    return Reply(text, open_app())


def on_off(flag: bool) -> str:
    return "включены" if flag else "выключены"


def notify_reply(db: Session, user: User | None, arg: str) -> Reply:
    if user is None:
        return Reply("Сначала откройте приложение: настройки уведомлений появятся после регистрации.", open_app())
    word = arg.split(" ")[0] if arg else ""
    if word in ON_WORDS or word in OFF_WORDS:
        on = word in ON_WORDS
        user.notify = user.notify_activity = on
        db.commit()
        return Reply(
            "Уведомления включены: напишу о новых приглашениях по вашим интересам и обо всём, что касается ваших приглашений."
            if on
            else "Уведомления выключены. Приглашения по-прежнему можно смотреть в приложении. Включить обратно: /notify on",
            open_app(),
        )
    return Reply(
        f"Уведомления о новых приглашениях: {on_off(user.notify)}.\n"
        f"Сообщения о моих приглашениях и откликах: {on_off(user.notify_activity)}.\n\n"
        "Выключить всё: /notify off. Включить: /notify on. Тонкие настройки — в приложении.",
        open_app("Настройки в приложении"),
    )


_last_hint: dict[int, float] = {}
HINT_MEMORY = 10_000


def hint_reply(user_id: int, now: float | None = None) -> Reply | None:
    now = time.time() if now is None else now
    if now - _last_hint.get(user_id, -HINT_EVERY) < HINT_EVERY:
        return None
    if len(_last_hint) >= HINT_MEMORY:
        for uid, at in list(_last_hint.items()):
            if now - at >= HINT_EVERY:
                del _last_hint[uid]
    _last_hint[user_id] = now
    return Reply("Я понимаю команды /my, /notify и /help. Всё остальное — в приложении.", open_app())


def reply_to(db: Session, user_id: int, text: str, now: float | None = None) -> Reply | None:
    command, arg = parse(text)
    user = db.get(User, user_id)
    if command == "start":
        return start_reply()
    if command == "help":
        return Reply(HELP, open_app())
    if command == "my":
        return my_reply(db, user)
    if command == "notify":
        return notify_reply(db, user, arg)
    if command == "off":
        return notify_reply(db, user, "off")
    return hint_reply(user_id, now)
