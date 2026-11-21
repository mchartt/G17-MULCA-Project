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


def test_follow_ups_last_a_few_minutes_after_cadence_answered_and_only_for_that_member():
    now = [0.0]
    follow = FollowUps(window=180, clock=lambda: now[0])
    assert not follow.is_follow_up("g1", "and by when?", member=7)
    follow.asked("g1", 7)
    follow.answered("g1")
    now[0] = 60
    assert follow.is_follow_up("g1", "and by when?", member=7)
    # 21/11, four members in one chat: the others' lines are not follow-ups.
    assert not follow.is_follow_up("g1", "and by when?", member=8)
    assert not follow.is_follow_up("g2", "and by when?", member=7)  # another group
    assert not follow.is_follow_up("g1", "Bruno, by when?", ["Bruno"], member=7)
    assert not follow.is_follow_up("g1", "   ", member=7)
    now[0] = 200
    assert not follow.is_follow_up("g1", "and by when?", member=7)


def test_what_cadence_says_unasked_opens_no_follow_up_window():
    follow = FollowUps(window=180, clock=lambda: 0.0)
    follow.answered("g1")  # a card, the plan opener, a progress question: nobody asked
    assert not follow.is_follow_up("g1", "blu o verde?", member=7)
    # ...and it closes the window of an earlier answer: the talk has moved on.
    follow.asked("g1", 7)
    follow.answered("g1")
    follow.answered("g1")
    assert not follow.is_follow_up("g1", "e per quando?", member=7)


def test_a_clear_call_is_sure_a_passing_mention_is_only_maybe():
    """Matteo, 20/11: "Cadence ieri ha risposto male" talks about Cadence; it is offered as maybe, never a sure call."""
    from mulca_discord.addressing import call

    sure = [
        "Cadence, come procede il progetto?",
        "Ehi cadence, controlli le scadenze?",
        "@Cadence chi segue il frontend?",
        "Cadence?",
        "Coordinator, mi fai un riepilogo?",
        "cadence chi si occupa delle API?",
        "vero, Cadence?",
        "cadence: aggiungi la dipendenza",
    ]
    maybe = [
        "Cadence ieri ha risposto male.",
        "cadence what is our goal",
        "the demo is on friday, right cadence?",
    ]
    never = ["Secondo voi dobbiamo migliorare Cadence?", "ragazzi, vi piace cadence?", "what do you all think of cadence?",
             "Ho modificato il codice del coordinator.", "Mi aiuti a capire cosa manca?"]
    for text in sure:
        assert call(text)[1] is True, text
    for text in maybe:
        assert call(text)[1] is False, text
    for text in never:
        assert call(text) is None, text


def test_a_clear_call_to_cadence_inside_a_group_message_still_counts():
    from mulca_discord.addressing import call

    assert call("Cadence, secondo voi... no, secondo te il piano regge?")[1] is True
    assert call("@cadence ragazzi chiedono chi fa le slide")[1] is True


def test_a_stretched_greeting_before_the_name_is_a_call():
    """20/11 screenshot: "Oii Cadence, sono al 30%..." reached the lab's agent, not Cadence."""
    from mulca_discord.addressing import call

    assert call("Oii Cadence, sono al 30% della mia task.") == ("sono al 30% della mia task.", True)
    assert call("Ehiii cadence, mi senti?") == ("mi senti?", True)
    assert call("heyyy Cadence quanto manca alla demo") == ("quanto manca alla demo", True)
    assert call("Cadence ma funzioni?") == ("ma funzioni?", True)
    # Talking about Cadence is still not a sure call.
    assert call("Cadence ieri ha risposto male.") == ("ieri ha risposto male.", False)
    assert call("oggi Cadence era lenta") == ("oggi Cadence era lenta", False)


def test_the_name_anywhere_is_offered_as_maybe_so_the_server_decides():
    """Matteo, 20/11: Cadence notices it is named anywhere, and the model stays silent on talk about it."""
    from mulca_discord.addressing import call

    for text in ["Cadence è troppo forte", "Secondo me Cadence è inutile", "Mannaggia mi sa che cadence non basta",
                 "I told Cadence about it yesterday", "puoi dirmi tu cadence chi fa le slide"]:
        assert call(text)[1] is False, text  # maybe: the hub offers the whole message
    assert call("le cadences dello sprint sono settimanali") is None
    assert call("ho scritto a support@cadence.io") is None
