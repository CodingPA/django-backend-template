FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /uvx /usr/local/bin/

WORKDIR /app

# Dependencies first, so code-only changes skip the (slow) build layer.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    apt-get update && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && uv sync --frozen --no-install-project --no-dev \
    && apt-get purge -y build-essential libpq-dev && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

COPY . .
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/staticfiles /app/media \
    && chown -R app:app /app
USER app

# DEBUG has no default (see config/settings.py) and there is no .env in the
# build context, so it must be supplied here for this build-time step only —
# it is not baked into the image's runtime environment.
RUN DEBUG=True python manage.py collectstatic --noinput

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
