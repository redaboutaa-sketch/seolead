# SEO Lead Factory — isolated Last30Days runner.
#
# Structurally the same two-stage build ChainPilot uses, and pinned to the same
# engine commit, so both projects run an identical engine. The build context is
# /opt/seolead, so nothing outside this repository is read.
#
# The three properties this file must guarantee, each verifiable:
#
#   1. The engine commit is PINNED and the build FAILS if that exact commit
#      cannot be fetched and verified. Following a branch would make two
#      identical research runs return different results with nothing to explain it.
#   2. The process runs NON-ROOT on a read-only filesystem with one writable volume.
#   3. NO secret enters an image layer. Keys arrive from the environment at
#      container start.

FROM python:3.12-slim-bookworm AS fetch

ARG LAST30DAYS_REPO=https://github.com/mvanhorn/last30days-skill.git
# Deliberate pin. Change only on purpose, never automatically.
ARG LAST30DAYS_REF=52f53312ff2f272e16bbc1785e1c04f9d9c19b31

RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /src

# `git fetch <sha>` fails if the server will not serve that exact commit, and the
# rev-parse check fails if HEAD is not exactly the requested SHA. A
# `clone --branch` + checkout would silently accept a moved tag; this does not.
#
# The hex guard rejects any non-hex character FIRST, then checks the length.
# Testing `[0-9a-f]*` alone only inspects the first character, which would let a
# 40-character string ending in `Z` through and turn a readable refusal into an
# obscure git error later.
RUN set -eux; \
    case "$LAST30DAYS_REF" in \
      *[!0-9a-f]*) \
        echo "LAST30DAYS_REF must be lowercase hex — got: $LAST30DAYS_REF" >&2; \
        echo "A branch or tag is not accepted: it can move, and a moving engine" >&2; \
        echo "makes every research run irreproducible." >&2; \
        exit 1;; \
    esac; \
    [ "${#LAST30DAYS_REF}" = 40 ] || { \
      echo "LAST30DAYS_REF must be a full 40-character commit SHA, got ${#LAST30DAYS_REF} chars" >&2; \
      exit 1; }; \
    git init -q .; \
    git remote add origin "$LAST30DAYS_REPO"; \
    git fetch --depth 1 origin "$LAST30DAYS_REF"; \
    git checkout -q FETCH_HEAD; \
    ACTUAL="$(git rev-parse HEAD)"; \
    if [ "$ACTUAL" != "$LAST30DAYS_REF" ]; then \
      echo "PIN VERIFICATION FAILED: expected $LAST30DAYS_REF, got $ACTUAL" >&2; \
      exit 1; \
    fi; \
    echo "$ACTUAL" > /src/.engine_commit; \
    python3 -c "import re,pathlib,sys; \
t=pathlib.Path('pyproject.toml').read_text(); \
m=re.search(r'^version\s*=\s*\"([^\"]+)\"', t, re.M); \
sys.exit('version not found in pyproject.toml') if not m else None; \
pathlib.Path('/src/.engine_version').write_text(m.group(1))"; \
    test -f skills/last30days/scripts/last30days.py \
      || { echo "engine entry point missing at the pinned commit" >&2; exit 1; }; \
    rm -rf .git


FROM python:3.12-slim-bookworm AS runtime

LABEL org.opencontainers.image.title="seolead-last30days-runner" \
      org.opencontainers.image.description="Isolated Last30Days research runner for SEO Lead Factory" \
      org.opencontainers.image.source="https://github.com/mvanhorn/last30days-skill"

ARG LAST30DAYS_REF=52f53312ff2f272e16bbc1785e1c04f9d9c19b31

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    L30D_ENGINE_BIN=last30days \
    L30D_MEMORY_DIR=/data/last30days \
    L30D_TIMEOUT_SECONDS=600 \
    L30D_MAX_CONCURRENT_RUNS=2 \
    HOME=/home/runner

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --gid 10001 runner \
 && useradd --uid 10001 --gid 10001 --create-home --home-dir /home/runner \
            --shell /usr/sbin/nologin runner

COPY infra/last30days/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

COPY --from=fetch /src /opt/last30days
COPY --from=fetch /src/.engine_commit /opt/.engine_commit
COPY --from=fetch /src/.engine_version /opt/.engine_version

# The engine declares no console script, so an explicit launcher is installed
# rather than assuming a binary that does not exist.
RUN printf '#!/bin/sh\nexec python3 /opt/last30days/skills/last30days/scripts/last30days.py "$@"\n' \
      > /usr/local/bin/last30days \
 && chmod 0555 /usr/local/bin/last30days \
 && L30D_ENGINE_COMMIT="$(cat /opt/.engine_commit)" \
 && if [ "$L30D_ENGINE_COMMIT" != "$LAST30DAYS_REF" ]; then \
      echo "runtime pin mismatch: $L30D_ENGINE_COMMIT != $LAST30DAYS_REF" >&2; exit 1; \
    fi

COPY infra/last30days/runner /opt/runner

RUN mkdir -p /data/last30days && chown -R runner:runner /data/last30days

USER runner
WORKDIR /opt/runner

ENV L30D_ENGINE_COMMIT_FILE=/opt/.engine_commit \
    L30D_ENGINE_VERSION_FILE=/opt/.engine_version

# No port is published by compose; EXPOSE is documentation for the internal network.
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python3 -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=4).status==200 else 1)"

ENTRYPOINT ["/bin/sh", "-c", \
  "export L30D_ENGINE_COMMIT=$(cat /opt/.engine_commit) \
   && export L30D_ENGINE_VERSION=$(cat /opt/.engine_version) \
   && exec uvicorn app:app --host 0.0.0.0 --port 8080 --workers 1 --no-server-header"]
