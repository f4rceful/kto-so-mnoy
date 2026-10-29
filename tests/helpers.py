import asyncio
from datetime import datetime, timezone

from app.db import City, Invitation, Response, SessionLocal, User
from app.terms import TERMS_VERSION
from scripts.import_cities import import_cities

UTC = timezone.utc
TATARSTAN = "Республика Татарстан"


def run(coro):
    return asyncio.run(coro)


def add(*objects):
    with SessionLocal() as s:
        s.add_all(objects)
        s.commit()


def get(model, pk):
    with SessionLocal() as s:
        return s.get(model, pk)


def city(id=1, offset=180, name="Казань", region=TATARSTAN):
    return City(id=id, region=region, name=name, name_norm=name.lower(), utc_offset=offset, custom=False)


def user(uid, **kw):
    fields = dict(name=f"Тест {uid}", interests="chess", city_id=1, notify=True, notify_activity=True, onboarded=True, terms_version=TERMS_VERSION)
    return User(id=uid, **(fields | kw))


def invitation(id=1, author=1, **kw):
    fields = dict(author_id=author, interest="chess", title="Шахматы после уроков", city_id=1, max_participants=3, fmt="offline", status="open", created_at=datetime(2026, 10, 20, 9, 0, tzinfo=UTC))
    return Invitation(id=id, **(fields | kw))


def response(id, inv, uid, status="pending"):
    return Response(id=id, invitation_id=inv, user_id=uid, status=status)


def texts(outbox, uid=None):
    return [t for u, t, _ in outbox if uid is None or u == uid]


def to(outbox):
    return sorted(u for u, _, _ in outbox)


def as_user(uid):
    return {"X-Dev-User": str(uid)}


def agree(client, *uids):
    for uid in uids:
        assert client.put("/api/me", json={"accept_terms": True}, headers=as_user(uid)).status_code == 200


def register(client, uid, city_id, school, region=TATARSTAN):
    h = as_user(uid)
    r = client.put("/api/me", json={"region": region, "city_id": city_id, "school": school, "grade": 9, "accept_terms": True}, headers=h)
    assert r.status_code == 200 and r.json()["onboarded"], r.text
    return h


def new_invitation(client, uid, title="Шахматы"):
    r = client.post("/api/invitations", json={"interest": "chess", "title": title}, headers=as_user(uid))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def seed_cities():
    rows = [
        {"region_type": "Респ", "region": "Татарстан", "city": "Казань", "population": "1300000"},
        {"region_type": "Респ", "region": "Татарстан", "city": "Казанлы", "population": "5000"},
        {"region_type": "Респ", "region": "Татарстан", "city": "Набережные Челны", "population": "530000"},
        {"region_type": "обл", "region": "Тверская", "city": "Тверь", "population": "400000"},
        {"region_type": "г", "region": "Москва", "city": "", "population": "11500000"},
        {"region_type": "обл", "region": "Московская", "area_type": "г", "area": "Одинцово", "population": "139000"},
        {"region_type": "обл", "region": "Московская", "city": "Голицыно", "area_type": "г", "area": "Одинцово"},
        {"region_type": "обл", "region": "Нарния", "city": "Ничто", "population": "1"},
    ]
    assert import_cities(rows) == (7, 1)
    assert import_cities(rows) == (0, 1)


def find_city(client, uid, q, region=TATARSTAN):
    return client.get("/api/cities", params={"region": region, "q": q}, headers=as_user(uid)).json()[0]["id"]


def region_cities(client, uid, region=TATARSTAN):
    return {c["name"]: c["id"] for c in client.get("/api/cities", params={"region": region}, headers=as_user(uid)).json()}
