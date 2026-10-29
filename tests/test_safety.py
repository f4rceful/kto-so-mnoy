from datetime import datetime, timedelta

from helpers import agree, as_user, find_city, new_invitation, register, seed_cities

from app import db, main
from app.config import settings
from app.routers.invitations import INVITATIONS_PER_HOUR
from app.safety import REPORTS_PER_DAY


def test_report_reasons_and_validation(client):
    agree(client, 1, 2)
    reasons = {r["id"] for r in client.get("/api/report-reasons", headers=as_user(2)).json()}
    assert reasons == {"spam", "abuse", "danger", "personal", "other"}
    inv = new_invitation(client, 1)
    url = f"/api/invitations/{inv}/report"
    assert client.post(url, json={"reason": "nope"}, headers=as_user(2)).status_code == 422
    assert client.post(url, json={"reason": "spam", "text": "я" * 301}, headers=as_user(2)).status_code == 422
    assert client.post("/api/invitations/999/report", json={"reason": "spam"}, headers=as_user(2)).status_code == 404
    assert client.post(url, json={"reason": "spam"}, headers=as_user(1)).status_code == 409
    assert client.post(url, json={"reason": "spam"}).status_code == 401
    assert client.post(url, json={"reason": "spam", "text": "  реклама   казино "}, headers=as_user(2)).status_code == 201
    assert client.post(url, json={"reason": "abuse"}, headers=as_user(2)).status_code == 409
    assert client.get(f"/api/invitations/{inv}", headers=as_user(2)).json()["reported"] is True
    assert client.get(f"/api/invitations/{inv}", headers=as_user(3)).json()["reported"] is False


def test_three_reports_hide_invitation(client):
    agree(client, 1, 2, 3, 4, 5)
    inv = new_invitation(client, 1, "Подозрительное")
    url = f"/api/invitations/{inv}"
    client.post(f"{url}/respond", headers=as_user(5))

    client.sent.clear()
    for uid in (2, 3):
        assert client.post(f"{url}/report", json={"reason": "spam"}, headers=as_user(uid)).status_code == 201
    assert [i["id"] for i in client.get("/api/invitations", headers=as_user(4)).json()] == [inv]
    assert client.sent == []

    assert client.post(f"{url}/report", json={"reason": "danger"}, headers=as_user(4)).status_code == 201
    assert client.get("/api/invitations", headers=as_user(5)).json() == []
    assert client.get(url, headers=as_user(5)).status_code == 404
    assert client.get(url, headers=as_user(2)).status_code == 404
    assert client.post(f"{url}/report", json={"reason": "spam"}, headers=as_user(5)).status_code == 404
    assert client.post(f"{url}/respond", headers=as_user(2)).status_code == 404
    assert client.get("/api/invitations/joined", headers=as_user(5)).json() == []
    mine = client.get(f"{url}", headers=as_user(1)).json()
    assert mine["hidden"] is True and mine["hidden_reason"] == "Жалобы пользователей"
    assert client.get("/api/invitations/mine", headers=as_user(1)).json()[0]["hidden"] is True
    assert [uid for uid, _ in client.sent] == [1] and "скрыто до проверки" in client.sent[0][1]
    r = client.put(url, json={"interest": "chess", "title": "Исправленное"}, headers=as_user(1))
    assert r.status_code == 200 and r.json()["hidden"] is True


def test_block_author(client):
    agree(client, 1, 2, 3)
    inv1, inv2 = new_invitation(client, 1, "От первого"), new_invitation(client, 2, "От второго")
    h1, h2, h3 = as_user(1), as_user(2), as_user(3)
    assert sorted(i["id"] for i in client.get("/api/invitations", headers=h3).json()) == [inv1, inv2]

    assert client.post(f"/api/invitations/{inv1}/block-author", headers=h1).status_code == 409
    assert client.post("/api/invitations/999/block-author", headers=h3).status_code == 404
    assert client.post(f"/api/invitations/{inv1}/block-author", headers=h3).status_code == 200
    assert client.post(f"/api/invitations/{inv1}/block-author", headers=h3).status_code == 200

    assert [i["id"] for i in client.get("/api/invitations", headers=h3).json()] == [inv2]
    assert client.get(f"/api/invitations/{inv1}", headers=h3).status_code == 404
    assert [i["id"] for i in client.get("/api/invitations", headers=h1).json()] == [inv2, inv1]
    assert client.post(f"/api/invitations/{inv1}/respond", headers=h3).status_code == 409
    inv3 = new_invitation(client, 3, "От третьего")
    assert [i["id"] for i in client.get("/api/invitations", headers=h1).json()] == [inv2, inv1]
    assert inv3 not in [i["id"] for i in client.get("/api/invitations", headers=h1).json()]
    assert client.post(f"/api/invitations/{inv3}/respond", headers=h1).status_code == 409
    assert client.get(f"/api/invitations/{inv3}", headers=h1).status_code == 404
    assert client.get(f"/api/invitations/{inv1}", headers=h2).status_code == 200

    blocks = client.get("/api/blocks", headers=h3).json()
    assert [b["name"] for b in blocks] == ["Тест"] and len(blocks) == 1
    assert client.get("/api/blocks", headers=h1).json() == []
    assert client.delete(f"/api/blocks/{blocks[0]['id']}", headers=h1).status_code == 404
    assert client.delete(f"/api/blocks/{blocks[0]['id']}", headers=h3).status_code == 200
    assert client.delete(f"/api/blocks/{blocks[0]['id']}", headers=h3).status_code == 404
    assert sorted(i["id"] for i in client.get("/api/invitations", headers=h3).json() if i["id"] != inv3) == [inv1, inv2]
    assert client.post(f"/api/invitations/{inv1}/respond", headers=h3).status_code == 201


def test_existing_response_survives_block(client):
    agree(client, 1, 2)
    inv = new_invitation(client, 1)
    client.post(f"/api/invitations/{inv}/respond", headers=as_user(2))
    client.post(f"/api/invitations/{inv}/block-author", headers=as_user(2))
    assert client.get(f"/api/invitations/{inv}", headers=as_user(2)).status_code == 200
    assert client.get("/api/invitations", headers=as_user(2)).json() == []


def test_rate_limits(client):
    agree(client, 1)
    for n in range(INVITATIONS_PER_HOUR):
        new_invitation(client, 1, f"Шахматы {n}")
    r = client.post("/api/invitations", json={"interest": "chess", "title": "Лишнее"}, headers=as_user(1))
    assert r.status_code == 429
    agree(client, 2)
    new_invitation(client, 2, "У другого лимит свой")

    authors = list(range(10, 10 + REPORTS_PER_DAY + 1))
    agree(client, *authors, 99)
    ids = [new_invitation(client, uid, f"Чужое {uid}") for uid in authors]
    for inv in ids[:REPORTS_PER_DAY]:
        assert client.post(f"/api/invitations/{inv}/report", json={"reason": "spam"}, headers=as_user(99)).status_code == 201
    assert client.post(f"/api/invitations/{ids[-1]}/report", json={"reason": "spam"}, headers=as_user(99)).status_code == 429


def test_rate_limit_window_forgets_old_activity(client):
    agree(client, 1, 2, 99)
    with db.SessionLocal() as s:
        for n in range(INVITATIONS_PER_HOUR):
            s.add(db.Invitation(author_id=1, interest="chess", title=f"Старое {n}", created_at=db.now() - timedelta(hours=2)))
        s.commit()
    new_invitation(client, 1, "Новое")
    with db.SessionLocal() as s:
        for n in range(REPORTS_PER_DAY):
            inv = db.Invitation(author_id=2, interest="chess", title=f"Чьё-то {n}", created_at=db.now() - timedelta(days=2))
            s.add(inv)
            s.flush()
            s.add(db.Report(invitation_id=inv.id, reporter_id=99, reason="spam", created_at=db.now() - timedelta(days=2)))
        s.commit()
    fresh = new_invitation(client, 2, "Свежее")
    assert client.post(f"/api/invitations/{fresh}/report", json={"reason": "spam"}, headers=as_user(99)).status_code == 201


def test_admin_requires_key(client, monkeypatch, tmp_path):
    assert client.get("/api/admin/reports").status_code == 404
    monkeypatch.setattr(settings, "admin_key", "secret-key-123")
    assert client.get("/api/admin/reports").status_code == 401
    assert client.get("/api/admin/reports", headers={"X-Admin-Key": "wrong"}).status_code == 401
    assert client.get("/api/admin/reports", headers=as_user(1)).status_code == 401
    assert client.post("/api/admin/invitations/1/hide", headers={"X-Admin-Key": "wrong"}, json={}).status_code == 401
    assert client.post("/api/admin/users/1/ban", headers={"X-Admin-Key": "wrong"}).status_code == 401
    ok = client.get("/api/admin/reports", headers={"X-Admin-Key": "secret-key-123"})
    assert ok.status_code == 200 and ok.json() == {"items": []}

    monkeypatch.setattr(main, "WEBAPP_DIR", tmp_path)
    missing = client.get("/admin")
    assert missing.status_code == 404 and "npm run build" in missing.json()["detail"]
    (tmp_path / "admin.html").write_text("<!doctype html><title>Модерация</title><div id=root></div>", encoding="utf-8")
    page = client.get("/admin")
    assert page.status_code == 200 and "text/html" in page.headers["content-type"] and "Модерация" in page.text
    assert page.headers["cache-control"] == "no-store"


def test_admin_moderation_flow(client, admin):
    agree(client, 1, 2, 3)
    bad, good = new_invitation(client, 1, "Плохое"), new_invitation(client, 3, "Нормальное")
    client.post(f"/api/invitations/{bad}/report", json={"reason": "abuse", "text": "оскорбления"}, headers=as_user(2))
    client.post(f"/api/invitations/{good}/report", json={"reason": "other", "text": "не понравилось"}, headers=as_user(2))
    client.post(f"/api/invitations/{bad}/report", json={"reason": "spam"}, headers=as_user(3))

    items = client.get("/api/admin/reports", headers=admin).json()["items"]
    assert [i["id"] for i in items] == [bad, good]
    first = items[0]
    assert len(first["reports"]) == 2 and first["reports"][0]["text"] == "оскорбления"
    assert first["author"]["id"] == 1 and first["hidden"] is False
    assert "reporter" not in str(first), "кто пожаловался, модератору не показываем"

    client.sent.clear()
    r = client.post(f"/api/admin/invitations/{bad}/hide", json={"reason": "Оскорбления"}, headers=admin)
    assert r.status_code == 200
    assert client.get(f"/api/invitations/{bad}", headers=as_user(2)).status_code == 404
    assert client.get(f"/api/invitations/{bad}", headers=as_user(1)).json()["hidden_reason"] == "Оскорбления"
    assert [uid for uid, _ in client.sent] == [1] and "Оскорбления" in client.sent[0][1]
    hidden = next(i for i in client.get("/api/admin/reports", headers=admin).json()["items"] if i["id"] == bad)
    assert hidden["hidden"] is True and hidden["reports"] == []

    assert client.post(f"/api/admin/invitations/{good}/dismiss", headers=admin).status_code == 200
    assert [i["id"] for i in client.get("/api/admin/reports", headers=admin).json()["items"]] == [bad]
    assert client.get(f"/api/invitations/{good}", headers=as_user(2)).status_code == 200

    assert client.post(f"/api/admin/invitations/{bad}/restore", headers=admin).status_code == 200
    assert client.get(f"/api/invitations/{bad}", headers=as_user(2)).status_code == 200
    assert client.get("/api/admin/reports", headers=admin).json()["items"] == []
    assert client.post("/api/admin/invitations/999/hide", json={}, headers=admin).status_code == 404

    for uid in (2, 3):
        client.post(f"/api/invitations/{bad}/report", json={"reason": "spam"}, headers=as_user(uid))
    assert client.get(f"/api/invitations/{bad}", headers=as_user(2)).status_code == 200


def test_ban_user(client, admin):
    agree(client, 1, 2)
    a, b = new_invitation(client, 1, "Первое"), new_invitation(client, 1, "Второе")
    assert client.post("/api/admin/users/999/ban", headers=admin).status_code == 404
    assert client.post("/api/admin/users/1/ban", headers=admin).status_code == 200
    assert client.get("/api/me", headers=as_user(1)).status_code == 403
    assert client.post("/api/invitations", json={"interest": "chess", "title": "Ещё"}, headers=as_user(1)).status_code == 403
    assert client.get("/api/invitations", headers=as_user(2)).json() == []
    assert client.get(f"/api/invitations/{a}", headers=as_user(2)).status_code == 404
    assert client.get("/api/me", headers=as_user(2)).status_code == 200
    assert client.post("/api/admin/users/1/unban", headers=admin).status_code == 200
    assert client.get("/api/me", headers=as_user(1)).status_code == 200
    assert client.get("/api/invitations", headers=as_user(2)).json() == []
    client.post(f"/api/admin/invitations/{b}/restore", headers=admin)
    assert [i["id"] for i in client.get("/api/invitations", headers=as_user(2)).json()] == [b]


def test_admin_overview_endpoints(client, admin):
    seed_cities()
    for path in ("/api/admin/stats", "/api/admin/invitations", "/api/admin/users"):
        assert client.get(path).status_code == 401, path
        assert client.get(path, headers={"X-Admin-Key": "bad"}).status_code == 401, path

    assert client.get("/api/admin/stats", headers=admin).json() == {"reports": 0, "reported_invitations": 0, "hidden": 0, "banned": 0, "invitations": 0, "users": 0}
    assert client.get("/api/admin/invitations", headers=admin).json() == {"items": []}
    assert client.get("/api/admin/users", headers=admin).json() == {"items": []}

    kazan = find_city(client, 1, "Казань")
    for uid in (1, 2, 3):
        register(client, uid, kazan, "Гимназия 7")
    a, b, c = new_invitation(client, 1, "Первое"), new_invitation(client, 1, "Второе"), new_invitation(client, 2, "Третье")
    client.post(f"/api/invitations/{a}/respond", headers=as_user(3))
    client.post(f"/api/invitations/{a}/report", json={"reason": "spam", "text": "реклама"}, headers=as_user(3))
    client.post(f"/api/invitations/{a}/report", json={"reason": "abuse"}, headers=as_user(2))
    client.post(f"/api/invitations/{c}/report", json={"reason": "other"}, headers=as_user(3))
    client.post(f"/api/admin/invitations/{b}/hide", json={"reason": "Тест"}, headers=admin)

    assert client.get("/api/admin/stats", headers=admin).json() == {"reports": 3, "reported_invitations": 2, "hidden": 1, "banned": 0, "invitations": 3, "users": 3}

    items = client.get("/api/admin/invitations", headers=admin).json()["items"]
    assert [i["id"] for i in items] == [c, b, a]
    first = next(i for i in items if i["id"] == a)
    assert first["school"] == "Гимназия 7" and first["responses"] == 1 and first["status"] == "open"
    assert first["author"] == {"id": 1, "name": "Тест 1", "username": None, "banned": False, "invitations": 2}
    assert len(first["reports"]) == 2 and {r["reason"] for r in first["reports"]} == {"Спам или реклама", "Оскорбления или неприемлемое содержание"}
    assert datetime.fromisoformat(first["created_at"]).tzinfo is not None and datetime.fromisoformat(first["reports"][0]["at"]).tzinfo is not None
    assert next(i for i in items if i["id"] == b)["hidden"] is True
    assert "reporter" not in str(items)
    assert len(client.get("/api/admin/invitations", params={"limit": 2}, headers=admin).json()["items"]) == 2
    assert client.get("/api/admin/invitations", params={"limit": 0}, headers=admin).status_code == 422
    assert client.get("/api/admin/invitations", params={"limit": 501}, headers=admin).status_code == 422

    client.post("/api/admin/users/2/ban", headers=admin)
    banned = client.get("/api/admin/users", headers=admin).json()["items"]
    assert banned == [{"id": 2, "name": "Тест 2", "username": None, "banned": True, "invitations": 1}]
    assert client.get("/api/admin/stats", headers=admin).json()["banned"] == 1
    assert [u["id"] for u in client.get("/api/admin/users", params={"banned": "false"}, headers=admin).json()["items"]] == [3, 1]
    client.post("/api/admin/users/2/unban", headers=admin)
    assert client.get("/api/admin/users", headers=admin).json() == {"items": []}
