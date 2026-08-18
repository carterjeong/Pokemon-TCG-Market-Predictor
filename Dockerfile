# syntax=docker/dockerfile:1
# ============================================================
# Hardened multi-stage build — Owner: CyberSec partner
#   * multi-stage: build tools never reach the runtime image
#   * non-root user (uid/gid 10001), no shell login, no home write access
#   * slim base, pinned tag; upgrade to digest pinning in CI
# ============================================================

# ---------- Stage 1: builder ----------
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

# Build deps only in this stage (asyncpg ships wheels; keep gcc for fallback)
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# ---------- Stage 2: runtime ----------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Non-root user: fixed high UID, no login shell, no password
RUN groupadd --gid 10001 appgroup \
    && useradd --uid 10001 --gid appgroup --shell /usr/sbin/nologin \
       --no-create-home appuser

WORKDIR /srv/app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=root:root --chmod=755 app ./app

USER appuser:appgroup

EXPOSE 8000

# Container-level healthcheck without curl (smaller attack surface)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status==200 else sys.exit(1)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
