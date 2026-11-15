"""
Deleting a web group's data on MUCA-Server (project rule 10: "delete all the
group's data on confirmation").

MUCA-Server keeps one SQLite file per conversation (memory, episodic log,
project state). `DELETE /conversation?conversation_id=...` removes it; the
endpoint is gated on the server's MUCA_ADMIN_TOKEN, which this adapter reads
from the same variable. WebHub.delete_group closes the group's session first,
so nothing writes the file again after it is gone.

Plain urllib in a thread: no new dependency for one request.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 15


def http_base(muca_ws_url: str) -> str:
    """ws://host:8000/ -> http://host:8000 (wss -> https)."""
    parts = urllib.parse.urlsplit(muca_ws_url)
    scheme = {"ws": "http", "wss": "https"}.get(parts.scheme, parts.scheme)
    return urllib.parse.urlunsplit((scheme, parts.netloc, "", "", "")).rstrip("/")


async def delete_conversation(muca_ws_url: str, admin_token: str, conversation_id: str) -> bool:
    """True when MUCA-Server confirmed the deletion (or had nothing to delete)."""
    if not admin_token:
        logger.warning("MUCA_ADMIN_TOKEN is not set: cannot delete %s on MUCA-Server", conversation_id)
        return False
    query = urllib.parse.urlencode({"conversation_id": conversation_id})
    request = urllib.request.Request(
        f"{http_base(muca_ws_url)}/conversation?{query}",
        method="DELETE",
        headers={"x-admin-token": admin_token},
    )

    def call() -> bool:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            json.loads(response.read() or b"{}")
            return 200 <= response.status < 300

    try:
        return await run_in_threadpool(call)
    except (urllib.error.URLError, OSError, ValueError):
        logger.exception("MUCA-Server did not delete %s", conversation_id)
        return False
