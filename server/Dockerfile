FROM ghcr.io/astral-sh/uv:0.8.17 AS uv-bin
FROM python:3.12-slim

COPY --from=uv-bin /uv /uvx /bin/
WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY alembic.ini ./
COPY app ./app
COPY migrations ./migrations

EXPOSE 3000
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port 3000"]
