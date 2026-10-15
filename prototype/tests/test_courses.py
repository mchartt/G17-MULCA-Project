"""
The courses MULCA can teach (courses/<id>/): detecting one from a Discord
server's name, and IMI's own setup -- a single tutoring group, and nothing
of AUI's university in it.
"""

import re
from datetime import date

import pytest

from mulca_discord.courses import (
    COURSES,
    COURSES_DIR,
    cohort_for_channel,
    detect,
    load_schedule,
    main_instructions,
)


def test_every_course_folder_is_a_course():
    assert COURSES == ("aui", "imi")


@pytest.mark.parametrize(
    ("server_name", "course"),
    [
        ("IMI 2026/27", "imi"),
        ("imi-students", "imi"),
        ("aui-polimi", "aui"),
        ("Advanced User Interfaces - AUI", "aui"),
        ("Mimic Club", None),  # whole words only
        ("AUI & IMI", None),  # both: not for the name to decide
        ("", None),
    ],
)
def test_the_course_is_the_one_the_server_name_names(server_name, course):
    assert detect(server_name) == course


def test_imi_has_a_single_group_whatever_the_channel():
    schedule = load_schedule("imi")

    for channel in ("group-4", "team-blue", "", "general"):
        assert cohort_for_channel(channel, schedule) == "IMI"


@pytest.mark.parametrize(
    ("today", "next_due"),
    [
        (date(2026, 10, 14), "survey report of reviewed papers/products"),
        (date(2026, 10, 29), "Thu 29 Oct 2026"),  # due today
        (date(2026, 10, 30), "initial user scenarios (UX design), at the tutoring on Thu 5 Nov 2026"),
        (date(2026, 11, 6), "revised scenarios"),
        (date(2026, 11, 13), "further project work"),
    ],
)
def test_imi_is_told_its_next_deliverable(today, next_due):
    text = main_instructions(today=today, channel_name="group-1", course="imi")

    assert text.split("Next deliverable: ")[1].count(next_due) == 1


def test_imi_instructions_name_imi_and_nothing_of_auis_university():
    text = main_instructions(today=date(2026, 10, 30), course="imi")

    assert "course teaching assistant for Interactive Multimodal Interfaces (IMI, 2026/27)." in text
    assert "This channel's team is in tutoring cohort IMI (Thursdays)" in text
    assert "{course_" not in text
    for banned in ("AUI", "Advanced User Interfaces", "Politecnico", "PoliMi", "Milan", "WeBeep"):
        assert not re.search(re.escape(banned), text, re.IGNORECASE), banned


def test_imi_material_files_never_mention_auis_university():
    for path in (COURSES_DIR / "imi").rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            for banned in ("polimi", "politecnico", "milan", "webeep"):
                assert banned not in text.lower(), (path.name, banned)
