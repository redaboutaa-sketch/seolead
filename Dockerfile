# SEO Lead Factory application image.
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN groupadd --gid 10002 seolead \
 && useradd --uid 10002 --gid 10002 --create-home --home-dir /home/seolead \
            --shell /usr/sbin/nologin seolead

WORKDIR /app

# Dependencies first so application edits do not invalidate the layer.
COPY pyproject.toml /app/pyproject.toml
RUN pip install --no-cache-dir \
      "fastapi>=0.115" "uvicorn[standard]>=0.32" "pydantic>=2.9" \
      "pydantic-settings>=2.6" "sqlalchemy[asyncio]>=2.0.36" "asyncpg>=0.30" \
      "alembic>=1.14" "httpx>=0.27" "pyyaml>=6.0"

COPY app /app/app
COPY config /app/config
COPY migrations /app/migrations
COPY alembic.ini /app/alembic.ini

# `seolead` on PATH without a build step.
RUN printf '#!/bin/sh\nexec python -m app.cli "$@"\n' > /usr/local/bin/seolead \
 && chmod 0555 /usr/local/bin/seolead

USER seolead

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--no-server-header"]
