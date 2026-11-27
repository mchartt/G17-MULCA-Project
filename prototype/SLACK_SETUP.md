# Cadence on Slack

**For a group (no setup):** in the web app, *Connect Slack or Discord* →
*Slack* → **Add Cadence to Slack**, pick the workspace, *Allow*. Then in the
group's channel write `/invite @Cadence` and paste the space's link. Done.

**For whoever runs the Cadence server (once):** create one Slack app, turn
on distribution, and give the server four values. After that every group
adds Cadence with the button: nobody else creates an app or copies a token.

The Slack channel uses **Socket Mode**: the bot opens the connection to Slack
itself, so it needs no public address for events. Only the "Add to Slack"
redirect comes to the web adapter (`/api/slack/oauth`).

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
  redirect_urls:
    - https://cadence-coordinator.onrender.com/api/slack/oauth   # your CADENCE_PUBLIC_URL + /api/slack/oauth
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
      - app_uninstalled         # a workspace removed Cadence: its token is deleted
      - tokens_revoked
  interactivity:
    is_enabled: true        # the buttons on the cards
  socket_mode_enabled: true
```

## 2. Let every workspace add it

1. **Manage Distribution** → check the list → **Activate Public Distribution**
   (this only allows the "Add to Slack" link; the app is not listed in the
   Slack Marketplace, which does not accept Socket Mode apps).
2. Give the server these values (Render → Environment, or `prototype/.env`;
   never in git):

| Variable | Where to find it | Note |
|---|---|---|
| `SLACK_APP_TOKEN` | Basic Information → App-Level Tokens → **Generate**, scope `connections:write` | starts with `xapp-` |
| `SLACK_CLIENT_ID` | Basic Information → App Credentials | |
| `SLACK_CLIENT_SECRET` | Basic Information → App Credentials | secret |
| `CADENCE_PUBLIC_URL` | the server's address, e.g. `https://cadence-coordinator.onrender.com` | must match the redirect URL above |

The web app then shows **Add Cadence to Slack**. Each workspace's bot token
is saved by the server in `slack_installs.sqlite3`, next to the web database
(`mulca_discord/slack/installs.py`), and deleted when the workspace removes
the app.

**Old setup, one workspace:** `SLACK_BOT_TOKEN` (OAuth & Permissions, "Bot
User OAuth Token", `xoxb-`) plus `SLACK_APP_TOKEN` still works, also together
with the button.

## 3. Run it

MUCA-Server must be running with `MUCA_COORDINATOR_ENABLED=true`, then:

```sh
cd prototype && python -m mulca_discord.slack
```

On Render nothing else is needed: `deploy/render/start.sh` starts the Slack
channel when `SLACK_APP_TOKEN` and either `SLACK_CLIENT_ID` or
`SLACK_BOT_TOKEN` are set. A workspace added with the button starts within a
minute, without a restart.

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
MUCA-Server (`tests/test_slack.py`, `tests/test_easy_connect.py`). NOT
VERIFIED LIVE: the real "Add to Slack" round trip (OAuth exchange, a second
workspace, uninstall) and the run against the real Slack API.
