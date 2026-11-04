import pytest
from helpers import add, agree, as_user, city, invitation, response, user

from app.config import settings
from app.serializers import LIST_DESCRIPTION_MAX, LIST_OMITTED, list_description

LONG = "Приходите с досками и часами, играем турнир на вылет. " * 20


@pytest.fixture()
def world(client, monkeypatch):
    monkeypatch.setattr(settings, "bot_username", "kto_bot")
    add(city(), user(1), user(2), user(3))
    add(invitation(1, 1, description=LONG, school_id=None), invitation(2, 2, description="Коротко", school_id=None))
    return client


def test_feed_items_are_brief(world):
    items = world.get("/api/invitations", params={"scope": "city"}, headers=as_user(3)).json()
    assert len(items) == 2
    for item in items:
        assert not set(LIST_OMITTED) & set(item)
        assert {"id", "title", "description", "when_date", "max_participants", "accepted", "author", "my_response", "is_mine", "hidden", "edited"} <= set(item)


def test_my_and_joined_lists_are_brief(world):
    add(response(1, 2, 1, "accepted"))
    mine = world.get("/api/invitations/mine", headers=as_user(1)).json()
    joined = world.get("/api/invitations/joined", headers=as_user(1)).json()
    assert [i["id"] for i in mine] == [1] and [i["id"] for i in joined] == [2]
    for item in mine + joined:
        assert not set(LIST_OMITTED) & set(item)
    assert "responses" in mine[0], "автору нужны отклики для счётчика «ждут ответа»"


def test_detail_keeps_every_field_and_the_full_text(world):
    item = world.get("/api/invitations/1", headers=as_user(3)).json()
    assert item["description"] == LONG.strip() or item["description"].startswith(LONG[:100])
    assert len(item["description"]) > LIST_DESCRIPTION_MAX
    assert item["link"] == "https://max.ru/kto_bot?startapp=inv_1"
    assert set(LIST_OMITTED) <= set(item)


def test_actions_that_return_an_invitation_stay_complete(client):
    agree(client, 1)
    created = client.post("/api/invitations", json={"interest": "chess", "title": "Шахматы", "description": LONG[:900]}, headers=as_user(1))
    assert created.status_code == 201
    assert set(LIST_OMITTED) <= set(created.json()) and len(created.json()["description"]) > LIST_DESCRIPTION_MAX


def test_long_description_is_cut_in_the_feed_only(world):
    brief = world.get("/api/invitations", params={"scope": "city"}, headers=as_user(3)).json()
    long_one = next(i for i in brief if i["id"] == 1)
    assert len(long_one["description"]) <= LIST_DESCRIPTION_MAX + 1 and long_one["description"].endswith("…")
    short = next(i for i in brief if i["id"] == 2)
    assert short["description"] == "Коротко"


@pytest.mark.parametrize("text, expected", [("", ""), ("коротко", "коротко"), ("я" * LIST_DESCRIPTION_MAX, "я" * LIST_DESCRIPTION_MAX)])
def test_short_descriptions_are_untouched(text, expected):
    assert list_description(text) == expected


def test_cut_prefers_a_word_boundary():
    text = ("слово " * 100).strip()
    out = list_description(text)
    assert out.endswith("слово…") and len(out) <= LIST_DESCRIPTION_MAX + 1


def test_cut_without_spaces_still_ends_with_an_ellipsis():
    out = list_description("я" * 1000)
    assert out == "я" * LIST_DESCRIPTION_MAX + "…"


def test_cut_does_not_leave_trailing_spaces():
    text = "а" * (LIST_DESCRIPTION_MAX - 5) + "      " + "б" * 100
    out = list_description(text)
    assert not out[:-1].endswith(" ") and out.endswith("…")


def test_cut_keeps_emoji_intact():
    text = "😀" * 400
    out = list_description(text)
    assert out == "😀" * LIST_DESCRIPTION_MAX + "…"
