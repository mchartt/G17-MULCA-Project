"""
The AUI course setup MULCA gives MUCA-Server's main agent: persona, task,
course material (knowledge/*.md) and the project schedule
(knowledge/schedule.yaml). muca_client.py sends it as a session.update right
after each connect; MUCA-Server's own main agent knows nothing of the course.

Only the listed deliverables are tracked; later deadlines exist, but are not
the assistant's to announce.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

AUI_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DIR = AUI_DIR / "knowledge"

# Which project team (its Discord channel is named "group-<N>") sits in
# which tutoring cohort (schedule.yaml's own "groups" keys, A/B) -- not
# derivable from the schedule itself, which only tracks cohort-level
# tutoring slots/deadlines, never which of the ~20 individual teams
# belongs to which cohort. Every team not listed here is assumed to be B.
COHORT_A_TEAMS = frozenset(
    {"1", "4", "5", "6", "7", "8", "9", "11", "12", "14", "15"}
)

_TEAM_NUMBER = re.compile(r"group[-_]?(\d+)", re.IGNORECASE)


def cohort_for_channel(channel_name: str) -> str | None:
    """
    "A" or "B" for a channel named like "group-10", or None if the name
    doesn't match that pattern at all (a DM, or a channel not actually one
    of the numbered teams) -- callers fall back to the unscoped schedule
    for None, rather than guessing which cohort applies.
    """

    match = _TEAM_NUMBER.search(channel_name)
    if match is None:
        return None
    return "A" if match.group(1) in COHORT_A_TEAMS else "B"


def load_schedule(path: Path = KNOWLEDGE_DIR / "schedule.yaml") -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _day(value: date) -> str:
    return f"{value:%a} {value.day} {value:%b %Y}"


def render_schedule(schedule: dict) -> str:
    """The whole schedule as text, for the main agent's instructions."""

    lines = [f"# {schedule['title']}", schedule["header"], ""]
    lines += [
        f"Tutoring of Group {group}: {slot}."
        for group, slot in schedule["groups"].items()
    ]
    lines += ["", "Events:"]
    lines += [f"- {_day(event['date'])}: {event['what']}" for event in schedule["events"]]
    lines += ["", "Deliverables, each due at a group's tutoring:"]
    for item in schedule["deliverables"]:
        dates = ", ".join(
            f"Group {group} on {_day(due)}" for group, due in item["due"].items()
        )
        lines.append(f"- {item['what']}: {dates}")
    lines += [f"- Then: {schedule['then']}", "", schedule["untracked"]]
    return "\n".join(lines)


def today_in(schedule: dict) -> date:
    return datetime.now(ZoneInfo(schedule["timezone"])).date()


def _next_for(schedule: dict, today: date, group: str) -> str:
    upcoming = next(
        (item for item in schedule["deliverables"] if item["due"][group] >= today),
        None,
    )
    return (
        f"{upcoming['what']}, at the tutoring on {_day(upcoming['due'][group])}"
        if upcoming is not None
        else f"{schedule['then']} (not tracked further)"
    )


def next_deliverables(
    schedule: dict,
    today: date,
    *,
    cohort: str | None = None,
) -> str:
    """
    What's due next, as of `today` (inclusive). Scoped to one cohort's own
    deliverable when known (the normal case: a team's own channel maps to
    exactly one, via cohort_for_channel) -- stated unambiguously, not next
    to the other cohort's own, unrelated deadline. Falls back to every
    cohort's, concatenated, only for a channel this mapping couldn't
    resolve (e.g. a DM).
    """

    if cohort in schedule["groups"]:
        return f"Next deliverable: {_next_for(schedule, today, cohort)}."

    parts = [
        f"Group {group}: {_next_for(schedule, today, group)}"
        for group in schedule["groups"]
    ]
    return "Next deliverables -- " + "; ".join(parts) + "."


def load_knowledge(knowledge_dir: Path = KNOWLEDGE_DIR) -> str:
    """The course material: every knowledge/*.md file, then the schedule."""

    parts = [
        path.read_text(encoding="utf-8").strip()
        for path in sorted(knowledge_dir.glob("*.md"))
    ]
    parts.append(render_schedule(load_schedule(knowledge_dir / "schedule.yaml")))
    return "\n\n".join(parts)


def main_instructions(today: date | None = None, *, channel_name: str = "") -> str:
    """
    The main agent's whole instructions, replacing MUCA-Server's own. Built
    at every connect, and a session lasts at most an hour (OpenAI's limit),
    so today's date is at most that stale.

    channel_name: the linked text channel's own Discord name (e.g.
    "group-10") -- found live, without this the "next deliverable" line
    listed every cohort's own deadline together with no indication of
    which one actually applies to this team, so the model had to guess
    (and sometimes guessed wrong) which cohort its own channel was in.
    """

    schedule = load_schedule()
    today = today or today_in(schedule)
    cohort = cohort_for_channel(channel_name)
    persona = (AUI_DIR / "persona.md").read_text(encoding="utf-8").strip()
    task = (AUI_DIR / "task.md").read_text(encoding="utf-8").strip()
    cohort_line = (
        f"This channel's team is in tutoring cohort {cohort} "
        f"({schedule['groups'][cohort]}) -- a known, certain fact about "
        "everyone in this channel, not a guess. When asked about a "
        "deadline or tutoring date, answer directly for this cohort; do "
        "not hedge with phrases like \"if you're unsure which group "
        "you're in\" or tell them to go check -- you already know.\n\n"
        if cohort is not None
        else ""
    )
    return (
        f"{persona}\n\nTask context:\n{task}\n\n{cohort_line}"
        f"Course material:\n{load_knowledge()}"
        f"\n\nToday is {today:%A} {today.day} {today:%B %Y}. "
        f"{next_deliverables(schedule, today, cohort=cohort)}"
    )
