import sys
import time

import pytest
from helpers import add, agree, as_user, city, invitation, new_invitation, response, user
from prometheus_client.parser import text_string_to_metric_families

from app import bot, db, metrics
from app.config import settings
from app.max_client import max_client

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


def test_endpoint_is_off_without_a_token(client):
    assert client.get("/metrics").status_code == 404
    assert client.get("/metrics", headers=AUTH).status_code == 404


def test_endpoint_requires_the_bearer_token(client, enabled):
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/metrics", headers={"Authorization": TOKEN}).status_code == 401
    ok = client.get("/metrics", headers=AUTH)
    assert ok.status_code == 200 and ok.headers["content-type"].startswith("text/plain")
    assert "kto_db_up 1.0" in ok.text


def test_metrics_are_not_in_the_api_docs(client, enabled):
    assert "/metrics" not in client.get("/openapi.json").json()["paths"]


def test_business_gauges_reflect_the_database(client, enabled, admin):
    add(city(), user(1), user(2), user(3, banned=True, onboarded=False))
    add(
        invitation(1, 1),
        invitation(2, 1, status="closed"),
        invitation(3, 2, hidden=True),
        response(1, 1, 2, "accepted"),
        response(2, 1, 3, "pending"),
        response(3, 2, 2, "declined"),
    )
    agree(client, 9)
    client.post("/api/invitations/1/report", json={"reason": "spam"}, headers=as_user(9))
    client.post("/api/admin/invitations/2/restore", headers=admin)

    m = scrape(client)
    assert value(m, "kto_users", state="registered") == 4
    assert value(m, "kto_users", state="onboarded") == 2
    assert value(m, "kto_users", state="banned") == 1
    assert value(m, "kto_invitations", status="open") == 2
    assert value(m, "kto_invitations", status="closed") == 1
    assert value(m, "kto_invitations_hidden") == 1
    assert value(m, "kto_invitations_created_total") == 3
    assert value(m, "kto_responses", status="accepted") == 1
    assert value(m, "kto_responses", status="pending") == 1
    assert value(m, "kto_responses", status="declined") == 1
    assert value(m, "kto_responses_created_total") == 3
    assert value(m, "kto_reports_open") == 1
    assert value(m, "kto_reports_created_total") == 1
    assert value(m, "kto_moderation_actions_total", action="restore") == 1
    assert value(m, "kto_notification_outbox") == 0


def test_temporary_bans_are_counted(client, enabled, admin):
    agree(client, 1, 2)
    client.post("/api/admin/users/1/ban", json={"days": 3}, headers=admin)
    client.post("/api/admin/users/2/ban", headers=admin)
    m = scrape(client)
    assert value(m, "kto_bans_temporary") == 1
    assert value(m, "kto_moderation_actions_total", action="ban") == 2


def test_request_metrics_use_route_templates(client, enabled):
    agree(client, 1)
    first, second = new_invitation(client, 1, "Первое"), new_invitation(client, 1, "Второе")
    before = scrape(client)
    key = dict(method="GET", route="/api/invitations/{inv_id}", status="200")
    for inv in (first, second, first):
        assert client.get(f"/api/invitations/{inv}", headers=as_user(1)).status_code == 200
    after = scrape(client)
    assert value(after, "kto_http_requests_total", **key) - (value(before, "kto_http_requests_total", **key) or 0) == 3
    assert not [k for k in after if any(v == f"/api/invitations/{first}" for _, v in k[1])]
    duration = value(after, "kto_http_request_duration_seconds_count", method="GET", route="/api/invitations/{inv_id}")
    assert duration >= 3


def test_error_and_unknown_routes_are_labelled(client, enabled):
    before = scrape(client)
    assert client.get("/api/invitations/99999", headers=as_user(1)).status_code in (403, 404)
    assert client.get("/api/me").status_code == 401
    after = scrape(client)
    unauthorized = dict(method="GET", route="/api/me", status="401")
    assert value(after, "kto_http_requests_total", **unauthorized) - (value(before, "kto_http_requests_total", **unauthorized) or 0) == 1


def test_scraping_itself_is_not_counted(client, enabled):
    scrape(client)
    scrape(client)
    assert not [k for k in scrape(client) if any(v == "/metrics" for _, v in k[1])]


def test_in_progress_gauge_returns_to_zero(client, enabled):
    client.get("/api/me")
    assert value(scrape(client), "kto_http_requests_in_progress") == 0


def test_database_outage_is_reported_not_raised(client, enabled, monkeypatch):
    class Broken:
        def __enter__(self):
            raise RuntimeError("db is down")

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(metrics, "SessionLocal", lambda: Broken())
    m = scrape(client)
    assert value(m, "kto_db_up") == 0
    assert value(m, "kto_users", state="registered") is None
    assert value(m, "kto_bot_state", state="off") == 1


def test_bot_state_is_one_hot(client, enabled, monkeypatch):
    monkeypatch.setattr(settings, "bot_token", "token")
    monkeypatch.setattr(bot, "status", {"enabled": True, "mode": "polling", "last_ok": time.time(), "failures": 0, "last_error": ""})
    m = scrape(client)
    assert [value(m, "kto_bot_state", state=s) for s in ("ok", "stale", "down", "off")] == [1, 0, 0, 0]
    monkeypatch.setattr(bot, "status", {"enabled": False, "mode": "polling", "last_ok": None, "failures": 0, "last_error": ""})
    m = scrape(client)
    assert [value(m, "kto_bot_state", state=s) for s in ("ok", "stale", "down", "off")] == [0, 0, 1, 0]


def test_delivery_and_reminder_counters_mirror_runtime_state(client, enabled, monkeypatch):
    max_client.stats.update(sent=7, failed=2, retries=3)
    monkeypatch.setattr("app.reminders.status", {"last_run": 1700000000.0, "sent": 4})
    m = scrape(client)
    assert value(m, "kto_notifications_total", result="sent") == 7
    assert value(m, "kto_notifications_total", result="failed") == 2
    assert value(m, "kto_notifications_total", result="retried") == 3
    assert value(m, "kto_reminders_total") == 4
    assert value(m, "kto_reminders_last_run_timestamp_seconds") == 1700000000.0


def test_process_metrics_are_exported(client, enabled):
    text = client.get("/metrics", headers=AUTH).text
    assert "python_info" in text and "python_gc_objects_collected_total" in text
    if sys.platform.startswith("linux"):
        assert "process_resident_memory_bytes" in text and "process_cpu_seconds_total" in text
