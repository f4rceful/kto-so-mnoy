import pytest
from helpers import add, city, get, invitation, response, run, texts, to, user

from app import bot, botcmd
from app.config import settings
from app.db import Invitation, Response, SessionLocal, User
from app.max_client import max_client
from app.terms import TERMS_VERSION


@pytest.fixture(autouse=True)
def fresh_hints():
    botcmd._last_hint.clear()
    yield
    botcmd._last_hint.clear()


@pytest.fixture()
def world(database, outbox, clock):
    add(city(), user(1, onboarded=True), user(2), user(3), invitation())
    return outbox


@pytest.fixture()
def answers(monkeypatch):
    log = []

    async def fake_answer(callback_id, text):
        log.append((callback_id, text))
        return True

    monkeypatch.setattr(max_client, "answer_callback", fake_answer)
    return log


def reply(uid, text, now=None):
    with SessionLocal() as s:
        return botcmd.reply_to(s, uid, text, now)


def update(kind, uid=1, **extra):
    base = {"update_type": kind, "user": {"user_id": uid, "name": f"Имя {uid}"}}
    return base | extra


def message(uid, text):
    return {"update_type": "message_created", "message": {"sender": {"user_id": uid, "name": "Имя"}, "body": {"text": text}}}


def callback(uid, payload, cid="cb1"):
    return {"update_type": "message_callback", "callback": {"callback_id": cid, "payload": payload, "user": {"user_id": uid}}}


@pytest.mark.parametrize(
    "text,expected",
    [
        ("/my", ("my", "")),
        ("/Notify@kto_bot off", ("notify", "off")),
        ("МОИ", ("my", "")),
        ("мои приглашения", ("my", "")),
        ("  привет  ", ("start", "")),
        ("/start", ("start", "")),
        ("что ты умеешь", ("help", "")),
        ("/stop", ("off", "")),
        ("СТОП", ("off", "")),
        ("уведомления выкл", ("notify", "выкл")),
        ("привет, бот!", ("start", "бот!")),
        ("Помощь!!!", ("help", "")),
        ("мои?", ("my", "")),
        ("blah blah", ("blah", "blah")),
        ("", ("", "")),
        (None, ("", "")),
        ("   ", ("", "")),
        ("/", ("", "")),
    ],
)
def test_parse(text, expected):
    assert botcmd.parse(text) == expected


def test_commands_are_registered_for_hints():
    names = {c["name"] for c in botcmd.COMMANDS}
    assert names == {"my", "notify", "help"}
    assert all(1 <= len(c["name"]) <= 64 and 1 <= len(c["description"]) <= 128 for c in botcmd.COMMANDS), "лимиты MAX на длину"
    assert len(botcmd.COMMANDS) <= 32


def test_start_and_help_replies(world):
    r = reply(1, "/start")
    assert r.text == botcmd.WELCOME and r.buttons[0][0]["type"] == "link"
    h = reply(1, "помощь")
    assert "/my" in h.text and "/notify" in h.text and "/help" in h.text
    assert h.buttons, "в справке всегда есть кнопка открыть приложение"


def test_my_for_unregistered_and_empty(world):
    assert "зарегистрируйтесь" in reply(404, "/my").text
    add(user(5, onboarded=False))
    assert "зарегистрируйтесь" in reply(5, "/my").text, "не прошёл регистрацию — как не зарегистрированный"
    with SessionLocal() as s:
        s.delete(s.get(Invitation, 1))
        s.commit()
    assert "пока нет открытых приглашений" in reply(1, "/my").text


def test_my_lists_open_invitations_with_waiting_responses(world):
    add(response(1, 1, 2, "pending"), response(2, 1, 3, "accepted"), invitation(2, title="Футбол", max_participants=10))
    text = reply(1, "/my").text
    assert "«Шахматы после уроков» — 1 из 3, ждут ответа: 1" in text
    assert "«Футбол» — 0 из 10" in text and "ждут ответа: 0" not in text
    add(invitation(3, title="Закрытое", status="closed"), invitation(4, title="Скрытое", hidden=True))
    text = reply(1, "/my").text
    assert "Закрытое" not in text and "Скрытое" not in text
    add(*[invitation(10 + n, title=f"Ещё {n}") for n in range(6)])
    text = reply(1, "/my").text
    assert text.count("•") == 5 and "…и ещё" in text


def test_my_mentions_participation(world):
    add(response(1, 1, 2, "accepted"))
    text = reply(2, "/my").text
    assert "Своих открытых приглашений у вас нет" in text and "участвуете в чужих" in text


def test_notify_shows_and_changes_both_switches(world):
    status = reply(2, "/notify").text
    assert "новых приглашениях: включены" in status and "моих приглашениях и откликах: включены" in status
    off = reply(2, "/notify off")
    assert "выключены" in off.text
    u = get(User, 2)
    assert (u.notify, u.notify_activity) == (False, False)
    assert "выключены" in reply(2, "/notify").text.split("\n")[0]
    reply(2, "/notify on")
    u = get(User, 2)
    assert (u.notify, u.notify_activity) == (True, True)
    reply(2, "уведомления выкл")
    assert get(User, 2).notify is False
    reply(2, "/notify вкл")
    assert get(User, 2).notify is True
    reply(2, "стоп")
    assert (get(User, 2).notify, get(User, 2).notify_activity) == (False, False)
    assert "откройте приложение" in reply(404, "/notify off").text, "человек, которого нет в базе, ничего не настраивает"


def test_unknown_text_gets_a_hint_but_not_spam(world):
    r = reply(2, "как дела?", now=1000)
    assert r is not None and "/my" in r.text
    assert reply(2, "ещё что-то", now=1100) is None, "повторно в течение 10 минут не отвечаем"
    assert reply(3, "абракадабра", now=1100) is not None, "у каждого человека свой отсчёт"
    assert reply(2, "ещё", now=1000 + botcmd.HINT_EVERY - 1) is None
    assert reply(2, "ещё", now=1000 + botcmd.HINT_EVERY) is not None, "через 10 минут — снова можно"
    assert reply(2, "/help", now=1101) is not None, "команды отвечают всегда, ограничение только на «не понял»"


def test_start_payload_is_validated(world):
    good = botcmd.start_reply("inv_42")
    assert good.buttons[0][0]["url"].endswith("?startapp=inv_42") and good.buttons[0][0]["text"] == "Открыть приглашение"
    school = botcmd.start_reply("school_7")
    assert school.buttons[0][0]["url"].endswith("?startapp=school_7")
    for bad in ["", None, "inv_", "inv_x", "inv_1;drop", "inv_1 2", "evil", "school_1234567890", "inv_-1", "INV_1", "inv_1\n"]:
        r = botcmd.start_reply(bad)
        assert r.buttons[0][0]["url"].endswith("?startapp"), f"{bad!r}: чужое значение в ссылку не попадает"


def test_bot_started_creates_user_and_sends_welcome(world):
    run(bot.handle_update(update("bot_started", 77)))
    u = get(User, 77)
    assert u.bot_state == "ok" and u.name == "Имя 77", "человек мог запустить бота раньше, чем открыл приложение"
    assert to(world) == [77] and world[0][1] == botcmd.WELCOME
    world.clear()
    run(bot.handle_update(update("bot_started", 2, payload="inv_9")))
    assert world[0][2][0][0]["url"].endswith("?startapp=inv_9"), "ссылка-приглашение открывает нужное приглашение"
    run(bot.handle_update(update("bot_started", 3, payload="evil<script>")))
    assert world[1][2][0][0]["url"].endswith("?startapp")


def test_bot_stopped_then_started_again(world):
    run(bot.handle_update(update("bot_stopped", 2)))
    assert get(User, 2).bot_state == "blocked"
    with SessionLocal() as s:
        s.get(User, 2).bot_fails = 2
        s.commit()
    run(bot.handle_update(update("bot_started", 2)))
    u = get(User, 2)
    assert (u.bot_state, u.bot_fails) == ("ok", 0), "вернулся — снова можно писать"


def test_message_created_routes_commands(world):
    run(bot.handle_update(message(1, "/my")))
    assert to(world) == [1] and "Ваши открытые приглашения" in world[0][1]
    run(bot.handle_update(message(2, "/notify off")))
    assert get(User, 2).notify is False
    assert get(User, 2).bot_state == "ok", "написал нам — диалог открыт"
    world.clear()
    run(bot.handle_update(message(3, "")))
    run(bot.handle_update(message(3, "что-то")))
    assert len(world) == 1


def test_broken_and_unknown_updates_are_ignored(world):
    for u in [{}, {"update_type": "message_created"}, {"update_type": "bot_started"}, {"update_type": "bot_stopped"}, {"update_type": "dialog_muted"},
              {"update_type": "message_created", "message": {"sender": {}}}, {"update_type": "message_callback"}, {"update_type": "message_created", "message": {"sender": {"user_id": 2}, "body": None}}]:
        run(bot.handle_update(u))
    assert world == [] or all(uid == 2 for uid, _, _ in world)


def test_callbacks_are_ignored_unless_enabled(world, answers):
    add(response(1, 1, 2))
    run(bot.handle_update(callback(1, "acc:1")))
    assert answers == [] and get(Response, 1).status == "pending"


def test_accept_and_decline_from_chat(world, answers, monkeypatch):
    monkeypatch.setattr(settings, "bot_quick_actions", True)
    add(response(1, 1, 2), response(2, 1, 3), invitation(2, max_participants=1), response(3, 2, 3))
    run(bot.handle_update(callback(1, "acc:1", "a")))
    assert get(Response, 1).status == "accepted"
    assert answers[-1][0] == "a" and "Принято" in answers[-1][1] and "1 из 3" in answers[-1][1]
    assert to(world) == [2] and "принял(а) ваш отклик" in world[0][1], "участнику уходит то же сообщение, что и из приложения"
    run(bot.handle_update(callback(1, "acc:1", "b")))
    assert "уже обработан" in answers[-1][1] and len(world) == 1
    run(bot.handle_update(callback(1, "dec:2", "c")))
    assert get(Response, 2).status == "declined" and "Отклонено" in answers[-1][1]
    assert texts(world, 3)[-1].startswith("К сожалению")
    world.clear()
    run(bot.handle_update(callback(1, "acc:3", "d")))
    assert get(Response, 3).status == "accepted"
    assert any(uid == 1 and "собран" in text for uid, text, _ in world)


def test_callback_refusals(world, answers, monkeypatch):
    monkeypatch.setattr(settings, "bot_quick_actions", True)
    add(response(1, 1, 2), invitation(2, max_participants=1), response(2, 2, 2, "accepted"), response(3, 2, 3))
    run(bot.handle_update(callback(2, "acc:1", "x")))
    assert "Только автор" in answers[-1][1] and get(Response, 1).status == "pending"
    run(bot.handle_update(callback(404, "acc:1", "y")))
    assert get(Response, 1).status == "pending" and "откройте приложение" in answers[-1][1].lower()
    with SessionLocal() as db:
        db.get(User, 1).terms_version = "old"
        db.commit()
    run(bot.handle_update(callback(1, "acc:1", "v")))
    assert "примите условия" in answers[-1][1] and get(Response, 1).status == "pending"
    with SessionLocal() as db:
        db.get(User, 1).terms_version = TERMS_VERSION
        db.commit()
    run(bot.handle_update(callback(1, "acc:999", "z")))
    assert "не найден" in answers[-1][1]
    run(bot.handle_update(callback(1, "acc:3", "w")))
    assert "уже полный" in answers[-1][1] and get(Response, 3).status == "pending"
    assert world == []
    before = len(answers)
    for bad in ["", "acc", "acc:", "acc:x", "drop:1", "acc:1;2", "ACC:1", "acc:-1", "acc:1234567890", None]:
        run(bot.handle_update(callback(1, bad)))
    run(bot.handle_update({"update_type": "message_callback", "callback": {"payload": "acc:1", "user": {"user_id": 1}}}))
    assert len(answers) == before and get(Response, 1).status == "pending"
