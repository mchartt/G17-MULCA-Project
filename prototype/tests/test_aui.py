"""
The AUI course setup MULCA sends MUCA-Server's main agent: aui/ (persona,
task, knowledge, schedule) and main_instructions.
"""

import re
from datetime import date

import pytest

from mulca_discord.aui import (
    KNOWLEDGE_DIR,
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
        (date(2026, 10, 12), "Mon 12 Oct 2026", "Wed 14 Oct 2026"),  # due today
        (date(2026, 10, 13), f"{UX}, at the tutoring on Mon 26 Oct", REQUIREMENTS),
        (date(2026, 10, 27), REFINED, f"{UX}, at the tutoring on Wed 28 Oct"),
        (date(2026, 11, 3), PROTOTYPING, f"{REFINED}"),
        (date(2026, 11, 10), PROTOTYPING, PROTOTYPING),
    ],
)
def test_each_group_is_told_its_own_next_deliverable(today, group_a, group_b):
    a, b = next_deliverables(SCHEDULE, today).split("; Group B: ")

    assert group_a in a
    assert group_b in b


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
