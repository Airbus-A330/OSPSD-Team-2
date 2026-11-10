# Both bases are immutable; update deliberately and rerun the container checks.
FROM ghcr.io/astral-sh/uv:0.12.17@sha256:10787c682e4184e4f290de1171fd4703dc63de99221f10fe1c99002ce7fa9acc AS uv
FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS dependencies
COPY --from=uv /uv /usr/local/bin/uv
# Git is needed only to resolve the shared package's locked Git revision.
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-editable

FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS runtime
RUN groupadd --gid 10001 calendar && useradd --uid 10001 --gid calendar --no-create-home calendar && mkdir -p /var/data && chown calendar:calendar /var/data
WORKDIR /app
COPY --from=dependencies /app/.venv /app/.venv
COPY app/ /app/app/
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PORT=10000 GOOGLE_CALENDAR_NONINTERACTIVE=1
USER 10001:10001
EXPOSE 10000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ['PORT'] + '/readyz', timeout=3)"
# One worker is required for the credential lock and process-local cache.
# Disable access logs: raw paths contain event IDs; existing sanitized app logs remain.
CMD ["sh", "-c", "exec uvicorn app.hosting:app --host 0.0.0.0 --port \"${PORT}\" --workers 1 --no-access-log"]
