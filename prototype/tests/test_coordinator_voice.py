"""/coordinator voice and /coordinator transcript on Discord (coordinator/bridge.py, commands.py)."""

from __future__ import annotations

from types import SimpleNamespace

from mulca_discord.coordinator.bridge import CoordinatorBridge
from mulca_discord.coordinator.texts import channel_name
from mulca_discord.links import Link


class Store:
    def __init__(self, problems=()) -> None:
        self.problems = list(problems)
        self.saved: list[Link] = []

    def conflicts(self, link):
        return self.problems

    def save(self, link, created_by=None):
        self.saved.append(link)
        return None


def world(problems=()):
    link = Link(text_channel_id=42, guild_id=1, bot_id=7, post_voice_transcripts=True, allow_dms=True)
    applied = []

    async def apply_link(new, previous):
        applied.append(new)

    bot = SimpleNamespace(store=Store(problems), apply_link=apply_link)
    manager = SimpleNamespace(link_for_channel=lambda channel_id: (bot, link) if channel_id == 42 else None)
    interaction = SimpleNamespace(channel=SimpleNamespace(id=42), user=SimpleNamespace(id=9001), guild_id=1)
    return CoordinatorBridge(manager), bot, applied, interaction


async def test_voice_listens_to_the_call_in_ambient_and_keeps_the_rest_of_the_link():
    bridge, bot, applied, interaction = world()
    said = await bridge.serve_voice(interaction, SimpleNamespace(id=555, mention="<#555>"))
    (saved,) = bot.store.saved
    assert saved.voice_channel_id == 555 and saved.listening_mode == "ambient"
    assert saved.text_channel_id == 42 and saved.post_voice_transcripts and saved.allow_dms
    assert applied == [saved]
    assert "Cadence now listens to <#555>" in said and "/coordinator transcript" in said


async def test_voice_explains_a_conflict_and_changes_nothing():
    bridge, bot, applied, interaction = world(["That voice channel already belongs to another text channel."])
    said = await bridge.serve_voice(interaction, SimpleNamespace(id=555, mention="<#555>"))
    assert said.startswith("Cadence cannot listen to that call:")
    assert bot.store.saved == [] and applied == []


def test_spoken_lines_have_their_own_tag():
    assert channel_name("discord_voice") == "Discord voice"
