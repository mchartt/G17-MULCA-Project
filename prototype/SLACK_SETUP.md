# Cadence on Slack: setup in five minutes

The Slack channel uses **Socket Mode**: the bot opens the connection to Slack
itself, so it needs no public address. It works on a laptop and on Render.

## 1. Create the Slack app

1. Open https://api.slack.com/apps, **Create New App**, **From a manifest**.
2. Pick your workspace and paste the manifest below (YAML).
3. **Install to Workspace** and allow it.

```yaml
display_information:
  name: Cadence
  description: The group's project coordinator
features:
  bot_user:
    display_name: Cadence
    always_online: true
  slash_commands:
    - command: /coordinator
      description: The group's project coordinator
      usage_hint: "kickoff | planning | checkin | task | why | plan | link | catchup"
      should_escape: false
oauth_config:
  scopes:
    bot:
      - chat:write          # post answers and cards
      - commands            # /coordinator
      - channels:history    # read messages in public channels it was invited to
      - groups:history      # the same, private channels
      - channels:read       # who is in the channel
      - groups:read
      - users:read          # members' names
      - app_mentions:read
settings:
  event_subscriptions:
    bot_events:
      - message.channels
      - message.groups
      - member_joined_channel   # Cadence greets a channel it is added to
  interactivity:
    is_enabled: true        # the buttons on the cards
  socket_mode_enabled: true
```

## 2. The two tokens

| Variable | Where to find it | Starts with |
|---|---|---|
| `SLACK_BOT_TOKEN` | OAuth & Permissions, "Bot User OAuth Token" | `xoxb-` |
| `SLACK_APP_TOKEN` | Basic Information, App-Level Tokens, **Generate** with the scope `connections:write` | `xapp-` |

Put them in `prototype/.env` (never in git), or in Render's Environment page.

## 3. Run it

MUCA-Server must be running with `MUCA_COORDINATOR_ENABLED=true`, then:

```sh
cd prototype && python -m mulca_discord.slack
```

On Render nothing else is needed: `deploy/render/start.sh` starts the Slack
channel when the two tokens are set.

## 4. Try it

1. In Slack, invite the bot to your group's channel: `/invite @Cadence`.
   Cadence greets the channel with the two steps below.
2. **Paste the web space's invite link** in the channel (the web app shows it
   under *Connect Slack or Discord*), or `/coordinator link <invite code>`.
   From now on the plan, the tasks, the decisions and the cards are shared,
   and messages written on Slack show in the web chat.
3. Talk as usual: cards appear here, on the web and on a linked Discord
   channel; one click confirms everywhere. Write `Cadence` or `@Cadence` to
   ask about the project.
4. `/coordinator task add <title>`, `task 3 waits on 1, 2`, `task 2 done`:
   the plan changes for everyone.

## App icon

Basic Information → Display Information → App icon: upload
`webapp/public/brand/cadence-icon-512.png` (the Cadence mark, 512×512), and
background colour `#2E2A5A`.

`/coordinator help` lists every command.

## Not verified live

Everything is tested offline with a fake Slack against a real local
MUCA-Server (`tests/test_slack.py`). The run against the real Slack API, with
the two tokens, still has to be done by the team.
