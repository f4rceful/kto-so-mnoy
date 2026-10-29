import asyncio
import json
import logging
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app import bot, reminders
from app.config import settings
from app.deps import get_db
from app.main import app
from app.max_client import ATTEMPTS, CONCURRENCY, MAX_RETRY_AFTER, MaxClient, max_client


def make_client(handler):
    sleeps: list[float] = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.test")
    return MaxClient(http=http, sleep=fake_sleep), sleeps


def send(client, **kw):
    return asyncio.run(client.send_message(kw.get("user_id", 7), kw.get("text", "Привет"), kw.get("buttons")))


def test_sent_first_time():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={})

    client, sleeps = make_client(handler)
    buttons = [[{"type": "link", "text": "Открыть", "url": "https://max.ru/b?startapp=inv_1"}]]
    assert send(client, user_id=42, text="Текст", buttons=buttons) is True
    assert len(seen) == 1 and sleeps == []
    assert seen[0].url.params["user_id"] == "42"
    body = seen[0].read().decode()
    assert "Текст" in body and "inline_keyboard" in body and "inv_1" in body
    assert client.stats == {"sent": 1, "failed": 0, "retries": 0}


def test_transient_server_errors_are_retried():
    answers = iter([500, 502, 200])
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(next(answers))

    client, sleeps = make_client(handler)
    assert send(client) is True
    assert len(calls) == 3 and sleeps == [0.5, 1.5]
    assert client.stats == {"sent": 1, "failed": 0, "retries": 2}


def test_gives_up_after_all_attempts():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(503, text="перегрузка")

    client, sleeps = make_client(handler)
    assert send(client) is False
    assert len(calls) == ATTEMPTS and len(sleeps) == ATTEMPTS - 1
    assert client.stats["failed"] == 1 and client.stats["sent"] == 0 and client.last_error == "HTTP 503"


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_permanent_errors_are_not_retried(status):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status, text="dialog.not.found")

    client, sleeps = make_client(handler)
    assert send(client) is False
    assert len(calls) == 1 and sleeps == [], "повтором такое не исправить"
    assert client.stats == {"sent": 0, "failed": 1, "retries": 0}


def test_rejected_keyboard_on_last_attempt_still_sends_plain_message():
    keyboard = [[{"type": "callback", "text": "Принять", "payload": "acc_1"}]]
    plain = [[{"type": "link", "text": "Открыть", "url": "https://max.ru/b?startapp=inv_1"}]]
    answers = iter([503, 503, 400, 200])
    bodies = []

    def handler(request):
        bodies.append(request.read().decode())
        return httpx.Response(next(answers), text="bad keyboard")

    client, sleeps = make_client(handler)
    result = asyncio.run(client.send(7, "Отклик", keyboard, fallback_buttons=plain))
    assert result.ok, "замена клавиатуры на последней попытке не должна терять сообщение"
    assert len(bodies) == ATTEMPTS + 1 and "acc_1" in bodies[2] and "acc_1" not in bodies[3] and "inv_1" in bodies[3]
    assert len(sleeps) == ATTEMPTS - 1 and client.stats == {"sent": 1, "failed": 0, "retries": 2}


def test_rate_limit_respects_retry_after_but_not_forever():
    answers = iter([httpx.Response(429, headers={"Retry-After": "2"}), httpx.Response(429, headers={"Retry-After": "999"}), httpx.Response(200)])
    client, sleeps = make_client(lambda request: next(answers))
    assert send(client) is True
    assert sleeps == [2.0, float(MAX_RETRY_AFTER)]

    answers = iter([httpx.Response(429, headers={"Retry-After": "soon"}), httpx.Response(200)])
    client, sleeps = make_client(lambda request: next(answers))
    assert send(client) is True and sleeps == [0.5], "непонятный Retry-After — пауза по умолчанию"


def test_network_errors_are_retried_and_never_raised():
    attempts = []

    def flaky(request):
        attempts.append(1)
        if len(attempts) < 3:
            raise httpx.ConnectError("нет сети")
        return httpx.Response(200)

    client, sleeps = make_client(flaky)
    assert send(client) is True and len(attempts) == 3

    def dead(request):
        raise httpx.ReadTimeout("таймаут")

    client, sleeps = make_client(dead)
    assert send(client) is False
    assert client.last_error.startswith("сеть: ReadTimeout")


def test_failure_log_has_no_message_text(caplog):
    client, _ = make_client(lambda request: httpx.Response(403, text="forbidden"))
    with caplog.at_level(logging.WARNING, logger="app.max_client"):
        send(client, user_id=555, text="Аня откликнулась на «Секретное приглашение»")
    log = caplog.text
    assert "555" in log and "HTTP 403" in log
    assert "Аня" not in log and "Секретное" not in log, "имена и тексты в логи не попадают"


def test_concurrency_is_limited():
    state = {"now": 0, "peak": 0}

    async def handler(request):
        state["now"] += 1
        state["peak"] = max(state["peak"], state["now"])
        await asyncio.sleep(0.01)
        state["now"] -= 1
        return httpx.Response(200)

    client, _ = make_client(handler)

    async def burst():
        return await asyncio.gather(*(client.send_message(i, "x") for i in range(CONCURRENCY * 4)))

    assert all(asyncio.run(burst()))
    assert 1 < state["peak"] <= CONCURRENCY, f"одновременно было {state['peak']}"


class Stop(asyncio.CancelledError):
    pass


@pytest.fixture()
def run_poll(database, monkeypatch):
    return lambda steps: _run_poll(monkeypatch, steps)


def _run_poll(monkeypatch, steps):
    sleeps, handled = [], []
    steps = iter(steps)

    async def fake_get(marker=None, timeout=30):
        try:
            step = next(steps)
        except StopIteration:
            raise Stop()
        if isinstance(step, BaseException):
            raise step
        return step

    async def fake_send(user_id, text, buttons=None):
        handled.append(user_id)
        return True

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(max_client, "get_updates", fake_get)
    monkeypatch.setattr(max_client, "send_message", fake_send)
    monkeypatch.setattr(bot, "status", {**bot.status, "enabled": False, "last_ok": None, "failures": 0, "last_error": ""})

    async def go():
        try:
            await bot.poll_forever(sleep=fake_sleep)
        except asyncio.CancelledError:
            return "cancelled"

    assert asyncio.run(go()) == "cancelled"
    return sleeps, handled


def started(uid):
    return {"update_type": "bot_started", "user": {"user_id": uid}}


def test_polling_survives_any_error(run_poll):
    sleeps, handled = run_poll(
        [
            httpx.ConnectError("нет сети"),
            ValueError("битый JSON"),
            KeyError("marker"),
            {"marker": 5, "updates": [started(1)]},
            httpx.ReadTimeout("пусто"),
            {"marker": 6, "updates": [started(2)]},
        ],
    )
    assert sleeps == [5, 10, 20], "паузы нарастают при подряд идущих сбоях"
    assert handled == [1, 2], "после сбоев обновления продолжают обрабатываться"
    assert bot.status["failures"] == 0 and bot.status["last_ok"] is not None and bot.status["last_error"] == ""


def test_backoff_resets_and_is_capped(run_poll):
    errors = [httpx.ConnectError("x")] * 6
    sleeps, _ = run_poll(errors + [{"updates": []}] + [httpx.ConnectError("y")])
    assert sleeps == [5, 10, 20, 40, 60, 60, 5], "потолок 60 с, а после успеха отсчёт начинается заново"


def test_bad_update_does_not_stop_the_loop(run_poll):
    sleeps, handled = run_poll(
        [{"marker": 1, "updates": [{"update_type": "bot_started"}, {"update_type": "message_created", "message": {}}, started(9)]}],
    )
    assert handled == [9] and sleeps == [], "битые обновления пропускаются, остальные обрабатываются"
    assert bot.status["failures"] == 0


def test_poll_status_flags(run_poll):
    run_poll([httpx.ConnectError("нет сети")])
    assert bot.status["failures"] == 1 and bot.status["last_error"] == "ConnectError" and bot.status["enabled"] is False


@pytest.fixture()
def api(database, monkeypatch):
    monkeypatch.setattr(max_client, "stats", {"sent": 0, "failed": 0, "retries": 0})
    monkeypatch.setattr(max_client, "last_error", "")
    monkeypatch.setattr(reminders, "status", {"last_run": None, "sent": 0})
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


def test_health_ok_without_bot(api):
    r = api.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {
        "status": "ok", "db": "ok", "bot": "off",
        "notifications": {"sent": 0, "failed": 0, "retries": 0, "last_error": "", "queued": 0},
        "reminders": {"last_run": None, "sent": 0},
    }
    assert "no-store" not in r.headers.get("cache-control", "")


def test_health_reports_bot_state(api, monkeypatch):
    monkeypatch.setattr(settings, "bot_token", "token")
    now = time.time()
    cases = [
        ({"enabled": True, "last_ok": now}, "ok", "ok"),
        ({"enabled": True, "last_ok": now - 600}, "stale", "degraded"),
        ({"enabled": True, "last_ok": None}, "stale", "degraded"),
        ({"enabled": False, "last_ok": now}, "down", "degraded"),
        ({"enabled": True, "mode": "webhook", "last_ok": now - 600}, "ok", "ok"),
        ({"enabled": False, "mode": "webhook", "last_ok": None}, "down", "degraded"),
    ]
    for state, bot_state, status in cases:
        monkeypatch.setattr(bot, "status", {"failures": 0, "last_error": "", **state})
        r = api.get("/api/health")
        assert r.status_code == 200, "сбой бота не должен приводить к перезапуску контейнера"
        assert (r.json()["bot"], r.json()["status"]) == (bot_state, status), state


def test_health_shows_notification_counters(api):
    max_client.stats.update(sent=5, failed=2, retries=3)
    max_client.last_error = "HTTP 403"
    assert api.get("/api/health").json()["notifications"] == {"sent": 5, "failed": 2, "retries": 3, "last_error": "HTTP 403", "queued": 0}


def test_health_is_503_when_database_is_down(api):
    class BrokenSession:
        def execute(self, *a, **k):
            raise RuntimeError("база недоступна")

    app.dependency_overrides[get_db] = lambda: BrokenSession()
    r = api.get("/api/health")
    assert r.status_code == 503 and r.json() == {"status": "down", "db": "error"}


def test_unexpected_error_gets_friendly_message_and_log(api, caplog):
    def boom():
        raise RuntimeError("секретная внутренняя причина")

    app.dependency_overrides[get_db] = boom
    with caplog.at_level(logging.ERROR, logger="app.main"):
        r = api.get("/api/health")
    assert r.status_code == 500
    body = r.json()
    assert body["detail"].startswith("Что-то пошло не так")
    assert "секретная" not in r.text and "Traceback" not in r.text, "внутренние детали пользователю не показываем"
    assert "секретная внутренняя причина" in caplog.text and "/api/health" in caplog.text, "а в лог — со всеми подробностями"


def test_health_needs_no_login(api):
    assert api.get("/api/health").status_code == 200


def test_bot_asks_max_for_every_event_it_handles():
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json={"updates": [], "marker": 1})

    client, _ = make_client(handler)
    asyncio.run(client.get_updates(marker=5, timeout=7))
    asked = set(seen[0]["types"].split(","))
    assert asked == {"message_created", "bot_started", "bot_stopped", "message_callback"}
    assert seen[0]["marker"] == "5" and seen[0]["timeout"] == "7"
    assert asked == set(bot.HANDLERS), "просим у MAX ровно те события, которые бот умеет обрабатывать"


@pytest.fixture()
def hook(api, monkeypatch):
    monkeypatch.setattr(settings, "bot_token", "token")
    monkeypatch.setattr(settings, "public_url", "https://kto.example.ru/")
    handled = []

    async def fake_handle(updates):
        handled.extend(updates)

    monkeypatch.setattr(bot, "handle_updates", fake_handle)
    api.handled = handled
    return api


def test_webhook_url_and_secret(hook):
    assert bot.webhook_url() == "https://kto.example.ru/api/bot/webhook"
    assert 5 <= len(bot.webhook_secret()) <= 256 and "token" not in bot.webhook_secret()


def test_webhook_accepts_only_max_with_secret(hook):
    update = {"update_type": "bot_started", "user": {"user_id": 7}}
    assert hook.post(bot.WEBHOOK_PATH, json=update).status_code == 401
    assert hook.post(bot.WEBHOOK_PATH, json=update, headers={"X-Max-Bot-Api-Secret": "wrong-secret"}).status_code == 401
    assert hook.handled == []
    r = hook.post(bot.WEBHOOK_PATH, json=update, headers={"X-Max-Bot-Api-Secret": bot.webhook_secret()})
    assert r.status_code == 200 and hook.handled == [update]


def test_webhook_rejects_garbage(hook):
    headers = {"X-Max-Bot-Api-Secret": bot.webhook_secret(), "Content-Type": "application/json"}
    assert hook.post(bot.WEBHOOK_PATH, content=b"{", headers=headers).status_code == 400
    assert hook.post(bot.WEBHOOK_PATH, json=[1, 2], headers=headers).status_code == 400
    assert hook.handled == []


def test_webhook_is_off_without_public_url(hook, monkeypatch):
    monkeypatch.setattr(settings, "public_url", "")
    r = hook.post(bot.WEBHOOK_PATH, json={}, headers={"X-Max-Bot-Api-Secret": bot.webhook_secret()})
    assert r.status_code == 404


def test_subscription_is_retried_until_max_agrees(monkeypatch):
    monkeypatch.setattr(settings, "public_url", "https://kto.example.ru")
    monkeypatch.setattr(bot, "status", {**bot.status, "enabled": False, "failures": 0, "last_error": ""})
    calls, sleeps = [], []

    def handler(request):
        calls.append(json.loads(request.content))
        if len(calls) < 3:
            return httpx.Response(200, json={"success": False, "message": "url недоступен"})
        return httpx.Response(200, json={"success": True})

    client, _ = make_client(handler)
    monkeypatch.setattr(bot, "max_client", client)

    async def fake_sleep(s):
        sleeps.append(s)

    asyncio.run(bot.subscribe_forever(sleep=fake_sleep))
    assert sleeps == [5, 10] and bot.status["enabled"] is True and bot.status["mode"] == "webhook"
    assert calls[-1]["url"] == "https://kto.example.ru/api/bot/webhook"
    assert set(calls[-1]["update_types"]) == set(bot.HANDLERS) and calls[-1]["secret"] == bot.webhook_secret()
