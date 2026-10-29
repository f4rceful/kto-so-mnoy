import asyncio
from datetime import datetime, timedelta

import pytest
from helpers import UTC, add, agree, as_user, city, get, invitation, new_invitation, response, run, texts, to, user

from app import db, notifications, reminders
from app.config import settings
from app.db import Invitation, NotificationLog, QueuedMessage, SessionLocal, User
from app.max_client import SendResult


@pytest.fixture()
def world(database, outbox, clock):
    add(city(), user(1), user(2), user(3), user(4), invitation())
    return outbox


def test_activity_switch_controls_activity_messages(world):
    add(user(5, notify_activity=False), user(6))
    assert run(notifications.deliver(5, "response", "x")) is False
    assert run(notifications.deliver(6, "response", "x")) is True
    assert to(world) == [6]


def test_system_messages_ignore_switches_but_not_bans(world):
    add(user(5, notify=False, notify_activity=False), user(6, banned=True))
    run(notifications.tell(5, "решение модератора"))
    run(notifications.tell(6, "и этому не пишем"))
    assert to(world) == [5], "служебное идёт всегда, заблокированному — нет"
    assert run(notifications.deliver(404, "system", "x")) is False, "неизвестному человеку — нет"


def test_new_invitation_pushes_respect_notify_and_blocked_bot(world):
    add(user(5, notify=False), user(6, bot_state="blocked"), user(7, bot_state="unknown"), user(8, bot_state="ok"))
    assert [run(notifications.deliver(u, "new", "x", ref=1)) for u in (5, 6, 7, 8)] == [False, False, True, True]


def test_quiet_hours_depend_on_recipient_city(world, clock):
    add(city(2, offset=420, name="Новосибирск"), user(5, city_id=2))
    for hour, expected in [(12, True), (21, True), (22, False), (23, False), (3, False), (7, False), (8, True)]:
        clock.now = datetime(2026, 10, 22, hour, 0, tzinfo=UTC) - timedelta(minutes=180)
        got = run(notifications.deliver(2, "new", "x", ref=hour + 100))
        assert got is expected, f"{hour}:00 по Москве"
    clock.now = datetime(2026, 10, 22, 9, 0, tzinfo=UTC)
    assert run(notifications.deliver(5, "new", "x", ref=201)) is True
    clock.now = datetime(2026, 10, 22, 16, 0, tzinfo=UTC)
    assert run(notifications.deliver(5, "new", "x", ref=202)) is False
    assert run(notifications.deliver(2, "new", "x", ref=202)) is True, "а у москвича 19:00, ещё день"
    clock.now = datetime(2026, 10, 22, 0, 30, tzinfo=UTC)
    assert run(notifications.deliver(2, "response", "x")) is True
    assert run(notifications.deliver(2, "remind", "x", ref=1)) is True


def test_daily_cap_for_new_invitations(world, clock):
    add(*[invitation(10 + n, author=1) for n in range(8)])
    results = [run(notifications.deliver(2, "new", "x", ref=10 + n)) for n in range(8)]
    assert results == [True] * notifications.NEW_PER_DAY + [False] * 3, "после лимита — тишина до конца суток"
    assert run(notifications.deliver(2, "response", "x")) is True, "лимит только на рассылки о новых приглашениях"
    clock.now += timedelta(hours=25)
    assert run(notifications.deliver(2, "new", "x", ref=15)) is True
    with SessionLocal() as s:
        assert s.query(NotificationLog).filter_by(user_id=2, kind="new").count() == notifications.NEW_PER_DAY + 1


def test_once_per_invitation(world):
    assert run(notifications.deliver(2, "new", "x", ref=1)) is True
    assert run(notifications.deliver(2, "new", "x", ref=1)) is False, "о том же приглашении дважды не пишем"
    for kind in ("remind", "full", "closed"):
        assert run(notifications.deliver(2, kind, "x", ref=1)) is True
        assert run(notifications.deliver(2, kind, "x", ref=1)) is False
        assert run(notifications.deliver(2, kind, "x", ref=2)) is True, "по другому приглашению — можно"
    for _ in range(3):
        assert run(notifications.deliver(2, "change", "x")) is True
        assert run(notifications.deliver(2, "response", "x")) is True
    assert run(notifications.deliver(3, "new", "x", ref=1)) is True, "у каждого человека своя запись"


def queued():
    with SessionLocal() as s:
        return [(m.user_id, m.kind, m.attempts) for m in s.query(QueuedMessage).order_by(QueuedMessage.id)]


def test_failed_send_stays_in_queue_and_is_retried(world, clock):
    world.result = SendResult(False)
    assert run(notifications.deliver(2, "remind", "x", ref=1)) is False
    assert queued() == [(2, "remind", 1)], "не дошло — сообщение ждёт на диске"
    assert run(notifications.deliver(2, "remind", "x", ref=1)) is False, "второй раз в очередь не ставим"
    world.result = SendResult(True)
    assert run(notifications.drain_once()) == 0, "повтор только после паузы"
    clock.now += timedelta(seconds=notifications.QUEUE_RETRY[0])
    assert run(notifications.drain_once()) == 1
    assert queued() == [] and to(world) == [2, 2]
    assert run(notifications.deliver(2, "remind", "x", ref=1)) is False, "дошло — больше не пишем"


def test_message_survives_restart_in_the_middle_of_sending(world, clock):
    with SessionLocal() as s:
        notifications.enqueue(s, 2, "response", "отклик", None, None, None)
    assert run(notifications.drain_once()) == 0, "пока идёт отправка, второй обработчик её не трогает"
    clock.now += notifications.QUEUE_LOCK + timedelta(seconds=1)
    assert run(notifications.drain_once()) == 1
    assert texts(world) == ["отклик"] and queued() == []


def test_permanent_failure_leaves_queue(world):
    world.result = SendResult(False, permanent=True)
    assert run(notifications.deliver(2, "response", "x")) is False
    assert queued() == []


def test_queue_gives_up_after_all_retries(world, clock):
    world.result = SendResult(False)
    run(notifications.deliver(2, "response", "x"))
    for delay in notifications.QUEUE_RETRY:
        clock.now += timedelta(seconds=delay)
        run(notifications.drain_once())
    assert queued() == [] and len(world) == len(notifications.QUEUE_RETRY) + 1


def test_stale_messages_are_dropped(world, clock):
    world.result = SendResult(False)
    run(notifications.deliver(2, "new", "x", ref=1))
    run(notifications.deliver(2, "response", "x"))
    clock.now += timedelta(hours=7)
    world.result = SendResult(True)
    world.clear()
    run(notifications.drain_once())
    assert to(world) == [2] and world[0][1] == "x" and queued() == [], "новость устарела, а отклик всё ещё важен"


def test_reachability_is_tracked(world):
    def state(uid=2):
        u = get(User, uid)
        return u.bot_state, u.bot_fails

    assert state() == ("unknown", 0)
    run(notifications.deliver(2, "response", "x"))
    assert state() == ("ok", 0), "дошло — бот может писать"

    world.result = SendResult(False)
    run(notifications.deliver(2, "response", "x"))
    assert state() == ("ok", 0)

    world.result = SendResult(False, permanent=True)
    run(notifications.deliver(2, "response", "x"))
    run(notifications.deliver(2, "response", "x"))
    assert state() == ("ok", 2)
    run(notifications.deliver(2, "response", "x"))
    assert state() == ("blocked", 3)

    world.clear()
    assert run(notifications.deliver(2, "new", "x", ref=1)) is False
    world.result = SendResult(True)
    assert run(notifications.deliver(2, "decision", "x")) is True
    assert state() == ("ok", 0), "дошло — снова всё хорошо"
    world.result = SendResult(False, permanent=True)
    run(notifications.deliver(3, "response", "x"))
    run(notifications.deliver(3, "response", "x"))
    world.result = SendResult(True)
    run(notifications.deliver(3, "response", "x"))
    world.result = SendResult(False, permanent=True)
    run(notifications.deliver(3, "response", "x"))
    run(notifications.deliver(3, "response", "x"))
    assert state(3) == ("ok", 2)


def test_new_invitation_recipients_and_text(world):
    add(
        city(2, name="Набережные Челны"),
        user(5, city_id=2),
        user(6, interests="football"),
        user(7, interests="football,chess"),
        user(8, notify=False),
        user(9, banned=True),
        user(10, interests=""),
        user(11, interests="chessboard"),
    )
    with SessionLocal() as s:
        s.get(Invitation, 1).when_date = (db.now() + timedelta(days=1)).date()
        s.get(Invitation, 1).when_time = "15:30"
        s.commit()
    run(notifications.new_invitation(1))
    assert to(world) == [2, 3, 4, 7], "автору, другому городу, другому интересу, отключившим и заблокированным не пишем"
    text = texts(world, 2)[0]
    for part in ("Новое приглашение · Шахматы", "«Шахматы после уроков»", "15:30", "очно", "мест: 3", "Автор: Тест"):
        assert part in text, part
    assert world[0][2] == notifications.open_button(1, "Посмотреть"), "кнопка ведёт именно на это приглашение"


def test_new_invitation_skips_blocked_pairs_hidden_and_closed(world):
    add(db.Block(blocker_id=2, blocked_id=1), db.Block(blocker_id=1, blocked_id=3))
    run(notifications.new_invitation(1))
    assert to(world) == [4], "скрывшие автора и скрытые им ничего не получают"
    world.clear()
    with SessionLocal() as s:
        s.get(Invitation, 1).hidden = True
        s.commit()
    run(notifications.new_invitation(1))
    assert world == [], "скрытое модератором не рассылаем"
    with SessionLocal() as s:
        s.get(Invitation, 1).hidden, s.get(Invitation, 1).status = False, "closed"
        s.commit()
    run(notifications.new_invitation(1))
    assert world == [], "закрытое тоже"
    run(notifications.new_invitation(999))


def test_new_invitation_has_recipient_limit(world, monkeypatch):
    add(*[user(100 + n) for n in range(10)])
    monkeypatch.setattr(notifications, "MAX_NOTIFY_RECIPIENTS", 4)
    run(notifications.new_invitation(1))
    assert len(world) == 4


def test_new_response_message(world):
    add(response(1, 1, 2), response(2, 1, 3, "accepted"))
    run(notifications.new_response(1))
    assert to(world) == [1]
    text = world[0][1]
    assert "Тест откликнулся(ась) на «Шахматы после уроков»" in text and "принято 1 из 3" in text
    assert world[0][2] == notifications.open_button(1) and world.fallbacks[0] is None, "без быстрых действий — обычная кнопка"
    world.clear(); world.fallbacks.clear()
    run(notifications.new_response(999))
    assert world == []


def test_quick_actions_add_callback_buttons_with_fallback(world, monkeypatch):
    monkeypatch.setattr(settings, "bot_quick_actions", True)
    add(response(7, 1, 2))
    run(notifications.new_response(7))
    buttons = world[0][2]
    callbacks = [b for row in buttons for b in row if b["type"] == "callback"]
    assert [(b["text"], b["payload"]) for b in callbacks] == [("Принять", "acc:7"), ("Отклонить", "dec:7")]
    assert any(b["type"] == "link" for row in buttons for b in row), "ссылка на приложение остаётся"
    assert world.fallbacks[0] == notifications.open_button(1), "если MAX не примет кнопки — уйдёт обычная ссылка, а не пропадёт сообщение"


def test_response_decided_messages(world):
    add(response(1, 1, 2, "accepted"), response(2, 1, 3, "declined"), response(3, 1, 4, "pending"))
    with SessionLocal() as s:
        s.get(User, 1).username = "anya_k"
        s.commit()
    run(notifications.response_decided(1))
    run(notifications.response_decided(2))
    run(notifications.response_decided(3))
    assert to(world) == [2, 3]
    accepted, declined = world[0], world[1]
    assert "принял(а) ваш отклик" in accepted[1]
    assert {"type": "link", "text": "Написать автору", "url": "https://max.ru/anya_k"} in [b for row in accepted[2] for b in row]
    assert "не принят" in declined[1] and all(b["type"] != "link" or "max.ru/anya_k" not in b["url"] for row in declined[2] for b in row), "отклонённому контакт автора не даём"
    world.clear()
    with SessionLocal() as s:
        s.get(User, 1).username = None
        s.commit()
    run(notifications.response_decided(1))
    assert len([b for row in world[0][2] for b in row]) == 1, "нет username — нет и кнопки «Написать»"


def test_invitation_changed_goes_to_accepted_and_pending_only(world):
    add(response(1, 1, 2, "accepted"), response(2, 1, 3, "pending"), response(3, 1, 4, "declined"))
    run(notifications.invitation_changed(1, ["Когда: 5 мар, 17:30 (было: 15:00)"]))
    assert to(world) == [2, 3]
    assert "Автор изменил приглашение «Шахматы после уроков»" in world[0][1] and "17:30" in world[0][1]
    world.clear()
    run(notifications.invitation_changed(1, []))
    assert world == []


def test_set_full_tells_author_once(world):
    add(response(1, 1, 2, "accepted"), response(2, 1, 3, "accepted"))
    run(notifications.set_full(1))
    assert world == [], "набрано 2 из 3 — рано"
    add(response(3, 1, 4, "accepted"))
    run(notifications.set_full(1))
    run(notifications.set_full(1))
    assert to(world) == [1], "автору — один раз, сколько бы ни вызывали"
    assert "собран: 3 из 3" in world[0][1]
    world.clear()
    with SessionLocal() as s:
        s.get(Invitation, 1).status = "closed"
        s.commit()
    add(invitation(2, max_participants=1), response(4, 2, 2, "accepted"))
    with SessionLocal() as s:
        s.get(Invitation, 2).status = "closed"
        s.commit()
    run(notifications.set_full(2))
    assert world == [], "закрытому ничего не сообщаем"


def test_set_closed_messages(world):
    add(response(1, 1, 2, "accepted"), response(2, 1, 3, "pending"), response(3, 1, 4, "declined"))
    run(notifications.set_closed(1))
    assert to(world) == [2, 3], "отклонённым ничего: они уже получили отказ"
    assert "Вы в списке участников" in texts(world, 2)[0]
    assert "ваш отклик не был принят" in texts(world, 3)[0]
    world.clear()
    run(notifications.set_closed(1))
    assert world == [], "второй раз не пишем"


def test_remind_goes_to_author_and_accepted(world):
    add(response(1, 1, 2, "accepted"), response(2, 1, 3, "pending"))
    with SessionLocal() as s:
        s.get(Invitation, 1).when_time, s.get(Invitation, 1).when = "17:00", "у входа"
        s.commit()
    run(notifications.remind(1, soon=True))
    assert to(world) == [1, 2], "автор и принятые; ожидающим не пишем"
    assert "Напоминаем: сегодня в 17:00 «Шахматы после уроков» · у входа" in world[0][1] and "Участников: 1" in world[0][1]
    world.clear()
    run(notifications.remind(1, soon=True))
    assert world == [], "дважды одно напоминание не уходит"
    world.clear()
    add(invitation(2))
    run(notifications.remind(2, soon=False))
    assert texts(world) == ["Напоминаем: сегодня «Шахматы после уроков»."], "утреннее: без времени и без «участников: 0»"


def test_activity_off_silences_reminders_and_responses_only(world):
    add(response(1, 1, 2, "accepted"))
    with SessionLocal() as s:
        s.get(User, 2).notify_activity = False
        s.commit()
    run(notifications.remind(1, soon=False))
    assert to(world) == [1]
    world.clear()
    run(notifications.response_decided(1))
    assert world == []
    run(notifications.tell(2, "модерация"))
    assert to(world) == [2], "служебное всё равно доходит"


def when(inv_id, date, time="", offset_city=1, **kw):
    with SessionLocal() as s:
        i = s.get(Invitation, inv_id)
        i.when_date, i.when_time, i.city_id = date, time, offset_city
        for k, v in kw.items():
            setattr(i, k, v)
        s.commit()


def due(at):
    with SessionLocal() as s:
        return reminders.due(s, at)


def test_reminder_with_time_goes_two_hours_before(world):
    day = datetime(2026, 10, 22).date()
    when(1, day, "15:00")
    start = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
    assert due(start - timedelta(hours=2, minutes=1)) == []
    assert due(start - timedelta(hours=2)) == [(1, True)]
    assert due(start - timedelta(minutes=1)) == [(1, True)]
    assert due(start) == [], "встреча началась — напоминать поздно"
    assert due(start + timedelta(hours=1)) == []


def test_reminder_uses_the_events_city_time_zone(world):
    add(city(2, offset=420, name="Новосибирск"))
    day = datetime(2026, 10, 22).date()
    when(1, day, "15:00", offset_city=2)
    assert due(datetime(2026, 10, 22, 5, 59, tzinfo=UTC)) == []
    assert due(datetime(2026, 10, 22, 6, 0, tzinfo=UTC)) == [(1, True)]
    assert due(datetime(2026, 10, 22, 12, 0, tzinfo=UTC)) == [], "по московскому времени этой встречи уже нет"


def test_reminder_without_time_is_sent_in_the_daytime_only(world):
    day = datetime(2026, 10, 22).date()
    when(1, day)
    for hour, expected in [(4, False), (7, False), (8, True), (13, True), (19, True), (20, False), (23, False)]:
        at = datetime(2026, 10, 22, hour, 30, tzinfo=UTC) - timedelta(minutes=180)
        assert due(at) == ([(1, False)] if expected else []), f"{hour}:30 по Москве"
    assert due(datetime(2026, 10, 21, 12, 0, tzinfo=UTC)) == [], "накануне не напоминаем"
    assert due(datetime(2026, 10, 23, 12, 0, tzinfo=UTC)) == [], "и на следующий день"


def test_no_reminder_right_after_creating_a_soon_event(world):
    day = datetime(2026, 10, 22).date()
    created = datetime(2026, 10, 22, 11, 0, tzinfo=UTC)
    when(1, day, "15:00", created_at=created)
    assert due(datetime(2026, 10, 22, 11, 5, tzinfo=UTC)) == [], "человек только что сам про это написал"
    when(1, day, "15:00", created_at=datetime(2026, 10, 22, 9, 0, tzinfo=UTC))
    assert due(datetime(2026, 10, 22, 11, 5, tzinfo=UTC)) == [(1, True)]
    when(1, day, "", created_at=datetime(2026, 10, 22, 7, 0, tzinfo=UTC))
    assert due(datetime(2026, 10, 22, 9, 0, tzinfo=UTC)) == [], "утро уже прошло, когда приглашение появилось"


def test_reminder_skips_closed_hidden_and_undated(world):
    day = datetime(2026, 10, 22).date()
    at = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
    when(1, day, "", status="closed")
    assert due(at) == []
    when(1, day, "", status="open", hidden=True)
    assert due(at) == []
    when(1, None, "", hidden=False)
    assert due(at) == [], "без даты напоминать не о чем"
    when(1, day, "")
    assert due(at) == [(1, False)]


def test_run_once_sends_each_reminder_once(world, clock):
    add(response(1, 1, 2, "accepted"))
    when(1, datetime(2026, 10, 22).date(), "")
    clock.now = datetime(2026, 10, 22, 8, 0, tzinfo=UTC)
    assert run(reminders.run_once()) == 1
    assert to(world) == [1, 2]
    assert run(reminders.run_once()) == 1, "приглашение всё ещё «созревшее»…"
    assert to(world) == [1, 2], "…но повторно никому не уходит"
    assert reminders.status["last_run"] is not None and reminders.status["sent"] >= 2


def test_reminder_loop_survives_errors(database, monkeypatch):
    calls = []
    sleeps = []

    async def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("сбой базы")
        if len(calls) == 3:
            raise asyncio.CancelledError()
        return 0

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(reminders, "run_once", flaky)

    async def go():
        try:
            await reminders.remind_forever(sleep=fake_sleep)
        except asyncio.CancelledError:
            return "cancelled"

    assert run(go()) == "cancelled"
    assert len(calls) == 3 and sleeps == [reminders.INTERVAL] * 2, "после сбоя цикл продолжился"


def test_full_notification_story(client):
    agree(client, 1, 2, 3)
    h1, h2, h3 = as_user(1), as_user(2), as_user(3)
    inv = client.post("/api/invitations", json={"interest": "chess", "title": "Блиц", "max_participants": 2}, headers=h1).json()["id"]
    url = f"/api/invitations/{inv}"
    client.sent.clear()

    assert client.post(f"{url}/respond", headers=h2).status_code == 201
    assert client.post(f"{url}/respond", headers=h3).status_code == 201
    assert [u for u, _ in client.sent] == [1, 1], "автору — про каждый отклик"
    assert "Тест откликнулся(ась) на «Блиц»" in client.sent[0][1]

    responses = client.get(url, headers=h1).json()["responses"]
    client.sent.clear()
    client.post(f"/api/responses/{responses[0]['id']}/accept", headers=h1)
    assert [u for u, _ in client.sent] == [2], "принятому — решение; набор ещё не собран"
    client.sent.clear()
    client.post(f"/api/responses/{responses[1]['id']}/accept", headers=h1)
    assert sorted(u for u, _ in client.sent) == [1, 3]
    assert any(u == 1 and "собран: 2 из 2" in t for u, t in client.sent), "автору — что комплект собран"

    client.sent.clear()
    client.post(f"{url}/close", headers=h1)
    assert sorted(u for u, _ in client.sent) == [2, 3] and all("Вы в списке участников" in t for _, t in client.sent)
    client.sent.clear()
    client.post(f"{url}/close", headers=h1)
    assert len(client.sent) == 0


def test_closing_tells_waiting_responders(client):
    agree(client, 1, 2, 3)
    inv = new_invitation(client, 1)
    client.post(f"/api/invitations/{inv}/respond", headers=as_user(2))
    client.sent.clear()
    client.post(f"/api/invitations/{inv}/close", headers=as_user(1))
    assert [(u, "не был принят" in t) for u, t in client.sent] == [(2, True)]


def test_activity_setting_via_api_and_bot_info(client, monkeypatch):
    agree(client, 1)
    me = client.get("/api/me", headers=as_user(1)).json()
    assert me["notify_activity"] is True and me["bot"] == {"state": "unknown", "link": None}
    monkeypatch.setattr(settings, "bot_username", "kto_bot")
    assert client.get("/api/me", headers=as_user(1)).json()["bot"]["link"] == "https://max.ru/kto_bot"
    assert client.put("/api/me", json={"notify_activity": False}, headers=as_user(1)).json()["notify_activity"] is False
    assert client.put("/api/me", json={"notify": False}, headers=as_user(1)).json()["notify_activity"] is False, "одно не трогает другое"
    assert client.put("/api/me", json={"notify_activity": True}, headers=as_user(1)).json()["notify"] is False

    agree(client, 2)
    inv = new_invitation(client, 1)
    client.put("/api/me", json={"notify_activity": False}, headers=as_user(1))
    client.sent.clear()
    client.post(f"/api/invitations/{inv}/respond", headers=as_user(2))
    assert len(client.sent) == 0
    client.put("/api/me", json={"notify_activity": True}, headers=as_user(1))
    assert client.get("/api/me", headers=as_user(1)).json()["bot"]["state"] == "unknown", "пока ничего не доходило — не знаем"


def test_delivery_updates_bot_state_in_profile(client, outbox):
    agree(client, 1, 2)
    inv = new_invitation(client, 1)
    client.post(f"/api/invitations/{inv}/respond", headers=as_user(2))
    assert client.get("/api/me", headers=as_user(1)).json()["bot"]["state"] == "ok", "автору дошло — значит, бот может писать"

    outbox.result = SendResult(False, permanent=True)
    for _ in range(notifications.BOT_FAILS_TO_BLOCK):
        run(notifications.deliver(1, "response", "x"))
    assert client.get("/api/me", headers=as_user(1)).json()["bot"]["state"] == "blocked"


def test_user_deleted_while_sending_does_not_crash(world, monkeypatch):
    from app.max_client import max_client

    async def send_then_delete(user_id, text, buttons=None, fallback_buttons=None):
        with SessionLocal() as s:
            s.delete(s.get(User, user_id))
            s.commit()
        return SendResult(True)

    monkeypatch.setattr(max_client, "send", send_then_delete)
    assert run(notifications.deliver(2, "response", "x")) is True
    assert get(User, 2) is None
