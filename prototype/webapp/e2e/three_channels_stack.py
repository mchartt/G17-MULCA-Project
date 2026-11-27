"""
The demo video's flow, offline: one project on the web, Discord and Slack.

Starts the offline stack (fake_stack.py: the real MUCA-Server with the
coordinator on and a SCRIPTED model, the real web adapter serving the built
app) and, in the same process, the real Discord bridge and the real Slack hub
talking to it, with a fake Discord channel and a fake Slack that record
exactly what the bot would post (embeds, buttons, Block Kit). A small control
API lets a browser script act as Discord and Slack members:

    POST /discord/say   {"who": "Ada", "text": "..."}    a message in #presentation
    POST /slack/say     {"who": "Bruno", "text": "..."}  a message in #school-talk
    POST /discord/click {"action": "confirm"}            a button on the last card
    POST /discord/me    {"who": "Ada", "code": "..."}    /coordinator me <code>
    POST /slack/me      {"who": "Bruno", "code": "..."}
    GET  /payloads                                       what Discord and Slack show

What is fake: the model (scripted drafts), the intervention agent (a scripted
phrase fires a strategy: "printed" -> CS5 owner and date), Discord and Slack
themselves. Everything else is the code that runs live.

    cd prototype && python webapp/e2e/three_channels_stack.py   # web on :8190, control on :8192
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

E2E = Path(__file__).resolve().parent
sys.path.insert(0, str(E2E))
import fake_stack  # noqa: E402  (also puts the prototype on sys.path)

import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from muca_server import create_app  # noqa: E402
from muca_server.cognition.coordination.settings import CoordinatorSettings  # noqa: E402
from muca_server.cognition.coordination.wiring import build_coordinator_factory  # noqa: E402
from muca_server.sessions import DefaultSessionComponentsFactory  # noqa: E402

from mulca_discord.coordinator.bridge import CoordinatorBridge, scope_for  # noqa: E402
from mulca_discord.coordinator.cards import split_action  # noqa: E402
from mulca_discord.sessions import SessionRegistry  # noqa: E402
from mulca_discord.slack import SlackHub  # noqa: E402
from mulca_discord.web import WebHub, WebStore, create_web_app  # noqa: E402
from tests.test_muca_client import Factory  # noqa: E402

MUCA_PORT, WEB_PORT, CONTROL_PORT = 8191, 8190, 8192
DISCORD = {9001: "Ada", 9002: "Bruno", 9003: "Chiara"}
SLACK = {"U0ADA0001": "Ada", "U0BRUNO02": "Bruno"}
BOT = "U0CADENCE"

# CS5, SCRIPTED: "printed" in a message -> an owner-and-date card for the survey printout.
fake_stack.TRIGGERS["printed"] = "cs5_owner_and_date"
_scripted = fake_stack.scripted


def scripted(name: str, user: str) -> dict:
    if name != "owner_and_date":
        return _scripted(name, user)
    members = dict((int(i), n) for i, n in re.findall(r"- id (\d+): ([^\n(|]+)", user))
    ada = next((i for i, n in members.items() if n.strip().startswith("Ada")), None)
    lines = user.split("<chat>")[1].count("\n[")
    return {
        "task_id": None,
        "title": "Print the survey results",
        "owner_id": ada,
        "due_date": "2026-11-28",
        "topic": "Printing the survey results",
        "evidence": list(range(max(1, lines - 1), lines + 1)),
        "rationale": "Printing the survey results came up, but nobody took it.",
    }


fake_stack.scripted = scripted


class QuietPolicy(fake_stack.FakePolicy):
    """SCRIPTED: like the real judge most of the time, Cadence says nothing unless a strategy fires."""

    async def on_utterance(self, utterance) -> bool:
        if any(phrase in utterance.content.lower() for phrase in fake_stack.TRIGGERS):
            return await super().on_utterance(utterance)
        self._history.append(utterance)
        await self._port.no_reply()
        return False


class DiscordChannel:
    """#presentation, recording every message and card as Discord would show it."""

    id = 42

    def __init__(self) -> None:
        self.items: list[dict] = []

    async def send(self, content=None, *, embed=None, view=None, allowed_mentions=None, **_):
        item = {"kind": "card" if embed is not None else "text", "who": "Cadence", "text": content or "", "at": time.time()}
        if embed is not None:
            item.update(embed=embed.to_dict(), buttons=_buttons(view))
        self.items.append(item)
        channel = self

        class Sent:
            async def edit(self, *, embed, view):
                item.update(embed=embed.to_dict(), buttons=_buttons(view))

        return Sent()

    def typing(self):
        class Typing:
            async def __aenter__(self):
                return None

            async def __aexit__(self, *exc):
                return False

        return Typing()


def _buttons(view) -> list[dict]:
    if view is None or not hasattr(view, "children"):
        return []
    return [
        {"label": child.item.label, "style": child.item.style.name, "custom_id": child.item.custom_id, "row": child.item.row}
        for child in view.children
    ]


class FakeSlack:
    bot_user = BOT

    def __init__(self) -> None:
        self.posts: list[dict] = []

    async def post(self, channel, text, blocks=None) -> str:
        self.posts.append({"who": "Cadence", "text": text, "blocks": blocks, "at": time.time()})
        return str(len(self.posts))

    async def update(self, channel, ts, text, blocks=None) -> None:
        self.posts[int(ts) - 1].update(text=text, blocks=blocks)

    async def ephemeral(self, channel, user, text) -> None:
        pass

    async def roster(self, channel) -> dict[str, str]:
        return dict(SLACK)

    async def channels(self) -> list[str]:
        return ["C1"]


async def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="cadence-3ch-"))
    muca = create_app(
        components_factory=DefaultSessionComponentsFactory(
            agent_factory=Factory(),
            policy_factory=lambda context: QuietPolicy(),
            coordinator_factory=build_coordinator_factory(
                CoordinatorSettings(enabled=True), client=fake_stack.ScriptedModel(), db_dir=str(tmp)
            ),
        ),
        db_dir=tmp,
    )
    muca_url = f"ws://127.0.0.1:{MUCA_PORT}/"
    hub = WebHub(WebStore(tmp / "web.sqlite3"), muca_url)
    web = create_web_app(hub, static_dir=E2E.parent / "dist", film_dir=E2E.parent / "film" / "public")

    # Discord: the real bridge, one linked text channel, a fake channel.
    channel = DiscordChannel()
    link = SimpleNamespace(conversation_id="channel:42", listening_mode="", guild_id=1, text_channel_id=42)
    bot = SimpleNamespace(
        name="Cadence", registry=SessionRegistry(muca_url), roster_text=lambda link: dict(DISCORD),
        _channel_name_for=lambda link: "presentation", course_for=lambda guild_id: "aui", paused=False,
        links=lambda: [link],
        client=SimpleNamespace(get_channel=lambda channel_id: channel, add_dynamic_items=lambda *items: None),
    )
    bridge = CoordinatorBridge(SimpleNamespace(bots=[bot], primary=bot, link_for_channel=lambda channel_id: (bot, link)))
    bridge.attach()
    slack = FakeSlack()
    slack_hub = SlackHub(slack, muca_url)

    def member(user_id: int):
        said: list[str] = []

        async def record(*args, **kwargs):
            if args:
                said.append(args[0])

        return SimpleNamespace(
            channel_id=42, channel=channel, guild_id=1, user=SimpleNamespace(id=user_id),
            response=SimpleNamespace(defer=record), followup=SimpleNamespace(send=record), said=said,
        )

    def discord_id(who: str) -> int:
        return next(i for i, n in DISCORD.items() if n == who)

    def slack_id(who: str) -> str:
        return next(i for i, n in SLACK.items() if n == who)

    control = FastAPI()

    @control.post("/discord/say")
    async def discord_say(body: dict):
        speaker = discord_id(body["who"])
        text = body["text"]
        channel.items.append({"kind": "text", "who": body["who"], "text": text, "at": time.time()})
        message = SimpleNamespace(content=text, guild=SimpleNamespace(id=1), channel=channel, author=SimpleNamespace(id=speaker))
        if await bridge.invite(message):
            return {"ok": True, "linked": True}

        async def action(client) -> None:
            await client.send_participants(dict(DISCORD), modality="text")
            await client.send_user_text(speaker=speaker, speaker_name=body["who"], text=text, mentions_assistant=False)

        await bot.registry.run(scope_for(bot, link), action, reply_channel=channel)
        return {"ok": True}

    @control.post("/slack/say")
    async def slack_say(body: dict):
        slack.posts.append({"who": body["who"], "text": body["text"], "blocks": None, "at": time.time()})
        await slack_hub.on_message({"type": "message", "channel": "C1", "user": slack_id(body["who"]), "text": body["text"]})
        return {"ok": True}

    @control.post("/discord/click")
    async def discord_click(body: dict):
        card = next(i for i in reversed(channel.items) if i["kind"] == "card")
        button = next(b for b in card["buttons"] if b["custom_id"].split(":")[1] == body["action"])
        _, action, proposal_id = button["custom_id"].split(":")
        who = member(discord_id(body.get("who", "Ada")))
        verb, option = split_action(action)
        await bridge.click(who, verb, proposal_id, option=option)
        return {"ok": True, "said": who.said}

    @control.post("/discord/me")
    async def discord_me(body: dict):
        return await bridge.send_command(member(discord_id(body["who"])), "me", {"code": body["code"]})

    @control.post("/slack/me")
    async def slack_me(body: dict):
        return {"text": await slack_hub.on_command("C1", slack_id(body["who"]), f"me {body['code']}")}

    @control.get("/payloads")
    async def payloads():
        return {"discord": channel.items, "slack": slack.posts}

    servers = [
        uvicorn.Server(uvicorn.Config(muca, host="127.0.0.1", port=MUCA_PORT, log_level="warning")),
        uvicorn.Server(uvicorn.Config(web, host="127.0.0.1", port=WEB_PORT, log_level="warning")),
        uvicorn.Server(uvicorn.Config(control, host="127.0.0.1", port=CONTROL_PORT, log_level="warning")),
    ]

    async def warm() -> None:
        while not all(s.started for s in servers):
            await asyncio.sleep(0.05)
        await bridge.warm_up(bot)
        await slack_hub.warm_up()

    print(f"Three-channel stack: web http://127.0.0.1:{WEB_PORT}, control http://127.0.0.1:{CONTROL_PORT} (data in {tmp})", flush=True)
    await asyncio.gather(*(s.serve() for s in servers), warm())


if __name__ == "__main__":
    os.environ.setdefault("MUCA_COORDINATOR_ENABLED", "true")
    asyncio.run(main())
