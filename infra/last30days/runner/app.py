"""
Runner Last30Days isolé — la seule chose du système qui parle à internet ouvert.

**Ce que ce service est.** Une enveloppe HTTP minuscule autour du CLI
Last30Days. Il reçoit du JSON validé, construit une ligne de commande à partir
de valeurs contrôlées, exécute le moteur en sous-processus et renvoie son JSON.

**Ce qu'il n'est pas.** Il n'a aucun accès à la base OntoAlpha, aucune clé de
courtage, aucune notion de portefeuille ou d'ordre. Compromettre ce conteneur
ne donne ni la base, ni le capital.

Règles de construction de commande, sans exception :

* `subprocess.exec` avec une **liste d'arguments**, jamais `shell=True`.
* Aucun secret en argument : les clés d'API passent par l'environnement, elles
  n'apparaissent donc ni dans `ps`, ni dans les journaux, ni dans un message
  d'erreur.
* Le topic est passé par `--topic` en tant qu'argument unique. Il n'est jamais
  interpolé dans une chaîne de commande.
* `--json-profile=agent` est **codé en dur**. Le profil `raw` n'est jamais
  employé en production : il transporte du contenu brut non borné.
* Sortie plafonnée. Un moteur qui renverrait 200 Mo est une anomalie, pas un
  gros résultat.

Le service n'écoute que sur le réseau Docker interne ; aucun port n'est publié.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import time
import uuid
from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field, field_validator

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger("last30days_runner")

RUNNER_VERSION = "1.0.0"

# Le binaire du moteur. Résolu au démarrage, pas construit depuis une entrée.
ENGINE_BIN = os.environ.get("L30D_ENGINE_BIN", "last30days")
ENGINE_COMMIT = os.environ.get("L30D_ENGINE_COMMIT", "")
ENGINE_VERSION = os.environ.get("L30D_ENGINE_VERSION", "")

# Liste blanche de sources. Une source absente d'ici ne peut pas atteindre la
# ligne de commande, quoi qu'envoie l'appelant.
ALLOWED_SOURCES = frozenset({
    "reddit", "x", "youtube", "hackernews", "github", "polymarket",
    "stocktwits", "techmeme", "arxiv", "web",
})

MAX_OUTPUT_BYTES = 64 * 1024 * 1024      # 64 Mio
MAX_TOPIC_CHARS = 300
MIN_TOPIC_CHARS = 3
DEFAULT_TIMEOUT = int(os.environ.get("L30D_TIMEOUT_SECONDS", "600"))
MAX_CONCURRENCY = int(os.environ.get("L30D_MAX_CONCURRENT_RUNS", "2"))

# Caractères admis dans un topic. Tout le reste est retiré — pas échappé,
# retiré. Un topic n'a besoin ni de `$`, ni de backticks, ni de `;`.
_TOPIC_ALLOWED = re.compile(r"[^\w\s\-.,:&/'()+#]", re.UNICODE)

# Les clés d'API que le moteur consomme. Elles sont transmises par
# l'environnement ; leurs valeurs ne sont jamais journalisées ni renvoyées.
ENGINE_SECRET_ENV = (
    "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "X_BEARER_TOKEN",
    "YOUTUBE_API_KEY", "GITHUB_TOKEN", "SERPER_API_KEY", "TAVILY_API_KEY",
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
)

app = FastAPI(title="Last30Days Runner", version=RUNNER_VERSION,
              docs_url=None, redoc_url=None, openapi_url=None)

_semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

# Résultats déjà produits, par clé d'idempotence. Volontairement en mémoire :
# le cache ne survit pas au conteneur, ce qui est correct — la source de vérité
# de l'idempotence est PostgreSQL côté OntoAlpha, pas ici.
_idempotency_cache: dict[str, dict] = {}
_IDEMPOTENCY_CACHE_MAX = 256


class ResearchIn(BaseModel):
    topic: str = Field(..., min_length=MIN_TOPIC_CHARS, max_length=MAX_TOPIC_CHARS)
    sources: list[str] = Field(default_factory=list, max_length=20)
    window_days: int = Field(7, ge=1, le=30)
    verify_freshness: bool = True
    max_results: int = Field(200, ge=1, le=1000)
    correlation_id: str = Field("", max_length=64)

    @field_validator("topic")
    @classmethod
    def scrub_topic(cls, value: str) -> str:
        cleaned = _TOPIC_ALLOWED.sub(" ", value)
        cleaned = " ".join(cleaned.split())
        if len(cleaned) < MIN_TOPIC_CHARS:
            raise ValueError("topic contains no usable characters")
        return cleaned

    @field_validator("sources")
    @classmethod
    def check_sources(cls, value: list[str]) -> list[str]:
        cleaned = sorted({s.strip().lower() for s in value if s and s.strip()})
        unknown = [s for s in cleaned if s not in ALLOWED_SOURCES]
        if unknown:
            raise ValueError(f"unknown source(s): {', '.join(unknown)}")
        return cleaned

    @field_validator("correlation_id")
    @classmethod
    def check_correlation(cls, value: str) -> str:
        # Voyage jusque dans les journaux : on le borne à un alphabet sûr.
        return re.sub(r"[^A-Za-z0-9_\-]", "", value)[:64]


def engine_available() -> Optional[str]:
    return shutil.which(ENGINE_BIN)


def build_command(payload: ResearchIn) -> list[str]:
    """Construit `argv`. Chaque élément est un argument distinct — aucune
    concaténation, donc aucun métacaractère de shell à interpréter.

    Les options viennent du CLI réel de `last30days.py` au commit épinglé, lues
    dans `parser.add_argument`, pas supposées :

        topic            positionnel (`nargs="*"`), **pas** `--topic`
        --emit json      le contrat agent n'existe que sur ce mode
        --json-profile   `agent` en dur ; `raw` est interdit en production
        --search         liste de sources séparées par des virgules
        --days           fenêtre de lookback
        --max-results    plafond du pool classé
        --no-browser-cookies  toujours posé : le moteur ne doit jamais aller
                              lire les cookies d'un navigateur personnel

    `--` sépare les options du positionnel, pour qu'un topic commençant par un
    tiret ne puisse pas être lu comme une option.
    """
    argv = [
        ENGINE_BIN,
        "--emit", "json",
        # Codé en dur : `raw` n'est jamais utilisé en production.
        "--json-profile", "agent",
        "--days", str(payload.window_days),
        "--max-results", str(payload.max_results),
        "--no-browser-cookies",
    ]
    if payload.sources:
        argv += ["--search", ",".join(payload.sources)]
    argv.append("--verify-freshness" if payload.verify_freshness
                else "--no-verify-freshness")
    argv += ["--", payload.topic]
    return argv


def engine_env() -> dict:
    """Environnement du sous-processus : le minimum, plus les clés du moteur.

    On ne recopie pas l'environnement entier — le sous-processus n'a aucune
    raison de voir ce qui ne le concerne pas.
    """
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/home/runner"),
        "LANG": "C.UTF-8",
        "PYTHONUNBUFFERED": "1",
        "L30D_MEMORY_DIR": os.environ.get("L30D_MEMORY_DIR", "/data/last30days"),
        # Le moteur ne doit jamais aller lire les cookies d'un navigateur.
        "L30D_USE_BROWSER_COOKIES": "0",
    }
    for key in ENGINE_SECRET_ENV:
        value = os.environ.get(key)
        if value:
            env[key] = value
    return env


@app.get("/healthz")
async def healthz():
    """Le processus répond. Ne dit rien de la disponibilité des sources."""
    return {"status": "ok", "runner_version": RUNNER_VERSION,
            "engine_commit": ENGINE_COMMIT, "engine_version": ENGINE_VERSION}


@app.get("/readyz")
async def readyz():
    """Prêt = le binaire du moteur est là et le répertoire de travail est
    inscriptible. Un service qui répond 200 sans moteur mentirait à
    l'orchestrateur."""
    binary = engine_available()
    memory_dir = os.environ.get("L30D_MEMORY_DIR", "/data/last30days")
    writable = os.access(memory_dir, os.W_OK) if os.path.isdir(memory_dir) else False
    ready = bool(binary) and writable
    if not ready:
        raise HTTPException(status_code=503, detail={
            "ready": False,
            "engine_binary": binary or "not found",
            "memory_dir": memory_dir,
            "memory_dir_writable": writable,
        })
    return {"ready": True, "engine_binary": binary, "memory_dir": memory_dir}


@app.get("/doctor")
async def doctor(probe: bool = False):
    """Quelles sources sont configurées, lesquelles ne le sont pas.

    Répond par **présence de la variable**, jamais par sa valeur. Une clé
    absente est une information d'exploitation ; sa valeur est un secret.

    `?probe=true` exécute en plus le `--diagnose` du moteur, qui teste
    réellement les fournisseurs. Il n'est pas activé par défaut parce qu'il
    consomme du quota chez les sources — un diagnostic ne doit pas coûter la
    ressource qu'il diagnostique.
    """
    configured = {
        "reddit": bool(os.environ.get("REDDIT_CLIENT_ID")
                       and os.environ.get("REDDIT_CLIENT_SECRET")),
        "x": bool(os.environ.get("X_BEARER_TOKEN")),
        "youtube": bool(os.environ.get("YOUTUBE_API_KEY")),
        "github": bool(os.environ.get("GITHUB_TOKEN")),
        "web": bool(os.environ.get("SERPER_API_KEY")
                    or os.environ.get("TAVILY_API_KEY")),
        # Sources publiques sans clé.
        "hackernews": True, "polymarket": True, "stocktwits": True,
        "techmeme": True, "arxiv": True,
    }
    report = {
        "runner_version": RUNNER_VERSION,
        "engine_binary": engine_available(),
        "engine_commit": ENGINE_COMMIT,
        "engine_version": ENGINE_VERSION,
        "sources_configured": configured,
        "sources_unconfigured": sorted(k for k, v in configured.items() if not v),
        "engine_probe": None,
        "note": ("An unconfigured source is reported as skipped-unconfigured by "
                 "the engine. That is not the same as finding nothing."),
    }

    if probe and report["engine_binary"]:
        try:
            proc = await asyncio.create_subprocess_exec(
                ENGINE_BIN, "--diagnose",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                env=engine_env())
            out, err = await asyncio.wait_for(proc.communicate(), timeout=60)
            report["engine_probe"] = {
                "exit_code": proc.returncode,
                "stdout": out.decode("utf-8", "replace")[:4000],
                "stderr": err.decode("utf-8", "replace")[:1000],
            }
        except (asyncio.TimeoutError, OSError) as exc:
            report["engine_probe"] = {"error": type(exc).__name__,
                                      "detail": str(exc)[:200]}
    return report


@app.post("/v1/research")
async def research(payload: ResearchIn,
                   idempotency_key: str = Header("", alias="Idempotency-Key"),
                   correlation_id: str = Header("", alias="X-Correlation-Id")):
    binary = engine_available()
    if not binary:
        raise HTTPException(status_code=503,
                            detail=f"engine binary {ENGINE_BIN!r} not found")

    key = re.sub(r"[^A-Za-z0-9_\-]", "", idempotency_key)[:128]
    if key and key in _idempotency_cache:
        cached = dict(_idempotency_cache[key])
        cached["idempotent_replay"] = True
        return cached

    corr = (re.sub(r"[^A-Za-z0-9_\-]", "", correlation_id)[:64]
            or payload.correlation_id or uuid.uuid4().hex)
    run_id = uuid.uuid4().hex
    argv = build_command(payload)

    # Le topic est journalisé tronqué : il vient de l'extérieur.
    logger.info("run %s starting [correlation_id=%s sources=%s window=%s] topic=%r",
                run_id, corr, ",".join(payload.sources) or "default",
                payload.window_days, payload.topic[:60])

    started = time.monotonic()
    async with _semaphore:
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=engine_env(),
                cwd=os.environ.get("L30D_MEMORY_DIR", "/tmp"),
            )
        except OSError as exc:
            raise HTTPException(status_code=503,
                                detail=f"could not start engine: {exc}") from exc

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(),
                                                    timeout=DEFAULT_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise HTTPException(
                status_code=504,
                detail=f"engine exceeded {DEFAULT_TIMEOUT}s") from None

    duration_ms = int((time.monotonic() - started) * 1000)

    if len(stdout) > MAX_OUTPUT_BYTES:
        raise HTTPException(
            status_code=502,
            detail=f"engine emitted {len(stdout)} bytes, over the "
                   f"{MAX_OUTPUT_BYTES} byte cap")

    if proc.returncode != 0:
        # `stderr` peut contenir du contenu externe : tronqué, jamais renvoyé
        # en entier, et surtout jamais interprété.
        detail = stderr.decode("utf-8", "replace")[:500]
        raise HTTPException(
            status_code=502,
            detail=f"engine exited {proc.returncode}: {detail}")

    try:
        report = json.loads(stdout.decode("utf-8", "replace"))
    except ValueError as exc:
        raise HTTPException(status_code=502,
                            detail=f"engine output is not JSON: {exc}") from exc

    warnings = [line for line in
                stderr.decode("utf-8", "replace").splitlines()[:20] if line.strip()]

    result = {
        "run_id": run_id,
        "correlation_id": corr,
        "engine_version": ENGINE_VERSION,
        "engine_commit": ENGINE_COMMIT,
        "runner_version": RUNNER_VERSION,
        "duration_ms": duration_ms,
        "warnings": [w[:300] for w in warnings],
        "report": report,
        "idempotent_replay": False,
    }

    if key:
        if len(_idempotency_cache) >= _IDEMPOTENCY_CACHE_MAX:
            _idempotency_cache.pop(next(iter(_idempotency_cache)))
        _idempotency_cache[key] = result

    logger.info("run %s completed in %sms [results=%s]", run_id, duration_ms,
                len(report.get("results", []) if isinstance(report, dict) else []))
    return result
