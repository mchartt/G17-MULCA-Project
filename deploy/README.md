# Deploying to the swarm

MULCA (the Discord bot) and MUCA-Server run as one Docker Swarm stack, deployed through
Swarmpit at https://swarm.i3lab.group. Swarmpit doesn't build images. GitLab does: each repo
has a GitLab copy whose pipeline builds its image into that project's container registry.

| Repo        | GitLab project                              | Image                                         |
| ----------- | ------------------------------------------- | --------------------------------------------- |
| MUCA-Server | https://gitlab.com/i3lab/muca/muca-server   | `registry.gitlab.com/i3lab/muca/muca-server`  |
| MULCA       | https://gitlab.com/i3lab/muca/mulca         | `registry.gitlab.com/i3lab/muca/mulca`        |

The team's code stays on GitHub. The GitLab copies aren't mirrors (that's a paid GitLab
feature), so they only change when you push to them.

## Every deploy

Push the `gitlab-deployment` branch to GitLab, in whichever repo changed:

```sh
git push origin gitlab-deployment   # GitHub, for the team
git push gitlab gitlab-deployment   # GitLab: builds and pushes the image
```

Each pipeline tags its image twice: with the commit (`:<8-char hash>`) and with the branch
(`:gitlab-deployment`). The stack follows the branch tag, and Swarmpit's autoredeploy picks up
the new image by itself within a few minutes. Nothing to do in Swarmpit.

MULCA's image includes MUCA-Server's source, taken from MUCA-Server's GitLab project at the
`gitlab-deployment` branch when MULCA's pipeline runs. So after a MUCA-Server change that MULCA
depends on (the protocol, the audio helpers), push MUCA-Server first, then re-run MULCA's
pipeline (Build > Pipelines > Run pipeline). Each MULCA image records the MUCA-Server commit it
was built with, as the `muca-server.commit` label.

To pin or roll back, replace `:gitlab-deployment` in the stack with a commit tag from the
project's Deploy > Container registry, and update the stack in Swarmpit.

## Once, before the first deploy

1. **Remotes** (on each machine that deploys): in each repo,
   `git remote add gitlab https://gitlab.com/i3lab/muca/<muca-server|mulca>.git`.

2. **Job token access.** MULCA's pipeline clones MUCA-Server. In MUCA-Server on GitLab, open
   Settings > CI/CD > Job token permissions and add `i3lab/muca/mulca`.

3. **Registry login for the swarm.** In the `i3lab/muca` group, open Settings > Repository >
   Deploy tokens and create one with only `read_registry`. A group token can pull every
   project's images in the group, which matters: Swarmpit keeps one login per registry
   address, and both images are on `registry.gitlab.com`. Then at
   https://swarm.i3lab.group/#/registries link a **Registry v2** registry: URL
   `https://registry.gitlab.com`, with auth, and the token's username and value. Not the
   GitLab type: that one wants a personal access token with full API access. Leave "Public"
   off unless other Swarmpit users must manage this stack (it shares the login with every
   Swarmpit user, not the images with the world). Without a registry login, the services sit
   at "no such image".

4. **Secrets** (Swarmpit: Secrets > New secret):

   | Secret name               | Value                  |
   | ------------------------- | ---------------------- |
   | `muca_openai_api_key`     | the OpenAI API key     |
   | `mulca_discord_bot_token` | the Discord bot token  |

   The containers receive them as `OPENAI_API_KEY` and `DISCORD_BOT_TOKEN`. Keys never go in
   the stack file.

5. **The stack.** Stacks > New stack, name it `muca`, and paste `deploy/stack.yml`. Swarm
   names services `<stack>_<service>`, so they show up as `muca_muca-server` and `muca_mulca`.

## Things to know

- **Commands in Discord.** `/restart` in a MULCA channel restarts it, keeping its memory, and
  anyone can use it. `/mulca status`, `/mulca restart`, `/mulca stop` and `/mulca start` need
  the Manage Server permission. See `prototype/README.md` for the details.
- **The 60-minute OpenAI limit is handled.** OpenAI ends each Realtime connection after an
  hour. MUCA-Server then saves the memory and ends that session, and the bot opens a new one
  without anyone noticing. If MULCA ever stops answering anyway, `/restart` fixes it.
- **What a redeploy keeps.** A redeploy replaces containers, not volumes. Memory (in
  `muca-data`) and the secrets survive. The bot logs out cleanly first (`stop_grace_period`),
  so MUCA-Server saves each conversation. `/mulca stop` doesn't survive a redeploy yet: a
  redeployed bot starts again. Memory is lost only if the volume is deleted, the stack is
  renamed (volume names start with the stack name), or the `i3lab` node is lost, so back up
  the volume.

- **Only one bot.** Two processes on the same bot token both answer every message. The stack
  runs exactly one `mulca` and stops the old container before starting the new one.
  Don't also run the bot locally with the production token while the stack is up.
- **Both services run on the node `i3lab`** (`placement` in `stack.yml`). MUCA-Server's SQLite
  files are in the `muca-data` volume, which is local to the node that runs it, so moving it
  to another node would start with empty memory. The bot exited at startup on `i3lab-vm-1`,
  which also hosts the GitLab runner. If the node's name ever changes, the services sit at
  "no suitable node" until the constraint is updated.
- **MUCA-Server isn't exposed outside the swarm.** MULCA reaches it as
  `ws://muca-server:8000/` on the stack's own network. Uncomment `ports` in `stack.yml` only
  if a client outside the swarm (e.g. the Unity app) needs to connect directly.
- **Channels and rosters** come from `prototype/mulca_discord/instances.yaml`, built into the
  image. Changing them means a push and a new build. The entries are a priority list: the bot
  runs as the first one whose text channel it can see (team-alpha, else team-beta), and the
  `muca_mulca` logs say which (`Running as instance …`). Discord allows a bot in only one
  voice channel per server, so two teams at once need a second bot account, with its own
  token, secret and `mulca` service.
- **Building locally**, to check an image builds before pushing:

  ```sh
  docker build -t muca-server ../MUCA-Server
  docker buildx build --build-context muca-server=../MUCA-Server -t mulca prototype
  ```
