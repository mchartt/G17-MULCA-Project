"""
The text after "/coordinator" on Slack, turned into a coordinator command.

Slack gives a slash command one line of free text, so the first word is the
command and the rest its argument:

    /coordinator kickoff <the assignment text>
    /coordinator planning Server API; UI screens; Slides
    /coordinator checkin
    /coordinator task 2 done
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
    "*Coordinator commands*\n"
    "• `/coordinator kickoff <assignment text>`: propose the project charter\n"
    "• `/coordinator planning <task>; <task>; …`: suggest who takes each task\n"
    "• `/coordinator checkin`: compare the plan with reality\n"
    "• `/coordinator task <number> <todo|doing|done|blocked>`: update a task\n"
    "• `/coordinator why <question>`: answer from the decision log\n"
    "• `/coordinator ask <question>`: answer from the saved plan, dates and decisions\n"
    "• `/coordinator plan`: show the project (only you see it)\n"
    "• `/coordinator profile <discipline> | <skills, comma separated> | <weekly hours>`\n"
    "• `/coordinator link <invite code>`: share the project with a web space\n"
    "• `/coordinator unlink` · `/coordinator catchup`\n"
    "You can also write `@coordinator` in the channel to ask it something."
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


def _task(rest: str) -> tuple[str, dict]:
    parts = rest.split()
    if len(parts) != 2 or not parts[0].isdigit() or parts[1].lower() not in STATUSES:
        raise Usage("Write the task's number in `/coordinator plan` and its new status: `/coordinator task 2 done`.")
    return "task", {"task": parts[0], "status": parts[1].lower()}


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


PARSERS: dict[str, Callable[[str], tuple[str, dict]]] = {
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
    lines = ["*Coordinator · Project plan*", f"*Goal*\n{charter['goal'] if charter else 'No charter yet: use `/coordinator kickoff`.'}"]
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
