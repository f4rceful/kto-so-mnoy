from datetime import date
from urllib.parse import parse_qs, urlparse

from helpers import add, as_user, city, invitation, user

from app import ics
from app.config import settings


def unfold(body):
    return body.replace("\r\n ", "").split("\r\n")


def setup_invitation(**kw):
    add(city(), user(1), user(2), invitation(when_date=date(2026, 11, 10), when_time="15:30", **kw))


def fetch(client, inv_id=1, token=None):
    token = ics.sign(inv_id) if token is None else token
    return client.get(f"/api/invitations/{inv_id}/calendar.ics", params={"t": token})


def test_detail_exposes_signed_calendar_path(client):
    setup_invitation()
    body = client.get("/api/invitations/1", headers=as_user(2)).json()
    assert body["calendar_url"] == f"/api/invitations/1/calendar.ics?t={ics.sign(1)}"
    assert body["calendar_google_url"] == f"/api/invitations/1/google-calendar?t={ics.sign(1)}"


def test_no_calendar_path_without_date(client):
    add(city(), user(1), user(2), invitation(when="Договоримся в чате"))
    body = client.get("/api/invitations/1", headers=as_user(2)).json()
    assert body["calendar_url"] is None and body["calendar_google_url"] is None


def test_file_needs_no_login_but_needs_valid_token(client):
    setup_invitation()
    assert fetch(client).status_code == 200
    assert fetch(client, token="wrong").status_code == 404
    assert fetch(client, token="").status_code == 404
    assert client.get("/api/invitations/1/calendar.ics").status_code == 404
    assert fetch(client, inv_id=1, token=ics.sign(2)).status_code == 404


def test_timed_event_is_converted_from_city_time_to_utc(client):
    setup_invitation()
    r = fetch(client)
    assert r.headers["content-type"].startswith("text/calendar")
    assert "kto-so-mnoy.ics" in r.headers["content-disposition"]
    lines = unfold(r.text)
    assert "DTSTART:20261110T123000Z" in lines
    assert "DTEND:20261110T133000Z" in lines
    assert "SUMMARY:Шахматы после уроков" in lines
    assert "TRIGGER:-PT1H" in lines
    assert lines[0] == "BEGIN:VCALENDAR" and lines[-2] == "END:VCALENDAR"


def test_event_without_time_is_all_day(client):
    add(city(), user(1), invitation(when_date=date(2026, 11, 10)))
    lines = unfold(fetch(client).text)
    assert "DTSTART;VALUE=DATE:20261110" in lines
    assert "DTEND;VALUE=DATE:20261111" in lines
    assert "TRIGGER:-PT1H" not in lines


def test_online_format_sets_location(client):
    setup_invitation(fmt="online")
    assert "LOCATION:Онлайн" in unfold(fetch(client).text)


def test_text_is_escaped_and_lines_are_folded(client):
    setup_invitation(title="Шахматы, блиц; турнир", description="первая строка\nвторая " + "я" * 120)
    body = fetch(client).text
    lines = unfold(body)
    assert "SUMMARY:Шахматы\\, блиц\\; турнир" in lines
    description = next(line for line in lines if line.startswith("DESCRIPTION:первая"))
    assert "\\nвторая" in description
    assert all(len(raw.encode()) <= 75 for raw in body.split("\r\n"))


def test_hidden_invitation_has_no_calendar_file(client):
    setup_invitation(hidden=True)
    assert fetch(client).status_code == 404


def test_link_to_app_is_included_when_bot_is_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "bot_username", "kto_bot")
    setup_invitation()
    lines = unfold(fetch(client).text)
    assert "URL:https://max.ru/kto_bot?startapp=inv_1" in lines


def google(client, inv_id=1, token=None):
    token = ics.sign(inv_id) if token is None else token
    return client.get(f"/api/invitations/{inv_id}/google-calendar", params={"t": token}, follow_redirects=False)


def test_google_link_redirects_with_event_in_utc(client):
    setup_invitation(fmt="online")
    r = google(client)
    assert r.status_code == 302
    url = urlparse(r.headers["location"])
    query = parse_qs(url.query)
    assert url.netloc == "calendar.google.com"
    assert query["action"] == ["TEMPLATE"]
    assert query["text"] == ["Шахматы после уроков"]
    assert query["dates"] == ["20261110T123000Z/20261110T133000Z"]
    assert query["location"] == ["Онлайн"]


def test_google_link_for_all_day_event(client):
    add(city(), user(1), invitation(when_date=date(2026, 11, 10)))
    assert parse_qs(urlparse(google(client).headers["location"]).query)["dates"] == ["20261110/20261111"]


def test_google_link_checks_token_and_visibility(client):
    setup_invitation(hidden=True)
    assert google(client).status_code == 404
    assert google(client, token="wrong").status_code == 404
