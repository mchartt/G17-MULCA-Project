"""
"wake_v2" links: MUCA-Server's "wake" with the fixes from the 15-28 Oct
exports. On MULCA's side: a voice addendum to the persona, and first names.
"""

from datetime import date

import mulca_discord.courses as courses
from mulca_discord.courses import main_instructions
from mulca_discord.runtime import spoken_names


def test_spoken_names_are_first_names_with_surnames_for_namesakes():
    assert spoken_names(
        {
            1: "Name1.Surname1.Group-17",
            2: "name2_surname2_group11",
            3: "Name3.Surname3.3",
            4: "Name4.Surname4.group-6",
            5: "Name4.Surname5.Group-18",
            6: "Admin",
        }
    ) == {
        1: "Name1",
        2: "Name2",
        3: "Name3",
        4: "Name4 Surname4",
        5: "Name4 Surname5",
        6: "Admin",
    }
    # Already spoken names stay as they are.
    assert spoken_names({1: "Name4 Surname4", 2: "Name4 Surname5", 3: "Name2"}) == {
        1: "Name4 Surname4",
        2: "Name4 Surname5",
        3: "Name2",
    }


def test_wake_v2_adds_the_voice_lines_to_the_persona(monkeypatch):
    today = date(2026, 10, 13)
    plain = main_instructions(today=today)  # a DM: no link, no mode
    v2 = main_instructions(today=today, listening_mode="wake_v2")

    assert "language of the turn you are answering" not in plain
    assert "language of the turn you are answering" in v2
    assert "only when asked to do that exact thing" in v2
    assert "In voice, at most two sentences." in v2
    assert v2.index("at most two sentences") < v2.index("Task context:")

    monkeypatch.setattr(courses, "VOICE_TWO_SENTENCES", False)
    assert "at most two sentences" not in main_instructions(
        today=today, listening_mode="wake_v2"
    )


def test_wake_and_the_default_get_the_lines_but_not_two_sentences():
    today = date(2026, 10, 13)
    for mode in ("wake", ""):  # "": the server's default, "wake"
        text = main_instructions(today=today, listening_mode=mode)
        assert "language of the turn you are answering" in text, mode
        assert "only when asked to do that exact thing" in text, mode
        assert "at most two sentences" not in text, mode
    for mode in ("ambient", "toggle", "transcribe"):
        text = main_instructions(today=today, listening_mode=mode)
        assert "language of the turn you are answering" not in text, mode
