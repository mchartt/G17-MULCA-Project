"""
The AUI course setup MULCA gives MUCA-Server's main agent: persona, task,
course material (knowledge/*.md) and the project schedule
(knowledge/schedule.yaml). muca_client.py sends it as a session.update right
after each connect; MUCA-Server's own main agent knows nothing of the course.

Only the listed deliverables are tracked; later deadlines exist, but are not
the assistant's to announce.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

AUI_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DIR = AUI_DIR / "knowledge"


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


def next_deliverables(schedule: dict, today: date) -> str:
    """What each group has to deliver next, as of `today` (inclusive)."""

    parts = []
    for group in schedule["groups"]:
        upcoming = next(
            (item for item in schedule["deliverables"] if item["due"][group] >= today),
            None,
        )
        parts.append(
            f"Group {group}: {upcoming['what']}, at the tutoring on "
            f"{_day(upcoming['due'][group])}"
            if upcoming is not None
            else f"Group {group}: {schedule['then']} (not tracked further)"
        )
    return "Next deliverables -- " + "; ".join(parts) + "."


def load_knowledge(knowledge_dir: Path = KNOWLEDGE_DIR) -> str:
    """The course material: every knowledge/*.md file, then the schedule."""

    parts = [
        path.read_text(encoding="utf-8").strip()
        for path in sorted(knowledge_dir.glob("*.md"))
    ]
    parts.append(render_schedule(load_schedule(knowledge_dir / "schedule.yaml")))
    return "\n\n".join(parts)


def main_instructions(today: date | None = None) -> str:
    """
    The main agent's whole instructions, replacing MUCA-Server's own. Built
    at every connect, and a session lasts at most an hour (OpenAI's limit),
    so today's date is at most that stale.
    """

    schedule = load_schedule()
    today = today or today_in(schedule)
    persona = (AUI_DIR / "persona.md").read_text(encoding="utf-8").strip()
    task = (AUI_DIR / "task.md").read_text(encoding="utf-8").strip()
    return (
        f"{persona}\n\nTask context:\n{task}\n\nCourse material:\n{load_knowledge()}"
        f"\n\nToday is {today:%A} {today.day} {today:%B %Y}. "
        f"{next_deliverables(schedule, today)}"
    )
