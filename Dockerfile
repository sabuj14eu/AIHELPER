# AI Helper — application image.
#
# Two stages so nothing but the virtualenv and the source reaches the runtime
# image, and the container runs as a non-root user.
#
# There is deliberately no apt-get here. Every runtime dependency installs as a
# pre-built wheel, psycopg[binary] bundles its own libpq, and useradd is in the
# base image — so the build needs no compiler, no system libraries and no
# Debian package repository. That makes the image smaller, faster to build,
# and buildable on a host with no access to deb.debian.org.

FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
COPY requirements.txt .

# --only-binary=:all: is a guard, not an optimisation. If a future dependency
# ever needs compiling, this build fails loudly here rather than silently
# growing a requirement for a toolchain the image does not have. The fix in
# that case is to add the toolchain to THIS stage — never to the runtime one.
#
# The optional `pip_ca` secret lets the image build behind a TLS-intercepting
# proxy, which is the normal situation on a corporate network:
#
#   docker build --secret id=pip_ca,src=/path/to/corporate-ca.crt .
#
# It is a build SECRET rather than a COPY on purpose: a certificate baked into
# a layer ships with the image and outlives the build. Omit it and the build
# behaves exactly as before, using the default trust store.
RUN --mount=type=secret,id=pip_ca,target=/tmp/pip-ca.crt \
    python -m venv /opt/venv \
    && if [ -s /tmp/pip-ca.crt ]; then export PIP_CERT=/tmp/pip-ca.crt; fi \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --only-binary=:all: -r requirements.txt


FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

RUN useradd --create-home --uid 10001 aihelper

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
# Probed with the interpreter that is already here rather than curl, so the
# image carries no package purely for its healthcheck.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz', timeout=4).status == 200 else 1)"]

# --factory so the app is built inside the worker rather than at import time.
CMD ["uvicorn", "app.main:create_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
