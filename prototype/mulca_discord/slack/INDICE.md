# INDICE — `mulca_discord/slack/`

The Slack channel of the Group Coordinator. A Slack channel the bot was
invited to is one MUCA conversation, `slack:<channel id>`; it can be linked to
a web space with `/coordinator link <invite code>`. Setup: `prototype/SLACK_SETUP.md`.

```
Slack (Socket Mode) ── __main__.py ──> hub.py SlackHub ──> SessionRegistry ──> MUCA-Server
   message                on_message        user_text
   /coordinator ...       on_command        coordinator_command   (commands.py parses the text)
   card button            on_action         proposal_response
                                            <── coordinator_proposal  -> cards.py (Block Kit)
                                            <── coordinator_mirror    -> one line in the channel
```

| File | Lines | Responsibility |
|---|---|---|
| `__main__.py` | 94 | Entry point: Socket Mode, acknowledges each request, hands it to the hub. |
| `hub.py` | 273 | Between Slack and MUCA-Server: messages, commands, clicks, cards, mirror. |
| `api.py` | 77 | `SlackApi`, the few Slack calls the hub needs (Adapter), and the real one over `slack_sdk`. |
| `cards.py` | 91 | A proposal as Block Kit blocks and buttons; content from `coordinator/card_content.py`. |
| `commands.py` | 131 | The text after `/coordinator` -> a command (one small parser each), and the plan as text. |
| `ids.py` | 40 | Slack user ids <-> the integer ids MUCA-Server uses. |
| `installs.py` | 85 | The workspaces added with "Add to Slack": one bot token each, in SQLite (written by `web/connect_routes.py`). |
| `workspaces.py` | 140 | One app in many workspaces: a `SlackApi` that picks each channel's workspace token. |

Design patterns used, and why:
- **Adapter** (`api.py`, `SlackChannel`): the hub and `dispatch.py` see the same small
  interface whether the channel is Discord, the web or Slack.
- **Command table** (`commands.py` `PARSERS`): a new slash command is one function and one entry.
- Shared content (`coordinator/card_content.py`, `coordinator/texts.py`): a card and a
  catch-up read the same on every channel.

Tests: `tests/test_slack.py` (fake Slack, real local MUCA-Server). Not verified against the real Slack API.
