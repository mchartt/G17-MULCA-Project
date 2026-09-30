"""
The Discord half of the adapter.

Everything here is unchanged in spirit from the old (deleted) discord_adapter
module: bot-author filtering, DM detection, the roster-from-channel.members
lookup. What changed is what it's wired to -- a MUCA-Server session per
scope (sessions.py) instead of an in-process Orchestrator, and scoping is
driven by the configured MulcaInstance list (instances.py): an instance's
text channel and its paired voice channel share one scope, one memory.

Voice: whenever someone is in an instance's voice channel, MULCA is there
too, listening (voice/). It leaves when the channel empties.
"""

from __future__ import annotations

import logging

import discord

from .instances import (
    MulcaInstance,
    instance_for_channel,
    instance_for_participant,
)
from .sessions import Scope, SessionRegistry

logger = logging.getLogger(__name__)


async def _roster(channel: discord.abc.Messageable) -> dict[int, str]:
    members = getattr(channel, "members", [])
    return {member.id: member.display_name for member in members if not member.bot}


def _humans(channel) -> list:
    return [
        member
        for member in getattr(channel, "members", [])
        if not member.bot
    ]


def mulca_intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.message_content = True
    # Needed for channel.members / _roster to see participants who haven't
    # spoken yet -- also requires the "Server Members Intent" toggle enabled
    # in the Discord Developer Portal.
    intents.members = True
    # Who joins and leaves the voice channels (on by default; explicit here
    # because voice depends on it).
    intents.voice_states = True
    return intents


def build_discord_client(
    *,
    muca_server_url: str,
    instances: list[MulcaInstance],
    registry: SessionRegistry | None = None,
) -> discord.Client:
    """
    `client.mulca_sessions` holds the MUCA-Server session of each scope (a
    MulcaInstance's conversation_id, or "dm:<user_id>"), opened lazily on
    first use and reopened if MUCA-Server went away.
    """

    client = discord.Client(intents=mulca_intents())
    registry = registry or SessionRegistry(muca_server_url)
    client.mulca_sessions = registry
    client.mulca_voice = {}

    def instance_roster(instance: MulcaInstance) -> dict[int, str]:
        """Everyone in the instance's text channel or its voice channel."""

        roster: dict[int, str] = {}
        for channel_id in (instance.text_channel_id, instance.voice_channel_id):
            channel = client.get_channel(channel_id) if channel_id else None
            for member in _humans(channel):
                roster[member.id] = member.display_name

        return roster

    # ------------------------------------------------------------------
    # Voice
    # ------------------------------------------------------------------

    async def join_voice(instance: MulcaInstance) -> None:
        from discord.ext import voice_recv

        from .voice import VoiceBridge

        if instance.name in client.mulca_voice:
            return

        channel = client.get_channel(instance.voice_channel_id)
        if channel is None:
            logger.warning(
                "Voice channel %s of %s not found",
                instance.voice_channel_id,
                instance.name,
            )
            return

        logger.info("Joining voice channel %s for %s", channel, instance.name)
        voice_client = await channel.connect(cls=voice_recv.VoiceRecvClient)

        bridge = VoiceBridge(
            scope=Scope(conversation_id=instance.conversation_id),
            registry=registry,
            voice_client=voice_client,
            reply_channel=client.get_channel(instance.text_channel_id),
            post_voice_transcripts=instance.post_voice_transcripts,
            roster=lambda: instance_roster(instance),
        )
        client.mulca_voice[instance.name] = bridge
        await bridge.start()

    async def leave_voice(instance: MulcaInstance) -> None:
        bridge = client.mulca_voice.pop(instance.name, None)
        if bridge is None:
            return

        logger.info("Leaving the voice channel of %s", instance.name)
        await bridge.disconnect()

    async def sync_voice(instance: MulcaInstance) -> None:
        channel = client.get_channel(instance.voice_channel_id)
        if _humans(channel):
            await join_voice(instance)
        else:
            await leave_voice(instance)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    @client.event
    async def on_ready() -> None:
        logger.info(
            "MULCA bot logged in as %s (id=%s)",
            client.user,
            client.user.id,
        )

        for instance in instances:
            if instance.voice_channel_id is not None:
                try:
                    await sync_voice(instance)
                except Exception:
                    logger.exception("Could not join voice for %s", instance.name)

    @client.event
    async def on_voice_state_update(member, before, after) -> None:
        if member.bot:
            return

        touched = {
            channel.id
            for channel in (before.channel, after.channel)
            if channel is not None
        }

        for instance in instances:
            if instance.voice_channel_id not in touched:
                continue

            try:
                await sync_voice(instance)
            except Exception:
                logger.exception("Could not update voice for %s", instance.name)
                continue

            bridge = client.mulca_voice.get(instance.name)
            if bridge is None:
                continue

            if (
                before.channel is not None
                and before.channel.id == instance.voice_channel_id
                and (after.channel is None or after.channel.id != before.channel.id)
            ):
                bridge.forget(member.id)

            await bridge.update_participants()

    @client.event
    async def on_message(message: discord.Message) -> None:
        logger.debug(
            "on_message: author_id=%s is_bot=%s channel_id=%s content=%r",
            message.author.id,
            message.author.bot,
            message.channel.id,
            message.content,
        )

        if message.author.bot or not message.content:
            return

        is_dm = isinstance(message.channel, discord.DMChannel)
        instance: MulcaInstance | None = None

        if is_dm:
            # Answering is permissive by design (BLUEPRINT.md: "open to DMs
            # from any individual user") -- participant_ids doesn't gate
            # that. It does gate one-way read access to a group's memory:
            # a recognized participant's DM gets it, a stranger's doesn't.
            linked_instance = instance_for_participant(
                instances, message.author.id
            )
            scope = Scope(
                conversation_id=f"dm:{message.author.id}",
                is_dm=True,
                linked_conversation_id=(
                    linked_instance.conversation_id
                    if linked_instance is not None
                    else None
                ),
            )
        else:
            instance = instance_for_channel(instances, message.channel.id)
            if instance is None:
                # Not a channel any configured MulcaInstance owns.
                return
            scope = Scope(conversation_id=instance.conversation_id)

        roster = instance_roster(instance) if instance is not None else {}
        if instance is not None and not roster:
            roster = await _roster(message.channel)

        async def send(muca_client) -> None:
            if instance is not None:
                await muca_client.send_participants(roster)

            await muca_client.send_user_text(
                speaker=message.author.id,
                speaker_name=message.author.display_name,
                text=message.content,
            )

        try:
            await registry.run(
                scope,
                send,
                reply_channel=message.channel,
                post_voice_transcripts=(
                    instance.post_voice_transcripts if instance else False
                ),
                # A text message triggers a real cognitive turn -- unlike
                # voice's continuous frames, resending it on a reconnect
                # risks two independent replies to the same message (see
                # SessionRegistry.run's docstring). Drop it instead; the
                # next message reopens the session normally.
                retry_once=False,
            )
        except ConnectionError:
            logger.exception(
                "MUCA-Server is unreachable; dropping a message for %s",
                scope.conversation_id,
            )

    return client


async def close_all_sessions(client: discord.Client) -> None:
    for bridge in list(client.mulca_voice.values()):
        await bridge.disconnect()
    client.mulca_voice.clear()

    await client.mulca_sessions.close_all()
