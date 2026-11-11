# syntax=docker/dockerfile:1
FROM python:3.12-slim

# uv binary from the pinned astral-sh image (verified tag, multi-arch, binaries at /uv and /uvx).
COPY --from=ghcr.io/astral-sh/uv:0.11.24 /uv /uvx /usr/local/bin/

WORKDIR /app

# Sync dependencies first so this layer is cached until pyproject/uv.lock change.
# .python-version pins the interpreter; --frozen uses uv.lock as-is; --no-dev skips test/lint tools.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev

# Application source (.venv is excluded by .dockerignore, so the synced venv is preserved).
COPY . .

# Run as a non-root user. The app writes only to MongoDB and stdout, so no writable paths needed.
RUN useradd --create-home appuser
USER appuser

ENV PORT=5000
EXPOSE 5000

CMD ["uv", "run", "--no-sync", "python", "tradebook.py"]
