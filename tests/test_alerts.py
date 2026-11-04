import pytest

from app import alerts
from app.config import settings
from app.max_client import SendResult

TOKEN = "t" * 24
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def alert(name="DatabaseDown", status="firing", **extra):
    return {
        "status": status,
        "labels": {"alertname": name, "severity": extra.pop("severity", "critical")},
        "annotations": {"summary": extra.pop("summary", "База данных не отвечает"), "description": extra.pop("description", "Уже 2 минуты")},
    }


@pytest.fixture()
def configured(monkeypatch):
    monkeypatch.setattr(settings, "metrics_token", TOKEN)
    monkeypatch.setattr(settings, "alert_user_ids", "101, 202")


def post(client, alerts_list, headers=AUTH):
    return client.post("/api/alerts/webhook", json={"alerts": alerts_list, "status": "firing", "receiver": "kto", "version": "4"}, headers=headers)


def test_webhook_is_off_by_default(client):
    assert post(client, [alert()]).status_code == 404
    assert client.outbox == []


def test_webhook_is_off_without_recipients(client, monkeypatch):
    monkeypatch.setattr(settings, "metrics_token", TOKEN)
    assert post(client, [alert()]).status_code == 404


def test_webhook_is_off_without_a_token(client, monkeypatch):
    monkeypatch.setattr(settings, "alert_user_ids", "101")
    assert post(client, [alert()], headers={}).status_code == 404


def test_webhook_requires_the_bearer_token(client, configured):
    assert post(client, [alert()], headers={}).status_code == 401
    assert post(client, [alert()], headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.outbox == []


def test_firing_alert_reaches_every_recipient(client, configured):
    r = post(client, [alert()])
    assert r.status_code == 200 and r.json() == {"alerts": 1, "delivered": 2}
    assert [uid for uid, _ in client.sent] == [101, 202]
    text = client.sent[0][1]
    assert text.startswith("Проблема: База данных не отвечает")
    assert "Уже 2 минуты" in text and "Важность: критично" in text


def test_resolved_alert_says_so_and_skips_severity(client, configured):
    post(client, [alert(status="resolved")])
    text = client.sent[0][1]
    assert text.startswith("Решено: База данных не отвечает") and "Важность" not in text


def test_alert_without_annotations_falls_back_to_its_name(client, configured):
    post(client, [{"status": "firing", "labels": {"alertname": "Странное"}, "annotations": {}}])
    assert client.sent[0][1].splitlines()[0] == "Проблема: Странное"


def test_many_alerts_are_grouped_into_few_messages(client, configured, monkeypatch):
    monkeypatch.setattr(settings, "alert_user_ids", "101")
    batch = [alert(name=f"A{i}", summary=f"Сбой {i}") for i in range(alerts.ALERTS_PER_MESSAGE + 2)]
    r = post(client, batch)
    assert r.json() == {"alerts": len(batch), "delivered": 2}
    assert len(client.sent) == 2
    assert client.sent[0][1].count("Проблема:") == alerts.ALERTS_PER_MESSAGE
    assert client.sent[1][1].count("Проблема:") == 2


def test_undelivered_messages_are_not_counted(client, configured):
    client.outbox.result = SendResult(False)
    assert post(client, [alert()]).json() == {"alerts": 1, "delivered": 0}


def test_empty_payload_sends_nothing(client, configured):
    assert post(client, []).json() == {"alerts": 0, "delivered": 0}
    assert client.outbox == []


@pytest.mark.parametrize("raw, expected", [("101,202", [101, 202]), (" 5 ; 6 ", [5, 6]), ("abc, 7,", [7]), ("", []), ("-3, 4", [4])])
def test_recipient_list_parsing(monkeypatch, raw, expected):
    monkeypatch.setattr(settings, "alert_user_ids", raw)
    assert alerts.recipients() == expected
