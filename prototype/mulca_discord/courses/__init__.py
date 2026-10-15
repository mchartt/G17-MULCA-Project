"""
The course setups MULCA gives MUCA-Server's main agent: a shared persona and
task (persona.md, task.md), and per course (courses/<id>/) its material
(knowledge/*.md) and project schedule (knowledge/schedule.yaml), which also
names the course and where to check its official information.
muca_client.py sends it as a session.update right after each connect;
MUCA-Server's own main agent knows nothing of any course.

Which course a session gets is BotRuntime.course_for's to decide (a /mulca
course setting, else the Discord server's name via detect(), else
DEFAULT_COURSE).

Only the listed deliverables are tracked; later deadlines exist, but are not
the assistant's to announce.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

COURSES_DIR = Path(__file__).resolve().parent

# Every course with its own folder here, e.g. ("aui", "imi").
COURSES = tuple(
    sorted(path.name for path in COURSES_DIR.iterdir() if (path / "knowledge").is_dir())
)

# For a server with no setting whose name names no course: the course MULCA
# was first built for.
DEFAULT_COURSE = "aui"

_TEAM_NUMBER = re.compile(r"group[-_]?(\d+)", re.IGNORECASE)


def detect(server_name: str) -> str | None:
    """
    The one course whose id appears in a Discord server's name as a whole
    word, any case ("IMI 2026/27" -> "imi"); None if none or several do.
    """

    found = [
        course
        for course in COURSES
        if re.search(rf"\b{re.escape(course)}\b", server_name, re.IGNORECASE)
    ]
    return found[0] if len(found) == 1 else None


def cohort_for_channel(channel_name: str, schedule: dict) -> str | None:
    """
    The tutoring cohort (one of schedule.yaml's "groups" keys) of the team in
    a channel. A course with a single group: always that one. Otherwise, for
    a channel named like "group-10", the cohort whose "teams" list has 10, or
    "default_group"; None if the name doesn't match that pattern at all (a
    DM, or a channel not actually one of the numbered teams) -- callers fall
    back to the unscoped schedule for None, rather than guessing which
    cohort applies.
    """

    groups = list(schedule["groups"])
    if len(groups) == 1:
        return groups[0]

    match = _TEAM_NUMBER.search(channel_name)
    if match is None:
        return None
    team = int(match.group(1))
    return next(
        (group for group, teams in schedule.get("teams", {}).items() if team in teams),
        schedule.get("default_group"),
    )


def load_schedule(course: str = DEFAULT_COURSE) -> dict:
    path = COURSES_DIR / course / "knowledge" / "schedule.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _day(value: date) -> str:
    return f"{value:%a} {value.day} {value:%b %Y}"


def render_schedule(schedule: dict) -> str:
    """The whole schedule as text, for the main agent's instructions."""

    lines = [f"# {schedule['title']}", schedule["header"], ""]
    lines += [
        f"Tutoring of cohort {group}: {slot}."
        for group, slot in schedule["groups"].items()
    ]
    lines += ["", "Events:"]
    lines += [f"- {_day(event['date'])}: {event['what']}" for event in schedule["events"]]
    lines += ["", "Deliverables, each due at a team's cohort's tutoring:"]
    for item in schedule["deliverables"]:
        dates = ", ".join(
            f"cohort {group} on {_day(due)}" for group, due in item["due"].items()
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
        f"cohort {group}: {_next_for(schedule, today, group)}"
        for group in schedule["groups"]
    ]
    return "Next deliverables -- " + "; ".join(parts) + "."


def load_knowledge(course: str = DEFAULT_COURSE) -> str:
    """The course material: every knowledge/*.md file, then the schedule."""

    knowledge_dir = COURSES_DIR / course / "knowledge"
    parts = [
        path.read_text(encoding="utf-8").strip()
        for path in sorted(knowledge_dir.glob("*.md"))
    ]
    parts.append(render_schedule(load_schedule(course)))
    return "\n\n".join(parts)


def main_instructions(
    today: date | None = None,
    *,
    channel_name: str = "",
    course: str = DEFAULT_COURSE,
) -> str:
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

    schedule = load_schedule(course)
    today = today or today_in(schedule)
    cohort = cohort_for_channel(channel_name, schedule)
    persona = (
        (COURSES_DIR / "persona.md")
        .read_text(encoding="utf-8")
        .strip()
        .replace("{course_name}", schedule["name"])
        .replace("{course_page}", schedule["course_page"])
    )
    task = (COURSES_DIR / "task.md").read_text(encoding="utf-8").strip()
    cohort_line = (
        f"This channel's team is in tutoring cohort {cohort} "
        f"({schedule['groups'][cohort]}) -- a known, certain fact about "
        "everyone in this channel, not a guess. When asked about a "
        "deadline or tutoring date, just answer directly for this "
        "cohort.\n\n"
        if cohort is not None
        else ""
    )
    return (
        f"{persona}\n\nTask context:\n{task}\n\n{cohort_line}"
        f"Course material:\n{load_knowledge(course)}"
        f"\n\nToday is {today:%A} {today.day} {today:%B %Y}. "
        f"{next_deliverables(schedule, today, cohort=cohort)}"
    )
