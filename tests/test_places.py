from helpers import TATARSTAN, as_user, find_city, seed_cities

from app import db
from app.citylist import BUILTIN_CSV, parse_csv, seed_builtin, utc_offset
from app.config import settings
from app.db import City, SessionLocal
from app.names import norm_city, norm_school
from app.places import CUSTOM_PLACES_LIMIT, backfill_legacy_profiles
from app.regions import REGIONS, region_from_dataset
from scripts.import_cities import import_cities


def test_name_normalization():
    assert len({norm_school(n) for n in ["МБОУ СОШ №7", "Школа 7", "школа № 07", "СОШ  №7 "]}) == 1
    assert norm_school("Гимназия № 7") != norm_school("Школа № 7")
    assert norm_school("Школа") == "школа"
    assert norm_city("г. Ростов-на-Дону") == norm_city("Ростов на Дону") == "ростов на дону"
    assert norm_city("Орёл") == norm_city("орел")


def test_dataset_regions_map_to_known_names():
    cases = {
        ("Респ", "Адыгея"): "Республика Адыгея",
        ("Респ", "Удмуртская"): "Удмуртская Республика",
        ("Респ", "Саха /Якутия/"): "Республика Саха (Якутия)",
        ("Чувашия", "Чувашская Республика"): "Чувашская Республика",
        ("обл", "Кемеровская область - Кузбасс"): "Кемеровская область — Кузбасс",
        ("АО", "Ямало-Ненецкий"): "Ямало-Ненецкий автономный округ",
        ("Аобл", "Еврейская"): "Еврейская автономная область",
        ("г", "Москва"): "Москва",
        ("край", "Пермский"): "Пермский край",
    }
    for key, expected in cases.items():
        assert region_from_dataset(*key) == expected and expected in REGIONS
    assert region_from_dataset("обл", "Несуществующая") is None


def test_importer_parses_time_zones():
    for raw, expected in [("UTC+3", 180), ("UTC+12", 720), ("UTC-4", -240), ("UTC+5:30", 330), ("UTC+0", 0), (" UTC+7 ", 420), ("", None), ("МСК", None), ("UTC", None), ("UTC+25x", None)]:
        assert utc_offset({"timezone": raw}) == expected, raw
    assert utc_offset({}) is None


def test_importer_sets_and_updates_offsets(database):
    rows = [{"region_type": "Респ", "region": "Татарстан", "city": "Казань", "population": "1", "timezone": "UTC+3"}]
    import_cities(rows)
    rows[0]["timezone"] = "UTC+5"
    import_cities(rows)
    with SessionLocal() as s:
        assert s.query(City).filter_by(name="Казань").one().utc_offset == 300
    rows[0]["timezone"] = ""
    import_cities(rows)
    with SessionLocal() as s:
        assert s.query(City).filter_by(name="Казань").one().utc_offset == 300, "в данных пояса нет — прежний не затираем"


def test_custom_city_gets_regions_time_zone(client):
    rows = [
        {"region_type": "обл", "region": "Свердловская", "city": "Екатеринбург", "population": "1500000", "timezone": "UTC+5"},
        {"region_type": "обл", "region": "Свердловская", "city": "Малый", "population": "1000", "timezone": "UTC+5"},
        {"region_type": "обл", "region": "Тверская", "city": "Тверь", "population": "400000", "timezone": "UTC+3"},
    ]
    import_cities(rows)
    client.put("/api/me", json={"region": "Свердловская область", "city": "Деревня Дальняя"}, headers=as_user(1))
    client.put("/api/me", json={"region": "Орловская область", "city": "Село без справочника"}, headers=as_user(2))
    with SessionLocal() as s:
        assert s.query(City).filter_by(name="Деревня Дальняя").one().utc_offset == 300
        assert s.query(City).filter_by(name="Село без справочника").one().utc_offset == 180, "нет данных — московское"


def test_city_and_school_search(client):
    seed_cities()
    h = as_user(7)

    r = client.get("/api/cities", params={"region": TATARSTAN}, headers=h).json()
    assert [c["name"] for c in r] == ["Казань", "Набережные Челны", "Казанлы"]
    r = client.get("/api/cities", params={"region": TATARSTAN, "q": "каз"}, headers=h).json()
    assert [c["name"] for c in r] == ["Казань", "Казанлы"]
    r = client.get("/api/cities", params={"region": TATARSTAN, "q": "челны"}, headers=h).json()
    assert [c["name"] for c in r] == ["Набережные Челны"]
    assert client.get("/api/cities", params={"region": "Нарния"}, headers=h).status_code == 422
    assert client.get("/api/cities", params={"region": TATARSTAN}).status_code == 401

    kazan = find_city(client, 7, "Казань")
    assert client.get("/api/schools", params={"city_id": kazan}, headers=h).json() == []
    moscow = client.get("/api/cities", params={"region": "Москва"}, headers=h).json()
    assert [c["name"] for c in moscow] == ["Москва"]
    near = client.get("/api/cities", params={"region": "Московская область"}, headers=h).json()
    assert [c["name"] for c in near] == ["Одинцово", "Голицыно"]


def test_registration(client):
    seed_cities()
    h = as_user(7)
    kazan = find_city(client, 7, "Казань")
    tver = client.get("/api/cities", params={"region": "Тверская область"}, headers=h).json()[0]["id"]

    me = client.get("/api/me", headers=h).json()
    assert me["onboarded"] is False and me["region"] == "" and me["grade"] is None and me["city_id"] is None
    assert TATARSTAN in client.get("/api/regions").json()

    bad = [
        {"region": "Нарния"},
        {"grade": 3},
        {"grade": 12},
        {"city": "Казань"},
        {"school": "Школа 7"},
        {"region": TATARSTAN, "city": " "},
        {"region": TATARSTAN, "city": "7"},
        {"region": TATARSTAN, "city_id": tver},
        {"region": TATARSTAN, "city_id": 99999},
        {"region": TATARSTAN, "city_id": kazan, "school": "x"},
        {"region": TATARSTAN, "city_id": kazan, "school_id": 99999},
    ]
    for payload in bad:
        assert client.put("/api/me", json=payload, headers=h).status_code == 422, payload
    assert client.get("/api/me", headers=h).json()["region"] == ""

    for step, onboarded in [
        ({"region": TATARSTAN}, False),
        ({"city_id": kazan}, False),
        ({"school": "  МБОУ   Гимназия № 7 "}, False),
        ({"grade": 9}, False),
        ({"accept_terms": True}, True),
    ]:
        r = client.put("/api/me", json=step, headers=h).json()
        assert r["onboarded"] is onboarded, step
    assert (r["city"], r["city_id"], r["school"]) == ("Казань", kazan, "МБОУ Гимназия № 7")

    h2 = as_user(8)
    client.put("/api/me", json={"region": TATARSTAN, "city_id": kazan, "school": "мбоу гимназия №07"}, headers=h2)
    assert client.get("/api/me", headers=h2).json()["school_id"] == r["school_id"]
    found = client.get("/api/schools", params={"city_id": kazan, "q": "гимн 7"}, headers=h2).json()
    assert [s["id"] for s in found] == [r["school_id"]] and found[0]["custom"] is True

    r3 = client.put("/api/me", json={"school_id": r["school_id"]}, headers=h2).json()
    assert r3["school"] == "МБОУ Гимназия № 7"
    chelny = find_city(client, 7, "челны")
    assert client.put("/api/me", json={"city_id": chelny, "school_id": r["school_id"]}, headers=h2).status_code == 422

    r4 = client.put("/api/me", json={"city_id": chelny}, headers=h2).json()
    assert r4["city"] == "Набережные Челны" and r4["school"] == "" and r4["onboarded"] is False
    r5 = client.put("/api/me", json={"region": "Тверская область"}, headers=h).json()
    assert r5["city"] == r5["school"] == "" and r5["onboarded"] is False

    for uid, spelling in [(9, "д. Новая  Слобода"), (10, "Новая слобода")]:
        client.put("/api/me", json={"region": TATARSTAN, "city": spelling}, headers=as_user(uid))
    ids = {client.get("/api/me", headers=as_user(u)).json()["city_id"] for u in (9, 10)}
    assert len(ids) == 1 and None not in ids

    r = client.put("/api/me", json={"interests": ["sport"], "notify": False}, headers=h2).json()
    assert r["city"] == "Набережные Челны"


def test_legacy_profiles_are_migrated(client):
    with db.SessionLocal() as s:
        s.add_all(
            [
                db.User(id=1, region=TATARSTAN, legacy_city="Казань ", legacy_school="Гимназия  № 7", grade=9),
                db.User(id=2, region=TATARSTAN, legacy_city="казань", legacy_school="гимназия №7", grade=8),
                db.User(id=3, region=TATARSTAN, legacy_city="?", legacy_school="Школа"),
                db.User(id=4),
            ]
        )
        s.commit()
        backfill_legacy_profiles(s)
        u1, u2, u3 = (s.get(db.User, i) for i in (1, 2, 3))
        assert u1.city_id == u2.city_id and u1.school_id == u2.school_id and u1.school_id
        assert u3.city_id is None and s.get(db.User, 4).city_id is None
        backfill_legacy_profiles(s)
        assert s.query(db.City).count() == 1 and s.query(db.School).count() == 1


def test_school_invite_link_and_members(client, monkeypatch):
    seed_cities()
    h = as_user(1)
    kazan = find_city(client, 1, "Казань")
    client.put("/api/me", json={"region": TATARSTAN, "city_id": kazan, "school": "Гимназия 7", "grade": 9}, headers=h)
    me = client.get("/api/me", headers=h).json()
    assert me["school_invite"] is None

    monkeypatch.setattr(settings, "bot_username", "kto_bot")
    me = client.get("/api/me", headers=h).json()
    assert me["school_invite"] == f"https://max.ru/kto_bot?startapp=school_{me['school_id']}"

    h2 = as_user(2)
    found = client.get(f"/api/schools/{me['school_id']}", headers=h2).json()
    assert found == {"id": me["school_id"], "name": "Гимназия 7", "city_id": kazan, "city": "Казань", "region": TATARSTAN, "members": 1}
    assert client.get("/api/schools/9999", headers=h2).status_code == 404
    client.put("/api/me", json={"region": found["region"], "city_id": found["city_id"], "school_id": found["id"]}, headers=h2)
    assert client.get(f"/api/schools/{found['id']}", headers=h2).json()["members"] == 2
    listed = client.get("/api/schools", params={"city_id": kazan}, headers=h2).json()
    assert listed[0]["members"] == 2


def test_custom_places_quota(client):
    seed_cities()
    h = as_user(1)
    for n in range(CUSTOM_PLACES_LIMIT):
        r = client.put("/api/me", json={"region": TATARSTAN, "city": f"Выдуманный {n} город"}, headers=h)
        assert r.status_code == 200, r.text
    over = client.put("/api/me", json={"region": TATARSTAN, "city": "Ещё один выдуманный"}, headers=h)
    assert over.status_code == 429
    kazan = find_city(client, 1, "Казань")
    assert client.put("/api/me", json={"region": TATARSTAN, "city_id": kazan}, headers=h).status_code == 200
    assert client.put("/api/me", json={"region": TATARSTAN, "city": "Выдуманный 3 город"}, headers=h).status_code == 200
    assert client.put("/api/me", json={"region": TATARSTAN, "city": "Ещё один выдуманный"}, headers=as_user(2)).status_code == 200
    client.put("/api/me", json={"region": TATARSTAN, "city_id": kazan}, headers=as_user(3))
    for n in range(CUSTOM_PLACES_LIMIT):
        assert client.put("/api/me", json={"school": f"Школа номер {n}"}, headers=as_user(3)).status_code == 200
    assert client.put("/api/me", json={"school": "Школа сверх лимита"}, headers=as_user(3)).status_code == 429


def test_builtin_cities_are_loaded_once(database):
    with SessionLocal() as s:
        s.add(City(region=TATARSTAN, name="Своё село", name_norm="своё село", custom=True))
        s.commit()
        assert seed_builtin(s) > 1000, "встроенный справочник загружается в базу без встроенных городов"
        assert seed_builtin(s) == 0, "повторный старт ничего не добавляет"
        kazan = s.query(City).filter_by(region=TATARSTAN, name_norm=norm_city("Казань")).one()
        assert kazan.custom is False and kazan.population and kazan.utc_offset == 180
        assert s.query(City).filter_by(name="Своё село").one().custom is True


def test_builtin_city_file_is_readable():
    rows = parse_csv(BUILTIN_CSV.read_text(encoding="utf-8"))
    assert len(rows) > 1000 and {"region_type", "region", "city", "timezone", "population"} <= set(rows[0])
