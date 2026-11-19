"""
The plan opener's card (CS-OPEN-01) on Discord and Slack: both read
coordinator/card_content.py, so the same title, fields and buttons.
"""

from mulca_discord.coordinator.card_content import actions_for, card_fields, card_title, why_text
from mulca_discord.slack.cards import card_blocks

PAYLOAD = {
    "context": {
        "strategy_id": "plan_opener",
        "topic": "how you plan the work",
        "evidence": [{"speaker": "Ada", "text": "Let's split by area.", "at_ms": 1}],
    },
    "question": "How the group plans the work",
    "summary": "Split by area, check in every Monday.",
    "agreements": ["Split by area", "Check in every Monday"],
    "open_points": ["Where to keep the slides"],
}
PROPOSAL = {"proposal_id": "a1", "kind": "approach", "status": "pending", "rationale": "Stepping in because you answered.", "payload": PAYLOAD}


def test_the_approach_card_has_its_title_fields_and_buttons():
    assert card_title("approach", PAYLOAD) == "How you plan the work · Plan"
    fields = dict(card_fields("approach", PAYLOAD, who=str))
    assert fields["In short"] == "Split by area, check in every Monday."
    assert "Check in every Monday" in fields["What you agreed"]
    assert "Where to keep the slides" in fields["Still open (raised, not agreed)"]
    assert actions_for("approach", PAYLOAD) == ["confirm", "reject", "why", "helpful", "not_now"]


def test_why_names_the_question_and_quotes_the_answers():
    text = why_text(PROPOSAL)
    assert "Plan together" in text and "Let's split by area." in text


def test_slack_shows_the_same_card():
    blocks = str(card_blocks(PROPOSAL))
    assert "How you plan the work" in blocks and "Split by area, check in every Monday." in blocks
