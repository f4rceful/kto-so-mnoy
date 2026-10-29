import hashlib
import hmac
import re
import time
from urllib.parse import quote

from helpers import agree, as_user, find_city, new_invitation, register, seed_cities

from app import db, terms
from app.security import validate_init_data

TOKEN = "test-token"


def sign(fields: dict, token: str = TOKEN) -> str:
    launch = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, launch.encode(), hashlib.sha256).hexdigest()
    return "&".join(f"{k}={quote(v)}" for k, v in fields.items()) + f"&hash={h}"


def test_init_data_valid_and_tampered():
    fields = {"auth_date": str(int(time.time())), "user": '{"id":1,"first_name":"Аня"}'}
    data = validate_init_data(sign(fields), TOKEN)
    assert data and data["user"]["first_name"] == "Аня"
    assert validate_init_data(sign(fields), "other-token") is None
    assert validate_init_data(sign(fields).replace("%D0%90", "%D0%91"), TOKEN) is None
    old = {**fields, "auth_date": str(int(time.time()) - 10**6)}
    assert validate_init_data(sign(old), TOKEN, ttl=3600) is None


def test_requires_auth(client):
    assert client.get("/api/invitations").status_code == 401


def test_username_is_sanitized(client):
    for bad in ["bad name!", "a", "x" * 65, "evil/../x", "a b"]:
        client.get("/api/me", headers={**as_user(5), "X-Dev-Username": bad})
        with db.SessionLocal() as s:
            assert s.get(db.User, 5).username is None, bad
    client.get("/api/me", headers={**as_user(5), "X-Dev-Username": "ok_user.1"})
    with db.SessionLocal() as s:
        assert s.get(db.User, 5).username == "ok_user.1"
    client.get("/api/me", headers=as_user(5))
    with db.SessionLocal() as s:
        assert s.get(db.User, 5).username is None


def test_profile_and_follower_notifications(client):
    agree(client, 1)
    me = client.get("/api/me", headers=as_user(2)).json()
    assert me["onboarded"] is False and me["interests"] == [] and me["notify"] is True

    r = client.put("/api/me", json={"interests": ["sport", "sport", "music"], "notify": True}, headers=as_user(2))
    assert r.json()["interests"] == ["sport", "music"] and r.json()["onboarded"] is False
    assert client.put("/api/me", json={"interests": ["nope"]}, headers=as_user(2)).status_code == 422

    client.put("/api/me", json={"interests": ["sport"], "notify": False}, headers=as_user(3))
    client.put("/api/me", json={"interests": ["games"], "notify": True}, headers=as_user(4))
    client.put("/api/me", json={"interests": ["sport"], "notify": True}, headers=as_user(1))

    body = {"interest": "sport", "title": "Футбол во дворе"}
    inv = client.post("/api/invitations", json=body, headers=as_user(1)).json()
    assert [uid for uid, _ in client.sent] == [2]
    assert "Футбол во дворе" in client.sent[0][1]

    d = client.get(f"/api/invitations/{inv['id']}", headers=as_user(2)).json()
    assert d["title"] == "Футбол во дворе" and "responses" not in d
    assert client.get("/api/invitations/9999", headers=as_user(2)).status_code == 404
    assert client.get("/api/invitations/mine", headers=as_user(1)).status_code == 200


def test_profile_stats_and_joined(client):
    agree(client, 1, 2, 3)
    inv = client.post(
        "/api/invitations", json={"interest": "music", "title": "Соберём группу", "max_participants": 3}, headers=as_user(1)
    ).json()
    assert client.get("/api/me", headers=as_user(1)).json()["stats"] == {"created": 1, "joined": 0, "gathered": 0}

    client.post(f"/api/invitations/{inv['id']}/respond", headers=as_user(2))
    assert client.get("/api/invitations/joined", headers=as_user(2)).json()[0]["my_response"] == "pending"
    assert client.get("/api/me", headers=as_user(2)).json()["stats"]["joined"] == 0

    r = client.get("/api/invitations/mine", headers=as_user(1)).json()[0]["responses"][0]["id"]
    client.post(f"/api/responses/{r}/accept", headers=as_user(1))
    assert client.get("/api/me", headers=as_user(2)).json()["stats"]["joined"] == 1
    assert client.get("/api/me", headers=as_user(1)).json()["stats"]["gathered"] == 1
    assert client.get("/api/invitations/joined", headers=as_user(3)).json() == []


def test_interests_are_grouped_and_legacy_ids_survive(client):
    items = client.get("/api/interests").json()
    ids = {i["id"] for i in items}
    assert len(items) >= 40 and len(ids) == len(items)
    assert {"sport", "music", "games", "creative", "video", "projects"} <= ids
    assert {i["group"] for i in items} >= {"Спорт", "Игры", "Учёба и наука"}
    h = as_user(1)
    everything = [i["id"] for i in items]
    r = client.put("/api/me", json={"interests": everything}, headers=h)
    assert r.status_code == 200 and r.json()["interests"] == everything
    assert client.put("/api/me", json={"interests": ["football", "chess"]}, headers=h).status_code == 200


def test_terms_consent_and_display_name(client):
    docs = client.get("/api/terms").json()
    assert docs["version"] and {d["id"] for d in docs["documents"]} == {"terms", "privacy"}

    h = as_user(1)
    body = {"interest": "sport", "title": "Баскетбол после уроков"}
    assert client.post("/api/invitations", json=body, headers=h).status_code == 403
    assert client.post("/api/invitations/1/respond", headers=h).status_code == 403
    me = client.get("/api/me", headers=h).json()
    assert me["accepted_terms"] is False and me["onboarded"] is False

    assert client.put("/api/me", json={"accept_terms": False}, headers=h).json()["accepted_terms"] is False
    assert client.put("/api/me", json={"accept_terms": True}, headers=h).json()["accepted_terms"] is True
    assert client.post("/api/invitations", json=body, headers=h).status_code == 201

    agree(client, 2)
    inv = client.get("/api/invitations", headers=as_user(2)).json()[0]
    assert client.get("/api/me", headers=h).json()["name"] == "Тест 1"
    assert inv["author"] == "Тест"
    assert client.get("/api/me", headers=h).json()["display_name"] == "Тест"
    assert client.put("/api/me", json={"display_name": "  Анюта  К. "}, headers=h).json()["display_name"] == "Анюта К."
    assert client.get("/api/invitations", headers=as_user(2)).json()[0]["author"] == "Анюта К."
    for bad in ["", " ", "7", "x" * 31]:
        assert client.put("/api/me", json={"display_name": bad}, headers=h).status_code == 422, bad

    client.sent.clear()
    client.post("/api/invitations/1/respond", headers=as_user(2))
    assert any("Тест" in text and "Тест 2" not in text for _, text in client.sent)


def test_new_terms_version_asks_again(client, monkeypatch):
    agree(client, 1)
    assert client.get("/api/me", headers=as_user(1)).json()["accepted_terms"] is True
    monkeypatch.setattr(terms, "TERMS_VERSION", terms.TERMS_VERSION + "-v2")
    assert client.get("/api/me", headers=as_user(1)).json()["accepted_terms"] is False


def test_terms_documents_are_complete_and_honest(client):
    data = client.get("/api/terms").json()
    assert data["version"] == terms.TERMS_VERSION and data["version"] != "2026-10-draft", "после смены текста версия поднята"
    docs = {d["id"]: d for d in data["documents"]}
    assert set(docs) == {"terms", "privacy"}

    everything = []
    for d in docs.values():
        assert d["title"] and d["short"] and d["updated"], d["id"]
        assert len(d["sections"]) >= 8
        for n, section in enumerate(d["sections"], 1):
            assert section["title"].startswith(f"{n}. "), f"нумерация разделов подряд: {section['title']}"
            assert section["paragraphs"] and all(p.strip() for p in section["paragraphs"]), section["title"]
            everything += [section["title"], *section["paragraphs"]]
    text = "\n".join(everything)

    assert "ЧЕРНОВИК" not in text and "заглушк" not in text.lower()
    assert set(re.findall(r"\[[^\]]+\]", text)) == {"[название команды]", "[адрес электронной почты для обращений]"}
    for phrase in ["14 лет", "Пожаловаться", "Скрыть автора", "/notify off", "username", "«Старт»", "HTTPS", "отозвать согласие", "не продаём", "Действующая версия"]:
        assert phrase in text, phrase
    assert "телефон" in text and "не видят" in text.lower()


def test_terms_text_matches_what_the_service_really_shows(client):
    agree(client, 1, 2)
    seed_cities()
    kazan = find_city(client, 1, "Казань")
    register(client, 1, kazan, "Гимназия 7")
    inv = new_invitation(client, 1)
    shown = str(client.get(f"/api/invitations/{inv}", headers=as_user(2)).json()) + str(client.get("/api/invitations", params={"scope": "city"}, headers=as_user(2)).json())
    assert "Республика Татарстан" not in shown and "Казань" not in shown, "регион и город другим не отдаются"
    assert "'grade'" not in shown and "interests" not in shown, "класс и интересы тоже"
    assert "username" not in shown.replace("'author_contact'", ""), "username без принятия отклика не раскрывается"


def test_dev_header_must_be_a_number(client):
    for bad in ["abc", "1.5", "-1", " "]:
        assert client.get("/api/me", headers={"X-Dev-User": bad}).status_code == 401, bad
