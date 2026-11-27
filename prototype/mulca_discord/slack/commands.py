"""
The text after "/coordinator" on Slack, turned into a coordinator command.

Slack gives a slash command one line of free text, so the first word is the
command and the rest its argument:

    /coordinator kickoff <the assignment text>
    /coordinator planning Server API; UI screens; Slides
    /coordinator checkin
    /coordinator task 2 done          /coordinator task add Print the survey
    /coordinator task 3 waits on 1, 2  /coordinator task 2 due 2026-12-01
    /coordinator why did we drop the notifications?
    /coordinator ask who does the slides?
    /coordinator plan
    /coordinator profile HCI | figma, ux | 6
    /coordinator link AB12CD      /coordinator unlink      /coordinator catchup

Each command is one small function in PARSERS (name -> function): adding a
command means adding one function and one line of HELP, nothing else changes.
A parser returns the server command and its arguments, or raises Usage with
the words to show the member.
"""

from __future__ import annotations

from collections.abc import Callable

from .ids import who

HELP = (
    "*Cadence commands*\n"
    "• `/coordinator link <invite code>`: work here on a project created in the web app\n"
    "• `/coordinator me <personal code>`: be the same member here as on the web or on Discord (with no code: get one here)\n"
    "• `/coordinator kickoff <assignment text>`: propose the project charter (in a linked channel)\n"
    "• `/coordinator planning <task>; <task>; …`: suggest who takes each task\n"
    "• `/coordinator checkin`: compare the plan with reality\n"
    "• `/coordinator task <number> <todo|doing|done|blocked>`: update a task\n"
    "• `/coordinator task add <title>` · `task <number> waits on <numbers>` · `task <number> due <YYYY-MM-DD>`\n"
    "• `/coordinator why <question>`: answer from the decision log\n"
    "• `/coordinator ask <question>`: answer from the saved plan, dates and decisions\n"
    "• `/coordinator plan`: show the project (only you see it)\n"
    "• `/coordinator profile <discipline> | <skills, comma separated> | <weekly hours>`\n"
    "• `/coordinator unlink` · `/coordinator catchup`\n"
    "You can also just write to Cadence in the channel: start with its name or @ it."
)
STATUSES = ("todo", "doing", "done", "blocked")


class Usage(ValueError):
    """The member wrote the command in a way that cannot be run; the message says how."""


def _kickoff(rest: str) -> tuple[str, dict]:
    if not rest:
        raise Usage("Paste the assignment after the command: `/coordinator kickoff <text>`.")
    return "kickoff", {"text": rest}


def _planning(rest: str) -> tuple[str, dict]:
    tasks = [part.strip() for part in rest.split(";") if part.strip()]
    if not tasks:
        raise Usage("Write the tasks separated by `;`: `/coordinator planning Server API; UI screens`.")
    return "planning", {"text": "\n".join(tasks)}


TASK_USAGE = (
    "Use the task's number in `/coordinator plan`:\n"
    "• `/coordinator task 2 done` (todo, doing, done, blocked)\n"
    "• `/coordinator task add Print the survey results`\n"
    "• `/coordinator task 3 waits on 1, 2` (or `waits on nothing`)\n"
    "• `/coordinator task 2 due 2026-12-01`"
)


def waits_on(text: str) -> list[str]:
    """ "1, 2" or "1 2" -> ["1", "2"]; "nothing" -> []. Raises Usage on anything else."""
    text = text.strip().lower()
    if text in ("nothing", "none", "-"):
        return []
    numbers = [part for part in text.replace(",", " ").split() if part != "and"]
    if not numbers or not all(part.isdigit() for part in numbers):
        raise Usage(TASK_USAGE)
    return numbers


def _task(rest: str) -> tuple[str, dict]:
    head, _, tail = rest.strip().partition(" ")
    tail = tail.strip()
    if head.lower() == "add":
        if not tail:
            raise Usage(TASK_USAGE)
        return "task", {"add": tail}
    if not head.isdigit() or not tail:
        raise Usage(TASK_USAGE)
    low = tail.lower()
    if low in STATUSES:
        return "task", {"task": head, "status": low}
    if low.startswith("waits on "):
        return "task", {"task": head, "depends_on": waits_on(tail[len("waits on "):])}
    if low.startswith("due "):
        return "task", {"task": head, "due": tail[len("due "):].strip()}
    raise Usage(TASK_USAGE)


def _why(rest: str) -> tuple[str, dict]:
    if not rest:
        raise Usage("Ask a question: `/coordinator why did we choose React?`.")
    return "why", {"question": rest}


def _ask(rest: str) -> tuple[str, dict]:
    if not rest:
        raise Usage("Ask a question: `/coordinator ask who does the slides?`.")
    return "ask", {"question": rest}


def _profile(rest: str) -> tuple[str, dict]:
    parts = [part.strip() for part in rest.split("|")]
    parts += [""] * (3 - len(parts))
    hours = parts[2]
    if hours and not hours.isdigit():
        raise Usage("Weekly hours is a number: `/coordinator profile HCI | figma, ux | 6`.")
    return "profile", {"discipline": parts[0], "skills": parts[1], "weekly_hours": int(hours) if hours else None}


def _link(rest: str) -> tuple[str, dict]:
    if not rest:
        raise Usage("Write the web space's invite code: `/coordinator link AB12CD`.")
    return "link", {"code": rest.split()[0]}


def _me(rest: str) -> tuple[str, dict]:
    # With no code the server gives one here, to use in the project's other
    # channel (the same person on Slack and Discord without a web account).
    return "me", {"code": rest.split()[0] if rest else ""}


PARSERS: dict[str, Callable[[str], tuple[str, dict]]] = {
    "me": _me,
    "kickoff": _kickoff,
    "planning": _planning,
    "task": _task,
    "why": _why,
    "ask": _ask,
    "profile": _profile,
    "link": _link,
    "checkin": lambda rest: ("checkin", {}),
    "unlink": lambda rest: ("unlink", {}),
    "catchup": lambda rest: ("catchup", {}),
    "plan": lambda rest: ("state", {}),
}


def parse(text: str) -> tuple[str, dict]:
    """ "task 2 done" -> ("task", {"task": "2", "status": "done"}). Raises Usage."""
    name, _, rest = text.strip().partition(" ")
    parser = PARSERS.get(name.lower())
    if parser is None:
        raise Usage(HELP)
    return parser(rest.strip())


def state_text(state: dict) -> str:
    """The project state as one private Slack message (/coordinator plan)."""
    names = state.get("names")
    charter = state.get("charter")
    lines = ["*Cadence · Project plan*", f"*Goal*\n{charter['goal'] if charter else 'No charter yet: create the project in the web app, then link this channel with `/coordinator link`.'}"]
    sections = {
        "Milestones": [f"{m['title']} — {m.get('due_date') or 'no date'}" for m in state.get("milestones", [])],
        "Members": [m["display_name"] + (f" · {m['discipline']}" if m.get("discipline") else "") for m in state.get("members", [])],
        # Numbered: /coordinator task takes this number.
        "Tasks": [
            f"{n}. {t['title']} · {t['status']}"
            + (f" · {who(t['owner_id'], names)}" if t.get("owner_id") else "")
            + (f" · {t['due_date']}" if t.get("due_date") else "")
            for n, t in enumerate(state.get("tasks", []), start=1)
        ],
        "Decisions": [f"{d['question']} → {d['choice']}" for d in state.get("decisions", [])],
    }
    for title, items in sections.items():
        lines.append(f"*{title}*\n" + ("\n".join(f"• {item}" for item in items) or "—"))
    return "\n\n".join(lines)[:2900]
