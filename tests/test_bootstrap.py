from datetime import date, timedelta

import pytest
from helpers import TATARSTAN, add, as_user, city, invitation, response, user
from sqlalchemy import event

from app import db
from app.db import School


def school():
    return School(id=1, city_id=1, name="Школа 1", name_norm="1", custom=False)


def member(uid, **kw):
    return user(uid, region=TATARSTAN, school_id=1, grade=9, **kw)


def seed(count=25):
    today = date.today()
    add(city(), school(), member(1), member(2), user(3, onboarded=False))
    add(
        *[
            invitation(
                i,
                1 + i % 2,
                title=f"Шахматы {i}" if i % 3 else f"Баскетбол {i}",
                interest="chess" if i % 3 else "sport",
                max_participants=2 + i % 3,
                fmt="online" if i % 4 == 0 else "offline",
                when_date=today + timedelta(days=i % 7),
                school_id=1,
            )
            for i in range(1, count + 1)
        ]
    )


def test_bootstrap_matches_the_separate_calls(client):
    seed()
    boot = client.get("/api/bootstrap", headers=as_user(2)).json()
    assert boot["me"] == client.get("/api/me", headers=as_user(2)).json()
    assert boot["interests"] == client.get("/api/interests").json()
    page = client.get("/api/invitations", params={"limit": 20, "scope": "city"}, headers=as_user(2))
    assert boot["feed"] is not None


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"scope": "city"},
        {"scope": "city", "sort": "spots"},
        {"scope": "city", "sort": "soon", "has_spots": "true"},
        {"scope": "city", "q": "шахматы"},
        {"scope": "city", "interest": "sport", "fmt": "offline"},
        {"scope": "city", "limit": 5},
    ],
)
def test_bootstrap_feed_equals_the_feed_endpoint(client, params):
    seed()
    boot = client.get("/api/bootstrap", params=params, headers=as_user(2)).json()
    limit = params.get("limit", 20)
    page = client.get("/api/invitations", params={**params, "limit": limit}, headers=as_user(2))
    assert boot["feed"]["items"] == page.json()
    assert boot["feed"]["total"] == int(page.headers["X-Total-Count"])


def test_first_page_is_twenty_items_by_default(client):
    seed(25)
    boot = client.get("/api/bootstrap", params={"scope": "city"}, headers=as_user(2)).json()
    assert len(boot["feed"]["items"]) == 20 and boot["feed"]["total"] == 25


def test_waiting_counts_only_pending_answers_on_my_open_invitations(client):
    add(city(), school(), member(1), member(2), member(3), member(4))
    add(
        invitation(1, 1, school_id=1),
        invitation(2, 1, status="closed", school_id=1),
        invitation(3, 2, school_id=1),
        invitation(4, 1, hidden=True, school_id=1),
        response(1, 1, 2, "pending"),
        response(2, 1, 3, "pending"),
        response(3, 1, 4, "accepted"),
        response(4, 2, 2, "pending"),
        response(5, 3, 1, "pending"),
        response(6, 4, 2, "pending"),
    )
    assert client.get("/api/bootstrap", headers=as_user(1)).json()["waiting"] == 3
    assert client.get("/api/bootstrap", headers=as_user(2)).json()["waiting"] == 1
    assert client.get("/api/bootstrap", headers=as_user(4)).json()["waiting"] == 0


def test_waiting_matches_what_the_app_computed_from_my_invitations(client):
    add(city(), school(), member(1), member(2), member(3))
    add(invitation(1, 1, school_id=1), invitation(2, 1, school_id=1), response(1, 1, 2, "pending"), response(2, 2, 3, "pending"), response(3, 2, 2, "declined"))
    mine = client.get("/api/invitations/mine", headers=as_user(1)).json()
    expected = sum(1 for i in mine if i["status"] == "open" for r in i["responses"] if r["status"] == "pending")
    assert client.get("/api/bootstrap", headers=as_user(1)).json()["waiting"] == expected == 2


def test_new_users_get_no_feed_but_still_get_their_profile_and_interests(client):
    add(city(), user(3, onboarded=False))
    boot = client.get("/api/bootstrap", headers=as_user(3)).json()
    assert boot["feed"] is None and boot["me"]["onboarded"] is False
    assert boot["interests"] and boot["waiting"] == 0


def test_first_visit_creates_the_user(client):
    boot = client.get("/api/bootstrap", headers=as_user(77))
    assert boot.status_code == 200 and boot.json()["feed"] is None
    with db.SessionLocal() as s:
        assert s.get(db.User, 77) is not None
        assert s.query(db.UserActivity).filter_by(user_id=77).count() == 1


def test_bootstrap_needs_login_and_rejects_banned_users(client):
    add(city(), user(1, banned=True))
    assert client.get("/api/bootstrap").status_code == 401
    assert client.get("/api/bootstrap", headers=as_user(1)).status_code == 403


@pytest.mark.parametrize("params", [{"sort": "nope"}, {"scope": "world"}, {"limit": 0}, {"limit": 101}, {"fmt": "hybrid"}])
def test_invalid_parameters_are_rejected(client, params):
    add(city(), user(1))
    assert client.get("/api/bootstrap", params=params, headers=as_user(1)).status_code == 422


def test_items_are_brief_like_in_the_feed(client):
    seed(3)
    items = client.get("/api/bootstrap", params={"scope": "city"}, headers=as_user(2)).json()["feed"]["items"]
    assert items and all("calendar_url" not in i and "link" not in i for i in items)


def test_bootstrap_uses_a_small_fixed_number_of_queries(client, database):
    seed(25)
    client.get("/api/bootstrap", params={"scope": "city"}, headers=as_user(2))
    statements = []

    def count(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(database, "before_cursor_execute", count)
    try:
        assert client.get("/api/bootstrap", params={"scope": "city"}, headers=as_user(2)).status_code == 200
    finally:
        event.remove(database, "before_cursor_execute", count)
    assert len(statements) <= 14, f"слишком много запросов к базе: {len(statements)}"
    separate = []
    event.listen(database, "before_cursor_execute", lambda *a: separate.append(1))
    client.get("/api/me", headers=as_user(2))
    client.get("/api/invitations", params={"scope": "city", "limit": 20}, headers=as_user(2))
    client.get("/api/invitations/mine", headers=as_user(2))
    assert len(statements) <= len(separate) + 2
