# MULCA imports MUCA-Server's protocol and audio code (requirements.txt
# installs it from ../../MUCA-Server), so the build needs that repo too, as a
# named build context:
#
#   docker buildx build --build-context muca-server=../../MUCA-Server .
#
# The GitLab pipeline (.gitlab-ci.yml) does this for you.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# libopus: discord.py loads it at runtime to encode and decode voice.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libopus0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=muca-server pyproject.toml README.md /src/muca-server/
COPY --from=muca-server muca_server /src/muca-server/muca_server
RUN pip install /src/muca-server

COPY requirements.txt ./
RUN grep -v -- '-e ../../MUCA-Server' requirements.txt > /tmp/requirements.txt \
    && pip install -r /tmp/requirements.txt

COPY mulca_discord ./mulca_discord
# Fails the build now, not the first Discord message, if a dependency is missing.
RUN python -c "import discord.opus, mulca_discord.muca_client, mulca_discord.voice.bridge, mulca_discord.commands, mulca_discord.runtime; discord.opus._load_default() or exit('libopus not found')"

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && useradd --system --no-create-home mulca \
    && chown mulca /app

USER mulca

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "-m", "mulca_discord"]
