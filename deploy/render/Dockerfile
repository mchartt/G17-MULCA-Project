# Cadence online (Render, free plan): ONE container with the two processes
# the demo already runs on a laptop (webapp/scripts/demo-up.sh):
#   1. MUCA-Server, coordinator on, listening only inside the container (:8000)
#   2. the web adapter, public on $PORT (Render sets it), talking to 1
# The frontend is not here: it is the static site on Vercel.
#
# Built from the "render" branch, which is group17/coordinator plus a copy
# of muca-server in vendor/muca-server (deploy/render/update-branch.sh).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# MUCA-Server (the brain), the same install as its own Dockerfile.
COPY vendor/muca-server/pyproject.toml vendor/muca-server/README.md /src/muca-server/
COPY vendor/muca-server/muca_server /src/muca-server/muca_server
RUN pip install "/src/muca-server[server,openai,storage]"

# MULCA (the web adapter), without the -e line that points to the sibling clone.
COPY prototype/requirements.txt ./
RUN grep -v -- '-e ../../MUCA-Server' requirements.txt > /tmp/requirements.txt \
    && pip install -r /tmp/requirements.txt
COPY prototype/mulca_discord ./mulca_discord
# Fails the build now, not at the first request, if something is missing.
RUN python -c "import muca_server.run_server, mulca_discord.web"

COPY deploy/render/start.sh /app/start.sh
RUN useradd --system --no-create-home cadence && mkdir -p /data && chown cadence /data /app

# The free plan has no persistent disk: /data is emptied at every restart
# or redeploy (spaces, memory, project state). Known limit, PROGRESS.md.
ENV MUCA_DB_DIR=/data/muca \
    MUCA_SERVER_HOST=127.0.0.1 \
    MUCA_SERVER_PORT=8000 \
    MUCA_SERVER_URL=ws://127.0.0.1:8000/ \
    MULCA_WEB_DB=/data/web.sqlite3 \
    MULCA_WEB_HOST=0.0.0.0 \
    MUCA_LOG_LEVEL=INFO

USER cadence
CMD ["sh", "/app/start.sh"]
