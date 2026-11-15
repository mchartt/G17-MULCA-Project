"""
Offline stack for the browser tests and for rehearsing the demo without Azure:
an in-process MUCA-Server with the coordinator on and a FAKE model, plus the
web adapter serving the built app and the film. No network, no cost. Never
use it for the live run.

What is fake (and only here):
  - the model: ScriptedModel answers each card schema with a fixed draft;
  - the intervention agent: FakePolicy fires a coordinator strategy when a
    message contains a scripted phrase (TRIGGERS) instead of a model judging
    it. Everything after that is the real code: ProactiveBridge rules R1-R7,
    ProactiveWriter validation, ProposalService, the adapter, the app.

    cd mulca/prototype && python webapp/e2e/fake_stack.py   # http://127.0.0.1:8090
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

PROTOTYPE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROTOTYPE))

import uvicorn  # noqa: E402
from muca_server import create_app  # noqa: E402
from muca_server.cognition.coordination.settings import CoordinatorSettings  # noqa: E402
from muca_server.cognition.coordination.wiring import build_coordinator_factory  # noqa: E402
from muca_server.sessions import DefaultSessionComponentsFactory  # noqa: E402

from mulca_discord.web import WebHub, WebStore, create_web_app  # noqa: E402
import json  # noqa: E402
from types import SimpleNamespace  # noqa: E402

from tests.test_coordinator_discord import CHARTER  # noqa: E402
from tests.test_muca_client import AnswerEverything, Factory  # noqa: E402

# Scripted drafts, by the name of the JSON schema the writer asks for.
DRAFTS = {
    "charter_draft": CHARTER,
    "delegate_simple_task": {
        "title": "Fix fonts and margins of the report",
        "due_date": None,
        "return_to": "Evaluation protocol",
        "topic": "Fonts and margins",
        "evidence": [],
        "rationale": "Stepping in because one person can fix the formatting while you go back to the protocol.",
    },
    "close_decision": {
        "question": "Which usability test do we run?",
        "options": [
            {"label": "Think-aloud", "argument": "Shows why users get stuck."},
            {"label": "SUS questionnaire", "argument": "Fast, but only gives a score."},
        ],
        "topic": "Test method",
        "evidence": [],
        "rationale": "Stepping in because the test method is open and both options are on the table.",
    },
}
# Phrase in a message -> the strategy the fake "intervention agent" picks.
TRIGGERS = {"font": "cs2_delegate_simple_task", "think-aloud": "cs3_close_decision"}


class ScriptedModel:
    """Stands in for AsyncOpenAI: answers each schema with its scripted draft."""

    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        name = kwargs["response_format"]["json_schema"]["name"]
        draft = dict(DRAFTS[name])
        if "evidence" in draft:
            # Point at the chat lines the writer numbered ([1], [2], ...): a
            # number that is not a line would be refused (proactive_writer.py).
            lines = kwargs["messages"][1]["content"].split("<chat>")[1].count("\n[")
            draft["evidence"] = list(range(1, min(lines, 5) + 1))
        content = json.dumps(draft)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))], usage=None)


class FakePolicy(AnswerEverything):
    """The test policy, plus the hooks a real CoalaPolicy has (catch-up text, proactive bridge)."""

    def __init__(self) -> None:
        self._bridge = None
        self._history: list = []

    def set_proactive_bridge(self, bridge) -> None:
        self._bridge = bridge

    def observer_catchup_text(self) -> str:
        return ""

    async def on_utterance(self, utterance) -> bool:
        self._history.append(utterance)
        strategy = next((s for phrase, s in TRIGGERS.items() if phrase in utterance.content.lower()), None)
        if strategy and self._bridge is not None:
            await self._bridge.offer(
                strategy, history=list(self._history), message_count=len(self._history), assistant_id=0
            )
            await self._port.no_reply()
            return False
        return await super().on_utterance(utterance)


MUCA_PORT = int(os.environ.get("FAKE_MUCA_PORT", "8091"))
WEB_PORT = int(os.environ.get("FAKE_WEB_PORT", "8090"))


async def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="cadence-fake-"))
    muca = create_app(
        components_factory=DefaultSessionComponentsFactory(
            agent_factory=Factory(),
            policy_factory=lambda context: FakePolicy(),
            coordinator_factory=build_coordinator_factory(
                CoordinatorSettings(enabled=True), client=ScriptedModel(), db_dir=str(tmp)
            ),
        )
    )
    hub = WebHub(WebStore(tmp / "web.sqlite3"), f"ws://127.0.0.1:{MUCA_PORT}/")
    web = create_web_app(
        hub,
        static_dir=PROTOTYPE / "webapp" / "dist",
        film_dir=PROTOTYPE / "webapp" / "film" / "public",
    )
    servers = [
        uvicorn.Server(uvicorn.Config(muca, host="127.0.0.1", port=MUCA_PORT, log_level="warning")),
        uvicorn.Server(uvicorn.Config(web, host="127.0.0.1", port=WEB_PORT, log_level="warning")),
    ]
    print(f"Fake stack on http://127.0.0.1:{WEB_PORT} (data in {tmp})", flush=True)
    await asyncio.gather(*(s.serve() for s in servers))


if __name__ == "__main__":
    asyncio.run(main())
