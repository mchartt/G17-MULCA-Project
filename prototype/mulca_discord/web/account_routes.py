"""
The HTTP routes of accounts (accounts.py), added to the web app by app.py.

    POST /api/register     {email, password, displayName}  -> {accountToken, user}
    POST /api/login        {email, password}               -> {accountToken, user}
    POST /api/logout       + Bearer account token          -> {ok}
    GET  /api/me           + Bearer                        -> {user, spaces}
    PUT  /api/me           {displayName, discipline, skills, weeklyHours} -> {user}
    POST /api/me/delete    {password}                      -> {deleted}
    POST /api/spaces/open  {groupId}                       -> {token, inviteCode, memberId}

Two kinds of token, on purpose:
  - the *account token* says who the person is (register / log in);
  - the *space token* opens one space as one member (create, join, open).
The console and the WebSocket keep using the space token exactly as before.
"""

from __future__ import annotations

import asyncio

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .accounts import AccountError, User
from .hub import WebHub


class Register(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)
    display_name: str = Field(alias="displayName", max_length=40)


class Login(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


class Profile(BaseModel):
    display_name: str = Field(alias="displayName", max_length=40)
    discipline: str = Field(default="", max_length=100)
    skills: list[str] = Field(default_factory=list, max_length=20)
    weekly_hours: int | None = Field(default=None, alias="weeklyHours", ge=0, le=80)


class DeleteAccount(BaseModel):
    password: str = Field(max_length=200)


class OpenSpace(BaseModel):
    group_id: int = Field(alias="groupId")


def bearer(authorization: str) -> str:
    return authorization.removeprefix("Bearer ").strip()


def add_account_routes(app: FastAPI, hub: WebHub) -> None:
    accounts = hub.accounts

    def signed_in(authorization: str) -> User:
        user = accounts.user_by_token(bearer(authorization))
        if user is None:
            raise HTTPException(401, "Log in again.")
        return user

    def session_json(user: User, token: str) -> dict:
        return {"accountToken": token, "user": user.to_json()}

    @app.post("/api/register")
    async def register(body: Register) -> dict:
        try:
            user, token = accounts.register(body.email, body.password, body.display_name)
        except AccountError as error:
            raise HTTPException(400, str(error)) from None
        return session_json(user, token)

    @app.post("/api/login")
    async def login(body: Login) -> dict:
        try:
            user, token = accounts.login(body.email, body.password)
        except AccountError as error:
            raise HTTPException(401, str(error)) from None
        return session_json(user, token)

    @app.post("/api/logout")
    async def logout(authorization: str = Header(default="")) -> dict:
        accounts.logout(bearer(authorization))
        return {"ok": True}

    @app.get("/api/me")
    async def me(authorization: str = Header(default="")) -> dict:
        user = signed_in(authorization)
        return {"user": user.to_json(), "spaces": accounts.spaces(user.id)}

    @app.put("/api/me")
    async def update_me(body: Profile, authorization: str = Header(default="")) -> dict:
        user = signed_in(authorization)
        try:
            user = accounts.update_profile(
                user.id,
                display_name=body.display_name,
                discipline=body.discipline,
                skills=body.skills,
                weekly_hours=body.weekly_hours,
            )
        except AccountError as error:
            raise HTTPException(400, str(error)) from None
        # Every space of this person gets the new profile (in the background:
        # the coordinator server may be slow or off, the account is saved anyway).
        asyncio.create_task(hub.share_profile(user))
        return {"user": user.to_json()}

    @app.post("/api/me/delete")
    async def delete_me(body: DeleteAccount, authorization: str = Header(default="")) -> dict:
        user = signed_in(authorization)
        try:
            accounts.login(user.email, body.password)  # the password, once more
        except AccountError as error:
            raise HTTPException(401, str(error)) from None
        accounts.delete_user(user.id)
        return {"deleted": True}

    @app.post("/api/spaces/open")
    async def open_space(body: OpenSpace, authorization: str = Header(default="")) -> dict:
        user = signed_in(authorization)
        member_id = accounts.member_in(user.id, body.group_id)
        group = hub.store.group(body.group_id)
        if member_id is None or group is None:
            raise HTTPException(404, "You are not a member of this space.")
        return {"token": accounts.new_access(member_id), "inviteCode": group.invite_code, "memberId": member_id}
