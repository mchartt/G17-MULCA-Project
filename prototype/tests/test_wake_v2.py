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
            1: "Francesco.Orlando.Group-17",
            2: "delia_trabuio_group11",
            3: "Pourya.Shahbazzadeh.3",
            4: "Andrea.Mori.group-6",
            5: "Andrea.Santarsiero.Group-18",
            6: "Admin",
        }
    ) == {
        1: "Francesco",
        2: "Delia",
        3: "Pourya",
        4: "Andrea Mori",
        5: "Andrea Santarsiero",
        6: "Admin",
    }
    # Already spoken names stay as they are.
    assert spoken_names({1: "Andrea Mori", 2: "Andrea Santarsiero", 3: "Delia"}) == {
        1: "Andrea Mori",
        2: "Andrea Santarsiero",
        3: "Delia",
    }


def test_wake_v2_adds_the_voice_lines_to_the_persona(monkeypatch):
    today = date(2026, 10, 13)
    plain = main_instructions(today=today)
    v2 = main_instructions(today=today, wake_v2=True)

    assert "language of the turn you are answering" not in plain
    assert "language of the turn you are answering" in v2
    assert "only when asked to do that exact thing" in v2
    assert "In voice, at most two sentences." in v2
    assert v2.index("at most two sentences") < v2.index("Task context:")

    monkeypatch.setattr(courses, "VOICE_TWO_SENTENCES", False)
    assert "at most two sentences" not in main_instructions(today=today, wake_v2=True)
