"""
One name per person in a channel, before it reaches MUCA-Server.

The model reads "who said what" by name. Two people shown as "Luca" in the
same Discord or Slack channel would be one person to it. The first keeps the
name (lowest id), the others get a number: "Luca", "Luca 2". Across channels
MUCA-Server does the same with the channel's name ("Ada (Discord)",
coordination/names.py on the server).
"""

from __future__ import annotations


def unique_in_channel(names: dict) -> dict:
    """member id -> name, with a number added to repeated names. Order and ids unchanged."""
    seen: dict[str, list] = {}
    for member_id in sorted(names, key=str):
        seen.setdefault((names[member_id] or "member").strip().casefold(), []).append(member_id)
    result = {}
    for member_id, name in names.items():
        twins = seen[(name or "member").strip().casefold()]
        n = twins.index(member_id) + 1
        result[member_id] = name if n == 1 else f"{name} {n}"
    return result
