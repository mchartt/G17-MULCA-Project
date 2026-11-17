"""
Accounts (mulca_discord/web/accounts.py and account_routes.py): register, log
in, profile, my spaces, and joining a space as a logged-in person.
No MUCA-Server needed: the hub points at an unreachable address on purpose.
"""

from __future__ import annotations

import sqlite3

import httpx
import pytest

from mulca_discord.web import WebHub, WebStore, create_web_app
from mulca_discord.web.accounts import (
    LOCK_SECONDS,
    LOGIN_SECONDS,
    MAX_FAILURES,
    AccountError,
    Accounts,
    hash_password,
    password_matches,
)

ADA = {"email": "Ada@Example.org", "password": "correct horse", "displayName": "Ada"}


@pytest.fixture
def store(tmp_path):
    return WebStore(tmp_path / "w.db")


@pytest.fixture
def hub(store):
    return WebHub(store, "ws://127.0.0.1:9/")


def api(hub):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=create_web_app(hub)), base_url="http://t")


def auth(token):
    return {"Authorization": f"Bearer {token}"}


# ----------------------------------------------------------------------
# Accounts, without HTTP
# ----------------------------------------------------------------------


def test_passwords_are_salted_hashes_never_the_password(tmp_path, store):
    accounts = Accounts(store.connection)
    accounts.register("ada@example.org", "correct horse", "Ada")
    raw = sqlite3.connect(tmp_path / "w.db").execute("SELECT password_hash FROM web_user").fetchone()[0]
    assert raw.startswith("scrypt$") and "correct horse" not in raw
    assert hash_password("x") != hash_password("x")  # a new salt every time
    assert password_matches("correct horse", raw) and not password_matches("wrong", raw)
    assert not password_matches("x", "not-a-hash")


def test_register_checks_what_the_person_typed(store):
    accounts = Accounts(store.connection)
    for email, password, name in [("nope", "long enough", "Ada"), ("a@b.it", "short", "Ada"), ("a@b.it", "long enough", "  ")]:
        with pytest.raises(AccountError):
            accounts.register(email, password, name)
    accounts.register("a@b.it", "long enough", "Ada")
    with pytest.raises(AccountError, match="already exists"):
        accounts.register(" A@B.it ", "another one", "Ada 2")


def test_login_logout_and_expiry(store):
    now = [1000.0]
    accounts = Accounts(store.connection, clock=lambda: now[0])
    user, first = accounts.register("a@b.it", "long enough", "Ada")
    _, second = accounts.login("A@b.it", "long enough")
    assert accounts.user_by_token(first) == accounts.user_by_token(second) == user
    accounts.logout(first)
    assert accounts.user_by_token(first) is None and accounts.user_by_token(second) == user
    now[0] += LOGIN_SECONDS + 1
    assert accounts.user_by_token(second) is None


def test_wrong_passwords_lock_the_email_for_a_while(store):
    now = [1000.0]
    accounts = Accounts(store.connection, clock=lambda: now[0])
    accounts.register("a@b.it", "long enough", "Ada")
    for _ in range(MAX_FAILURES):
        with pytest.raises(AccountError, match="not correct"):
            accounts.login("a@b.it", "wrong")
    with pytest.raises(AccountError, match="Too many"):
        accounts.login("a@b.it", "long enough")  # even the right one, for now
    with pytest.raises(AccountError, match="not correct"):
        accounts.login("nobody@b.it", "wrong")  # same words as a wrong password
    now[0] += LOCK_SECONDS + 1
    assert accounts.login("a@b.it", "long enough")[0].display_name == "Ada"


def test_the_profile_is_cleaned_and_renames_the_members(store):
    accounts = Accounts(store.connection)
    user, _ = accounts.register("a@b.it", "long enough", "Ada")
    group = store.create_group("Team")
    member, _ = store.add_member(group.id, "Ada")
    accounts.claim_member(member.id, user.id)
    user = accounts.update_profile(user.id, display_name=" Ada  L. ", discipline="HCI", skills=["figma", " ", "ux "], weekly_hours=6)
    assert (user.display_name, user.skills, user.weekly_hours) == ("Ada L.", ["figma", "ux"], 6)
    assert store.member(member.id).display_name == "Ada L."
    assert accounts.spaces(user.id) == [{"id": group.id, "name": "Team", "inviteCode": group.invite_code}]
    assert user.profile_args()["discipline"] == "HCI"


# ----------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------


async def test_register_login_me_and_logout(hub):
    async with api(hub) as http:
        created = await http.post("/api/register", json=ADA)
        assert created.status_code == 200 and created.json()["user"]["email"] == "ada@example.org"
        assert (await http.post("/api/register", json=ADA)).status_code == 400
        assert (await http.post("/api/login", json={"email": ADA["email"], "password": "wrong one"})).status_code == 401

        token = (await http.post("/api/login", json={"email": ADA["email"], "password": ADA["password"]})).json()["accountToken"]
        me = (await http.get("/api/me", headers=auth(token))).json()
        assert me == {"user": {**me["user"], "displayName": "Ada"}, "spaces": []}

        saved = await http.put("/api/me", headers=auth(token), json={"displayName": "Ada L.", "discipline": "HCI", "skills": ["figma"], "weeklyHours": 6})
        assert saved.json()["user"]["weeklyHours"] == 6
        assert (await http.put("/api/me", headers=auth(token), json={"displayName": "Ada", "weeklyHours": 500})).status_code == 422

        await http.post("/api/logout", headers=auth(token))
        assert (await http.get("/api/me", headers=auth(token))).status_code == 401


async def test_a_logged_in_person_creates_joins_and_reopens_spaces_as_themselves(hub):
    async with api(hub) as http:
        ada = (await http.post("/api/register", json=ADA)).json()["accountToken"]
        bruno = (await http.post("/api/register", json={"email": "bruno@example.org", "password": "long enough", "displayName": "Bruno"})).json()["accountToken"]

        # No displayName needed: the account has it.
        space = (await http.post("/api/groups", headers=auth(ada), json={"groupName": "Team 17"})).json()
        joined = (await http.post("/api/join", headers=auth(bruno), json={"inviteCode": space["inviteCode"]})).json()
        who = (await http.get("/api/session", headers=auth(joined["token"]))).json()
        assert who["me"]["name"] == "Bruno"

        # Joining again (another browser) is the same member, with a new key.
        again = (await http.post("/api/join", headers=auth(bruno), json={"inviteCode": space["inviteCode"]})).json()
        assert again["memberId"] == joined["memberId"] and again["token"] != joined["token"]
        assert len(hub.store.members(1)) == 2

        # "My spaces" and opening one from the list.
        mine = (await http.get("/api/me", headers=auth(bruno))).json()["spaces"]
        assert [s["name"] for s in mine] == ["Team 17"]
        opened = (await http.post("/api/spaces/open", headers=auth(bruno), json={"groupId": mine[0]["id"]})).json()
        assert (await http.get("/api/session", headers=auth(opened["token"]))).json()["me"]["id"] == joined["memberId"]

        # Not your space, not logged in, guest without a name: refused.
        other = (await http.post("/api/groups", headers=auth(ada), json={"groupName": "Other"})).json()
        other_id = (await http.get("/api/session", headers=auth(other["token"]))).json()["group"]["id"]
        assert (await http.post("/api/spaces/open", headers=auth(bruno), json={"groupId": other_id})).status_code == 404
        assert (await http.post("/api/spaces/open", json={"groupId": 1})).status_code == 401
        assert (await http.post("/api/groups", json={"groupName": "Guests"})).status_code == 422


async def test_deleting_the_account_needs_the_password_and_keeps_the_space(hub):
    async with api(hub) as http:
        ada = (await http.post("/api/register", json=ADA)).json()["accountToken"]
        space = (await http.post("/api/groups", headers=auth(ada), json={"groupName": "Team"})).json()
        assert (await http.post("/api/me/delete", headers=auth(ada), json={"password": "wrong one"})).status_code == 401
        assert (await http.post("/api/me/delete", headers=auth(ada), json={"password": ADA["password"]})).json() == {"deleted": True}
        assert (await http.get("/api/me", headers=auth(ada))).status_code == 401
        # The space and its history stay for the rest of the group.
        assert (await http.get("/api/session", headers=auth(space["token"]))).status_code == 200
