FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8.4 /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY services ./services
RUN uv sync --frozen --no-dev --package recruitment-worker
CMD ["uv", "run", "--no-dev", "--package", "recruitment-worker", "python", "-m", "worker.main"]
