FROM ghcr.io/astral-sh/uv:0.13.5 AS uv
FROM python:3.13.17-slim-trixie

COPY --from=uv /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_NO_DEV=1

WORKDIR /app
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --create-home app \
    && chown app:app /app

COPY --chown=app:app pyproject.toml uv.lock ./
COPY --chown=app:app src/ ./src/
COPY --chown=app:app alembic.ini ./alembic.ini
COPY --chown=app:app migrations/ ./migrations/

USER app
RUN uv sync --locked

EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "email_support.main:app", "--host", "0.0.0.0", "--port", "8000"]
