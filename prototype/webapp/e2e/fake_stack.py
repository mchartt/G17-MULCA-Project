"""
Offline stack for the browser tests and for rehearsing the demo without Azure:
an in-process MUCA-Server with the coordinator on and a FAKE model (it always
proposes the same charter and the agent echoes), plus the web adapter serving
the built app and the film. No network, no cost. Never use it for the live run.

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
from tests.test_coordinator_discord import FakeChat  # noqa: E402
from tests.test_muca_client import AnswerEverything, Factory  # noqa: E402

class FakePolicy(AnswerEverything):
    """The test policy plus the one hook a real policy also has (catch-up text for observers)."""

    def observer_catchup_text(self) -> str:
        return ""


MUCA_PORT = int(os.environ.get("FAKE_MUCA_PORT", "8091"))
WEB_PORT = int(os.environ.get("FAKE_WEB_PORT", "8090"))


async def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="cadence-fake-"))
    muca = create_app(
        components_factory=DefaultSessionComponentsFactory(
            agent_factory=Factory(),
            policy_factory=lambda context: FakePolicy(),
            coordinator_factory=build_coordinator_factory(
                CoordinatorSettings(enabled=True), client=FakeChat(), db_dir=str(tmp)
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
