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
def scripted(name: str, user: str) -> dict:
    """The draft for one schema, built from ids that really are in the request."""
    import re

    if name in DRAFTS:
        draft = dict(DRAFTS[name])
        if "evidence" in draft:
            # Point at the chat lines the writer numbered ([1], [2], ...): a
            # number that is not a line would be refused (proactive_writer.py).
            lines = user.split("<chat>")[1].count("\n[")
            draft["evidence"] = list(range(1, min(lines, 5) + 1))
        return draft
    members = [int(m) for m in re.findall(r"- id (\d+):", user)]
    if name == "plan_draft":
        titles = [t.strip() for t in user.split("<tasks>")[1].split("</tasks>")[0].splitlines() if t.strip()]
        return {
            "items": [
                {"title": t, "owner_id": members[n % len(members)] if members else None,
                 "reason": "Free hours this week.", "due_date": None}
                for n, t in enumerate(titles)
            ],
            "rationale": "Stepping in because you listed the tasks: here is a first split.",
        }
    if name == "checkin_options":
        task_id = re.findall(r"task_id (\w+):", user)[0]
        return {
            "options": [
                {"label": "Move it one week later", "task_id": task_id, "new_due_date": "2027-12-01", "new_owner_id": None, "drop": False},
                {"label": "Drop it: not essential", "task_id": task_id, "new_due_date": None, "new_owner_id": None, "drop": True},
            ],
            "rationale": "Stepping in because a task is late.",
        }
    if name == "plan_approach":
        # Plan opener (CS-OPEN-01), SCRIPTED: every answer becomes an agreed point.
        answers = re.findall(r"^\[(\d+)\] [^:]+: (.*)$", user.split("<chat>")[1], re.MULTILINE)
        points = [{"text": text[:150], "evidence": [int(n)]} for n, text in answers[:5]]
        return {
            "outcome": "agreed" if points else "none",
            "topic": "how we work",
            "evidence": [p["evidence"][0] for p in points],
            "rationale": "Stepping in because you said how you want to plan the work.",
            "question": "",
            "summary": "; ".join(p["text"] for p in points)[:190] or "-",
            "agreements": points,
            "open_points": [],
            "options": [],
        }
    if name == "project_answer":
        # Cadence's answer (ask), SCRIPTED: no ids cited; silence when offered a "maybe" follow-up.
        if "<note>" in user:
            return {"answer": "", "task_ids": [], "milestone_ids": [], "decision_ids": [], "documents": []}
        question = user.split("<question>")[1].split("</question>")[0].strip()
        return {"answer": f"SCRIPTED answer to: {question}", "task_ids": [], "milestone_ids": [], "decision_ids": [], "documents": []}
    if name == "likely_dependencies":
        # Dependency suggestion, SCRIPTED: a new task named "Test ..." waits on the first other open task.
        new = re.findall(r"task_id (\w+): (.*?) \|", user.split("<new>")[1].split("</new>")[0])
        rest = re.findall(r"task_id (\w+):", user.split("<plan>")[1])
        links = [{"task_id": t, "waits_on": rest[0], "reason": "Testing needs it built first."} for t, title in new if title.startswith("Test") and rest]
        return {"links": links[:1], "rationale": "Stepping in because a new task seems to need another one first."}
    if name == "week_topics":
        return {"topics": [{"title": "SCRIPTED topic", "summary": "The group talked about the plan (scripted, offline stack)."}]}
    if name == "decision_answer":
        ids = re.findall(r"- id (\w+):", user.split("<decisions>")[1])
        return {"answer": "The group chose it in the decision card.", "decision_ids": ids[:1]}
    raise KeyError(name)


# Phrase in a message -> the strategy the fake "intervention agent" picks.
TRIGGERS = {"font": "cs2_delegate_simple_task", "think-aloud": "cs3_close_decision"}


class ScriptedModel:
    """Stands in for AsyncOpenAI: answers each schema with its scripted draft."""

    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        name = kwargs["response_format"]["json_schema"]["name"]
        content = json.dumps(scripted(name, kwargs["messages"][1]["content"]))
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


# The plan opener's window (opener.py: 60 s minimum, 5 s quiet, 10 min cap) is
# shortened here only, so a browser test does not wait a minute. SCRIPTED timing.
from muca_server.cognition.coordination import opener as _opener  # noqa: E402

_opener.MIN_OPEN_SECONDS, _opener.QUIET_SECONDS, _opener.MAX_OPEN_SECONDS = 3.0, 1.5, 60.0

MUCA_PORT = int(os.environ.get("FAKE_MUCA_PORT", "8091"))
WEB_PORT = int(os.environ.get("FAKE_WEB_PORT", "8090"))
ADMIN_TOKEN = "offline-admin-token"


async def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="cadence-fake-"))
    muca = create_app(
        components_factory=DefaultSessionComponentsFactory(
            agent_factory=Factory(),
            policy_factory=lambda context: FakePolicy(),
            coordinator_factory=build_coordinator_factory(
                CoordinatorSettings(enabled=True), client=ScriptedModel(), db_dir=str(tmp)
            ),
        ),
        # "Delete space" removes the group's file on the server (offline token).
        db_dir=tmp,
        admin_token=ADMIN_TOKEN,
    )
    hub = WebHub(WebStore(tmp / "web.sqlite3"), f"ws://127.0.0.1:{MUCA_PORT}/", admin_token=ADMIN_TOKEN)
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
