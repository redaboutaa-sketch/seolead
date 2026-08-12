# Runbook — Last30Days runtime

## Boundary

`seolead_last30days` is ours. `last30days_runner` is ChainPilot's and is **defined
but has never been started** on this host. Never operate on the wrong one.

```bash
docker ps -a --filter name=last30days --format '{{.Names}}\t{{.Status}}'
```

Expect exactly one running container, `seolead_last30days`. If
`last30days_runner` ever appears, someone started ChainPilot's overlay — that is
not ours to stop, and it does not affect us.

## Build

```bash
cd /opt/seolead
docker compose build seolead_last30days
```

The build fetches the engine from GitHub at commit
`52f53312ff2f272e16bbc1785e1c04f9d9c19b31` and **fails closed** if that exact
commit cannot be fetched and verified. It also rejects a branch or tag: a moving
engine makes every research run irreproducible.

Network access to `github.com` is required. Without it the build fails at the
fetch stage with a readable error rather than silently building something else.

Changing the pin is deliberate:

```bash
LAST30DAYS_REF=<40-char-sha> docker compose build seolead_last30days
```

Record the change and re-run a known query — results are not comparable across
engine builds, which is why `research_run.engine_commit` is stored on every run.

## Start, stop, inspect

```bash
docker compose up -d seolead_last30days
docker compose logs -f seolead_last30days
docker compose stop seolead_last30days
```

```bash
docker exec seolead_api python -c "
import asyncio, httpx, json
async def m():
    async with httpx.AsyncClient(base_url='http://seolead_last30days:8080') as c:
        print((await c.get('/healthz')).json())
        print((await c.get('/readyz')).json())
        print(json.dumps((await c.get('/doctor')).json(), indent=2)[:1500])
asyncio.run(m())"
```

`/healthz` reports `engine_commit` and `engine_version` from files baked into the
image, so the image cannot misreport what it contains. As of 2026-08-12: engine
version `3.18.4` at the pinned commit.

## Security posture

Inherited from the upstream design and verifiable with `docker inspect`:

- **No published port.** Reachable only from `seolead_backend`.
- **No authentication** — network isolation is the entire control. Never expose it
  through Traefik and never add a host port binding.
- `read_only: true`, one writable volume (`seolead_last30days_memory`).
- `user: 10001:10001`, `cap_drop: ALL`, `no-new-privileges`.
- `/tmp` on tmpfs, `noexec,nosuid`, 256 MB.
- 1.0 CPU / 768 MiB limits. Measured idle: ~40 MiB.
- API keys arrive from the environment at start; none is in an image layer.

The runner downloads hostile content by construction. Every one of those
properties exists for that reason.

## Source API keys

All optional. **An absent key is a valid, informative state**: the source reports
`skipped-unconfigured`, which the pipeline records as "never queried" — never as
"found nothing".

```
SERPER_API_KEY=     # web/grounding search — NOT provisioned
TAVILY_API_KEY=     # web/grounding search — NOT provisioned
REDDIT_CLIENT_ID= / REDDIT_CLIENT_SECRET=
X_BEARER_TOKEN= / YOUTUBE_API_KEY= / GITHUB_TOKEN=
```

Set them in `/opt/seolead/.env` and `docker compose up -d seolead_last30days`.
Never in `/opt/techformanord/.env`, and never in git.

## Current capability — measured

| Source | Without a key |
|---|---|
| `hackernews` | works well; 12 relevant results for an English tech query |
| `grounding` (requested as `web`) | `no-results` or `unreachable` — needs Serper/Tavily |
| `reddit` | `partial`, 0 items |
| `youtube` | `skipped-unconfigured` |

**The engine returns no SERP structure at all**, with or without a key. It is a
recent-discussion engine. See `docs/providers/LAST30DAYS.md` for the full
characterisation and what it means for Phase 3.

## Troubleshooting

| Symptom | Cause | Action |
|---|---|---|
| build fails at `git fetch` | no GitHub access, or a bad pin | check egress; verify the SHA is 40 lowercase hex |
| `PIN VERIFICATION FAILED` | server served a different commit | do not override; investigate |
| `/readyz` 503 | engine binary missing or memory dir not writable | rebuild; check the volume |
| 504 from `/v1/research` | engine exceeded `L30D_TIMEOUT_SECONDS` | narrow the topic or raise the timeout |
| 502 `engine exited N` | engine failure | read the bounded stderr in the response detail |
| all sources `skipped-unconfigured` | no keys set | expected |
| container unhealthy after start | still warming | `start_period` is 20 s; then read logs |

## Concurrency

`L30D_MAX_CONCURRENT_RUNS=1`, deliberately below ChainPilot's 2: this host runs 40
containers on 4 CPUs with swap near exhaustion. Raise only after re-checking
`free -h` and `docker stats`.
