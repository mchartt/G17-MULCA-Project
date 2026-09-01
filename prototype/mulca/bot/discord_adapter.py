"""TextChannelAdapter (BLUEPRINT.md §6) -- the concrete text-modality half of
the channel-adapter seam. An AudioChannelAdapter is a separate module built by
the colleague; it must produce the same ConversationEvent shape from
core.events and call the same Orchestrator.enqueue(). Nothing here is
text-specific from the orchestrator's point of view -- see core/orchestrator.py
and core/events.py for the actual contract.
"""
from __future__ import annotations

import time

import discord
from asgiref.sync import sync_to_async

from mulca.core.events import ConversationEvent

from .models import WorkingMemorySnapshot


def _get_wm_snapshot_row(channel_id: str):
    return WorkingMemorySnapshot.objects.filter(channel_id=channel_id).first()


async def load_wm_snapshot(channel_id: str) -> dict | None:
    """BLUEPRINT.md §11.1 startup half. Returns None if no snapshot exists
    yet (first-ever boot for this channel)."""
    row = await sync_to_async(_get_wm_snapshot_row)(channel_id)
    if row is None:
        return None
    return {
        "history_summary": row.history_summary,
        "participant_roles_summary": row.participant_roles_summary,
        "history_tail": row.history_tail,
        "total_message_count": row.total_message_count,
    }


def _save_wm_snapshot_row(channel_id: str, snapshot: dict) -> None:
    WorkingMemorySnapshot.objects.update_or_create(
        channel_id=channel_id,
        defaults={
            "history_summary": snapshot["history_summary"],
            "participant_roles_summary": snapshot["participant_roles_summary"],
            "history_tail": snapshot["history_tail"],
            "total_message_count": snapshot["total_message_count"],
            "updated_at": time.time(),
        },
    )


async def save_wm_snapshot(channel_id: str, snapshot: dict) -> None:
    """BLUEPRINT.md §11.1 shutdown half. Overwrites any existing row for this
    channel -- a single current-state snapshot, not an append-only log."""
    await sync_to_async(_save_wm_snapshot_row)(channel_id, snapshot)


def build_discord_client(orchestrator_factory, channel_ids: set[str] | None):
    """`orchestrator_factory(bot_user_id, dispatch_fn, roster_fn, bot_display_name)
    -> Orchestrator` is deferred until on_ready, since the orchestrator's
    forced-intervention check needs the bot's own user id (BLUEPRINT.md §1
    "Forced-intervention bypass" -- @mention rule). Also loads any persisted
    WM snapshot (§11.1) before the bot starts processing messages, and stashes
    the orchestrator on the client itself so run_discord_bot.py can reach it
    after client.run() returns (on clean shutdown) to save a fresh one."""
    intents = discord.Intents.default()
    intents.message_content = True
    # Needed for channel.members / build_roster_fn to see participants who
    # haven't spoken yet -- also requires the "Server Members Intent" toggle
    # enabled in the Discord Developer Portal (Bot tab, same section as
    # Message Content Intent), or this stays empty even with this flag set.
    intents.members = True
    client = discord.Client(intents=intents)
    state = {"orchestrator": None}

    @client.event
    async def on_ready():
        orchestrator = orchestrator_factory(
            str(client.user.id), _dispatch_fn(client), build_roster_fn(client), client.user.display_name
        )
        state["orchestrator"] = orchestrator
        client.mulca_orchestrator = orchestrator  # so run_discord_bot.py can save a snapshot after client.run() returns
        await orchestrator.load_group_snapshot()
        print(f"MULCA text bot logged in as {client.user} (id={client.user.id})")

    @client.event
    async def on_message(message: discord.Message):
        # Logged before any filtering -- otherwise a message dropped by the
        # bot-account filter or the channel-id filter leaves literally no
        # trace anywhere, which is exactly the kind of gap that hides why a
        # participant silently never shows up. TODO: remove once live-tested.
        print(
            f"[MULCA debug] on_message: author_id={message.author.id} "
            f"is_bot={message.author.bot} display_name={message.author.display_name!r} "
            f"channel_id={message.channel.id} content={message.content!r}"
        )
        if message.author.bot:
            print(f"[MULCA debug] ignoring: author {message.author.id} is a bot account")
            return
        is_dm = isinstance(message.channel, discord.DMChannel)
        # The channel-id filter only applies to the group's registered
        # channels -- a DM is never in that set (it's a different Discord
        # object entirely), and should always be let through. Without this
        # carve-out, every DM would be silently dropped here, the same way an
        # unregistered guild channel is.
        if not is_dm and channel_ids and str(message.channel.id) not in channel_ids:
            print(f"[MULCA debug] ignoring: channel {message.channel.id} not in MULCA_CHANNEL_IDS={channel_ids}")
            return
        orchestrator = state["orchestrator"]
        if orchestrator is None:
            return
        event = ConversationEvent(
            speaker_id=str(message.author.id),
            modality="text",
            content=message.content,
            timestamp=time.time(),
            channel_id=str(message.channel.id),
            speaker_display_name=message.author.display_name,
            is_dm=is_dm,
        )
        await orchestrator.enqueue(event)

    return client


def build_roster_fn(client: discord.Client):
    """Known-participants lookup ({user_id: display_name}), passed to
    Orchestrator so trigger-variable computation can recognize a participant
    who is present but hasn't spoken yet (BLUEPRINT.md §7.6's roster question
    -- a minimal version of it: presence, not full team-role metadata).

    Note: `channel.members` reflects this client's member cache, which may be
    incomplete without the "Server Members Intent" privileged intent enabled
    (same portal toggle as Message Content Intent) -- if the roster looks
    empty or partial, that's the first thing to check.
    """
    async def get_roster(channel_id: str) -> dict:
        channel = client.get_channel(int(channel_id))
        if channel is None:
            channel = await client.fetch_channel(int(channel_id))
        members = getattr(channel, "members", [])
        return {str(m.id): m.display_name for m in members if not m.bot}

    return get_roster


def _dispatch_fn(client: discord.Client):
    async def dispatch(channel_id: str, chunk_iterator):
        channel = client.get_channel(int(channel_id))
        if channel is None:
            channel = await client.fetch_channel(int(channel_id))

        buffer = ""
        sent_message = None
        last_edit = time.monotonic()

        async for chunk in chunk_iterator:
            buffer += chunk
            if sent_message is None:
                sent_message = await channel.send(buffer)
                last_edit = time.monotonic()
                continue
            # Throttle edits so we forward the stream without hitting Discord's
            # rate limits (BLUEPRINT.md "Technical constraints" -- forward
            # partial output as it streams rather than buffering the full
            # completion first).
            if time.monotonic() - last_edit > 0.75:
                await sent_message.edit(content=buffer)
                last_edit = time.monotonic()

        if sent_message is None:
            return  # main LLM produced no output
        if sent_message.content != buffer:
            await sent_message.edit(content=buffer)

    return dispatch
