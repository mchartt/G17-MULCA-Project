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
2. `/coordinator plan` shows the (empty) project, only to you.
3. `/coordinator link <invite code>` with the invite code of your web space.
   From now on the plan, the decisions and the cards are shared, and messages
   written on Slack show in the web chat (and the other way round).
4. Write `@Cadence` in the channel to ask the coordinator something.

`/coordinator help` lists every command.

## Not verified live

Everything is tested offline with a fake Slack against a real local
MUCA-Server (`tests/test_slack.py`). The run against the real Slack API, with
the two tokens, still has to be done by the team.
