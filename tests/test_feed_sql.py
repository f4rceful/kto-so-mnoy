import random
from datetime import date, datetime, timedelta

import pytest
from helpers import UTC, add, as_user, city, invitation, response, user

from app import db
from app.db import Invitation, Response

TITLES = ["Шахматы после уроков", "Баскетбол во дворе", "Настольные игры", "Шахматный турнир", "Снимаем видео", "ШАХМАТЫ и чай"]


def populate(seed=11, count=60, users=12):
    rng = random.Random(seed)
    base = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
    add(city())
    add(*[user(uid) for uid in range(1, users + 1)])
    today = date.today()
    invitations, responses = [], []
    for i in range(1, count + 1):
        dated = rng.random() < 0.7
        invitations.append(
            invitation(
                i,
                rng.randint(1, users),
                title=f"{rng.choice(TITLES)} {i}",
                interest=rng.choice(["chess", "sport", "games"]),
                max_participants=rng.randint(1, 5),
                fmt=rng.choice(["offline", "online"]),
                when_date=today + timedelta(days=rng.randint(-10, 10)) if dated else None,
                when_time=rng.choice(["", "09:00", "15:30", "18:00"]) if dated else "",
                created_at=base + timedelta(minutes=rng.choice([0, 0, 5, 10, rng.randint(0, 500)])),
                school_id=None,
                status="open" if rng.random() < 0.9 else "closed",
                hidden=rng.random() < 0.05,
            )
        )
    add(*invitations)
    pair = set()
    for _ in range(count * 2):
        inv, uid = rng.randint(1, count), rng.randint(1, users)
        if (inv, uid) in pair:
            continue
        pair.add((inv, uid))
        responses.append(response(len(responses) + 1, inv, uid, rng.choice(["pending", "accepted", "accepted", "declined"])))
    add(*responses)


def rows():
    with db.SessionLocal() as s:
        taken = {}
        for r in s.query(Response).filter(Response.status == "accepted"):
            taken[r.invitation_id] = taken.get(r.invitation_id, 0) + 1
        return [(i, taken.get(i.id, 0)) for i in s.query(Invitation)]


def reference(sort, has_spots, needle, today):
    items = [(i, t) for i, t in rows() if i.status == "open" and not i.hidden]
    items.sort(key=lambda p: (p[0].created_at, p[0].id), reverse=(sort != "old"))
    if sort == "old":
        items.sort(key=lambda p: (p[0].created_at, p[0].id))
    if needle:
        items = [p for p in items if needle in p[0].title.lower()]
    if has_spots:
        items = [p for p in items if p[1] < p[0].max_participants]
    if sort == "soon":
        since = today - timedelta(days=1)

        def key(p):
            i = p[0]
            if i.when_date is None:
                return (1, 0, "")
            if i.when_date < since:
                return (2, -i.when_date.toordinal(), "")
            return (0, i.when_date.toordinal(), i.when_time)

        items.sort(key=key)
    elif sort == "spots":
        items.sort(key=lambda p: p[0].max_participants - p[1], reverse=True)
    return [p[0].id for p in items]


def fetch_all(client, params, step=7):
    ids, offset, total = [], 0, None
    while True:
        r = client.get("/api/invitations", params={**params, "limit": step, "offset": offset}, headers=as_user(1))
        assert r.status_code == 200, r.text
        total = int(r.headers["X-Total-Count"])
        batch = [i["id"] for i in r.json()]
        ids += batch
        if len(batch) < step:
            return ids, total
        offset += step


@pytest.mark.parametrize("sort", ["new", "old", "soon", "spots"])
@pytest.mark.parametrize("has_spots", [False, True])
@pytest.mark.parametrize("needle", ["", "шахмат"])
def test_sql_feed_matches_reference_order(client, sort, has_spots, needle):
    populate()
    expected = reference(sort, has_spots, needle, date.today())
    assert expected, "набор данных должен давать непустую ленту"
    params = {"scope": "city", "sort": sort, "has_spots": str(has_spots).lower(), "q": needle}
    ids, total = fetch_all(client, params)
    assert ids == expected
    assert total == len(expected)


def test_total_count_ignores_paging(client):
    populate()
    r = client.get("/api/invitations", params={"scope": "city", "limit": 5, "offset": 10}, headers=as_user(1))
    assert len(r.json()) == 5 and int(r.headers["X-Total-Count"]) == len(reference("new", False, "", date.today()))


def test_offset_beyond_the_end_is_empty(client):
    populate()
    r = client.get("/api/invitations", params={"scope": "city", "offset": 500}, headers=as_user(1))
    assert r.json() == [] and int(r.headers["X-Total-Count"]) > 0


def test_search_is_case_insensitive_and_ignores_extra_spaces(client):
    populate()
    a = fetch_all(client, {"scope": "city", "q": "ШАХМАТЫ"})[0]
    b = fetch_all(client, {"scope": "city", "q": "  шахматы   "})[0]
    assert a == b and a == reference("new", False, "шахматы", date.today())


def test_search_treats_percent_and_underscore_literally(client):
    add(city(), user(1))
    add(invitation(1, 1, title="Скидка 50% на всё", school_id=None), invitation(2, 1, title="Скидка 500 рублей", school_id=None))
    ids = fetch_all(client, {"scope": "city", "q": "50%"})[0]
    assert ids == [1]


def test_interest_and_format_filters_combine_with_search(client):
    populate()
    r = client.get("/api/invitations", params={"scope": "city", "interest": "chess,games", "fmt": "online", "q": "шахмат", "limit": 100}, headers=as_user(1))
    expected = [i for i, _ in rows() if i.status == "open" and not i.hidden and i.interest in ("chess", "games") and i.fmt == "online" and "шахмат" in i.title.lower()]
    assert sorted(x["id"] for x in r.json()) == sorted(i.id for i in expected)
