FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8.4 /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages ./packages
COPY services ./services
RUN uv sync --frozen --no-dev --package recruitment-api
EXPOSE 8000
CMD ["uv", "run", "--no-dev", "--package", "recruitment-api", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
