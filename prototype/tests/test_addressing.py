"""Matteo, 20/11: Cadence answers when called by name, with or without @, and follows up."""

from __future__ import annotations

from mulca_discord.addressing import FollowUps, addressed, calls_someone_else


def test_cadence_is_called_with_or_without_at():
    assert addressed("@coordinator who does the slides?") == "who does the slides?"
    assert addressed("@Cadence, when is the demo?") == "when is the demo?"
    assert addressed("Cadence, when is the demo?") == "when is the demo?"
    assert addressed("cadence what is our goal") == "what is our goal"
    assert addressed("hey Cadence: chi fa le slide?") == "chi fa le slide?"
    assert addressed("ciao cadence, mi riassumi il piano?") == "mi riassumi il piano?"
    assert addressed("the demo is on friday, right cadence?") == "the demo is on friday, right?"
    assert addressed("@coordinator why did we pick SUS?") == "why did we pick SUS?"
    assert addressed("@coordinator hello") == "hello"  # no question mark needed any more


def test_talking_about_cadence_is_not_calling_it():
    assert addressed("who does the slides?") is None
    assert addressed("I told Cadence about it yesterday") is None
    assert addressed("cadences of the sprint are weekly") is None
    assert addressed("@coordinatorwhy") is None


def test_long_messages_are_cut_to_the_question_limit():
    assert len(addressed("@coordinator " + "x" * 900 + "?")) == 500


def test_another_person_called_is_not_for_cadence():
    names = ["Ada Lovelace", "Bruno"]
    assert calls_someone_else("@Bruno can you send it?", names)
    assert calls_someone_else("Bruno, can you send it?", names)
    assert calls_someone_else("ada: ok", names)
    assert not calls_someone_else("and by when?", names)
    assert not calls_someone_else("Brunos are cool", names)


def test_follow_ups_last_a_few_minutes_after_cadence_answered():
    now = [0.0]
    follow = FollowUps(window=180, clock=lambda: now[0])
    assert not follow.is_follow_up("g1", "and by when?")
    follow.answered("g1")
    now[0] = 60
    assert follow.is_follow_up("g1", "and by when?")
    assert not follow.is_follow_up("g2", "and by when?")  # another group
    assert not follow.is_follow_up("g1", "Bruno, by when?", ["Bruno"])
    assert not follow.is_follow_up("g1", "   ")
    now[0] = 200
    assert not follow.is_follow_up("g1", "and by when?")
