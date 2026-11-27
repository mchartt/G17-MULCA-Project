"""
Cross-channel e2e, part 1: linking, identity and chat in sync (LIVE_TESTS.md, L1-L14).

One web space, its Discord and Slack channels. Each test says what a person
would see on each side; harness.py says what is real in this run.
"""

from __future__ import annotations

import pytest

from .harness import Group, SCRIPTED, stamp, until

pytestmark = pytest.mark.e2e


# -- Linking ---------------------------------------------------------------


async def test_L01_pasting_the_invite_link_links_discord_and_slack(group: Group):
    discord = group.discords[0][2]
    assert any("Linked to the web space" in line for line in discord.lines)
    assert any("/coordinator voice" in line for line in discord.lines)  # the next step, once
    assert any("Linked to the web space" in line for line in group.slack.lines)
    # Both channels now read the web space's project.
    assert (await group.discord_command("Ada", "state"))["state"]["charter"] is None
    assert "No charter yet" in await group.slack_command("Bruno", "plan")


async def test_L02_a_wrong_invite_link_is_explained_and_links_nothing(bare: Group):
    await bare.web_member("Ada")
    await bare.discord()
    await bare.slack_channel()
    await bare.discord_say("Ada", f"{bare.stack.http}/join/ZZZZZZZZ")
    await bare.slack_say("Bruno", f"{bare.stack.http}/join/ZZZZZZZZ")
    await until(lambda: bare.discords[0][2].lines and bare.slack.lines, what="both answers")
    assert "No web space" in bare.discords[0][2].lines[-1]
    assert "No web space" in bare.slack.lines[-1]
    tag = stamp()
    await bare.web_say("Ada", f"not linked {tag}")
    await bare.web_command("Ada", "state")
    assert not any(tag in line for line in bare.discords[0][2].lines + bare.slack.lines)


async def test_L03_a_bare_word_never_links_a_channel(bare: Group):
    await bare.web_member("Ada")
    await bare.slack_channel()
    await bare.slack_say("Bruno", f"the code is {bare.code}, see you")
    assert not any("Linked" in line for line in bare.slack.lines)


async def test_L04_unlink_gives_the_channel_its_own_plan_back_and_stops_the_copies(group: Group):
    await group.web_command("Ada", "kickoff", text="Deliver the survey report by 2 Dec.")
    await group.web_card("Ada")
    assert (await group.slack_command("Bruno", "unlink")).startswith("Unlinked")
    assert "No charter yet" in await group.slack_command("Bruno", "plan")
    tag = stamp()
    await group.web_say("Ada", f"after unlink {tag}")
    await group.web_command("Ada", "state")
    assert not any(tag in line for line in group.slack.lines)


# -- One person, one member ---------------------------------------------------


async def test_L05_the_same_person_on_web_discord_and_slack_is_one_member(group: Group):
    await group.same_person_everywhere("Ada", "Bruno")
    names = (await group.web_state("Ada"))["names"]
    assert sorted(set(names.values())) == ["Ada", "Bruno", "Chiara", "Dario"]
    # Bruno's line from Slack shows on the web as the web's Bruno (same id, same avatar).
    tag = stamp()
    await group.slack_say("Bruno", f"hello from slack {tag}")
    seen = await group.tabs["Ada"].wait_for(lambda e: e.get("type") == "message" and tag in e["message"]["text"])
    assert seen["message"]["author"] == {"id": group.web_ids["Bruno"], "name": "Bruno"}


async def test_L06_two_different_people_with_one_name_get_two_names(group: Group):
    # Ada on the web and Ada on Discord never said they are the same person.
    names = set((await group.web_state("Ada"))["names"].values())
    assert {"Ada (Web)", "Ada (Discord)"} <= names
    assert "Ada" not in names


async def test_L07_a_personal_code_works_once(group: Group):
    code = await group._personal_code("Ada")
    assert (await group.discord_command("Ada", "me", code=code))["ok"]
    assert "not valid" in await group.slack_command("Ada", f"me {code}")


# -- Chat in sync ---------------------------------------------------------------


async def test_L08_web_chat_shows_on_discord_and_slack(group: Group):
    tag = stamp()
    await group.web_say("Ada", f"lab booked for Tuesday {tag}")
    await until(lambda: any(f"Web: lab booked for Tuesday {tag}" in line for line in group.discords[0][2].lines), what="on Discord")
    await until(lambda: any(f"Web: lab booked for Tuesday {tag}" in line for line in group.slack.lines), what="on Slack")


async def test_L09_discord_chat_shows_on_the_web_and_slack(group: Group):
    tag = stamp()
    await group.discord_say("Chiara", f"25 paper forms are back {tag}")
    seen = await group.tabs["Bruno"].wait_for(lambda e: e.get("type") == "message" and tag in e["message"]["text"])
    assert seen["message"]["channel"] == "discord" and seen["message"]["author"]["name"] == "Chiara"
    await until(lambda: any(f"Chiara* · Discord: 25 paper forms are back {tag}" in line for line in group.slack.lines), what="on Slack")


async def test_L10_slack_chat_shows_on_the_web_and_discord(group: Group):
    tag = stamp()
    await group.slack_say("Dario", f"sources are final {tag}")
    seen = await group.tabs["Ada"].wait_for(lambda e: e.get("type") == "message" and tag in e["message"]["text"])
    assert seen["message"]["channel"] == "slack" and seen["message"]["author"]["name"] == "Dario"
    await until(lambda: any(f"Dario** · Slack: sources are final {tag}" in line for line in group.discords[0][2].lines), what="on Discord")


async def test_L11_a_line_never_comes_back_to_where_it_was_written(group: Group):
    tag = stamp()
    await group.discord_say("Chiara", f"only once {tag}")
    await group.slack_say("Dario", f"only once too {tag}")
    await until(lambda: any(tag in line for line in group.discords[0][2].lines), what="Slack's line on Discord")
    assert not any(f"Discord: only once {tag}" in line for line in group.discords[0][2].lines)
    assert not any(f"Slack: only once too {tag}" in line for line in group.slack.lines)


async def test_L12_slack_shows_special_characters_as_written(group: Group):
    await group.web_say("Ada", "R&D <-> UI: done")
    await until(lambda: any("R&amp;D &lt;-&gt; UI: done" in line for line in group.slack.lines), what="escaped line on Slack")


async def test_L13_cadences_answer_on_discord_reaches_the_web_and_slack(group: Group):
    tag = stamp()
    await group.discord_say("Chiara", f"Cadence, who is doing the slides? {tag}")
    await until(lambda: any("Cadence" in line and "Discord:" in line for line in group.slack.lines), what="Cadence's answer on Slack")
    seen = await group.tabs["Ada"].wait_for(
        lambda e: e.get("type") == "message" and e["message"]["channel"] == "discord" and (e["message"]["author"] or {}).get("name") == "Cadence"
    )
    assert seen["message"]["text"]


async def test_L14_three_channels_one_conversation_in_order(group: Group):
    """The demo video's chat: each side sees the other two, in the order they were written."""
    tag = stamp()
    lines = [("discord", "Chiara", "class 3B gave us 25 forms"), ("slack", "Dario", "typing them in now"), ("web", "Ada", "great, charts next")]
    for where, who, text in lines:  # people write a few seconds apart: each line lands before the next
        await {"discord": group.discord_say, "slack": group.slack_say, "web": group.web_say}[where](who, f"{text} {tag}")
        await group.tabs["Bruno"].wait_for(lambda e, t=f"{text} {tag}": e.get("type") == "message" and e["message"]["text"] == t)
    await until(lambda: sum(tag in m["text"] for m in group.web_messages("Bruno")) == 3,
                what=f"all three on the web, got {[m['text'] for m in group.web_messages('Bruno') if tag in m['text']]}")
    on_web = [m["text"] for m in group.web_messages("Bruno") if tag in m["text"]]
    assert on_web == [f"{text} {tag}" for _, _, text in lines]
    if SCRIPTED:
        assert len([line for line in group.discords[0][2].lines if tag in line]) == 2  # Slack's and the web's
