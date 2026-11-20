"""
The web adapter's HTTP and WebSocket surface (FastAPI), plus the built frontend.

    POST /api/groups   {groupName, displayName?}  -> {token, inviteCode}   create a space
    POST /api/join     {inviteCode, displayName?} -> {token}               join with a code
                       With "Authorization: Bearer <account token>" the member is the
                       logged-in person (name and profile from the account); without
                       it displayName is required (a guest, as before accounts).
    Accounts (register, log in, profile, my spaces): account_routes.py.
    GET  /api/session  Authorization: Bearer <t>  -> {group, me}           who am I
    GET  /api/health                              -> {ok: true}            is the adapter there
    POST /api/groups/delete {confirm: group name} + Bearer -> {deleted: true}  delete everything (rule 10)
    POST /api/groups/rename {name} + Bearer -> {group}                     a new name (Project settings)
    WS   /ws           first frame {type:"auth", token}, then:
         -> {type:"message", text}
         -> {type:"command", command:"profile"|"kickoff"|"state"|"planning"|"checkin"|"task"|"why"|"ask"|"catchup"|"language"|"charter"|"milestone"|"approach", args, requestId}
         -> {type:"click", proposalId, action:"confirm"|"reject"|"take"|"choose"|"not_now"|"helpful", option?, requestId}
         <- hello, message, members, group, proposal, state, status, reply{requestId, answer}, deleted

Every request is checked server side: the token names exactly one member of one
group, and a socket only ever receives its own group's events (section 10).
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Literal
from urllib.parse import unquote

from fastapi import FastAPI, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from ..attachments import MAX_BYTES, MAX_CHARS, extract_text
from .account_routes import add_account_routes, bearer
from .hub import SpaceFull, WebHub

logger = logging.getLogger(__name__)

AUTH_TIMEOUT_SECONDS = 10


class CreateGroup(BaseModel):
    group_name: str = Field(alias="groupName", min_length=1, max_length=80)
    display_name: str = Field(default="", alias="displayName", max_length=40)


class JoinGroup(BaseModel):
    invite_code: str = Field(alias="inviteCode", min_length=4, max_length=20)
    display_name: str = Field(default="", alias="displayName", max_length=40)


class RenameGroup(BaseModel):
    name: str = Field(max_length=80)


class DeleteGroup(BaseModel):
    # The member types the space's name: a deliberate act, not a stray click.
    confirm: str = Field(max_length=80)


class ChatFrame(BaseModel):
    type: Literal["message"]
    text: str = Field(max_length=4000)


class CommandFrame(BaseModel):
    type: Literal["command"]
    command: Literal["profile", "kickoff", "state", "planning", "checkin", "task", "why", "ask", "catchup", "language", "charter", "milestone", "approach", "document", "reflection"]
    args: dict = Field(default_factory=dict)
    request_id: str = Field(default="", alias="requestId", max_length=64)


class ClickFrame(BaseModel):
    type: Literal["click"]
    proposal_id: str = Field(alias="proposalId", max_length=64)
    action: Literal["confirm", "reject", "take", "choose", "not_now", "helpful"]
    option: int | None = None  # "choose": index of the option on a decision card
    request_id: str = Field(default="", alias="requestId", max_length=64)


def create_web_app(
    hub: WebHub,
    *,
    static_dir: str | Path | None = None,
    film_dir: str | Path | None = None,
    allowed_origins: list[str] | None = None,
) -> FastAPI:
    app = FastAPI(title="Cadence web adapter", docs_url=None, redoc_url=None)
    if allowed_origins:
        # Only when the frontend is hosted elsewhere (e.g. the Vercel preview):
        # the listed origins may call the API. Tokens travel in headers, no cookies.
        app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_methods=["GET", "POST", "PUT"], allow_headers=["Authorization", "Content-Type", "X-File-Name"])

    @app.get("/api/health")
    async def health() -> dict:
        """The frontend asks this before showing the forms (the static preview has no adapter)."""
        return {"ok": True}

    add_account_routes(app, hub)

    # CS6: groups with a deadline close get their progress assessment even when
    # nobody has opened them since this adapter started (hub.wake_loop).
    waking: list[asyncio.Task] = []

    async def start_waking() -> None:
        if os.environ.get("MULCA_WEB_WAKE", "on").strip().lower() not in ("0", "off", "false", "no"):
            waking.append(asyncio.create_task(hub.wake_loop()))

    async def stop_waking() -> None:
        for task in waking:
            task.cancel()

    app.router.on_startup.append(start_waking)
    app.router.on_shutdown.append(stop_waking)

    def who(authorization: str, display_name: str):
        """The logged-in person, or None for a guest (who must give a name)."""
        user = hub.accounts.user_by_token(bearer(authorization)) if authorization else None
        if user is None and not display_name.strip():
            raise HTTPException(422, "Log in, or write the name your group will see.")
        return user

    @app.post("/api/groups")
    async def create_group(body: CreateGroup, authorization: str = Header(default="")) -> dict:
        group, member, token = hub.create_group(body.group_name, body.display_name, who(authorization, body.display_name))
        return {"token": token, "inviteCode": group.invite_code, "memberId": member.id}

    @app.post("/api/join")
    async def join_group(body: JoinGroup, authorization: str = Header(default="")) -> dict:
        try:
            joined = await hub.join_group(body.invite_code, body.display_name, who(authorization, body.display_name))
        except SpaceFull as full:
            raise HTTPException(409, str(full)) from None
        if joined is None:
            raise HTTPException(404, "No space uses this invite code. Check it with the person who shared it.")
        group, member, token = joined
        return {"token": token, "inviteCode": group.invite_code, "memberId": member.id}

    @app.post("/api/extract")
    async def extract(request: Request, authorization: str = Header(default=""), x_file_name: str = Header(default="")) -> dict:
        """
        The text of a document a member uploads (PDF, Word, PowerPoint, plain
        text), so the assignment does not have to be pasted by hand. The file
        is read in memory and not kept: only its text goes back to the browser,
        where the member can edit it before sending it to Cadence.
        The body is the file itself; its name travels in X-File-Name.
        """
        if hub.store.member_by_token(authorization.removeprefix("Bearer ").strip()) is None:
            raise HTTPException(401, "Unknown or expired access.")
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > MAX_BYTES:
            raise HTTPException(413, "The file is larger than 10 MB.")
        data = await request.body()
        if len(data) > MAX_BYTES:
            raise HTTPException(413, "The file is larger than 10 MB.")
        name = unquote(x_file_name)[:200] or "document"
        text = await asyncio.to_thread(extract_text, name, data, request.headers.get("content-type"))
        text = "\n".join(line.rstrip() for line in (text or "").splitlines()).strip()
        if not text:
            raise HTTPException(422, "No text could be read from this file. Use a PDF with real text (not a scan), Word, PowerPoint or a text file.")
        return {"name": name, "text": text[:MAX_CHARS], "truncated": len(text) > MAX_CHARS}

    @app.get("/api/session")
    async def session(authorization: str = Header(default="")) -> dict:
        member = hub.store.member_by_token(authorization.removeprefix("Bearer ").strip())
        if member is None:
            raise HTTPException(401, "Unknown or expired access.")
        group = hub.store.group(member.group_id)
        return {
            "group": {"id": group.id, "name": group.name, "inviteCode": group.invite_code},
            "me": {"id": member.id, "name": member.display_name},
        }

    @app.post("/api/groups/delete")
    async def delete_group(body: DeleteGroup, authorization: str = Header(default="")) -> dict:
        """Rule 10: delete all the group's data (MUCA-Server and web), after typing its name."""
        member = hub.store.member_by_token(authorization.removeprefix("Bearer ").strip())
        if member is None:
            raise HTTPException(401, "Unknown or expired access.")
        group = hub.store.group(member.group_id)
        if " ".join(body.confirm.split()).lower() != group.name.lower():
            raise HTTPException(400, "Type the name of the space exactly to delete it.")
        if not await hub.delete_group(member):
            raise HTTPException(502, "The coordinator server could not delete the data. Nothing was deleted: try again later.")
        return {"deleted": True}

    @app.post("/api/groups/rename")
    async def rename_group(body: RenameGroup, authorization: str = Header(default="")) -> dict:
        """Project settings: any member gives the space a new name (their own action, no card)."""
        member = hub.store.member_by_token(authorization.removeprefix("Bearer ").strip())
        if member is None:
            raise HTTPException(401, "Unknown or expired access.")
        name = " ".join(body.name.split())
        if not name:
            raise HTTPException(422, "Write the new name of the space.")
        return {"group": await hub.rename_group(member, name)}

    @app.post("/api/calendar")
    async def calendar_link(authorization: str = Header(default="")) -> dict:
        """M5: a new private feed link for the member's group (the old link stops working)."""
        member = hub.store.member_by_token(authorization.removeprefix("Bearer ").strip())
        if member is None:
            raise HTTPException(401, "Unknown or expired access.")
        return {"path": f"/api/calendar/{hub.calendar.new_link(member.group_id)}.ics"}

    @app.post("/api/calendar/file")
    async def calendar_file(authorization: str = Header(default="")) -> Response:
        """Add to my calendar: a one-time .ics file (milestones + my tasks), no link to keep secret."""
        member = hub.store.member_by_token(authorization.removeprefix("Bearer ").strip())
        if member is None:
            raise HTTPException(401, "Unknown or expired access.")
        text = hub.calendar.file_for(member.group_id, member.id)
        return Response(
            text,
            media_type="text/calendar; charset=utf-8",
            headers={"Cache-Control": "no-store", "Content-Disposition": 'attachment; filename="cadence.ics"'},
        )

    @app.get("/api/calendar/{token}.ics")
    async def calendar_feed(token: str) -> Response:
        text = hub.calendar.feed(token)
        if text is None:
            raise HTTPException(404, "This calendar link does not exist or was replaced.")
        return Response(text, media_type="text/calendar; charset=utf-8", headers={"Cache-Control": "no-store"})

    @app.websocket("/ws")
    async def socket(ws: WebSocket) -> None:
        await ws.accept()
        try:
            first = await asyncio.wait_for(ws.receive_json(), AUTH_TIMEOUT_SECONDS)
        except (asyncio.TimeoutError, WebSocketDisconnect, ValueError):
            await ws.close(code=4401)
            return
        member = hub.store.member_by_token(str(first.get("token", ""))) if first.get("type") == "auth" else None
        if member is None:
            await ws.close(code=4401)
            return
        await hub.connect(ws, member)
        try:
            while True:
                frame = await ws.receive_json()
                if frame.get("type") == "message":
                    # Chat messages one at a time, so MUCA-Server gets them in the order typed.
                    await _handle(hub, ws, member, frame)
                else:
                    # Commands and clicks wait for the model: never block the chat behind them.
                    asyncio.create_task(_handle(hub, ws, member, frame))
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            hub.disconnect(ws, member)

    if film_dir and Path(film_dir).is_dir():
        app.mount("/film", StaticFiles(directory=str(film_dir)), name="film")
    if static_dir and Path(static_dir).is_dir():
        root = Path(static_dir)
        app.mount("/assets", StaticFiles(directory=str(root / "assets")), name="assets")

        @app.get("/{path:path}")
        async def spa(path: str) -> FileResponse:
            # Real files (favicon, og image) as they are; every route of the app -> index.html.
            candidate = (root / path).resolve()
            if path and candidate.is_file() and root.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(root / "index.html")

    return app


async def _handle(hub: WebHub, ws: WebSocket, member, frame: dict) -> None:
    """One frame from a member; answers to commands and clicks go back to that member only."""
    kind = frame.get("type")
    try:
        if kind == "message":
            await hub.post_message(member, ChatFrame.model_validate(frame).text)
        elif kind == "command":
            cmd = CommandFrame.model_validate(frame)
            answer = await hub.command(member, cmd.command, cmd.args)
            await ws.send_json({"type": "reply", "requestId": cmd.request_id, "answer": answer})
        elif kind == "click":
            click = ClickFrame.model_validate(frame)
            answer = await hub.click(member, click.proposal_id, click.action, option=click.option)
            await ws.send_json({"type": "reply", "requestId": click.request_id, "answer": answer})
    except ValidationError:
        text = "That request was not understood."
        request_id = frame.get("requestId") if isinstance(frame, dict) else None
        if isinstance(request_id, str) and request_id:
            # Answer the waiting request too, so the button does not spin forever.
            await ws.send_json({"type": "reply", "requestId": request_id[:64], "answer": {"type": "notice", "ok": False, "text": text}})
        await ws.send_json({"type": "error", "text": text})
    except Exception:  # never let one frame kill the socket
        logger.exception("Web frame %s failed", kind)
