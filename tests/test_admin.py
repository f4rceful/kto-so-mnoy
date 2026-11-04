from datetime import date, timedelta

from helpers import add, agree, as_user, city, get, invitation, new_invitation, response, run, user

from app import bans, db, reminders, safety
from app.config import settings
from app.db import Invitation, School, User

KEY = "secret-key-123"


def bad(client, n=1):
    return [client.get("/api/admin/stats", headers={"X-Admin-Key": "nope"}).status_code for _ in range(n)]


def test_failed_keys_lock_admin_and_expire(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_key", KEY)
    now = [1000.0]
    monkeypatch.setattr(safety, "clock", lambda: now[0])
    assert bad(client, safety.ADMIN_MAX_FAILURES) == [401] * safety.ADMIN_MAX_FAILURES
    locked = client.get("/api/admin/stats", headers={"X-Admin-Key": KEY})
    assert locked.status_code == 429 and int(locked.headers["retry-after"]) > 0
    assert "Повторите" in locked.json()["detail"]
    now[0] += safety.ADMIN_LOCK_SECONDS + 1
    assert client.get("/api/admin/stats", headers={"X-Admin-Key": KEY}).status_code == 200


def test_correct_key_resets_failure_counter(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_key", KEY)
    limit = safety.ADMIN_MAX_FAILURES
    assert bad(client, limit - 1) == [401] * (limit - 1)
    assert client.get("/api/admin/stats", headers={"X-Admin-Key": KEY}).status_code == 200
    assert bad(client, limit - 1) == [401] * (limit - 1)
    assert client.get("/api/admin/stats", headers={"X-Admin-Key": KEY}).status_code == 200


def test_moderation_log_records_every_action(client, admin):
    agree(client, 1, 2)
    inv = new_invitation(client, 1, "Спорное")
    client.post(f"/api/invitations/{inv}/report", json={"reason": "spam"}, headers=as_user(2))
    client.post(f"/api/admin/invitations/{inv}/dismiss", headers=admin)
    client.post(f"/api/admin/invitations/{inv}/hide", json={"reason": "Реклама"}, headers=admin)
    client.post(f"/api/admin/invitations/{inv}/restore", headers=admin)
    client.post("/api/admin/users/1/ban", json={"reason": "Оскорбления"}, headers=admin)
    client.post("/api/admin/users/1/unban", headers=admin)

    body = client.get("/api/admin/log", headers=admin).json()
    assert body["total"] == 5
    assert [r["action"] for r in body["items"]] == ["unban", "ban", "restore", "hide", "dismiss"]
    by_action = {r["action"]: r for r in body["items"]}
    assert by_action["hide"]["detail"] == "Реклама" and by_action["hide"]["target_label"] == "Спорное"
    assert by_action["hide"]["target_type"] == "invitation" and by_action["hide"]["target_id"] == inv
    assert by_action["dismiss"]["detail"] == "закрыто жалоб: 1"
    assert by_action["ban"]["detail"] == "Оскорбления" and by_action["ban"]["target_type"] == "user"
    assert by_action["unban"]["detail"] == "возвращено приглашений: 1"
    assert all(r["source"] and r["at"] for r in body["items"])

    page = client.get("/api/admin/log", params={"limit": 2, "offset": 1}, headers=admin).json()
    assert [r["action"] for r in page["items"]] == ["ban", "restore"] and page["total"] == 5


def test_failed_lookups_leave_no_log(client, admin):
    assert client.post("/api/admin/users/999/ban", headers=admin).status_code == 404
    assert client.post("/api/admin/invitations/999/hide", json={}, headers=admin).status_code == 404
    assert client.get("/api/admin/log", headers=admin).json() == {"items": [], "total": 0}


def test_ban_notifies_user_and_unban_restores_only_what_ban_hid(client, admin):
    agree(client, 1, 2)
    kept, manual = new_invitation(client, 1, "Первое"), new_invitation(client, 1, "Второе")
    client.post(f"/api/admin/invitations/{manual}/hide", json={"reason": "Спам"}, headers=admin)

    client.sent.clear()
    assert client.post("/api/admin/users/1/ban", json={"reason": "Оскорбления"}, headers=admin).status_code == 200
    assert [uid for uid, _ in client.sent] == [1] and "Оскорбления" in client.sent[0][1]
    assert client.post("/api/admin/users/1/ban", json={"reason": "Оскорбления"}, headers=admin).status_code == 200
    assert len(client.sent) == 1, "повторная такая же блокировка не пишет снова"
    assert client.get("/api/admin/log", headers=admin).json()["total"] == 2

    listed = client.get("/api/admin/users", params={"banned": "true"}, headers=admin).json()["items"]
    assert listed[0]["ban_reason"] == "Оскорбления"

    client.sent.clear()
    restored = client.post("/api/admin/users/1/unban", headers=admin)
    assert restored.json() == {"ok": True, "restored": 1}
    assert [uid for uid, _ in client.sent] == [1] and "восстановлен" in client.sent[0][1]
    assert [i["id"] for i in client.get("/api/invitations", headers=as_user(2)).json()] == [kept]
    assert client.get(f"/api/invitations/{manual}", headers=as_user(1)).json()["hidden_reason"] == "Спам"
    again = client.post("/api/admin/users/1/unban", headers=admin)
    assert again.json()["restored"] == 0 and len(client.sent) == 1


def test_default_ban_reason(client, admin):
    agree(client, 1)
    client.post("/api/admin/users/1/ban", headers=admin)
    assert client.get("/api/admin/users", params={"banned": "true"}, headers=admin).json()["items"][0]["ban_reason"] == "Нарушение правил"
    assert client.post("/api/admin/users/1/ban", json={"reason": "я" * 201}, headers=admin).status_code == 422


def test_invitation_search_and_paging(client, admin):
    add(city(), user(1, name="Иван Петров"), user(2, name="Мария"))
    add(
        invitation(1, 1, title="Шахматный турнир", description="Приходите с досками"),
        invitation(2, 1, title="Баскетбол во дворе"),
        invitation(3, 2, title="Настольные игры"),
    )
    ids = lambda **p: [i["id"] for i in client.get("/api/admin/invitations", params=p, headers=admin).json()["items"]]

    assert ids() == [3, 2, 1]
    assert ids(q="ШАХМАТ") == [1]
    assert ids(q="  досками ") == [1]
    assert ids(q="иван") == [2, 1]
    assert ids(q="3") == [3]
    assert ids(q="нет такого") == []
    body = client.get("/api/admin/invitations", params={"q": "иван", "limit": 1, "offset": 1}, headers=admin).json()
    assert [i["id"] for i in body["items"]] == [1] and body["total"] == 2
    page = client.get("/api/admin/invitations", params={"limit": 2, "offset": 2}, headers=admin).json()
    assert [i["id"] for i in page["items"]] == [1] and page["total"] == 3


def test_user_listing_search_and_report_counts(client, admin):
    add(city(), user(1, name="Иван Петров", username="ivan_p"), user(2, name="Мария"), user(3, name="Пётр", banned=True))
    add(invitation(1, 1), invitation(2, 1))
    agree(client, 4)
    client.post("/api/invitations/1/report", json={"reason": "spam"}, headers=as_user(4))
    client.post("/api/invitations/2/report", json={"reason": "abuse"}, headers=as_user(4))

    def users(**p):
        return client.get("/api/admin/users", params=p, headers=admin).json()

    everyone = users()
    assert [u["id"] for u in everyone["items"]] == [4, 3, 2, 1] and everyone["total"] == 4
    ivan = next(u for u in everyone["items"] if u["id"] == 1)
    assert ivan["invitations"] == 2 and ivan["reports"] == 2 and ivan["banned"] is False
    assert [u["id"] for u in users(q="ivan_p")["items"]] == [1]
    assert [u["id"] for u in users(q="МАРИ")["items"]] == [2]
    assert [u["id"] for u in users(q="3")["items"]] == [3]
    assert [u["id"] for u in users(banned="true")["items"]] == [3]
    assert [u["id"] for u in users(banned="false")["items"]] == [4, 2, 1]
    assert users(limit=2, offset=2)["total"] == 4 and len(users(limit=2, offset=2)["items"]) == 2


def test_search_treats_yo_as_ye(client, admin):
    add(city(), user(1, name="Пётр"))
    add(invitation(1, 1, title="Ёлка в школе"))
    assert [u["id"] for u in client.get("/api/admin/users", params={"q": "петр"}, headers=admin).json()["items"]] == [1]
    assert [i["id"] for i in client.get("/api/admin/invitations", params={"q": "елка"}, headers=admin).json()["items"]] == [1]


def test_invitation_items_carry_author_report_total(client, admin):
    add(city(), user(1), user(2))
    add(invitation(1, 1), invitation(2, 1))
    agree(client, 3)
    client.post("/api/invitations/1/report", json={"reason": "spam"}, headers=as_user(3))
    items = client.get("/api/admin/invitations", headers=admin).json()["items"]
    assert {i["id"]: i["author"]["reports"] for i in items} == {1: 1, 2: 1}


def test_metrics_per_day_and_totals(client, admin):
    agree(client, 1, 2, 3)
    inv = new_invitation(client, 1, "Сегодняшнее")
    client.post(f"/api/invitations/{inv}/respond", headers=as_user(2))
    client.post(f"/api/invitations/{inv}/respond", headers=as_user(3))
    rid = client.get("/api/invitations/mine", headers=as_user(1)).json()[0]["responses"][0]["id"]
    client.post(f"/api/responses/{rid}/accept", headers=as_user(1))

    past = date.today() - timedelta(days=30)
    add(invitation(50, 1, when_date=past), response(50, 50, 2, "accepted"), invitation(51, 1, when_date=past), response(51, 51, 2, "pending"))

    body = client.get("/api/admin/metrics", headers=admin).json()
    assert len(body["days"]) == 7
    dates = [d["date"] for d in body["days"]]
    assert dates == sorted(dates) and len(set(dates)) == 7
    today = body["days"][-1]
    assert today["invitations"] == 1 and today["responses"] == 4 and today["accepted"] == 2
    assert sum(d["invitations"] for d in body["days"][:-1]) == 0
    assert body["totals"] == {"invitations": 3, "responses": 4, "accepted": 2, "held": 1}


def test_metrics_period_is_selectable(client, admin):
    agree(client, 1)
    new_invitation(client, 1, "Сегодняшнее")
    for days in (7, 14, 30):
        body = client.get("/api/admin/metrics", params={"days": days}, headers=admin).json()
        assert len(body["days"]) == days and body["days"][-1]["invitations"] == 1
        assert body["totals"]["invitations"] == 1
    assert len(client.get("/api/admin/metrics", headers=admin).json()["days"]) == 7
    for bad in (0, 5, 31, 90):
        assert client.get("/api/admin/metrics", params={"days": bad}, headers=admin).status_code == 422


def test_metrics_exclude_hidden_invitations_from_held(client, admin):
    add(city(), user(1), user(2))
    past = date.today() - timedelta(days=3)
    add(invitation(1, 1, when_date=past, hidden=True), response(1, 1, 2, "accepted"))
    assert client.get("/api/admin/metrics", headers=admin).json()["totals"]["held"] == 0


def test_new_admin_endpoints_need_the_key(client, admin):
    for path in ("/api/admin/log", "/api/admin/metrics", "/api/admin/users", "/api/admin/invitations"):
        assert client.get(path).status_code == 401, path
        assert client.get(path, headers=admin).status_code == 200, path


def ban_row(uid):
    with db.SessionLocal() as s:
        return s.get(db.UserBan, uid)


def test_temporary_ban_expires_on_next_request(client, admin, monkeypatch):
    agree(client, 1, 2)
    inv = new_invitation(client, 1, "Первое")
    assert client.post("/api/admin/users/1/ban", json={"reason": "Спам", "days": 2}, headers=admin).status_code == 200

    listed = client.get("/api/admin/users", params={"banned": "true"}, headers=admin).json()["items"][0]
    assert listed["ban_reason"] == "Спам" and listed["ban_until"]
    denied = client.get("/api/me", headers=as_user(1))
    assert denied.status_code == 403 and "до " in denied.json()["detail"] and "МСК" in denied.json()["detail"]
    assert client.get(f"/api/invitations/{inv}", headers=as_user(2)).status_code == 404

    monkeypatch.setattr(bans, "utcnow", lambda: db.now() + timedelta(days=1))
    assert client.get("/api/me", headers=as_user(1)).status_code == 403

    monkeypatch.setattr(bans, "utcnow", lambda: db.now() + timedelta(days=3))
    assert client.get("/api/me", headers=as_user(1)).status_code == 200
    assert client.get(f"/api/invitations/{inv}", headers=as_user(2)).status_code == 200
    assert ban_row(1) is None
    last = client.get("/api/admin/log", headers=admin).json()["items"][0]
    assert last["action"] == "unban" and last["source"] == "auto" and "возвращено приглашений: 1" in last["detail"]


def test_temporary_ban_is_lifted_by_the_background_job_with_a_message(client, admin):
    agree(client, 1)
    inv = new_invitation(client, 1, "Первое")
    client.post("/api/admin/users/1/ban", json={"days": 1}, headers=admin)
    client.sent.clear()

    client.clock.now = db.now() + timedelta(hours=5)
    run(reminders.run_once())
    assert get(User, 1).banned is True and client.sent == []

    client.clock.now = db.now() + timedelta(days=2)
    run(reminders.run_once())
    assert get(User, 1).banned is False and get(Invitation, inv).hidden is False
    assert [uid for uid, _ in client.sent] == [1] and "закончился" in client.sent[0][1]
    run(reminders.run_once())
    assert len(client.sent) == 1


def test_ban_message_mentions_end_date_and_reban_changes_term(client, admin):
    agree(client, 1)
    client.sent.clear()
    client.post("/api/admin/users/1/ban", json={"reason": "Спам", "days": 7}, headers=admin)
    assert "до " in client.sent[0][1] and "Спам" in client.sent[0][1]
    client.post("/api/admin/users/1/ban", json={"reason": "Спам"}, headers=admin)
    assert len(client.sent) == 2 and "до " not in client.sent[1][1]
    assert ban_row(1).until is None
    assert client.get("/api/admin/users", params={"banned": "true"}, headers=admin).json()["items"][0]["ban_until"] is None


def test_ban_days_are_validated(client, admin):
    agree(client, 1)
    for days in (0, 366, -1):
        assert client.post("/api/admin/users/1/ban", json={"days": days}, headers=admin).status_code == 422


def test_unban_clears_ban_record(client, admin):
    agree(client, 1)
    client.post("/api/admin/users/1/ban", json={"days": 3}, headers=admin)
    assert ban_row(1) is not None
    client.post("/api/admin/users/1/unban", headers=admin)
    assert ban_row(1) is None


def seed_school(sid=1, name="Школа 15", custom=True, city_id=1):
    add(School(id=sid, city_id=city_id, name=name, name_norm=name.lower(), custom=custom))


def test_user_profile_view(client, admin):
    add(city(), user(1, name="Иван Петров", display_name="Ваня", username="ivan", grade=8, interests="chess,football"))
    seed_school()
    add(invitation(1, 1, title="Шахматы"))
    with db.SessionLocal() as s:
        s.get(User, 1).school_id = 1
        s.commit()
    body = client.get("/api/admin/users/1", headers=admin).json()
    assert body["name"] == "Иван Петров" and body["display_name"] == "Ваня" and body["public_name"] == "Ваня"
    assert body["grade"] == 8 and body["city"] == "Казань" and body["school"] == "Школа 15" and body["school_custom"] is True
    assert body["interests"] == ["Шахматы", "Футбол"]
    assert body["banned"] is False and body["ban_until"] is None
    assert [i["title"] for i in body["invitations"]] == ["Шахматы"]
    assert {"description", "when", "status", "hidden"} <= set(body["invitations"][0])
    assert client.get("/api/admin/users/999", headers=admin).status_code == 404
    assert client.get("/api/admin/users/1").status_code == 401


def test_edit_user_changes_what_others_see_and_notifies(client, admin):
    add(city(), user(1, name="Иван Петров", display_name="Вася лох123", grade=9), user(2))
    seed_school(1, "Школа-нонсенс")
    seed_school(2, "Гимназия 7", custom=False)
    client.sent.clear()
    r = client.patch("/api/admin/users/1", json={"display_name": "Вася", "grade": 8, "school_id": 2}, headers=admin)
    assert r.status_code == 200
    body = r.json()
    assert body["display_name"] == "Вася" and body["grade"] == 8 and body["school"] == "Гимназия 7"
    assert [uid for uid, _ in client.sent] == [1]
    assert all(word in client.sent[0][1] for word in ("публичное имя", "класс", "школа"))
    entry = client.get("/api/admin/log", headers=admin).json()["items"][0]
    assert entry["action"] == "edit_user" and "Вася лох123 → Вася" in entry["detail"] and "9 → 8" in entry["detail"]
    mine = client.get("/api/me", headers=as_user(1)).json()
    assert mine["display_name"] == "Вася" and mine["grade"] == 8
    assert client.get("/api/me", headers=as_user(1)).json()["display_name"] == "Вася"


def test_edit_user_validation_and_noop(client, admin):
    add(city(), user(1, display_name="Вася", grade=8))
    seed_school(1)
    assert client.patch("/api/admin/users/1", json={"display_name": "12345"}, headers=admin).status_code == 422
    assert client.patch("/api/admin/users/1", json={"display_name": "я" * 31}, headers=admin).status_code == 422
    assert client.patch("/api/admin/users/1", json={"grade": 4}, headers=admin).status_code == 422
    assert client.patch("/api/admin/users/1", json={"grade": 12}, headers=admin).status_code == 422
    assert client.patch("/api/admin/users/1", json={"school_id": 99}, headers=admin).status_code == 404
    assert client.patch("/api/admin/users/99", json={"grade": 8}, headers=admin).status_code == 404
    client.sent.clear()
    same = client.patch("/api/admin/users/1", json={"display_name": "Вася", "grade": 8}, headers=admin)
    assert same.status_code == 200 and client.sent == []
    assert client.get("/api/admin/log", headers=admin).json()["total"] == 0


def test_edit_user_can_reset_public_name(client, admin):
    add(city(), user(1, name="Иван Петров", display_name="Глупое имя"))
    r = client.patch("/api/admin/users/1", json={"display_name": "  "}, headers=admin).json()
    assert r["display_name"] == "" and r["public_name"] == "Иван"


def test_school_search_and_rename(client, admin):
    add(city(), user(1), user(2))
    seed_school(1, "Школа фывфыв")
    seed_school(2, "Гимназия 7", custom=False)
    with db.SessionLocal() as s:
        for uid in (1, 2):
            s.get(User, uid).school_id = 1
        s.commit()
    found = client.get("/api/admin/schools", params={"q": "фывфыв"}, headers=admin).json()["items"]
    assert found == [{"id": 1, "name": "Школа фывфыв", "custom": True, "city": "Казань", "region": "Республика Татарстан", "members": 2}]
    assert client.get("/api/admin/schools", params={"q": ""}, headers=admin).json() == {"items": []}
    assert client.get("/api/admin/schools", params={"q": "гимназия"}, headers=admin).json()["items"][0]["custom"] is False

    assert client.patch("/api/admin/schools/2", json={"name": "Другая"}, headers=admin).status_code == 409
    assert client.patch("/api/admin/schools/99", json={"name": "Другая"}, headers=admin).status_code == 404
    assert client.patch("/api/admin/schools/1", json={"name": "123"}, headers=admin).status_code == 422
    assert client.patch("/api/admin/schools/1", json={"name": "Гимназия 7"}, headers=admin).status_code == 409
    ok = client.patch("/api/admin/schools/1", json={"name": "Лицей 40"}, headers=admin)
    assert ok.status_code == 200 and ok.json() == {"id": 1, "name": "Лицей 40"}
    assert client.get("/api/admin/users/1", headers=admin).json()["school"] == "Лицей 40"
    entry = client.get("/api/admin/log", headers=admin).json()["items"][0]
    assert entry["action"] == "rename_school" and entry["detail"] == "Школа фывфыв → Лицей 40"


def test_edit_invitation_fixes_text_marks_edited_and_notifies(client, admin):
    add(city(), user(1), user(2))
    add(invitation(1, 1, title="Нормальное", description="какая-то чушь", when="бла бла"))
    client.sent.clear()
    r = client.patch("/api/admin/invitations/1", json={"title": "  Шахматы   вечером ", "description": "Приходите\r\n\r\n\r\n\r\nс досками", "when": "после   уроков"}, headers=admin)
    assert r.status_code == 200
    item = r.json()
    assert item["title"] == "Шахматы вечером" and item["description"] == "Приходите\n\nс досками"
    assert [uid for uid, _ in client.sent] == [1] and "Шахматы вечером" in client.sent[0][1]
    shown = client.get("/api/invitations/1", headers=as_user(2)).json()
    assert shown["edited"] is True and shown["when"] == "после уроков"
    entry = client.get("/api/admin/log", headers=admin).json()["items"][0]
    assert entry["action"] == "edit_inv" and entry["target_label"] == "Нормальное" and "название" in entry["detail"]


def test_edit_invitation_noop_validation_and_clearing(client, admin):
    add(city(), user(1))
    add(invitation(1, 1, title="Шахматы", description="Текст"))
    client.sent.clear()
    assert client.patch("/api/admin/invitations/1", json={"title": "Шахматы"}, headers=admin).status_code == 200
    assert client.sent == [] and client.get("/api/admin/log", headers=admin).json()["total"] == 0
    assert client.patch("/api/admin/invitations/1", json={"title": "ab"}, headers=admin).status_code == 422
    assert client.patch("/api/admin/invitations/1", json={"title": "я" * 121}, headers=admin).status_code == 422
    assert client.patch("/api/admin/invitations/1", json={"description": "я" * 1001}, headers=admin).status_code == 422
    assert client.patch("/api/admin/invitations/99", json={"title": "Шахматы"}, headers=admin).status_code == 404
    cleared = client.patch("/api/admin/invitations/1", json={"description": ""}, headers=admin).json()
    assert cleared["description"] == ""


def test_new_edit_endpoints_need_the_key(client, admin, monkeypatch):
    monkeypatch.setattr(safety, "ADMIN_MAX_FAILURES", 100)
    calls = (
        ("get", "/api/admin/users/1", None),
        ("patch", "/api/admin/users/1", {"grade": 8}),
        ("get", "/api/admin/schools?q=школа", None),
        ("patch", "/api/admin/schools/1", {"name": "Лицей"}),
        ("patch", "/api/admin/invitations/1", {"title": "Шахматы"}),
        ("post", "/api/admin/users/1/ban", {"days": 1}),
    )
    for method, path, body in calls:
        assert getattr(client, method)(path, **({"json": body} if body else {})).status_code == 401, path
        wrong = getattr(client, method)(path, headers={"X-Admin-Key": "nope"}, **({"json": body} if body else {}))
        assert wrong.status_code == 401, path
