"""
Adding Cadence where the group talks without bots, tokens or commands
(DECISIONS.md, 27/11): the install buttons, Slack's OAuth callback, one Slack
app in many workspaces, Cadence's greeting on a new Discord server and the
one-click voice offer. Fake Slack and Discord; the link test uses a real
local MUCA-Server.
"""

from __future__ import annotations

from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import discord
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mulca_discord.coordinator.easy_start import GUILD_WELCOME, VOICE_OFFER, VoiceOffer, greeting_channel
from mulca_discord.sessions import SessionRegistry
from mulca_discord.slack.__main__ import handle
from mulca_discord.slack.installs import Install, InstallStore
from mulca_discord.slack.workspaces import Workspaces
from mulca_discord.web.connect_routes import add_connect_routes, discord_install_url, make_state, state_ok
from tests.test_coordinator_discord import coordinator_server  # noqa: F401  (pytest fixture)
from tests.test_cross_channel import discord_side
from tests.test_easy_start import space
from tests.test_web import web  # noqa: F401  (pytest fixture)

SECRET = "test-secret"
ENV = {
    "DISCORD_CLIENT_ID": "123456",
    "SLACK_CLIENT_ID": "111.222",
    "SLACK_CLIENT_SECRET": SECRET,
    "CADENCE_PUBLIC_URL": "https://cadence.example",
}


def client(env, store=None, exchange=None) -> TestClient:
    app = FastAPI()
    add_connect_routes(app, env=env, store=store, exchange=exchange)
    return TestClient(app)


# -- the install buttons ------------------------------------------------------


def test_the_discord_button_asks_for_what_the_coordinator_and_voice_need():
    query = parse_qs(urlparse(discord_install_url("123456")).query)
    assert query["client_id"] == ["123456"]
    assert query["scope"] == ["bot applications.commands"]
    # view, send, embed, history, connect, speak, voice activity
    assert int(query["permissions"][0]) == 1024 + 2048 + 16384 + 65536 + 1048576 + 2097152 + 33554432


def test_the_discord_button_needs_only_the_bot_token_already_set():
    import base64

    token = base64.b64encode(b"1573774500464562309").decode().rstrip("=") + ".GxYz12.not-a-real-secret"
    from mulca_discord.web.connect_routes import discord_client_id

    assert discord_client_id({"DISCORD_BOT_TOKEN": token}) == "1573774500464562309"
    assert discord_client_id({"DISCORD_CLIENT_ID": "42", "DISCORD_BOT_TOKEN": token}) == "42"
    assert discord_client_id({"DISCORD_BOT_TOKEN": "garbage"}) == ""
    assert discord_client_id({}) == ""
    offered = client({"DISCORD_BOT_TOKEN": token}).get("/api/connect").json()
    assert "client_id=1573774500464562309" in offered["discord"] and "not-a-real-secret" not in offered["discord"]


def test_connect_offers_only_what_this_server_has():
    assert client({}).get("/api/connect").json() == {"discord": None, "slack": None}
    offered = client(ENV).get("/api/connect").json()
    assert offered["discord"].startswith("https://discord.com/oauth2/authorize?")
    assert offered["slack"] == "/api/slack/install"
    assert SECRET not in str(offered)


def test_slack_install_goes_to_slack_with_a_signed_state():
    answer = client(ENV).get("/api/slack/install", follow_redirects=False)
    assert answer.status_code == 302
    target = urlparse(answer.headers["location"])
    query = parse_qs(target.query)
    assert target.netloc == "slack.com" and query["client_id"] == ["111.222"]
    assert query["redirect_uri"] == ["https://cadence.example/api/slack/oauth"]
    assert state_ok(SECRET, query["state"][0])
    assert client({}).get("/api/slack/install").status_code == 404


def test_the_state_is_signed_and_expires():
    state = make_state(SECRET, now=1000)
    assert state_ok(SECRET, state, now=1100)
    assert not state_ok(SECRET, state, now=1000 + 601)
    assert not state_ok("another secret", state, now=1100)
    assert not state_ok(SECRET, state[:-1] + ("0" if state[-1] != "0" else "1"), now=1100)
    assert not state_ok(SECRET, "garbage", now=1100)


def test_slack_sends_the_member_back_and_the_token_is_saved(tmp_path):
    store = InstallStore(tmp_path / "slack.sqlite3")
    asked = []

    async def exchange(code, redirect_uri):
        asked.append((code, redirect_uri))
        return {"ok": True, "access_token": "xoxb-secret", "bot_user_id": "UBOT", "team": {"id": "T1", "name": "Group 17"}}

    page = client(ENV, store, exchange).get("/api/slack/oauth", params={"code": "c0de", "state": make_state(SECRET)})
    assert page.status_code == 200
    assert "Group 17" in page.text and "/invite @Cadence" in page.text
    assert "xoxb-secret" not in page.text  # the token never reaches the browser
    assert asked == [("c0de", "https://cadence.example/api/slack/oauth")]
    assert store.all() == [Install("T1", "Group 17", "xoxb-secret", "UBOT")]


def test_a_refused_forged_or_failed_install_saves_nothing(tmp_path):
    store = InstallStore(tmp_path / "slack.sqlite3")

    async def refused(code, redirect_uri):
        return {"ok": False, "error": "invalid_code"}

    web = client(ENV, store, refused)
    assert "Nothing was added" in web.get("/api/slack/oauth", params={"error": "access_denied"}).text
    assert web.get("/api/slack/oauth", params={"code": "c", "state": "forged.1.x"}).status_code == 400
    assert web.get("/api/slack/oauth", params={"code": "c", "state": make_state(SECRET)}).status_code == 502
    assert store.all() == []


# -- one Slack app, many workspaces ------------------------------------------


class FakeWebClient:
    """slack_sdk's AsyncWebClient for one workspace."""

    def __init__(self, token, teams, posted):
        self.token = token
        self.team, self.bot, self.channels = teams[token]
        self.posted = posted

    async def auth_test(self):
        return {"user_id": self.bot, "team_id": self.team}

    async def chat_postMessage(self, channel, text, blocks=None, unfurl_links=False):
        self.posted.append((self.team, channel, text))
        return {"ts": "1.0"}

    async def users_conversations(self, **_):
        return {"channels": [{"id": c} for c in self.channels]}


def workspaces(tmp_path):
    teams = {"xoxb-a": ("TA", "UBOTA", ["CA1"]), "xoxb-b": ("TB", "UBOTB", ["CB1", "CB2"])}
    posted = []
    store = InstallStore(tmp_path / "slack.sqlite3")
    store.save(Install("TA", "A", "xoxb-a", "UBOTA"))
    store.save(Install("TB", "B", "xoxb-b", "UBOTB"))
    return Workspaces(lambda token: FakeWebClient(token, teams, posted), store), store, posted


async def test_each_channel_is_answered_with_its_workspace_token(tmp_path):
    api, store, posted = workspaces(tmp_path)
    await api.reload()
    assert sorted(api.teams) == ["TA", "TB"]
    await api.post("CB2", "hello")  # unknown yet: found by listing the channels
    api.learn("CX", "TA")  # a request from workspace A named this channel
    await api.post("CX", "hi")
    assert posted == [("TB", "CB2", "hello"), ("TA", "CX", "hi")]
    assert api.is_me("UBOTA") and api.is_me("UBOTB") and not api.is_me("U123")


async def test_a_workspace_added_from_the_web_is_picked_up(tmp_path):
    api, store, posted = workspaces(tmp_path)
    store.remove("TB")
    await api.reload()
    assert api.teams == ["TA"]
    store.save(Install("TB", "B", "xoxb-b", "UBOTB"))  # "Add to Slack" in the other process
    await api.post("CB1", "welcome")
    assert posted[-1] == ("TB", "CB1", "welcome")


async def test_removing_the_app_deletes_the_workspace_token(tmp_path):
    api, store, _ = workspaces(tmp_path)
    await api.reload()
    hub = SimpleNamespace()
    await handle(hub, api, "events_api", {"team_id": "TB", "event": {"type": "app_uninstalled"}})
    assert api.teams == ["TA"]
    assert [i.team_id for i in store.all()] == ["TA"]


# -- Discord: greeting and one-click voice ------------------------------------


class Place:
    def __init__(self, can_write, name="general"):
        self.id = id(self)
        self.name = name
        self.can_write = can_write
        self.sent = []

    def permissions_for(self, member):
        return SimpleNamespace(send_messages=self.can_write)

    async def send(self, text, **kwargs):
        self.sent.append((text, kwargs))


async def test_cadence_greets_a_new_server_where_it_may_write():
    blocked, open_ = Place(False), Place(True)
    guild = SimpleNamespace(me=object(), system_channel=blocked, text_channels=[blocked, open_])
    assert greeting_channel(guild) is open_
    assert greeting_channel(SimpleNamespace(me=object(), system_channel=None, text_channels=[blocked])) is None
    bridge, bot, _, _ = discord_side("ws://unused")
    await bridge.greet_guild(guild)
    assert open_.sent[0][0] == GUILD_WELCOME and blocked.sent == []


async def test_a_pasted_link_offers_voice_with_one_click(web, coordinator_server):  # noqa: F811
    _, http, ws_url = web
    made, tab = await space(http, ws_url)
    bridge, bot, _, channel = discord_side(coordinator_server)
    sent = []

    async def send(text, **kwargs):
        sent.append((text, kwargs))

    call = SimpleNamespace(id=77, name="Study room", mention="#Study room")
    try:
        message = SimpleNamespace(
            content=f"https://cadence-coordinator.onrender.com/join/{made['inviteCode']}",
            guild=SimpleNamespace(id=1, voice_channels=[call]),
            channel=SimpleNamespace(id=42, send=send),
            author=SimpleNamespace(id=9001),
        )
        assert await bridge.invite(message)
        text, kwargs = sent[-1]
        assert "Linked to the web space" in text and VOICE_OFFER in text
        view = kwargs["view"]
        assert isinstance(view, VoiceOffer)
        (button,) = view.children
        assert isinstance(button, discord.ui.Button) and "Study room" in button.label
    finally:
        await tab.ws.close()
        await bot.registry.close_all()
        SessionRegistry.on_coordinator_event = None


async def test_several_voice_channels_give_a_menu_and_a_click_tells_the_channel():
    calls = [SimpleNamespace(id=1, name="A"), SimpleNamespace(id=2, name="B")]
    served = []

    async def serve_voice(interaction, voice):
        served.append(voice)
        return "Cadence now listens to #A: it joins when someone is there."

    view = VoiceOffer(SimpleNamespace(serve_voice=serve_voice), calls)
    (menu,) = view.children
    assert isinstance(menu, discord.ui.ChannelSelect)

    said, edits = [], []

    async def record(*args, **kwargs):
        said.append(args[0] if args else "deferred")

    async def edit(**kwargs):
        edits.append(kwargs)

    interaction = SimpleNamespace(
        user=SimpleNamespace(display_name="Ada"),
        response=SimpleNamespace(defer=record),
        followup=SimpleNamespace(send=record),
        message=SimpleNamespace(edit=edit),
    )
    await view.turn_on(interaction, calls[0])
    assert served == [calls[0]]
    assert said[-1].startswith("Cadence now listens")
    assert edits and edits[0]["view"] is None and "turned on by Ada" in edits[0]["content"]
