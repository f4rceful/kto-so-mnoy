from datetime import date, datetime, timedelta, timezone

from helpers import TATARSTAN, add, agree, as_user, city, find_city, invitation, region_cities, register, seed_cities, user

from app import db
from app.config import settings
from app.db import backfill_invitation_places


def test_full_flow(client):
    agree(client, 1, 2, 3)
    body = {"interest": "sport", "title": "Хочу поиграть в баскетбол", "max_participants": 1}
    inv = client.post("/api/invitations", json=body, headers=as_user(1)).json()

    feed = client.get("/api/invitations", headers=as_user(2)).json()
    assert [i["id"] for i in feed] == [inv["id"]]

    assert client.post(f"/api/invitations/{inv['id']}/respond", headers=as_user(1)).status_code == 409
    assert client.post(f"/api/invitations/{inv['id']}/respond", headers=as_user(2)).status_code == 201
    assert client.post(f"/api/invitations/{inv['id']}/respond", headers=as_user(2)).status_code == 409
    assert client.post(f"/api/invitations/{inv['id']}/respond", headers=as_user(3)).status_code == 201
    assert client.sent[0][0] == 1

    responses = client.get("/api/invitations/mine", headers=as_user(1)).json()[0]["responses"]
    r2, r3 = responses[0]["id"], responses[1]["id"]
    assert client.post(f"/api/responses/{r2}/accept", headers=as_user(2)).status_code == 403
    assert client.post(f"/api/responses/{r2}/accept", headers=as_user(1)).status_code == 200
    assert client.post(f"/api/responses/{r3}/accept", headers=as_user(1)).status_code == 409
    assert client.post(f"/api/responses/{r3}/decline", headers=as_user(1)).status_code == 200

    assert client.post(f"/api/invitations/{inv['id']}/close", headers=as_user(2)).status_code == 403
    assert client.post(f"/api/invitations/{inv['id']}/close", headers=as_user(1)).status_code == 200
    assert client.get("/api/invitations", headers=as_user(2)).json() == []


def test_feed_filters_and_sorting(client):
    agree(client, 1, 2)

    def make(interest, title, fmt="offline", spots=3):
        body = {"interest": interest, "title": title, "fmt": fmt, "max_participants": spots}
        return client.post("/api/invitations", json=body, headers=as_user(1)).json()["id"]

    a = make("sport", "Футбол во дворе", spots=1)
    b = make("music", "Группа на вечер", fmt="online", spots=4)
    c = make("games", "Настолки после уроков", spots=2)

    def feed(**params):
        r = client.get("/api/invitations", params=params, headers=as_user(2))
        assert r.status_code == 200
        return [i["id"] for i in r.json()]

    assert feed() == [c, b, a]
    assert feed(sort="old") == [a, b, c]
    assert feed(interest="sport,games") == [c, a]
    assert feed(interest="sport", fmt="online") == []
    assert feed(fmt="online") == [b]
    assert feed(sort="spots") == [b, c, a]

    client.post(f"/api/invitations/{a}/respond", headers=as_user(2))
    resp_id = client.get("/api/invitations/mine", headers=as_user(1)).json()[-1]["responses"][0]["id"]
    client.post(f"/api/responses/{resp_id}/accept", headers=as_user(1))
    assert feed(has_spots="true") == [c, b]
    assert client.get("/api/invitations", params={"sort": "bogus"}, headers=as_user(2)).status_code == 422


def test_feed_scope_school_and_city(client):
    seed_cities()
    cities = region_cities(client, 1)
    kazan, chelny = cities["Казань"], cities["Набережные Челны"]
    a1 = register(client, 1, kazan, "Гимназия 7")
    a2 = register(client, 2, kazan, "Гимназия 7")
    b = register(client, 3, kazan, "Лицей 2")
    c = register(client, 4, chelny, "Школа 5")

    def post(h, title):
        r = client.post("/api/invitations", json={"interest": "chess", "title": title}, headers=h)
        assert r.status_code == 201, r.text
        return r.json()

    mine, other_school, other_city = post(a1, "Шахматы в 7"), post(b, "Шахматы в лицее"), post(c, "Шахматы в Челнах")
    assert mine["school"] == "Гимназия 7" and mine["my_school"] is True

    def titles(h, **params):
        return [i["title"] for i in client.get("/api/invitations", params=params, headers=h).json()]

    assert titles(a2) == ["Шахматы в 7"]
    assert titles(a2, scope="school") == ["Шахматы в 7"]
    assert titles(a2, scope="city") == ["Шахматы в лицее", "Шахматы в 7"]
    assert titles(c, scope="city") == ["Шахматы в Челнах"]
    assert client.get("/api/invitations", params={"scope": "world"}, headers=a2).status_code == 422
    flags = {i["title"]: i["my_school"] for i in client.get("/api/invitations", params={"scope": "city"}, headers=a2).json()}
    assert flags == {"Шахматы в лицее": False, "Шахматы в 7": True}

    assert client.get(f"/api/invitations/{other_city['id']}", headers=a2).status_code == 404
    assert client.get(f"/api/invitations/{other_school['id']}", headers=a2).status_code == 200
    assert client.get(f"/api/invitations/{other_city['id']}", headers=c).status_code == 200


def test_new_invitation_notifies_only_same_city(client):
    seed_cities()
    cities = region_cities(client, 1)
    for uid, name in [(1, "Казань"), (2, "Казань"), (3, "Набережные Челны")]:
        h = register(client, uid, cities[name], "Школа 1")
        client.put("/api/me", json={"interests": ["chess"], "notify": True}, headers=h)
    client.sent.clear()
    client.post("/api/invitations", json={"interest": "chess", "title": "Шахматы"}, headers=as_user(1))
    assert [uid for uid, _ in client.sent] == [2]


def test_old_invitations_get_author_place(client):
    seed_cities()
    kazan = find_city(client, 1, "Казань")
    h = register(client, 1, kazan, "Гимназия 7")
    with db.SessionLocal() as s:
        s.add(db.Invitation(author_id=1, interest="sport", title="Старое приглашение"))
        s.commit()
        backfill_invitation_places(s)
        old = s.query(db.Invitation).one()
        assert old.city_id == kazan and old.school_id is not None
    assert [i["title"] for i in client.get("/api/invitations", headers=h).json()] == ["Старое приглашение"]


def test_feed_pagination_and_search(client):
    add(city(), *[user(uid) for uid in (1, 2)])
    base = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
    add(*[
        invitation(id=n, author=1, title=("Шахматы" if n % 2 else "Баскетбол") + f" № {n}", created_at=base + timedelta(minutes=n))
        for n in range(1, 46)
    ])
    h = as_user(2)

    def page(**params):
        r = client.get("/api/invitations", params={"scope": "city", **params}, headers=h)
        assert r.status_code == 200
        return [i["id"] for i in r.json()], int(r.headers["X-Total-Count"])

    ids, total = page(limit=20)
    assert total == 45 and ids == list(range(45, 25, -1))
    ids2, _ = page(limit=20, offset=20)
    ids3, _ = page(limit=20, offset=40)
    assert ids2 == list(range(25, 5, -1)) and ids3 == [5, 4, 3, 2, 1]
    assert sorted(ids + ids2 + ids3) == list(range(1, 46))
    assert page(limit=20, offset=100)[0] == []

    ids, total = page(limit=10, q="  ШАХМАТЫ ")
    assert total == 23 and len(ids) == 10 and all(i % 2 for i in ids)
    assert page(q="баскетбол № 44")[0] == [44]
    assert page(q="нет такого") == ([], 0)

    assert page(limit=3, sort="old")[0] == [1, 2, 3]
    assert page(has_spots="true")[1] == 45

    assert len(page()[0]) == 45
    assert client.get("/api/invitations", params={"limit": 101}, headers=h).status_code == 422
    assert client.get("/api/invitations", params={"offset": -1}, headers=h).status_code == 422


def test_description_is_cleaned_stored_and_limited(client):
    agree(client, 1, 2)
    raw = "Берите **форму**.\r\n\r\n\r\n\r\n- мяч  \n- вода\x00\x07"
    body = {"interest": "basketball", "title": "Баскетбол во дворе", "description": raw}
    inv = client.post("/api/invitations", json=body, headers=as_user(1)).json()
    assert inv["description"] == "Берите **форму**.\n\n- мяч\n- вода"

    xss = client.post("/api/invitations", json={**body, "description": "<script>alert(1)</script>"}, headers=as_user(1)).json()
    assert xss["description"] == "<script>alert(1)</script>"
    feed = {i["id"]: i["description"] for i in client.get("/api/invitations", headers=as_user(2)).json()}
    assert feed[inv["id"]].startswith("Берите")
    assert client.get(f"/api/invitations/{inv['id']}", headers=as_user(2)).json()["description"] == inv["description"]

    plain = client.post("/api/invitations", json={"interest": "chess", "title": "Шахматы"}, headers=as_user(1)).json()
    assert plain["description"] == ""
    assert client.post("/api/invitations", json={**body, "description": "я" * 1000}, headers=as_user(1)).status_code == 201
    assert client.post("/api/invitations", json={**body, "description": "я" * 1001}, headers=as_user(1)).status_code == 422
    assert client.post("/api/invitations", json={**body, "description": "  \n  "}, headers=as_user(1)).json()["description"] == ""


def test_structured_date_and_time(client):
    agree(client, 1, 2)
    h = as_user(1)
    today = date.today()

    def post(**extra):
        return client.post("/api/invitations", json={"interest": "chess", "title": "Шахматы", **extra}, headers=h)

    r = post(when_date=(today + timedelta(days=2)).isoformat(), when_time="15:30", when="после уроков").json()
    assert (r["when_date"], r["when_time"], r["when"]) == ((today + timedelta(days=2)).isoformat(), "15:30", "после уроков")

    plain = post().json()
    assert plain["when_date"] is None and plain["when_time"] == ""
    weekly = post(when="Каждую пятницу в 15:00", when_time="15:00").json()
    assert weekly["when_time"] == "" and weekly["when"] == "Каждую пятницу в 15:00"

    for bad in ["25:00", "9:00", "15:60", "15-30", "abc"]:
        assert post(when_date=today.isoformat(), when_time=bad).status_code == 422, bad
    assert post(when_date="не дата").status_code == 422
    assert post(when_date=(today - timedelta(days=5)).isoformat()).status_code == 422
    assert post(when_date=(today + timedelta(days=400)).isoformat()).status_code == 422
    assert post(when_date=(today - timedelta(days=1)).isoformat()).status_code == 201

    feed = {i["id"]: (i["when_date"], i["when_time"]) for i in client.get("/api/invitations", headers=as_user(2)).json()}
    assert feed[r["id"]] == ((today + timedelta(days=2)).isoformat(), "15:30")
    assert client.get(f"/api/invitations/{r['id']}", headers=as_user(2)).json()["when_time"] == "15:30"


def test_sort_by_soonest_date(client):
    agree(client, 1, 2)
    today = date.today()

    def post(title, days=None, time=""):
        body = {"interest": "chess", "title": title, "when_time": time}
        if days is not None:
            body["when_date"] = (today + timedelta(days=days)).isoformat()
        assert client.post("/api/invitations", json=body, headers=as_user(1)).status_code == 201

    post("Без даты")
    post("Через неделю", 7)
    post("Завтра вечером", 1, "19:00")
    post("Завтра утром", 1, "09:00")
    post("Сегодня", 0)
    with db.SessionLocal() as s:
        s.add(db.Invitation(author_id=1, interest="chess", title="Давно прошло", when_date=today - timedelta(days=5)))
        s.add(db.Invitation(author_id=1, interest="chess", title="Прошло недавно", when_date=today - timedelta(days=3)))
        s.commit()
    titles = [i["title"] for i in client.get("/api/invitations", params={"sort": "soon"}, headers=as_user(2)).json()]
    assert titles == ["Сегодня", "Завтра утром", "Завтра вечером", "Через неделю", "Без даты", "Прошло недавно", "Давно прошло"]


def test_invitation_share_link(client, monkeypatch):
    agree(client, 1, 2)
    inv = client.post("/api/invitations", json={"interest": "chess", "title": "Шахматы"}, headers=as_user(1)).json()
    assert inv["link"] is None

    monkeypatch.setattr(settings, "bot_username", "kto_bot")
    url = f"/api/invitations/{inv['id']}"
    assert client.get(url, headers=as_user(2)).json()["link"] == f"https://max.ru/kto_bot?startapp=inv_{inv['id']}"
    assert all(i["link"].endswith(f"inv_{i['id']}") for i in client.get("/api/invitations", headers=as_user(2)).json())


def test_author_edits_invitation(client):
    agree(client, 1, 2, 3, 4, 5)
    today = date.today()
    author = as_user(1)
    body = {"interest": "chess", "title": "Шахматы", "when_date": (today + timedelta(days=3)).isoformat(), "when_time": "15:00", "max_participants": 3}
    inv = client.post("/api/invitations", json=body, headers=author).json()
    url = f"/api/invitations/{inv['id']}"
    assert inv["edited"] is False and inv["edited_at"] is None

    for uid in (2, 3, 4):
        client.post(f"{url}/respond", headers=as_user(uid))
    responses = client.get(url, headers=author).json()["responses"]
    by_user = {uid: r["id"] for uid, r in zip((2, 3, 4), responses)}
    client.post(f"/api/responses/{by_user[2]}/accept", headers=author)
    client.post(f"/api/responses/{by_user[4]}/decline", headers=author)

    assert client.put(url, json=body, headers=as_user(2)).status_code == 403
    assert client.put("/api/invitations/9999", json=body, headers=author).status_code == 404
    assert client.put(url, json={**body, "interest": "nope"}, headers=author).status_code == 422
    assert client.put(url, json={**body, "max_participants": 0}, headers=author).status_code == 422
    assert client.put(url, json={**body, "when_time": "25:00"}, headers=author).status_code == 422
    assert client.put(url, json={**body, "when_date": (today + timedelta(days=500)).isoformat()}, headers=author).status_code == 422
    taken = client.get(url, headers=author).json()["accepted"]
    assert taken == 1
    assert client.put(url, json={**body, "max_participants": 1}, headers=author).status_code == 200
    assert client.put(url, json={**body, "max_participants": 3}, headers=author).status_code == 200

    client.sent.clear()
    assert client.put(url, json=body, headers=author).status_code == 200
    assert client.sent == []

    r = client.put(url, json={**body, "description": "Берите **доску**", "max_participants": 4}, headers=author).json()
    assert r["description"] == "Берите **доску**" and r["max_participants"] == 4 and r["edited"] is True
    stamp = datetime.fromisoformat(r["edited_at"])
    assert stamp.tzinfo is not None and abs((datetime.now(timezone.utc) - stamp).total_seconds()) < 60
    assert client.get(url, headers=as_user(5)).json()["edited_at"] == r["edited_at"]
    assert client.sent == [], "про описание и места не пишем"

    new_day = today + timedelta(days=5)
    r = client.put(url, json={**body, "when_date": new_day.isoformat(), "when_time": "17:30", "fmt": "online", "max_participants": 4}, headers=author).json()
    assert (r["when_date"], r["when_time"], r["fmt"]) == (new_day.isoformat(), "17:30", "online")
    assert sorted(uid for uid, _ in client.sent) == [2, 3]
    text = client.sent[0][1]
    assert "Автор изменил приглашение" in text and "17:30" in text and "онлайн" in text and "было: очно" in text and "15:00" in text

    client.sent.clear()
    r = client.put(url, json={**body, "interest": "football", "title": "Футбол во дворе", "when_date": new_day.isoformat(), "when_time": "17:30", "fmt": "online", "max_participants": 4}, headers=author).json()
    assert (r["interest"], r["title"]) == ("football", "Футбол во дворе")
    assert sorted(uid for uid, _ in client.sent) == [2, 3] and "Теперь называется «Футбол во дворе»" in client.sent[0][1]

    r = client.put(url, json={"interest": "football", "title": "Футбол во дворе", "when": "Каждую пятницу в 15:00", "max_participants": 4}, headers=author).json()
    assert (r["when_date"], r["when_time"], r["when"]) == (None, "", "Каждую пятницу в 15:00")

    assert client.get("/api/invitations", params={"scope": "city"}, headers=as_user(5)).json()[0]["title"] == "Футбол во дворе"

    client.post(f"{url}/close", headers=author)
    assert client.put(url, json=body, headers=author).status_code == 409


def test_edit_keeps_old_past_date(client):
    agree(client, 1)
    with db.SessionLocal() as s:
        s.add(db.Invitation(author_id=1, interest="chess", title="Старое", when_date=date.today() - timedelta(days=9)))
        s.commit()
    body = {"interest": "chess", "title": "Старое, но живое", "when_date": (date.today() - timedelta(days=9)).isoformat()}
    r = client.put("/api/invitations/1", json=body, headers=as_user(1))
    assert r.status_code == 200 and r.json()["title"] == "Старое, но живое"
    assert client.put("/api/invitations/1", json={**body, "when_date": (date.today() - timedelta(days=8)).isoformat()}, headers=as_user(1)).status_code == 422


def test_contact_revealed_only_after_accept(client):
    agree(client, 1, 2, 3)
    author = {**as_user(1), "X-Dev-Username": "anya_k"}
    bob = {**as_user(2), "X-Dev-Username": "bob.77"}
    carl = as_user(3)
    for uid, name in [(2, "Боб"), (3, "Карл")]:
        client.put("/api/me", json={"display_name": name}, headers=as_user(uid))
    inv = client.post("/api/invitations", json={"interest": "chess", "title": "Шахматы после уроков"}, headers=author).json()
    url = f"/api/invitations/{inv['id']}"
    for h in (bob, carl):
        client.post(f"{url}/respond", headers=h)

    mine = client.get(url, headers=author).json()
    assert [r["contact"] for r in mine["responses"]] == [None, None]
    assert client.get(url, headers=bob).json()["author_contact"] is None

    ids = {r["user"]: r["id"] for r in mine["responses"]}
    client.sent_buttons.clear()
    client.post(f"/api/responses/{ids['Боб']}/accept", headers=author)

    after = {r["user"]: r["contact"] for r in client.get(url, headers=author).json()["responses"]}
    assert after == {"Боб": "bob.77", "Карл": None}
    assert client.get(url, headers=bob).json()["author_contact"] == "anya_k"
    assert client.get(url, headers=carl).json()["author_contact"] is None

    flat = [b for uid, rows in client.sent_buttons if uid == 2 for row in (rows or []) for b in row]
    assert {"type": "link", "text": "Написать автору", "url": "https://max.ru/anya_k"} in flat

    client.post(f"/api/responses/{ids['Карл']}/accept", headers=author)
    client.get("/api/me", headers=as_user(1))
    client.sent_buttons.clear()
    inv2 = client.post("/api/invitations", json={"interest": "chess", "title": "Ещё шахматы"}, headers=as_user(1)).json()
    client.post(f"/api/invitations/{inv2['id']}/respond", headers=bob)
    rid = client.get(f"/api/invitations/{inv2['id']}", headers=as_user(1)).json()["responses"][0]["id"]
    client.post(f"/api/responses/{rid}/accept", headers=as_user(1))
    assert client.get(f"/api/invitations/{inv2['id']}", headers=bob).json()["author_contact"] is None
    flat = [b for _, rows in client.sent_buttons for row in (rows or []) for b in row]
    assert not any(b.get("text") == "Написать автору" for b in flat)


def test_author_sees_short_profile_of_responders(client):
    seed_cities()
    kazan = find_city(client, 1, "Казань")
    for uid, school, grade in [(1, "Гимназия 7", 9), (2, "Гимназия 7", 8), (3, "Лицей 2", 10)]:
        client.put("/api/me", json={"region": TATARSTAN, "city_id": kazan, "school": school, "grade": grade}, headers=as_user(uid))
    agree(client, 1, 2, 3)
    inv = client.post("/api/invitations", json={"interest": "sport", "title": "Баскетбол во дворе"}, headers=as_user(1)).json()
    for uid in (2, 3):
        client.post(f"/api/invitations/{inv['id']}/respond", headers=as_user(uid))

    def responses():
        return client.get(f"/api/invitations/{inv['id']}", headers=as_user(1)).json()["responses"]

    first, last = responses()
    assert (first["grade"], first["school"], first["same_school"]) == (8, "Гимназия 7", True)
    assert (last["grade"], last["school"], last["same_school"]) == (10, "Лицей 2", False)
    assert first["created_at"] and first["created_at"].endswith("+00:00")

    client.post(f"/api/responses/{first['id']}/accept", headers=as_user(1))
    assert responses()[0]["status"] == "accepted"
    assert not {"region", "city", "interests", "user_id", "stats"} & set(responses()[0])

    other = client.get(f"/api/invitations/{inv['id']}", headers=as_user(3)).json()
    assert "responses" not in other


def test_decisions_need_current_terms(client, monkeypatch):
    from app import terms

    agree(client, 1, 2)
    inv = client.post("/api/invitations", json={"interest": "chess", "title": "Шахматы"}, headers=as_user(1)).json()
    client.post(f"/api/invitations/{inv['id']}/respond", headers=as_user(2))
    resp_id = client.get(f"/api/invitations/{inv['id']}", headers=as_user(1)).json()["responses"][0]["id"]

    monkeypatch.setattr(terms, "TERMS_VERSION", terms.TERMS_VERSION + "-new")
    for path in (f"/api/responses/{resp_id}/accept", f"/api/responses/{resp_id}/decline", f"/api/invitations/{inv['id']}/close"):
        r = client.post(path, headers=as_user(1))
        assert r.status_code == 403 and "условия" in r.json()["detail"], path
    agree(client, 1)
    assert client.post(f"/api/responses/{resp_id}/accept", headers=as_user(1)).status_code == 200
    assert client.post(f"/api/invitations/{inv['id']}/close", headers=as_user(1)).status_code == 200
