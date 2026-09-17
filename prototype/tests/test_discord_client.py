"""
The roster MULCA sends MUCA-Server has to actually reflect who's present,
including anyone who hasn't spoken yet -- that's what feeds trigger-variable
seeding (compute_trigger_variables, on the MUCA-Server side) so a quiet
participant is visible before their first message.
"""

from mulca_discord.discord_client import _roster


class FakeMember:
    def __init__(self, id: int, display_name: str, *, bot: bool = False) -> None:
        self.id = id
        self.display_name = display_name
        self.bot = bot


class FakeChannel:
    def __init__(self, members: list[FakeMember]) -> None:
        self.members = members


async def test_roster_lists_every_present_member_by_id():
    channel = FakeChannel(
        [FakeMember(1, "Ada"), FakeMember(2, "Grace")],
    )

    roster = await _roster(channel)

    assert roster == {1: "Ada", 2: "Grace"}


async def test_roster_excludes_bot_accounts():
    channel = FakeChannel(
        [FakeMember(1, "Ada"), FakeMember(9, "MULCA", bot=True)],
    )

    roster = await _roster(channel)

    assert 9 not in roster
    assert roster == {1: "Ada"}


async def test_roster_is_empty_without_a_members_list():
    # A DM channel (or the Server Members Intent being off) has no .members
    # -- this must not raise, just report nobody present.
    class ChannelWithNoMembers:
        pass

    roster = await _roster(ChannelWithNoMembers())

    assert roster == {}
