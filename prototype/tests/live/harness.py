"""
The cross-channel end-to-end harness: one project on the web, Discord and Slack.

Every test builds a Group: a web space (the real web adapter, members talking
through its WebSocket like the browser does), a Discord channel (the real
CoordinatorBridge) and a Slack channel (the real SlackHub), all on one
MUCA-Server. What is real depends on the environment (LIVE_TESTS.md):

    CADENCE_MUCA_URL                 a running MUCA-Server (real model, e.g. Azure);
                                     unset: one in this process, with the SCRIPTED
                                     model of webapp/e2e/fake_stack.py
    SLACK_BOT_TOKEN +
    CADENCE_TEST_SLACK_CHANNEL       Cadence's posts go to that real Slack channel
    DISCORD_BOT_TOKEN +
    CADENCE_TEST_DISCORD_CHANNEL     Cadence's posts go to that real Discord channel

Members are simulated in every mode: a test cannot write on Discord as a person
nor press a Slack button through the APIs, so the harness calls the bot's code
where the platform's event would arrive (SlackHub.on_message / on_action /
on_command, CoordinatorBridge.click / send_command). Everything from there on
is the code that runs live; what Cadence posts is recorded here (and sent for
real when the tokens are set), so the assertions are the same in every mode.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import os
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
import uvicorn

from mulca_discord.coordinator.bridge import CoordinatorBridge, scope_for
from mulca_discord.coordinator.cards import CUSTOM_ID_PATTERN, CardButton
from mulca_discord.sessions import SessionRegistry
from mulca_discord.slack import SlackHub
from mulca_discord.web import WebHub, WebStore, create_web_app
from tests.test_muca_client import free_port
from tests.test_web import Tab as _Tab

E2E = Path(__file__).resolve().parents[2] / "webapp" / "e2e"
if str(E2E) not in sys.path:
    sys.path.insert(0, str(E2E))  # the offline demo server (three_channels_stack.py)

MUCA_URL = os.environ.get("CADENCE_MUCA_URL", "")
# The in-process server, with the REAL model for everything Cadence writes (cards,
# plan, ask, check-in; AZURE_OPENAI_* or OPENAI_API_KEY). The Realtime agents stay
# scripted: which strategy fires is the scripted judge's (TRIGGERS), the card is the model's.
LIVE_MODEL = not MUCA_URL and os.environ.get("CADENCE_LIVE_MODEL", "") in ("1", "true", "yes")
SLACK_CHANNEL = os.environ.get("CADENCE_TEST_SLACK_CHANNEL", "") if os.environ.get("SLACK_BOT_TOKEN") else ""
DISCORD_CHANNEL = os.environ.get("CADENCE_TEST_DISCORD_CHANNEL", "") if os.environ.get("DISCORD_BOT_TOKEN") else ""
# A real model takes seconds per card; the scripted one milliseconds.
TIMEOUT = float(os.environ.get("CADENCE_LIVE_TIMEOUT", "120" if MUCA_URL or LIVE_MODEL else "10"))
SCRIPTED = not MUCA_URL and not LIVE_MODEL  # every word Cadence writes is a fixed text
SCRIPTED_JUDGE = not MUCA_URL  # a scripted phrase fires a strategy (no chat log is kept either)

DISCORD_MEMBERS = {9001: "Ada", 9002: "Bruno", 9003: "Chiara"}
SLACK_MEMBERS = {"U0ADA0001": "Ada", "U0BRUNO02": "Bruno", "U0DARIO03": "Dario"}
SLACK_BOT = "U0CADENCE"
_ids = itertools.count(1)


def mode() -> str:
    """One line for the test report: what is real in this run."""
    return ", ".join([
        f"server {'at ' + MUCA_URL if MUCA_URL else 'in process, ' + ('REAL model for the coordinator' if LIVE_MODEL else 'scripted model')}",
        f"Slack {'real #' + SLACK_CHANNEL if SLACK_CHANNEL else 'recorded'}",
        f"Discord {'real #' + DISCORD_CHANNEL if DISCORD_CHANNEL else 'recorded'}",
    ])


async def until(check, timeout: float = TIMEOUT, what: str = "") -> None:
    """Wait for something that arrives a moment later; the message says what never came."""
    try:
        async with asyncio.timeout(timeout):
            while not check():
                await asyncio.sleep(0.05)
    except TimeoutError:
        raise AssertionError(f"waited {timeout:.0f} s for: {what or check}") from None


class Tab(_Tab):
    """A browser tab that keeps reading its socket, so `seen` is always up to date."""

    @classmethod
    async def open(cls, url: str, token: str) -> "Tab":
        tab = await super().open(url, token)
        tab.reader = asyncio.create_task(tab._read())
        return tab

    async def _read(self) -> None:
        import json

        try:
            async for raw in self.ws:
                self.seen.append(json.loads(raw))
        except Exception:
            pass  # the socket closed

    async def wait_for(self, check, timeout: float = TIMEOUT) -> dict:
        await until(lambda: any(check(e) for e in self.seen), timeout, "a frame on the web tab")
        return next(e for e in self.seen if check(e))


# ----------------------------------------------------------------------
# The server and the web adapter
# ----------------------------------------------------------------------


class Stack:
    """MUCA-Server (here or at CADENCE_MUCA_URL) and the web adapter in front of it."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.muca_url = MUCA_URL
        self.servers: list[uvicorn.Server] = []
        self.tasks: list[asyncio.Task] = []

    async def start(self) -> "Stack":
        if not self.muca_url:
            self.muca_url = await self._serve(_scripted_server(self.tmp))
        self.hub = WebHub(WebStore(self.tmp / "web.sqlite3"), self.muca_url)
        base = await self._serve(create_web_app(self.hub))
        self.http = base.replace("ws://", "http://").rstrip("/")
        self.ws = self.http.replace("http://", "ws://") + "/ws"
        return self

    async def _serve(self, app) -> str:
        port = free_port()
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
        self.servers.append(server)
        self.tasks.append(asyncio.create_task(server.serve()))
        while not server.started:
            await asyncio.sleep(0.01)
        return f"ws://127.0.0.1:{port}/"

    async def stop(self) -> None:
        await self.hub.close()
        for server in self.servers:
            server.should_exit = True
        await asyncio.gather(*self.tasks, return_exceptions=True)


def _scripted_server(tmp: Path):
    """The offline MUCA-Server of the demo (webapp/e2e/three_channels_stack.py): real code, SCRIPTED model."""
    import three_channels_stack as demo  # noqa: E402  (scripted CS5 on "printed", CS3 on "think-aloud", CS2 on "font")
    from muca_server import create_app
    from muca_server.cognition.coordination.settings import CoordinatorSettings
    from muca_server.cognition.coordination.wiring import build_coordinator_factory
    from muca_server.sessions import DefaultSessionComponentsFactory
    from tests.test_muca_client import Factory

    if LIVE_MODEL:
        from muca_server.agents.openai.client_config import build_openai_client

        settings = CoordinatorSettings.from_env({**os.environ, "MUCA_COORDINATOR_ENABLED": "true"})
        client = build_openai_client()
    else:
        settings, client = CoordinatorSettings(enabled=True), demo.fake_stack.ScriptedModel()
    return create_app(
        components_factory=DefaultSessionComponentsFactory(
            agent_factory=Factory(),
            policy_factory=lambda context: demo.QuietPolicy(),
            coordinator_factory=build_coordinator_factory(settings, client=client, db_dir=str(tmp)),
        ),
        db_dir=tmp,
    )


# ----------------------------------------------------------------------
# Discord: what the bot posts, recorded (and sent to a real channel if set)
# ----------------------------------------------------------------------


class Posted:
    """One message Cadence posted on Discord: its text or its card, as last edited."""

    def __init__(self, channel: "DiscordChannel", content: str, embed, view) -> None:
        self.channel = channel
        self.content = content or ""
        self.real = None
        self._draw(embed, view)

    def _draw(self, embed, view) -> None:
        self.embed = embed.to_dict() if embed is not None else None
        self.buttons = [
            {"label": child.item.label, "custom_id": child.item.custom_id}
            for child in getattr(view, "children", [])
        ]

    @property
    def footer(self) -> str:
        return ((self.embed or {}).get("footer") or {}).get("text", "")

    @property
    def fields(self) -> dict[str, str]:
        return {f["name"]: f["value"] for f in (self.embed or {}).get("fields", [])}

    async def edit(self, *, embed=None, view=None, **_) -> None:
        self._draw(embed, view)
        if self.real is not None:
            await self.real.edit(embed=embed, view=view)


class DiscordChannel:
    def __init__(self, channel_id: int, real=None) -> None:
        self.id = channel_id
        self.real = real
        self.posts: list[Posted] = []

    async def send(self, content=None, *, embed=None, view=None, allowed_mentions=None, **_):
        posted = Posted(self, content, embed, view)
        self.posts.append(posted)
        if self.real is not None:
            import discord

            kwargs = {"allowed_mentions": allowed_mentions or discord.AllowedMentions.none()}
            if embed is not None:
                kwargs["embed"] = embed
            if view is not None and view is not discord.utils.MISSING:
                kwargs["view"] = view
            posted.real = await self.real.send(content, **kwargs)
        return posted

    def typing(self):
        return contextlib.nullcontext()  # nothing to show while Cadence writes

    @property
    def lines(self) -> list[str]:
        return [p.content for p in self.posts if p.embed is None]

    @property
    def cards(self) -> list[Posted]:
        return [p for p in self.posts if p.embed is not None]


# ----------------------------------------------------------------------
# Slack: SlackApi recorded (and sent to a real channel if set)
# ----------------------------------------------------------------------


class SlackRecorder:
    """The SlackApi the hub uses. Members are the simulated ones even on a real channel."""

    bot_user = SLACK_BOT

    def __init__(self, channel: str, real=None, real_channel: str = "") -> None:
        self.channel = channel
        self.real = real  # slack/api.py SdkSlackApi, or None
        self.real_channel = real_channel  # where `real` posts
        self.posts: list[dict] = []
        self.private: list[tuple[str, str]] = []
        self._real_ts: dict[str, str] = {}

    async def post(self, channel, text, blocks=None) -> str:
        self.posts.append({"text": text, "blocks": blocks})
        ts = str(len(self.posts))
        if self.real is not None:
            self._real_ts[ts] = await self.real.post(self.real_channel, text, blocks)
        return ts

    async def update(self, channel, ts, text, blocks=None) -> None:
        self.posts[int(ts) - 1].update(text=text, blocks=blocks)
        if self.real is not None and ts in self._real_ts:
            await self.real.update(self.real_channel, self._real_ts[ts], text, blocks)

    async def ephemeral(self, channel, user, text) -> None:
        self.private.append((user, text))  # simulated members have no real account to see it

    async def roster(self, channel) -> dict[str, str]:
        return dict(SLACK_MEMBERS)

    async def channels(self) -> list[str]:
        return [self.channel]

    @property
    def lines(self) -> list[str]:
        return [p["text"] for p in self.posts if not p["blocks"]]

    @property
    def cards(self) -> list[dict]:
        return [p for p in self.posts if p["blocks"]]


def slack_status(card: dict) -> str:
    """The status line under a Slack card (its context block)."""
    return next((b["elements"][0]["text"] for b in reversed(card["blocks"]) if b["type"] == "context"), "")


def slack_buttons(card: dict) -> list[str]:
    return [e["action_id"] for b in card["blocks"] if b["type"] == "actions" for e in b["elements"]]


def slack_text(card: dict) -> str:
    return "\n".join(b["text"]["text"] for b in card["blocks"] if b["type"] == "section")


# ----------------------------------------------------------------------
# A group: one web space with its Discord and Slack channels
# ----------------------------------------------------------------------


class Group:
    def __init__(self, stack: Stack) -> None:
        self.stack = stack
        self.tabs: dict[str, Tab] = {}
        self.web_ids: dict[str, int] = {}
        self.code = ""
        self.discords: list[tuple[SimpleNamespace, SimpleNamespace, DiscordChannel]] = []
        self.bridge: CoordinatorBridge | None = None
        self.slack: SlackRecorder | None = None
        self.hub: SlackHub | None = None
        self._discord_client = None

    # -- web --------------------------------------------------------------

    async def web_member(self, name: str) -> Tab:
        """A member on the web: the first one creates the space, the others join with its code."""
        async with httpx.AsyncClient(base_url=self.stack.http) as api:
            if not self.code:
                made = (await api.post("/api/groups", json={"groupName": f"Group {uuid.uuid4().hex[:6]}", "displayName": name})).json()
                self.code = made["inviteCode"]
            else:
                made = (await api.post("/api/join", json={"inviteCode": self.code, "displayName": name})).json()
        tab = await Tab.open(self.stack.ws, made["token"])
        self.tabs[name] = tab
        self.web_ids[name] = tab.seen[0]["me"]["id"]
        await self.web_command(name, "state")  # the space has a project file on the server now
        return tab

    async def web_say(self, who: str, text: str) -> None:
        await self.tabs[who].send(type="message", text=text)

    async def _request(self, who: str, **frame) -> dict:
        """A command or a click from the web tab, and the answer meant for it."""
        request = uuid.uuid4().hex[:16]
        await self.tabs[who].send(**frame, requestId=request)
        reply = await self.tabs[who].wait_for(lambda e: e.get("type") == "reply" and e.get("requestId") == request)
        return reply["answer"]

    async def web_command(self, who: str, command: str, **args) -> dict:
        return await self._request(who, type="command", command=command, args=args)

    async def web_click(self, who: str, proposal_id: str, action: str, option: int | None = None) -> dict:
        extra = {} if option is None else {"option": option}
        return await self._request(who, type="click", proposalId=proposal_id, action=action, **extra)

    async def web_card(self, who: str, check=lambda p: True) -> dict:
        """The newest card this member's tab got that passes `check` (waits for it)."""
        tab = self.tabs[who]
        await tab.wait_for(lambda e: e.get("type") == "proposal" and check(e["proposal"]))
        return [e["proposal"] for e in tab.seen if e.get("type") == "proposal" and check(e["proposal"])][-1]

    def web_messages(self, who: str) -> list[dict]:
        return [e["message"] for e in self.tabs[who].seen if e.get("type") == "message"]

    async def web_state(self, who: str) -> dict:
        return (await self.web_command(who, "state"))["state"]

    # -- Discord ----------------------------------------------------------

    async def discord(self, *, members: dict[int, str] | None = None, channel_id: int | None = None) -> DiscordChannel:
        """A Discord text channel served by the bot (a second call: a second channel of the same bot)."""
        roster = dict(members or DISCORD_MEMBERS)
        channel_id = channel_id or 4200 + next(_ids)
        real = None
        if DISCORD_CHANNEL and not self.discords:
            real = await self._real_discord_channel()
        channel = DiscordChannel(channel_id, real)
        link = SimpleNamespace(
            conversation_id=f"channel:{channel_id}", listening_mode="", guild_id=1, text_channel_id=channel_id,
        )
        bot = SimpleNamespace(
            name="Cadence", registry=SessionRegistry(self.stack.muca_url), roster_text=lambda link: dict(roster),
            _channel_name_for=lambda link: "presentation", course_for=lambda guild_id: "aui", paused=False,
            links=lambda: [link], user_id=1,
            client=SimpleNamespace(get_channel=lambda cid: self._channel(cid), add_dynamic_items=lambda *items: None),
        )
        self.discords.append((bot, link, channel))
        if self.bridge is None:
            self.bridge = CoordinatorBridge(SimpleNamespace(
                bots=[b for b, _, _ in self.discords], primary=bot, link_for_channel=self._link_for,
            ))
            self.bridge.attach()
        return channel

    def _channel(self, channel_id: int):
        return next((c for _, _, c in self.discords if c.id == channel_id), None)

    def _link_for(self, channel_id: int):
        return next(((b, link) for b, link, c in self.discords if c.id == channel_id), None)

    def _discord(self, channel: DiscordChannel | None = None):
        if channel is None:
            return self.discords[0]
        return next(d for d in self.discords if d[2] is channel)

    async def _real_discord_channel(self):
        import discord

        self._discord_client = discord.Client(intents=discord.Intents.none())
        await self._discord_client.login(os.environ["DISCORD_BOT_TOKEN"])
        return await self._discord_client.fetch_channel(int(DISCORD_CHANNEL))

    @staticmethod
    def _discord_id(who: str | int) -> int:
        return who if isinstance(who, int) else next(i for i, n in DISCORD_MEMBERS.items() if n == who)

    def discord_member(self, who: str | int, channel: DiscordChannel | None = None):
        """The interaction of a member: what a slash command or a button press gives the bridge."""
        chan = self._discord(channel)[2]
        member_id = self._discord_id(who)
        said: list[str] = []

        async def record(*args, **kwargs):
            if args:
                said.append(args[0])

        return SimpleNamespace(
            channel_id=chan.id, channel=chan, guild_id=1, user=SimpleNamespace(id=member_id),
            response=SimpleNamespace(defer=record, send_message=record),
            followup=SimpleNamespace(send=record), said=said,
        )

    async def discord_say(self, who: str | int, text: str, channel: DiscordChannel | None = None) -> None:
        """A member writes in the channel: what runtime.py does with the message."""
        bot, link, chan = self._discord(channel)
        member_id = self._discord_id(who)
        name = bot.roster_text(link)[member_id]
        message = SimpleNamespace(content=text, guild=SimpleNamespace(id=1), channel=chan, author=SimpleNamespace(id=member_id))
        if await self.bridge.invite(message):
            return
        if await self.bridge.chat(chan, member_id, text):
            return

        async def action(client) -> None:
            await client.send_participants(bot.roster_text(link), modality="text")
            await client.send_user_text(
                speaker=member_id, speaker_name=name, text=text, mentions_assistant=False,
                **({"offered_to_ask": True} if self.bridge.offered(text) else {}),
            )

        await bot.registry.run(scope_for(bot, link), action, reply_channel=chan)

    async def discord_command(self, who: str, command: str, channel: DiscordChannel | None = None, **args) -> dict | None:
        return await self.bridge.send_command(self.discord_member(who, channel), command, args)

    async def discord_click(self, who: str, card: Posted, action: str, channel: DiscordChannel | None = None) -> str:
        """Press a button of a card on Discord (the real CardButton.callback); returns what the member is told."""
        import re

        found = next(m for b in card.buttons if (m := re.fullmatch(CUSTOM_ID_PATTERN, b["custom_id"])) and m["action"] == action)
        member = self.discord_member(who, channel)
        CardButton.bridge = self.bridge
        await CardButton(found["action"], found["proposal_id"]).callback(member)
        return member.said[-1] if member.said else ""

    # -- Slack ------------------------------------------------------------

    async def slack_channel(self) -> SlackRecorder:
        real = None
        if SLACK_CHANNEL:
            from slack_sdk.web.async_client import AsyncWebClient

            from mulca_discord.slack.api import SdkSlackApi

            real = SdkSlackApi(AsyncWebClient(token=os.environ["SLACK_BOT_TOKEN"]))
        self.slack = SlackRecorder("C" + uuid.uuid4().hex[:8].upper(), real, SLACK_CHANNEL)
        self.hub = SlackHub(self.slack, self.stack.muca_url)
        return self.slack

    def slack_user(self, who: str) -> str:
        return next(u for u, n in SLACK_MEMBERS.items() if n == who)

    async def slack_say(self, who: str, text: str) -> None:
        await self.hub.on_message({"type": "message", "channel": self.slack.channel, "user": self.slack_user(who), "text": text})

    async def slack_command(self, who: str, text: str) -> str:
        return await self.hub.on_command(self.slack.channel, self.slack_user(who), text)

    async def slack_click(self, who: str, card: dict, action: str) -> str:
        action_id = next(a for a in slack_buttons(card) if a.split(":")[1] == action)
        return await self.hub.on_action(self.slack.channel, self.slack_user(who), action_id, str(self.slack.posts.index(card) + 1))

    # -- everything at once -----------------------------------------------

    async def linked(self, *, web: tuple[str, ...] = ("Ada", "Bruno")) -> "Group":
        """The usual start: a web space, its Discord and Slack channels linked by pasting the invite link."""
        for name in web:
            await self.web_member(name)
        await self.discord()
        await self.slack_channel()
        link = f"{self.stack.http}/join/{self.code}"
        await asyncio.gather(self.discord_say("Ada", link), self.slack_say("Bruno", link))
        await until(lambda: any("Linked to the web space" in line for line in self.discords[0][2].lines), what="Discord linked")
        await until(lambda: any("Linked to the web space" in line for line in self.slack.lines), what="Slack linked")
        return self

    async def same_person_everywhere(self, *names: str) -> None:
        """/coordinator me with a code from the web, on Discord and on Slack, for each name."""
        for name in names:
            if name in DISCORD_MEMBERS.values():
                code = await self._personal_code(name)
                assert (await self.discord_command(name, "me", code=code))["ok"]
            if name in SLACK_MEMBERS.values():
                code = await self._personal_code(name)
                assert "Done" in await self.slack_command(name, f"me {code}")

    async def _personal_code(self, name: str) -> str:
        answer = await self.web_command(name, "me")
        return answer["text"].split("Your personal code is ")[1].split(".")[0]

    async def close(self) -> None:
        for tab in self.tabs.values():
            await tab.ws.close()
            tab.reader.cancel()
        for bot, _, _ in self.discords:
            await bot.registry.close_all()
        if self.hub is not None:
            await self.hub.close()
        if self._discord_client is not None:
            await self._discord_client.close()
        SessionRegistry.on_coordinator_event = None
        CardButton.bridge = None


def stamp() -> str:
    """A short unique tag, so a line can be found among everything a real channel holds."""
    return time.strftime("%H%M%S") + uuid.uuid4().hex[:4]
