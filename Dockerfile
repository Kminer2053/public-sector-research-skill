# syntax=docker/dockerfile:1.7

ARG PYTHON_IMAGE=python:3.12.13-slim-bookworm@sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b

FROM ${PYTHON_IMAGE} AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_NO_PROGRESS=1

WORKDIR /build

COPY pyproject.toml uv.lock README.md ./
COPY requirements/container-build.txt ./requirements/container-build.txt
COPY src ./src

RUN python -m pip install \
      --no-cache-dir \
      --only-binary=:all: \
      --require-hashes \
      --requirement requirements/container-build.txt \
    && uv export \
      --frozen \
      --no-dev \
      --no-emit-project \
      --format requirements.txt \
      --output-file /tmp/requirements.txt \
    && python -m pip wheel \
      --only-binary=:all: \
      --require-hashes \
      --wheel-dir /wheels \
      --requirement /tmp/requirements.txt \
    && uv build \
      --no-build-isolation \
      --python /usr/local/bin/python \
      --wheel \
      --out-dir /wheels

FROM ${PYTHON_IMAGE} AS runtime-base

LABEL org.opencontainers.image.title="Public Sector Research MCP" \
      org.opencontainers.image.description="Anonymous zero-retention public-sector research MCP" \
      org.opencontainers.image.source="https://github.com/Kminer2053/public-sector-research-mcp"

ENV HOME=/nonexistent \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PSR_ENV=production \
    PSR_SERVICE_MODE=public_ephemeral \
    PSR_AUTH_MODE=static \
    PSR_STORAGE_MODE=memory \
    PSR_HOST=0.0.0.0 \
    PSR_PORT=8000 \
    PSR_EPHEMERAL_ROOT=/var/lib/psr/ephemeral \
    PSR_PUBLIC_PAUSE_FILE=/run/psr/public.pause \
    PSR_LOG_LEVEL=INFO

COPY --from=builder /wheels /wheels

RUN python -m pip install \
      --no-cache-dir \
      --no-compile \
      --no-index \
      --find-links=/wheels \
      public-sector-research-mcp==0.1.0.dev0 \
    && python -m pip check \
    && rm -rf /wheels \
    && install -d -m 0755 /srv/psr /opt/psr \
    && install -d -m 0700 /var/lib/psr/ephemeral /run/psr \
    && chown 10001:10001 /var/lib/psr/ephemeral /run/psr

WORKDIR /srv/psr

EXPOSE 8000
STOPSIGNAL SIGTERM

USER 10001:10001

ENTRYPOINT ["psr-mcp"]

FROM runtime-base AS test

COPY --chown=10001:10001 scripts/container_smoke.py /opt/psr/container_smoke.py

FROM runtime-base AS runtime
