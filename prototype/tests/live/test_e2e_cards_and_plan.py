"""
Cross-channel e2e, part 2: cards and the plan (LIVE_TESTS.md, C1-C11, P1-P8).

A card made anywhere shows everywhere; the first valid click anywhere closes it
everywhere with who answered; what changes the plan on one side is the web
space's plan on every side.
"""

from __future__ import annotations

import pytest

from mulca_discord.slack.hub import SlackHub

from .harness import SCRIPTED, SCRIPTED_JUDGE, Group, slack_buttons, slack_status, slack_text, until

pytestmark = pytest.mark.e2e
# Which proactive card fires is the judge's call: scripted here, the real one's with CADENCE_MUCA_URL.
needs_scripted_judge = pytest.mark.skipif(not SCRIPTED_JUDGE, reason="which card fires is the real judge's call; see LIVE_TESTS.md")

ASSIGNMENT = "Survey on how students get to school. Report and slides by 2 Dec 2026, demo on 14 Dec 2026."


async def charter_everywhere(group: Group) -> tuple[dict, object, dict]:
    """Ada pastes the assignment on the web: the charter card on the web, Discord and Slack."""
    answer = await group.web_command("Ada", "kickoff", text=ASSIGNMENT)
    assert answer["ok"], answer
    web = await group.web_card("Ada", lambda p: p["kind"] == "charter")
    discord = group.discords[0][2]
    await until(lambda: discord.cards and group.slack.cards, what="the charter card on Discord and Slack")
    return web, discord.cards[-1], group.slack.cards[-1]


# -- Cards ---------------------------------------------------------------------


async def test_C01_a_card_made_on_the_web_shows_on_discord_and_slack(group: Group):
    web, on_discord, on_slack = await charter_everywhere(group)
    assert on_discord.embed["title"] == "Cadence · Project charter"
    assert "Cadence · Project charter" in slack_text(on_slack)
    assert {b["custom_id"].split(":")[1] for b in on_discord.buttons} == {"confirm", "reject"}
    assert {a.split(":")[1] for a in slack_buttons(on_slack)} == {"confirm", "reject"}
    assert on_discord.buttons[0]["custom_id"].endswith(web["proposal_id"])


async def test_C02_confirmed_on_discord_is_confirmed_on_slack_and_the_web(group: Group):
    web, on_discord, on_slack = await charter_everywhere(group)
    assert await group.discord_click("Chiara", on_discord, "confirm") == "Confirmed and saved."
    await group.web_card("Ada", lambda p: p["proposal_id"] == web["proposal_id"] and p["status"] == "applied")
    await until(lambda: slack_status(on_slack) == "✓ Confirmed by Chiara", what="Slack card confirmed")
    assert on_discord.footer == "✓ Confirmed by Chiara" and on_discord.buttons == []
    assert slack_buttons(on_slack) == []


async def test_C03_confirmed_on_slack_is_confirmed_on_discord_and_the_web(group: Group):
    web, on_discord, on_slack = await charter_everywhere(group)
    assert await group.slack_click("Dario", on_slack, "confirm") == "Confirmed and saved."
    await until(lambda: on_discord.footer == "✓ Confirmed by Dario", what="Discord card confirmed")
    applied = await group.web_card("Bruno", lambda p: p["proposal_id"] == web["proposal_id"] and p["status"] == "applied")
    assert applied["names"][str(applied["resolved_by"])] == "Dario"


async def test_C04_confirmed_on_the_web_is_confirmed_on_discord_and_slack(group: Group):
    web, on_discord, on_slack = await charter_everywhere(group)
    assert (await group.web_click("Bruno", web["proposal_id"], "confirm"))["ok"]
    await until(lambda: on_discord.footer.startswith("✓ Confirmed by Bruno"), what="Discord card confirmed by Bruno")
    await until(lambda: slack_status(on_slack).startswith("✓ Confirmed by Bruno"), what="Slack card confirmed by Bruno")


async def test_C05_rejected_anywhere_says_who_turned_it_down_everywhere(group: Group):
    web, on_discord, on_slack = await charter_everywhere(group)
    await group.slack_click("Dario", on_slack, "reject")
    await until(lambda: on_discord.footer == "✕ Turned down by Dario", what="Discord card rejected")
    rejected = await group.web_card("Ada", lambda p: p["proposal_id"] == web["proposal_id"] and p["status"] == "rejected")
    assert rejected["names"][str(rejected["resolved_by"])] == "Dario"
    assert (await group.web_state("Ada"))["charter"] is None  # nothing saved


async def test_C06_the_first_valid_click_wins(group: Group):
    web, on_discord, on_slack = await charter_everywhere(group)
    # Dario's Slack still shows the buttons when he presses one, a moment after Chiara.
    reject = next(a for a in slack_buttons(on_slack) if ":reject:" in a)
    assert await group.discord_click("Chiara", on_discord, "confirm") == "Confirmed and saved."
    late = await group.hub.on_action(group.slack.channel, group.slack_user("Dario"), reject, "1")
    assert late == "This card was already applied."
    assert not (await group.web_click("Ada", web["proposal_id"], "reject"))["ok"]
    assert (await group.web_state("Ada"))["charter"]["confirmed_by"] == 9003


async def test_C07_a_stranger_cannot_answer_a_card(group: Group):
    _, _, on_slack = await charter_everywhere(group)
    action = next(a for a in slack_buttons(on_slack) if ":confirm:" in a)
    said = await group.hub.on_action(group.slack.channel, "U0STRANGER", action, "1")
    assert said == "Only members of this group can use the coordinator here."
    assert slack_status(on_slack).startswith("Waiting")


@needs_scripted_judge
async def test_C08_a_card_cadence_proposes_from_discord_chat_reaches_everyone(group: Group):
    """The demo video: printing came up on Discord, nobody took it; Ada takes it there."""
    await group.same_person_everywhere("Ada")
    for who, text in [("Chiara", "class 3B gave us 25 paper forms back"), ("Chiara", "typing them into the sheet now"),
                      ("Bruno", "not me, I'm finishing the sources"), ("Ada", "we also need the results printed for the charts")]:
        await group.discord_say(who, text)
    discord = group.discords[0][2]
    await until(lambda: any(c.embed["title"] == "Cadence · Owner and date · Ownership" for c in discord.cards), what="CS5 card on Discord")
    card = next(c for c in discord.cards if "Owner and date" in c.embed["title"])
    # Ada said she is the web's Ada (/coordinator me): one member, written by name everywhere.
    title = card.fields["Task"]
    assert "print" in title.lower()  # the real model words it its own way
    await until(lambda: any("Owner and date" in slack_text(c) for c in group.slack.cards), what="CS5 card on Slack")
    on_slack = next(c for c in group.slack.cards if "Owner and date" in slack_text(c))
    button = "confirm" if any(":confirm:" in b["custom_id"] for b in card.buttons) else "take"
    said = await group.discord_click("Ada", card, button)
    assert said.startswith("Saved") or said.startswith("Confirmed"), said
    await until(lambda: slack_status(on_slack) == "✓ Confirmed by Ada", what="Slack: Confirmed by Ada")
    state = await group.web_state("Bruno")
    task = next(t for t in state["tasks"] if t["title"] == title)
    assert task["owner_id"] == group.web_ids["Ada"]
    if SCRIPTED:
        assert title == "Print the survey results" and card.fields["Suggested owner"] == "Ada"


@needs_scripted_judge
async def test_C09_a_decision_closed_on_slack_is_in_the_decision_log(group: Group):
    for who, text in [("Dario", "for the user test: interviews or a questionnaire?"),
                      ("Ada", "SUS is faster and gives a number"),
                      ("Dario", "but think-aloud shows why people get stuck")]:
        await group.slack_say(who, text)
    await until(lambda: any("Close the decision" in slack_text(c) for c in group.slack.cards), what="CS3 card on Slack")
    card = next(c for c in group.slack.cards if "Close the decision" in slack_text(c))
    assert {a.split(":")[1] for a in slack_buttons(card)} >= {"choose0", "choose1", "why", "not_now"}
    first_option = next(e["text"]["text"] for b in card["blocks"] if b["type"] == "actions" for e in b["elements"] if ":choose0:" in e["action_id"])
    await group.slack_click("Dario", card, "choose0")
    decisions = (await group.web_state("Ada"))["decisions"]
    assert decisions and decisions[-1]["choice"] == first_option
    on_discord = next(c for c in group.discords[0][2].cards if "Close the decision" in c.embed["title"])
    await until(lambda: on_discord.footer.startswith("✓ Confirmed by Dario"), what="Discord decision closed")


@needs_scripted_judge
async def test_C10_not_now_on_discord_silences_the_card_everywhere(group: Group):
    # DEMO_SCRIPT.md step 4: details one person could settle, discussed by everyone.
    for who, text in [("Ada", "Arial or Helvetica for the report?"), ("Bruno", "Helvetica, and margins at 2.5 cm"),
                      ("Ada", "no, 2 cm, the template says so"), ("Chiara", "let's check the template again"),
                      ("Bruno", "and the font size of the captions? 10 pt or 9?")]:
        await group.discord_say(who, text)
    discord = group.discords[0][2]
    await until(lambda: any("One person can do this" in c.embed["title"] for c in discord.cards), what="CS2 card")
    card = next(c for c in discord.cards if "One person can do this" in c.embed["title"])
    await group.discord_click("Bruno", card, "not_now")
    # Bruno on Discord and Bruno on the web never said they are one person: "Bruno (Discord)".
    await until(lambda: card.footer.startswith("◷ Not now (Bruno (Discord))"), what="snoozed on Discord")
    on_slack = next(c for c in group.slack.cards if "One person can do this" in slack_text(c))
    await until(lambda: slack_status(on_slack).startswith("◷ Not now (Bruno (Discord))"), what="snoozed on Slack")


@needs_scripted_judge
async def test_C11_why_on_slack_shows_the_messages_from_discord(group: Group):
    await group.discord_say("Chiara", "we must fix the font size in the report")
    await until(lambda: any("One person can do this" in slack_text(c) for c in group.slack.cards), what="CS2 card on Slack")
    card = next(c for c in group.slack.cards if "One person can do this" in slack_text(c))
    why = await group.slack_click("Dario", card, "why")
    assert "Delegate simple tasks (CS2)" in why and "we must fix the font size in the report" in why


async def test_C12_a_slack_channel_that_restarted_still_gets_the_cards(group: Group):
    await group.hub.close()
    group.hub = SlackHub(group.slack, group.stack.muca_url)  # the bot restarted; nobody wrote on Slack since
    assert await group.hub.warm_up() == [group.slack.channel]
    before = len(group.slack.cards)
    await charter_everywhere(group)
    assert len(group.slack.cards) == before + 1


async def test_C13_two_discord_channels_of_one_space_both_get_the_card(group: Group):
    second = await group.discord(channel_id=4299)
    await group.discord_say("Ada", f"{group.stack.http}/join/{group.code}", channel=second)
    await until(lambda: any("Linked to the web space" in line for line in second.lines), what="second channel linked")
    await charter_everywhere(group)
    await until(lambda: second.cards, what="the card in the second Discord channel")
    assert second.cards[-1].embed["title"] == group.discords[0][2].cards[-1].embed["title"]


# -- The plan ------------------------------------------------------------------


async def test_P01_a_task_added_on_discord_is_in_the_web_plan(group: Group):
    assert (await group.discord_command("Chiara", "task", add="Collect the paper forms", due="2026-11-28"))["ok"]
    state = await group.web_state("Ada")
    assert [(t["title"], t["due_date"]) for t in state["tasks"]] == [("Collect the paper forms", "2026-11-28")]


async def test_P02_a_dependency_set_on_slack_is_in_the_web_plan(group: Group):
    for title in ("Collect the paper forms", "Type the forms in", "Make the charts"):
        assert "Task added" in await group.slack_command("Dario", f"task add {title}")
    await group.slack_command("Dario", "task 3 waits on 1, 2")
    tasks = (await group.web_state("Ada"))["tasks"]
    assert sorted(tasks[2]["depends_on"]) == sorted([tasks[0]["task_id"], tasks[1]["task_id"]])


async def test_P03_a_status_set_on_the_web_shows_in_the_discord_plan(group: Group):
    await group.web_command("Ada", "task", add="Book the lab")
    assert (await group.web_command("Ada", "task", task="1", status="doing"))["ok"]
    on_discord = (await group.discord_command("Chiara", "state"))["state"]
    assert on_discord["tasks"][0]["status"] == "doing"
    assert "1. Book the lab · doing" in await group.slack_command("Dario", "plan")


async def test_P04_task_numbers_stay_put_when_tasks_are_added(group: Group):
    for title in ("Alpha", "Bravo", "Charlie", "Delta"):
        await group.web_command("Ada", "task", add=title)
    await group.slack_command("Dario", "task 2 done")
    await group.discord_command("Chiara", "task", add="Echo")
    await group.slack_command("Dario", "task 3 doing")
    tasks = (await group.web_state("Bruno"))["tasks"]
    assert [(t["title"], t["status"]) for t in tasks] == [
        ("Alpha", "todo"), ("Bravo", "done"), ("Charlie", "doing"), ("Delta", "todo"), ("Echo", "todo"),
    ]


async def test_P05_a_plan_asked_on_slack_is_confirmed_on_the_web(group: Group):
    said = await group.slack_command("Dario", "planning Collect the forms; Type them in; Make the charts")
    assert "Not done" not in said
    plan = await group.web_card("Ada", lambda p: p["kind"] == "plan")
    await until(lambda: any(c.embed["title"].startswith("Cadence · Plan") for c in group.discords[0][2].cards), what="plan card on Discord")
    assert (await group.web_click("Ada", plan["proposal_id"], "confirm"))["ok"]
    titles = [t["title"] for t in (await group.web_state("Bruno"))["tasks"]]
    assert titles == ["Collect the forms", "Type them in", "Make the charts"]


async def test_P06_a_check_in_from_discord_answers(group: Group):
    await group.web_command("Ada", "task", add="Late task", due="2026-01-10")
    answer = await group.discord_command("Chiara", "checkin")
    assert answer is not None and answer.get("event") in ("coordinator_notice", "coordinator_state")


@pytest.mark.skipif(SCRIPTED_JUDGE, reason="the scripted policy keeps no chat log; the real one logs every turn (policy.py)")
async def test_P07_catch_up_on_slack_tells_what_was_said_on_discord(group: Group):
    await group.discord_say("Chiara", "the printer on floor 2 works again")
    said = await group.slack_command("Dario", "catchup")
    assert "On Discord" in said and "the printer on floor 2 works again" in said


async def test_P08_the_voice_transcript_answers_even_when_nobody_spoke(group: Group):
    answer = await group.discord_command("Chiara", "transcript", minutes=30)
    assert answer["ok"] and answer["text"] == "Nothing was said in the voice call in the last 30 minutes."
