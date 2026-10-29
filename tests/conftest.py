import os
import sys
from datetime import datetime, timezone

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DEV_MODE"] = "true"
os.environ["BOT_TOKEN"] = ""
os.environ["BOT_USERNAME"] = ""
os.environ["ADMIN_KEY"] = ""
os.environ["BOT_QUICK_ACTIONS"] = "false"
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app import citylist, db, notifications
from app.config import settings
from app.main import app
from app.max_client import SendResult, max_client

ADMIN_KEY = "k" * 20


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 22, 9, 0, tzinfo=timezone.utc)


class Outbox(list):
    def __init__(self):
        super().__init__()
        self.result = SendResult(True)
        self.fallbacks = []


class SentTexts:
    def __init__(self, outbox: Outbox):
        self._outbox = outbox

    def __iter__(self):
        return iter((u, t) for u, t, _ in self._outbox)

    def __len__(self):
        return len(self._outbox)

    def __getitem__(self, i):
        u, t, _ = self._outbox[i]
        return (u, t)

    def __eq__(self, other):
        return list(self) == other

    def clear(self):
        self._outbox.clear()


class SentButtons:
    def __init__(self, outbox: Outbox):
        self._outbox = outbox

    def __iter__(self):
        return iter((u, b) for u, _, b in self._outbox)

    def clear(self):
        self._outbox.clear()


@pytest.fixture()
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(notifications, "utcnow", lambda: c.now)
    return c


@pytest.fixture()
def outbox(monkeypatch):
    box = Outbox()

    async def fake_send(user_id, text, buttons=None, fallback_buttons=None):
        box.append((user_id, text, buttons))
        box.fallbacks.append(fallback_buttons)
        return box.result

    monkeypatch.setattr(max_client, "send", fake_send)
    return box


@pytest.fixture()
def database(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    db.Base.metadata.create_all(engine)
    monkeypatch.setattr(db.SessionLocal, "kw", {**db.SessionLocal.kw, "bind": engine})
    monkeypatch.setattr(citylist, "seed_builtin", lambda session: 0)
    return engine


@pytest.fixture()
def client(database, outbox, clock):
    with TestClient(app) as c:
        c.sent, c.sent_buttons, c.outbox, c.clock = SentTexts(outbox), SentButtons(outbox), outbox, clock
        yield c


@pytest.fixture()
def admin(monkeypatch):
    monkeypatch.setattr(settings, "admin_key", ADMIN_KEY)
    return {"X-Admin-Key": ADMIN_KEY}
