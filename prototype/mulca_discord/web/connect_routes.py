"""
"Add Cadence to Discord" and "Add to Slack": the buttons of the web app's
Connect dialog, so that a group adds Cadence where it already talks without
creating a bot, copying tokens or typing commands (DECISIONS.md, 27/11).

    GET /api/connect        -> {discord: url|null, slack: path|null}
                               what the dialog can offer; null = not set up
                               on this server, and the dialog says so.
    GET /api/slack/install  -> 302 to Slack's "Allow Cadence?" page
    GET /api/slack/oauth    <- Slack sends the member back here; the code is
                               exchanged for the workspace's bot token, saved
                               in the install store (slack/installs.py), and
                               the member sees a page with the next step.

Discord needs no callback: one Cadence bot serves every server it is added
to, so the button is the bot's invite address (client id + the permissions
the coordinator and the voice call need).

Environment (all optional; a missing one only hides its button):
    DISCORD_CLIENT_ID     the Discord application's id (Developer Portal, General Information)
    SLACK_CLIENT_ID       the Slack app's Client ID  (Basic Information)
    SLACK_CLIENT_SECRET   its Client Secret          (never sent to the browser)
    CADENCE_PUBLIC_URL    this server's public address, for Slack's redirect URL
                          (default: the address the request came to)
    CADENCE_APP_URL       where "Back to Cadence" goes (default: this server)
"""

from __future__ import annotations

import hashlib
import hmac
import html
import logging
import os
import secrets
import time
from typing import Awaitable, Callable, Mapping
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from ..slack.installs import Install, InstallStore

logger = logging.getLogger(__name__)

# What the Discord bot may do in a server: read and write in the linked
# channel, show cards (embeds), and join, hear and speak in the voice call.
DISCORD_PERMISSIONS = {
    "view_channel": 1 << 10,
    "send_messages": 1 << 11,
    "embed_links": 1 << 14,
    "read_message_history": 1 << 16,
    "connect": 1 << 20,
    "speak": 1 << 21,
    "use_voice_activity": 1 << 25,
}
DISCORD_SCOPES = "bot applications.commands"

# The same scopes as the manifest in SLACK_SETUP.md.
SLACK_SCOPES = (
    "chat:write,commands,channels:history,groups:history,channels:read,groups:read,users:read,app_mentions:read"
)
STATE_SECONDS = 600  # the member has ten minutes on Slack's page

# code, redirect_uri -> Slack's oauth.v2.access answer (a dict)
Exchange = Callable[[str, str], Awaitable[dict]]


def discord_install_url(client_id: str) -> str:
    permissions = sum(DISCORD_PERMISSIONS.values())
    return "https://discord.com/oauth2/authorize?" + urlencode(
        {"client_id": client_id, "scope": DISCORD_SCOPES, "permissions": permissions}
    )


def _sign(secret: str, value: str) -> str:
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()[:32]


def make_state(secret: str, now: float | None = None) -> str:
    """A signed, time-limited state: Slack hands it back, so the callback knows it started here."""
    value = f"{int(now if now is not None else time.time())}.{secrets.token_urlsafe(8)}"
    return f"{value}.{_sign(secret, value)}"


def state_ok(secret: str, state: str, now: float | None = None) -> bool:
    value, _, signature = state.rpartition(".")
    if not value or not hmac.compare_digest(_sign(secret, value), signature):
        return False
    try:
        issued = int(value.split(".", 1)[0])
    except ValueError:
        return False
    return 0 <= (now if now is not None else time.time()) - issued <= STATE_SECONDS


async def slack_exchange(client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    """The real exchange, with the Slack SDK (imported here: tests pass their own)."""
    from slack_sdk.web.async_client import AsyncWebClient

    answer = await AsyncWebClient().oauth_v2_access(
        client_id=client_id, client_secret=client_secret, code=code, redirect_uri=redirect_uri
    )
    return dict(answer.data)


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title} · Cadence</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;max-width:34rem;margin:12vh auto;padding:0 1.25rem;color:#1d1b2e}}
h1{{font-size:1.4rem}}ol{{padding-left:1.25rem}}li{{margin:.4rem 0}}code{{background:#f0eef8;padding:.1rem .3rem;border-radius:4px}}
a.btn{{display:inline-block;margin-top:1rem;background:#2E2A5A;color:#fff;padding:.6rem 1rem;border-radius:8px;text-decoration:none}}</style>
</head><body><main><h1>{title}</h1>{body}<a class="btn" href="{back}">Back to Cadence</a></main></body></html>"""


def add_connect_routes(
    app: FastAPI,
    env: Mapping[str, str] = os.environ,
    store: InstallStore | None = None,
    exchange: Exchange | None = None,
) -> None:
    def slack_ready() -> bool:
        return bool(env.get("SLACK_CLIENT_ID") and env.get("SLACK_CLIENT_SECRET"))

    def public_url(request: Request) -> str:
        return (env.get("CADENCE_PUBLIC_URL") or str(request.base_url)).rstrip("/")

    def redirect_uri(request: Request) -> str:
        return public_url(request) + "/api/slack/oauth"

    def page(request: Request, title: str, body: str, status: int = 200) -> HTMLResponse:
        back = html.escape(env.get("CADENCE_APP_URL") or public_url(request) + "/")
        return HTMLResponse(PAGE.format(title=html.escape(title), body=body, back=back), status_code=status)

    @app.get("/api/connect")
    async def connect() -> dict:
        client_id = env.get("DISCORD_CLIENT_ID", "").strip()
        return {
            "discord": discord_install_url(client_id) if client_id else None,
            "slack": "/api/slack/install" if slack_ready() else None,
        }

    @app.get("/api/slack/install")
    async def slack_install(request: Request):
        if not slack_ready():
            return page(request, "Slack is not set up here", "<p>Ask whoever runs this Cadence server to turn on Slack.</p>", 404)
        query = urlencode({
            "client_id": env["SLACK_CLIENT_ID"],
            "scope": SLACK_SCOPES,
            "redirect_uri": redirect_uri(request),
            "state": make_state(env["SLACK_CLIENT_SECRET"]),
        })
        return RedirectResponse(f"https://slack.com/oauth/v2/authorize?{query}", status_code=302)

    @app.get("/api/slack/oauth")
    async def slack_oauth(request: Request, code: str = "", state: str = "", error: str = ""):
        if error:
            return page(request, "Nothing was added", "<p>Slack did not add Cadence. You can try again from the web app.</p>")
        if not slack_ready() or not code or not state_ok(env["SLACK_CLIENT_SECRET"], state):
            return page(request, "This link has expired", "<p>Start again from <em>Connect Slack or Discord</em> in the web app.</p>", 400)
        try:
            run = exchange or (lambda c, r: slack_exchange(env["SLACK_CLIENT_ID"], env["SLACK_CLIENT_SECRET"], c, r))
            answer = await run(code, redirect_uri(request))
        except Exception:
            logger.exception("Slack install: the code exchange failed")
            answer = {"ok": False}
        team = answer.get("team") or {}
        if not answer.get("ok") or not answer.get("access_token") or not team.get("id"):
            return page(request, "Cadence could not be added", "<p>Slack did not confirm the install. Try again in a minute.</p>", 502)
        (store or InstallStore()).save(
            Install(team["id"], team.get("name", ""), answer["access_token"], answer.get("bot_user_id", ""))
        )
        logger.info("Slack install: Cadence added to the workspace %s", team["id"])
        name = html.escape(team.get("name") or "your workspace")
        body = (
            f"<p>Cadence is now in <strong>{name}</strong>. One more step, in Slack:</p><ol>"
            "<li>Open the channel where your group talks and write <code>/invite @Cadence</code>.</li>"
            "<li>Paste your space's link there (in the web app: <em>Connect Slack or Discord</em>, <em>Copy link</em>).</li>"
            "</ol><p>Cadence answers in the channel when it is linked.</p>"
        )
        return page(request, "Cadence is in your Slack", body)
