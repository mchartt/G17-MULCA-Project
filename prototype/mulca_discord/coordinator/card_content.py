"""
What a coordinator card says, whatever the channel: titles, the fields of each
kind of card, which buttons it has, and the text of "Why?".

Discord (cards.py) and Slack (slack/cards.py) both build their cards from
this file, so a card reads the same everywhere and a new kind of card is added
in one place. Nothing here imports discord or slack.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from .texts import day, member_name

# Writes a member id as text for one channel (see card_fields).
Who = Callable[[int], str]

BUTTON_LABELS = {
    "confirm": "Confirm",
    "take": "I'll take it",
    "reject": "Reject",
    "why": "Why?",
    "helpful": "Helpful",
    "not_now": "Not now",
}
STATUS_WORDS = {
    "pending": "Waiting for a member to confirm",
    "applied": "Confirmed",
    "rejected": "Rejected",
    "expired": "Expired",
    "snoozed": "Not now: this suggestion is silenced for 30 minutes",
}
KIND_TITLES = {
    "charter": "Project charter",
    "task_owner": "Owner and date",
    "delegation": "One person can do this",
    "decision": "Close the decision",
    "plan": "Plan: who does what",
    "checkin": "Check-in",
    "blocker": "Something is blocked",
    "revisit": "Already decided",
    "approach": "How you plan the work",
}
# The three shared needs (ownership, dependencies, decisions), as a short label.
NEED_LABELS = {
    "cs5_owner_and_date": "Ownership",
    "cs2_delegate_simple_task": "Ownership",
    "cs7_blockers_dependencies": "Dependency",
    "cs3_close_decision": "Decision",
    "cs3_reopened_decision": "Decision",
    "plan_opener": "Plan",
}
# Kinds whose answers are one button per option in payload["options"].
OPTION_KINDS = ("decision", "checkin", "revisit")
# Plain names of the strategies, for "Why?" (spec S5, S2, S3).
STRATEGY_NAMES = {
    "cs5_owner_and_date": "Owner and date (CS5): an agreed action had no owner or no date.",
    "cs2_delegate_simple_task": "Delegate simple tasks (CS2): several of you were discussing a task one person can do alone.",
    "cs3_close_decision": "Close the decision (CS3): the same question had two or more options and no decision.",
    "cs7_blockers_dependencies": "Blockers and dependencies (CS7): some work seems to wait on other work that is not ready, and a date is at risk.",
    "cs3_reopened_decision": "Already decided (CS3): a choice the group made, with a reason, was being discussed again.",
    "plan_opener": "Plan together: Cadence asked how you want to plan the work, and this is what you answered.",
}
PROACTIVE_KINDS = ("task_owner", "delegation", "decision", "blocker", "revisit", "approach")
# The "about this card" buttons, on a second row so the answers come first.
ABOUT_THE_CARD = ("why", "helpful", "not_now")

# A mark before the closed statuses, the same on every channel (the web app
# writes "Confirmed by Ada" in green): the word carries the meaning, the mark
# only makes it quicker to spot in a busy channel.
STATUS_MARKS = {"applied": "✓", "rejected": "✕", "expired": "◷", "snoozed": "◷"}


def status_line(proposal: dict, names: dict | None = None) -> str:
    """
    The card's status in words, as the web app writes it: "✓ Confirmed by Ada"
    once a member answered, "Waiting for a member to confirm · expires …" while
    open. Who answered is a plain name, because the click may have come from
    another channel (a Discord member is no mention on Slack).
    """
    status = proposal.get("status", "pending")
    line = STATUS_WORDS.get(status, status)
    by = proposal.get("resolved_by")
    if by:
        who = member_name(int(by), names if names is not None else proposal.get("names"))
        line = {
            "applied": f"Confirmed by {who}",
            "rejected": f"Turned down by {who}",
            "snoozed": f"Not now ({who}): silenced on this topic for 30 minutes",
        }.get(status, line)
    if status == "pending" and proposal.get("expires_at"):
        expires = datetime.fromtimestamp(proposal["expires_at"], tz=timezone.utc)
        line += f" · expires {expires:%d %b %H:%M} UTC"
    mark = STATUS_MARKS.get(status)
    return f"{mark} {line}" if mark else line


def card_title(kind: str | None, payload: dict, status: str = "pending") -> str:
    """
    The card's title. A CS7 card the group has not confirmed says so, and
    stops saying it once a member confirmed it (22/11: "not confirmed yet"
    stayed on a confirmed card). An update a member asked for in words uses
    the check-in card: it is titled as what it is, as on the web.
    """
    if kind == "blocker" and payload.get("certainty") == "possible":
        title = "Dependency" if status == "applied" else "Possible dependency (not confirmed yet)"
    elif kind == "checkin" and payload.get("requested") is True:
        title = "Update a task"
    else:
        title = KIND_TITLES.get(kind or "", "Proposal")
    need = NEED_LABELS.get((payload.get("context") or {}).get("strategy_id", ""))
    return f"{title} · {need}" if need else title


def card_fields(kind: str | None, payload: dict, who: Who) -> list[tuple[str, str]]:
    """
    The content of each kind of card, as (field name, text). `who` writes a
    member the way the channel does (a mention on Discord and Slack, a name
    for a member of another channel).
    """
    if kind == "charter":
        return [
            ("Goal", payload.get("goal", "")),
            ("Deliverables", _bullets(payload.get("deliverables", []))),
            (
                "Milestones",
                _bullets(f"{m.get('title')} — {day(m.get('due_date')) or 'no date'}" for m in payload.get("milestones", [])),
            ),
        ]
    if kind in ("task_owner", "delegation"):
        fields = [("Task", payload.get("title", "")), ("By", day(payload.get("due_date")) or "no date yet")]
        if kind == "task_owner":
            owner = payload.get("owner_id")
            fields.append(("Suggested owner", who(owner) if owner else "nobody suggested: anyone can take it"))
        elif payload.get("return_to"):
            fields.append(("Then back to", payload["return_to"]))
        return fields
    if kind == "decision":
        options = payload.get("options", [])
        return [
            ("Question", payload.get("question", "")),
            (
                "Options",
                "\n".join(
                    f"**{n}. {o.get('label')}**" + (f" — {o['argument']}" if o.get("argument") else "")
                    for n, o in enumerate(options, start=1)
                ) or "—",
            ),
        ]
    if kind == "plan":
        return [
            (
                "Tasks",
                "\n".join(
                    f"• **{i.get('title')}** — "
                    + (who(i["owner_id"]) if i.get("owner_id") else "anyone")
                    + (f" · {day(i['due_date'])}" if i.get("due_date") else "")
                    + (f"\n  _{i['reason']}_" if i.get("reason") else "")
                    for i in payload.get("items", [])
                ) or "—",
            ),
            # A split: the task these replace leaves the plan on confirm.
            *([("Replaces", payload["replaces_title"])] if payload.get("replaces_title") else []),
        ]
    if kind == "checkin":
        return [
            ("What was asked" if payload.get("requested") is True else "What is late or at risk", _bullets(payload.get("findings", []))),
            ("Options", "\n".join(f"**{n}.** {o.get('label')}" for n, o in enumerate(payload.get("options", []), start=1)) or "—"),
        ]
    if kind == "blocker":
        possible = payload.get("certainty") == "possible"
        fields = [("Task", payload.get("title", ""))]
        if payload.get("depends_on_title"):
            fields.append(("May wait on" if possible else "Waits on", payload["depends_on_title"]))
        if payload.get("question"):
            fields.append(("Question", payload["question"]))
        if payload.get("helper_id"):
            fields.append(("Who could help", who(payload["helper_id"])))
        if payload.get("ways_forward"):
            fields.append(("Possible ways forward (ideas, nothing changes by itself)", _bullets(payload["ways_forward"])))
        return fields
    if kind == "approach":
        fields = [("In short", payload.get("summary", "")), ("What you agreed", _bullets(payload.get("agreements", [])))]
        if payload.get("open_points"):
            fields.append(("Still open (raised, not agreed)", _bullets(payload["open_points"])))
        return fields
    if kind == "revisit":
        fields = [("Question", payload.get("question", "")), ("The group chose", payload.get("choice", ""))]
        if payload.get("reason"):
            fields.append(("Because", payload["reason"]))
        fields.append(("What seems new", payload.get("new_point") or "Nothing new so far: the same arguments as before."))
        return fields
    return []


def actions_for(kind: str | None, payload: dict) -> list[str]:
    """The buttons of a pending card, in order (option buttons are added by the channel)."""
    actions = {
        "charter": ["confirm", "reject"],
        "task_owner": (["confirm"] if payload.get("owner_id") else []) + ["take", "reject"],
        "delegation": ["take", "reject"],
        "decision": ["reject"],
        "checkin": ["reject"],
        "plan": ["confirm", "reject"],
        "blocker": ["confirm", "reject"],
        "revisit": [],
        "approach": ["confirm", "reject"],
    }.get(kind, ["confirm", "reject"])
    if kind in PROACTIVE_KINDS:
        actions += ["why", "helpful", "not_now"]
    return actions


def why_text(proposal: dict | None) -> str:
    """What "Why?" shows, privately: the strategy and the messages behind the card."""
    context = (proposal or {}).get("payload", {}).get("context")
    if not context:
        return "This card was asked for by a member of the group."
    lines = [STRATEGY_NAMES.get(context.get("strategy_id"), context.get("strategy_id", ""))]
    lines.append(f"Topic: {context.get('topic', '')}")
    lines.append("Messages that made it step in:")
    lines += [f"> **{e.get('speaker')}**: {e.get('text')}" for e in context.get("evidence", [])]
    lines.append("If it is not useful now, press Not now: it stays silent on this topic for 30 minutes.")
    return clip("\n".join(lines), 1900)


def _bullets(items) -> str:
    lines = [f"• {item}" for item in items]
    return "\n".join(lines) if lines else "—"


def clip(text: str, limit: int = 1000) -> str:
    """Discord refuses embed fields over 1024 characters; Slack sections over 3000."""
    text = text or "—"
    return text if len(text) <= limit else text[: limit - 1] + "…"
