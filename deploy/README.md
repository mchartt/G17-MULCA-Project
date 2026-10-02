# Deploying to the swarm

MULCA (the Discord bot) and MUCA-Server run as one Docker Swarm stack, deployed through
Swarmpit at https://swarm.i3lab.group. Swarmpit doesn't build images. It pulls them from a
registry, so you build and push them from your machine and then paste the stack file into Swarmpit.

## Prerequisites

- Docker running locally (Docker Desktop on Windows), with `buildx` (included).
- MUCA-Server checked out beside this repo (`../MUCA-Server`), the same layout
  `prototype/requirements.txt` expects. Set `MUCA_SERVER_DIR` if yours is elsewhere.
- A container registry the swarm can pull from, and `docker login <registry host>` done once.
  With GitHub's registry, `REGISTRY=ghcr.io/<your-github-user>` (lowercase) and a classic
  personal access token with `write:packages` as the password.

## Every deploy

1. From Git Bash, in this repo:

   ```sh
   REGISTRY=ghcr.io/<owner> ./deploy/build-and-push.sh
   ```

   This builds both images for `linux/amd64`, pushes them, and writes `deploy/out/stack.yml`
   with the exact image tags, one commit hash per repo (`-dirty` if that repo had uncommitted
   changes). Commit before deploying, so you know what's running.

2. In Swarmpit: **Stacks**, then the `mulca` stack, then **Edit**. On the first deploy, use
   **New stack** and name it `mulca`. Replace the compose file with the contents of
   `deploy/out/stack.yml` and deploy.

Rolling back means pasting an older `out/stack.yml`, or editing the tags back to an older commit.

## Once, before the first deploy

- **Secrets** (Swarmpit: **Secrets**, then **New secret**). The stack expects both to exist:

  | Secret name               | Value                  |
  | ------------------------- | ---------------------- |
  | `muca_openai_api_key`     | the OpenAI API key     |
  | `mulca_discord_bot_token` | the Discord bot token  |

  The containers receive them as `OPENAI_API_KEY` and `DISCORD_BOT_TOKEN`. Keys never go in
  the stack file.

- **Registry access**. GHCR images are private by default, so the swarm needs a login to pull
  them. Without one, the services sit at "no such image". At
  https://swarm.i3lab.group/#/registries, link a registry of type **Registry v2**:
  URL `https://ghcr.io`, your GitHub username, and a classic personal access token with only
  `read:packages` as the password. Keep the `write:packages` token you push with on your machine.

## Things to know

- **Only one bot.** Two processes on the same bot token both answer every message. The stack
  runs exactly one `mulca-discord` and stops the old container before starting the new one.
  Don't also run the bot locally with the production token while the stack is up.
- **Conversation memory lives on one node.** MUCA-Server's SQLite files are in the `muca-data`
  volume, which is local to whichever node runs the service. If Swarm moves the service to
  another node, it starts with empty memory. Uncomment the `placement` constraint in
  `stack.yml` and set a node name to prevent that.
- **MUCA-Server isn't exposed outside the swarm.** MULCA reaches it as
  `ws://muca-server:8000/` on the stack's own network. Uncomment `ports` in `stack.yml` only
  if a client outside the swarm (e.g. the Unity app) needs to connect directly.
- **Channels and rosters** come from `prototype/mulca_discord/instances.yaml`, built into the
  image. Changing them means a rebuild and redeploy.
- **Build without pushing** (to check the images build): `PUSH=0 REGISTRY=local ./deploy/build-and-push.sh`.
  If the swarm's nodes are ARM, set `PLATFORM=linux/arm64`.
