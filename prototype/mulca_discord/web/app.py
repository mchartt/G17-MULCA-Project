"""
The web adapter's HTTP and WebSocket surface (FastAPI), plus the built frontend.

    POST /api/groups   {groupName, displayName}   -> {token, inviteCode}   create a space
    POST /api/join     {inviteCode, displayName}  -> {token}               join with a code
    GET  /api/session  Authorization: Bearer <t>  -> {group, me}           who am I
    WS   /ws           first frame {type:"auth", token}, then:
         -> {type:"message", text}
         -> {type:"command", command:"profile"|"kickoff"|"state", args, requestId}
         -> {type:"click", proposalId, action:"confirm"|"reject", requestId}
         <- hello, message, members, proposal, state, status, reply{requestId, answer}

Every request is checked server side: the token names exactly one member of one
group, and a socket only ever receives its own group's events (section 10).
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from .hub import WebHub

logger = logging.getLogger(__name__)

AUTH_TIMEOUT_SECONDS = 10


class CreateGroup(BaseModel):
    group_name: str = Field(alias="groupName", min_length=1, max_length=80)
    display_name: str = Field(alias="displayName", min_length=1, max_length=40)


class JoinGroup(BaseModel):
    invite_code: str = Field(alias="inviteCode", min_length=4, max_length=20)
    display_name: str = Field(alias="displayName", min_length=1, max_length=40)


class ChatFrame(BaseModel):
    type: Literal["message"]
    text: str = Field(max_length=4000)


class CommandFrame(BaseModel):
    type: Literal["command"]
    command: Literal["profile", "kickoff", "state"]
    args: dict = Field(default_factory=dict)
    request_id: str = Field(default="", alias="requestId", max_length=64)


class ClickFrame(BaseModel):
    type: Literal["click"]
    proposal_id: str = Field(alias="proposalId", max_length=64)
    action: Literal["confirm", "reject"]
    request_id: str = Field(default="", alias="requestId", max_length=64)


def create_web_app(hub: WebHub, *, static_dir: str | Path | None = None, film_dir: str | Path | None = None) -> FastAPI:
    app = FastAPI(title="Cadence web adapter", docs_url=None, redoc_url=None)

    @app.post("/api/groups")
    async def create_group(body: CreateGroup) -> dict:
        group, member, token = hub.create_group(body.group_name, body.display_name)
        return {"token": token, "inviteCode": group.invite_code, "memberId": member.id}

    @app.post("/api/join")
    async def join_group(body: JoinGroup) -> dict:
        joined = await hub.join_group(body.invite_code, body.display_name)
        if joined is None:
            raise HTTPException(404, "No space with this invite code.")
        group, member, token = joined
        return {"token": token, "inviteCode": group.invite_code, "memberId": member.id}

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
            answer = await hub.click(member, click.proposal_id, click.action)
            await ws.send_json({"type": "reply", "requestId": click.request_id, "answer": answer})
    except ValidationError:
        await ws.send_json({"type": "error", "text": "That request was not understood."})
    except Exception:  # never let one frame kill the socket
        logger.exception("Web frame %s failed", kind)
