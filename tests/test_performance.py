import pytest
from helpers import add, agree, as_user, city, invitation, response, user
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app import activity, db, metrics, notifications
from app.config import settings

NEW_INDEXES = {
    "invitations": {"ix_invitations_author_id", "ix_invitations_feed_school", "ix_invitations_feed_city", "ix_invitations_open_when"},
    "responses": {"uq_responses_invitation_user", "ix_responses_user_created"},
    "users": {"ix_users_city_id", "ix_users_school_id"},
    "reports": {"ix_reports_reporter_id", "ix_reports_open"},
}


def index_names(engine, table):
    return {i["name"] for i in inspect(engine).get_indexes(table)}


def test_fresh_schema_has_every_index(database):
    for table, names in NEW_INDEXES.items():
        assert names <= index_names(database, table), table


def test_ensure_indexes_adds_missing_ones_to_an_existing_database(database, monkeypatch):
    with database.begin() as conn:
        for name in ("ix_invitations_author_id", "uq_responses_invitation_user", "ix_users_city_id"):
            conn.execute(text(f"DROP INDEX {name}"))
    assert "ix_invitations_author_id" not in index_names(database, "invitations")
    monkeypatch.setattr(db, "engine", database)
    assert db.ensure_indexes() == []
    for table, names in NEW_INDEXES.items():
        assert names <= index_names(database, table), table


def test_ensure_indexes_is_idempotent(database, monkeypatch):
    monkeypatch.setattr(db, "engine", database)
    assert db.ensure_indexes() == []
    assert db.ensure_indexes() == []


def test_ensure_indexes_reports_but_survives_legacy_duplicates(database, monkeypatch):
    add(city(), user(1), user(2), invitation(1, 1))
    with database.begin() as conn:
        conn.execute(text("DROP INDEX uq_responses_invitation_user"))
        conn.execute(text("INSERT INTO responses (invitation_id, user_id, status, created_at) VALUES (1, 2, 'pending', '2026-10-20'), (1, 2, 'pending', '2026-10-21')"))
    monkeypatch.setattr(db, "engine", database)
    assert db.ensure_indexes() == ["uq_responses_invitation_user"]
    assert "ix_users_city_id" in index_names(database, "users")


def test_one_response_per_user_and_invitation_is_enforced(database):
    add(city(), user(1), user(2), invitation(1, 1), response(1, 1, 2))
    with pytest.raises(IntegrityError):
        add(response(2, 1, 2))


def test_pool_options_depend_on_the_database():
    sqlite = db.engine_options("sqlite:///:memory:")
    assert sqlite == {"pool_pre_ping": True}
    pg = db.engine_options("postgresql+psycopg://u:p@db:5432/x")
    assert pg["pool_size"] == db.POOL_SIZE and pg["max_overflow"] == db.POOL_OVERFLOW
    assert pg["pool_timeout"] == db.POOL_TIMEOUT and pg["pool_recycle"] == db.POOL_RECYCLE and pg["pool_pre_ping"] is True


def test_repeated_requests_by_a_known_user_do_not_commit(client, monkeypatch):
    agree(client, 1)
    client.get("/api/me", headers=as_user(1))
    commits = []
    original = db.SessionLocal.class_.commit

    def counting(self, *args, **kwargs):
        commits.append(1)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(db.SessionLocal.class_, "commit", counting)
    for _ in range(3):
        assert client.get("/api/me", headers=as_user(1)).status_code == 200
    assert commits == []


def test_changed_username_is_still_saved(client):
    agree(client, 1)
    client.get("/api/me", headers={**as_user(1), "X-Dev-Username": "first_name"})
    client.get("/api/me", headers={**as_user(1), "X-Dev-Username": "second_name"})
    with db.SessionLocal() as s:
        assert s.get(db.User, 1).username == "second_name"


def test_first_request_creates_user_and_activity(client):
    assert client.get("/api/me", headers=as_user(7)).status_code == 200
    with db.SessionLocal() as s:
        assert s.get(db.User, 7) is not None
        assert s.query(db.UserActivity).filter_by(user_id=7).count() == 1


def test_activity_record_reports_whether_it_wrote(database):
    add(user(1))
    with db.SessionLocal() as s:
        assert activity.record(s, 1) is True
        s.commit()
        assert activity.record(s, 1) is False
        activity.seen.clear()
        assert activity.record(s, 1) is False


@pytest.mark.parametrize("path, cache", [("/api/interests", "public, max-age=3600"), ("/api/regions", "public, max-age=3600"), ("/api/terms", "no-cache")])
def test_static_dictionaries_are_cacheable_and_revalidate(client, path, cache):
    first = client.get(path)
    assert first.status_code == 200 and first.headers["cache-control"] == cache
    etag = first.headers["etag"]
    assert etag.startswith('"') and first.json()
    again = client.get(path, headers={"If-None-Match": etag})
    assert again.status_code == 304 and again.content == b"" and again.headers["etag"] == etag
    assert client.get(path, headers={"If-None-Match": '"other"'}).status_code == 200


def test_etag_changes_when_the_content_changes(client, monkeypatch):
    before = client.get("/api/terms").headers["etag"]
    monkeypatch.setattr("app.terms.TERMS_VERSION", "2099-01-01")
    assert client.get("/api/terms").headers["etag"] != before


def test_dictionary_content_is_unchanged(client):
    interests = client.get("/api/interests").json()
    assert {"id": "chess", "name": "Шахматы", "group": "Игры"} in interests
    assert "Республика Татарстан" in client.get("/api/regions").json()


def test_recipients_only_include_users_with_the_exact_interest(database):
    add(city(), user(1), user(2, interests="video"), user(3, interests="videogames"), user(4, interests="chess,video"), user(5, interests="videogames,games"))
    add(invitation(1, 1, interest="video"))
    with db.SessionLocal() as s:
        inv = s.get(db.Invitation, 1)
        assert notifications.new_invitation_recipients(s, inv) == [2, 4]


def test_recipients_respect_city_blocks_and_switches(database):
    add(city(), city(2, name="Другой", offset=300), user(1))
    add(user(2, interests="chess"), user(3, interests="chess", city_id=2), user(4, interests="chess", notify=False), user(5, interests="chess", banned=True), user(6, interests="chess", bot_state="blocked"))
    add(invitation(1, 1, interest="chess"))
    with db.SessionLocal() as s:
        assert notifications.new_invitation_recipients(s, s.get(db.Invitation, 1)) == [2]


def test_expensive_metrics_are_cached_but_db_status_stays_live(client, monkeypatch):
    monkeypatch.setattr(settings, "metrics_token", "t" * 24)
    monkeypatch.setattr(metrics, "CACHE_SECONDS", 60)
    headers = {"Authorization": "Bearer " + "t" * 24}
    users = lambda: [line for line in client.get("/metrics", headers=headers).text.splitlines() if line.startswith('kto_users{state="registered"}')][0]
    assert users().endswith(" 0.0")
    add(user(1), user(2))
    assert users().endswith(" 0.0"), "значение берётся из кэша"
    monkeypatch.setattr(metrics, "CACHE_SECONDS", 0)
    assert users().endswith(" 2.0")


def test_cached_metrics_do_not_hide_a_database_outage(client, monkeypatch):
    monkeypatch.setattr(settings, "metrics_token", "t" * 24)
    monkeypatch.setattr(metrics, "CACHE_SECONDS", 60)
    headers = {"Authorization": "Bearer " + "t" * 24}
    assert "kto_db_up 1.0" in client.get("/metrics", headers=headers).text

    class Broken:
        def __enter__(self):
            raise RuntimeError("db down")

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(metrics, "SessionLocal", lambda: Broken())
    text_ = client.get("/metrics", headers=headers).text
    assert "kto_db_up 0.0" in text_ and "kto_users" not in text_
