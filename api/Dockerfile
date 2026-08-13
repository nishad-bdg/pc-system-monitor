FROM python:3.14-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/root/.local/bin:$PATH"

WORKDIR /srv

# uv for dependency management (matches local dev workflow)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev

ENV PATH="/srv/.venv/bin:$PATH"

# Render injects PORT; bind 0.0.0.0 so the container accepts traffic.
CMD ["sh", "-c", "uv run uvicorn sysinfo_api.main:app --host 0.0.0.0 --port \"${PORT:-8000}\""]