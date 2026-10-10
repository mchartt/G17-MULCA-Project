"""
The AUI course setup MULCA sends MUCA-Server's main agent: aui/ (persona,
task, knowledge, schedule) and main_instructions.
"""

import re
from datetime import date

import pytest

from mulca_discord.aui import (
    COHORT_A_TEAMS,
    KNOWLEDGE_DIR,
    cohort_for_channel,
    load_knowledge,
    load_schedule,
    main_instructions,
    next_deliverables,
    render_schedule,
)

SCHEDULE = load_schedule()

REQUIREMENTS = "initial user requirements analysis"
UX = "initial UX design (with scenarios)"
REFINED = "refined UX design"
PROTOTYPING = "initial prototyping, at the following tutoring"


@pytest.mark.parametrize(
    ("today", "group_a", "group_b"),
    [
        (date(2026, 10, 7), f"{REQUIREMENTS}", f"{REQUIREMENTS}"),
        (date(2026, 10, 19), "Mon 19 Oct 2026", "Wed 28 Oct 2026"),  # due today (A)
        (date(2026, 10, 15), REQUIREMENTS, f"{UX}, at the tutoring on Wed 28 Oct"),
        (date(2026, 10, 27), REFINED, f"{UX}, at the tutoring on Wed 28 Oct"),
        (date(2026, 11, 3), PROTOTYPING, f"{REFINED}"),
        (date(2026, 11, 10), PROTOTYPING, PROTOTYPING),
    ],
)
def test_each_group_is_told_its_own_next_deliverable(today, group_a, group_b):
    a, b = next_deliverables(SCHEDULE, today).split("; cohort B: ")

    assert group_a in a
    assert group_b in b


def test_cohort_for_channel_matches_the_team_number():
    for team in COHORT_A_TEAMS:
        assert cohort_for_channel(f"group-{team}") == "A"
    assert cohort_for_channel("group-2") == "B"  # not in COHORT_A_TEAMS
    assert cohort_for_channel("group-99") == "B"  # unknown team -> still B
    assert cohort_for_channel("GROUP-4") == "A"  # case-insensitive
    assert cohort_for_channel("group_4") == "A"  # underscore variant
    assert cohort_for_channel("general") is None
    assert cohort_for_channel("") is None


def test_next_deliverables_scoped_to_one_cohort_is_unambiguous():
    today = date(2026, 10, 13)

    scoped_a = next_deliverables(SCHEDULE, today, cohort="A")
    scoped_b = next_deliverables(SCHEDULE, today, cohort="B")

    assert REQUIREMENTS in scoped_a and "Mon 19 Oct 2026" in scoped_a
    assert REQUIREMENTS in scoped_b and "Wed 14 Oct 2026" in scoped_b
    # Neither mentions the other cohort's own, unrelated deadline.
    assert "Group" not in scoped_a and "Group" not in scoped_b


def test_the_instructions_name_the_channels_own_cohort_and_deliverable():
    today = date(2026, 10, 13)

    for_a = main_instructions(today=today, channel_name="group-4")  # cohort A

    assert "This channel's team is in tutoring cohort A" in for_a
    assert next_deliverables(SCHEDULE, today, cohort="A") in for_a
    # Not the other cohort's own next deliverable.
    assert next_deliverables(SCHEDULE, today, cohort="B") not in for_a


def test_the_instructions_fall_back_to_every_cohort_for_an_unresolved_channel():
    text = main_instructions(today=date(2026, 10, 13), channel_name="")

    assert "tutoring cohort" not in text
    assert "cohort A" in text and "cohort B" in text


def test_the_schedule_stops_at_the_listed_deliverables():
    text = render_schedule(SCHEDULE)

    for item in SCHEDULE["deliverables"]:
        assert item["what"] in text
    assert "Wed 4 Nov 2026" in text
    assert "Dec" not in text
    assert "not tracked here" in text


def test_the_knowledge_holds_every_file_with_its_type_version_and_source():
    text = load_knowledge()
    files = sorted(KNOWLEDGE_DIR.glob("*.md"))

    assert files
    # Each file (and the schedule) opens with its title, then a line giving
    # its type, version and source -- what a teacher updates with it.
    headers = [path.read_text(encoding="utf-8").splitlines()[:2] for path in files]
    headers.append(render_schedule(SCHEDULE).splitlines()[:2])
    for title, header in headers:
        assert title.startswith("# ") and title in text
        assert re.match(r"Type: (normative|support) · Version: v\d+ \(.+\) · Source: .+", header)
        assert header in text


def test_the_instructions_hold_persona_task_material_and_today():
    text = main_instructions(today=date(2026, 10, 13))

    assert text.startswith("Your name is MULCA.")
    assert "course teaching assistant for Advanced User Interfaces" in text
    assert "Task context:\nThere is no specific structured task" in text
    assert "Course material:\n" in text and load_knowledge() in text
    assert text.endswith(
        "Today is Tuesday 13 October 2026. "
        + next_deliverables(SCHEDULE, date(2026, 10, 13))
    )
