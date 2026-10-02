# Deploying to the swarm

MULCA (the Discord bot) and MUCA-Server run as one Docker Swarm stack, deployed through
Swarmpit at https://swarm.i3lab.group. Swarmpit doesn't build images. GitLab does: each repo
has a GitLab copy whose pipeline builds its image into that project's container registry.

| Repo        | GitLab project                                  | Image                                                  |
| ----------- | ----------------------------------------------- | ------------------------------------------------------ |
| MUCA-Server | https://gitlab.com/PietroAmmaturo/MUCA-Server   | `registry.gitlab.com/pietroammaturo/muca-server`       |
| MULCA       | https://gitlab.com/PietroAmmaturo/MULCA         | `registry.gitlab.com/pietroammaturo/mulca`             |

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
   `git remote add gitlab https://gitlab.com/PietroAmmaturo/<MUCA-Server|MULCA>.git`.

2. **Job token access.** MULCA's pipeline clones MUCA-Server. In MUCA-Server on GitLab, open
   Settings > CI/CD > Job token permissions and add `PietroAmmaturo/MULCA`.

3. **Registry login for the swarm.** In each GitLab project, open Settings > Repository >
   Deploy tokens and create one with only `read_registry`. Then at
   https://swarm.i3lab.group/#/registries link `https://registry.gitlab.com` (type GitLab, or
   Registry v2) with that token's username and value. Without this, the services sit at
   "no such image".

4. **Secrets** (Swarmpit: Secrets > New secret):

   | Secret name               | Value                  |
   | ------------------------- | ---------------------- |
   | `muca_openai_api_key`     | the OpenAI API key     |
   | `mulca_discord_bot_token` | the Discord bot token  |

   The containers receive them as `OPENAI_API_KEY` and `DISCORD_BOT_TOKEN`. Keys never go in
   the stack file.

5. **The stack.** Stacks > New stack, name it `mulca`, and paste `deploy/stack.yml`.

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
  image. Changing them means a push and a new build.
- **Building locally**, to check an image builds before pushing:

  ```sh
  docker build -t muca-server ../MUCA-Server
  docker buildx build --build-context muca-server=../MUCA-Server -t mulca prototype
  ```
