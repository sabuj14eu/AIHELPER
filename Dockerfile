# AI Helper — application image.
#
# Two stages so build tooling (compilers for psycopg, lxml) never ships in the
# runtime image, and the container runs as a non-root user.

FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt


FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 aihelper

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=aihelper:aihelper alembic.ini pyproject.toml ./
COPY --chown=aihelper:aihelper app ./app
COPY --chown=aihelper:aihelper scripts ./scripts

RUN chmod +x scripts/*.sh
USER aihelper

EXPOSE 8000

# The liveness probe is /healthz — process-up only. /health does component
# checks and is for humans and dashboards, not for a restart decision.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

# --factory so the app is built inside the worker rather than at import time.
CMD ["uvicorn", "app.main:create_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
