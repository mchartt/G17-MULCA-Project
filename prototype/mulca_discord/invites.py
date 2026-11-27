"""
A web space's invite link pasted in a Discord or Slack channel.

The simplest way to join a channel to the project: paste the link the web app
shows ("…/join/AB12CD34" or the older "…?code=AB12CD34"). Only a link counts,
never a bare word, so no ordinary message ever links a channel by mistake.
The code itself is checked by MUCA-Server (links.invite_code), as for
/coordinator link.
"""

from __future__ import annotations

import re

INVITE_LINK = re.compile(r"https?://\S+?(?:/join/|[?&]code=)([A-Za-z0-9]{4,20})\b", re.IGNORECASE)


def invite_in(text: str) -> str | None:
    """The invite code of the first invite link in the message, upper case; None without one."""
    found = INVITE_LINK.search(text or "")
    return found[1].upper() if found else None
