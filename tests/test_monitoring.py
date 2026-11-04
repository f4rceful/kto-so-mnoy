import asyncio
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from helpers import UTC, add, agree, as_user, city, get, invitation, response, run, user
from prometheus_client.parser import text_string_to_metric_families

from app import activity, bans, bot, db
from app.config import settings
from app.db import QueuedMessage, UserActivity
from app.main import app
from app.max_client import HOOKS, MaxClient

TOKEN = "t" * 24
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture()
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "metrics_token", TOKEN)


def scrape(client):
    r = client.get("/metrics", headers=AUTH)
    assert r.status_code == 200, r.text
    samples = {}
    for family in text_string_to_metric_families(r.text):
        for s in family.samples:
            samples[(s.name, tuple(sorted(s.labels.items())))] = s.value
    return samples


def value(samples, name, **labels):
    return samples.get((name, tuple(sorted(labels.items()))))


def activity_rows():
    with db.SessionLocal() as s:
        return s.query(UserActivity).count()


def test_each_authenticated_user_is_recorded_once_per_day(client):
    agree(client, 1, 2)
    for _ in range(3):
        client.get("/api/me", headers=as_user(1))
    assert activity_rows() == 2
    client.get("/api/me", headers=as_user(2))
    assert activity_rows() == 2


def test_anonymous_requests_leave_no_activity(client):
    client.get("/api/me")
    client.get("/api/terms")
    assert activity_rows() == 0


def test_activity_survives_a_cleared_cache(client):
    agree(client, 1)
    activity.seen.clear()
    client.get("/api/me", headers=as_user(1))
    assert activity_rows() == 1


def test_active_users_by_period(client, enabled, monkeypatch):
    agree(client, 1, 2, 3)
    today = activity.today()
    monkeypatch.setattr(activity, "today", lambda: today - timedelta(days=5))
    client.get("/api/me", headers=as_user(1))
    monkeypatch.setattr(activity, "today", lambda: today - timedelta(days=40))
    client.get("/api/me", headers=as_user(2))
    monkeypatch.setattr(activity, "today", lambda: today)
    activity.seen.clear()
    client.get("/api/me", headers=as_user(3))

    m = scrape(client)
    assert value(m, "kto_active_users", period="1d") >= 1
    assert value(m, "kto_active_users", period="7d") >= 2
    assert value(m, "kto_active_users", period="30d") >= 2
    assert value(m, "kto_active_users", period="30d") < 6


def test_funnel_counts_users_reaching_each_step(client, enabled):
    add(city(), user(1), user(2), user(3, onboarded=False), user(4))
    add(
        invitation(1, 1),
        invitation(2, 1),
        invitation(3, 2),
        response(1, 1, 3, "accepted"),
        response(2, 1, 4, "pending"),
        response(3, 3, 3, "pending"),
    )
    m = scrape(client)
    stage = lambda name: value(m, "kto_funnel_users", stage=name)
    assert stage("registered") == 4
    assert stage("onboarded") == 3
    assert stage("created_invitation") == 2
    assert stage("got_response") == 2
    assert stage("accepted_response") == 1
    assert stage("responded") == 2


def test_filled_and_held_counters(client, enabled):
    past = date.today() - timedelta(days=3)
    add(city(), user(1), user(2), user(3), user(4))
    add(
        invitation(1, 1, max_participants=2, when_date=past),
        invitation(2, 1, max_participants=3),
        invitation(3, 2, max_participants=1, when_date=past, hidden=True),
        response(1, 1, 2, "accepted"),
        response(2, 1, 3, "accepted"),
        response(3, 2, 2, "accepted"),
        response(4, 3, 4, "accepted"),
    )
    m = scrape(client)
    assert value(m, "kto_invitations_filled") == 2
    assert value(m, "kto_meetups_held") == 1


def test_first_response_histogram(client, enabled):
    base = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
    add(city(), user(1), user(2), user(3))
    add(invitation(1, 1, created_at=base), invitation(2, 1, created_at=base), invitation(3, 1, created_at=base))
    add(
        response(1, 1, 2),
        response(2, 2, 2),
        response(3, 2, 3),
    )
    with db.SessionLocal() as s:
        s.get(db.Response, 1).created_at = base + timedelta(minutes=2)
        s.get(db.Response, 2).created_at = base + timedelta(hours=2)
        s.get(db.Response, 3).created_at = base + timedelta(days=2)
        s.commit()
    m = scrape(client)
    assert value(m, "kto_first_response_seconds_count") == 2
    assert value(m, "kto_first_response_seconds_bucket", le="300.0") == 1
    assert value(m, "kto_first_response_seconds_bucket", le="10800.0") == 2
    assert value(m, "kto_first_response_seconds_sum") == 120 + 7200


def test_oldest_queued_message_age(client, enabled, monkeypatch):
    now = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(bans, "utcnow", lambda: now)
    assert value(scrape(client), "kto_notification_outbox_oldest_age_seconds") == 0
    add(user(1))
    add(
        QueuedMessage(user_id=1, kind="system", text="a", next_at=now, created_at=now - timedelta(minutes=10)),
        QueuedMessage(user_id=1, kind="system", text="b", next_at=now, created_at=now - timedelta(minutes=2)),
    )
    m = scrape(client)
    assert value(m, "kto_notification_outbox") == 2
    assert value(m, "kto_notification_outbox_oldest_age_seconds") == 600


def test_build_info_and_start_time(client, enabled, monkeypatch):
    monkeypatch.setattr(settings, "app_version", "9.9.9")
    m = scrape(client)
    assert value(m, "kto_build_info", version="9.9.9") == 1
    assert value(m, "kto_start_time_seconds") > 1_700_000_000


def test_unhandled_errors_are_counted_by_route(client, enabled):
    async def boom():
        raise RuntimeError("test failure")

    app.add_api_route("/api/test-boom", boom, methods=["GET"])
    app.router.routes.insert(0, app.router.routes.pop())
    try:
        quiet = TestClient(app, raise_server_exceptions=False)
        before = scrape(client)
        assert quiet.get("/api/test-boom").status_code == 500
        after = scrape(client)
    finally:
        app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", "") != "/api/test-boom"]
    key = dict(route="/api/test-boom")
    assert value(after, "kto_unhandled_errors_total", **key) - (value(before, "kto_unhandled_errors_total", **key) or 0) == 1
    assert value(after, "kto_http_requests_total", method="GET", route="/api/test-boom", status="500") >= 1


def max_client_with(handler):
    transport = httpx.MockTransport(handler)
    http = httpx.AsyncClient(transport=transport, base_url="https://api.test", event_hooks=HOOKS)

    async def no_sleep(_):
        return None

    return MaxClient(http=http, sleep=no_sleep)


def test_max_api_calls_are_measured(client, enabled):
    before = scrape(client)
    api = max_client_with(lambda request: httpx.Response(200, json={}))
    assert run(api.send(1, "привет")).ok
    after = scrape(client)
    key = dict(call="POST /messages", status="200")
    gained = value(after, "kto_max_api_responses_total", **key) - (value(before, "kto_max_api_responses_total", **key) or 0)
    assert gained == 1
    count = lambda m: value(m, "kto_max_api_duration_seconds_count", call="POST /messages") or 0
    assert count(after) - count(before) == 1


def test_max_api_error_codes_and_network_failures_are_measured(client, enabled):
    before = scrape(client)
    api = max_client_with(lambda request: httpx.Response(403, json={"code": "forbidden"}))
    assert not run(api.send(1, "x")).ok

    def broken(request):
        raise httpx.ConnectError("down")

    failing = max_client_with(broken)
    assert not run(failing.send(1, "x")).ok
    after = scrape(client)
    forbidden = dict(call="POST /messages", status="403")
    assert value(after, "kto_max_api_responses_total", **forbidden) - (value(before, "kto_max_api_responses_total", **forbidden) or 0) == 1
    failed = dict(call="POST /messages")
    assert value(after, "kto_max_api_failures_total", **failed) - (value(before, "kto_max_api_failures_total", **failed) or 0) == 3


def test_bot_events_are_counted_by_type(client, enabled, monkeypatch):
    seen = []

    async def handler(update):
        seen.append(update["update_type"])

    monkeypatch.setitem(bot.HANDLERS, "bot_started", handler)
    before = scrape(client)
    run(bot.handle_update({"update_type": "bot_started"}))
    run(bot.handle_update({"update_type": "something_new"}))
    run(bot.handle_update({}))
    after = scrape(client)
    delta = lambda **k: (value(after, "kto_bot_events_total", **k) or 0) - (value(before, "kto_bot_events_total", **k) or 0)
    assert delta(type="bot_started") == 1 and delta(type="other") == 2
    assert seen == ["bot_started"]


def test_bot_failure_streak_is_exported(client, enabled, monkeypatch):
    monkeypatch.setattr(bot, "status", {"enabled": True, "mode": "polling", "last_ok": None, "failures": 4, "last_error": "x"})
    assert value(scrape(client), "kto_bot_failures") == 4


def test_admin_links(client, admin):
    assert client.get("/api/admin/links").status_code == 401
    assert client.get("/api/admin/links", headers=admin).json() == {"grafana": ""}
    settings.grafana_url = " http://localhost:3300 "
    try:
        assert client.get("/api/admin/links", headers=admin).json() == {"grafana": "http://localhost:3300"}
    finally:
        settings.grafana_url = ""
