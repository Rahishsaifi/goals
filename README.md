# Recruitment Intelligence

Local-first POC for ranking candidates against a job description.

Azure use is limited to always-free SKUs. This subscription is pay-as-you-go with spending limit off, so paid resources are not created. The model provider is an **explicit local mock**, not Azure AI Foundry.

## Prerequisites

- Docker
- `uv`
- Node.js 22+

## Local setup

```bash
cp .env.example .env
docker compose up -d
uv sync --all-packages
uv run --directory services/api alembic upgrade head
uv run python scripts/seed_demo_data.py
```

Seeded local admin:

- tenant: `demo`
- email: `demo@demo.com`
- password: `admin123`

## Run

```bash
uv run --directory services/api uvicorn app.main:app --reload --port 8000
uv run --directory services/worker python -m worker.main
npm ci --prefix apps/web
npm run dev --prefix apps/web
```

- Web: http://127.0.0.1:3000
- API docs: http://127.0.0.1:8000/docs
- Health: `GET /api/v1/health/ready`

The Next.js app proxies `/api/*` to the API so auth cookies stay same-origin.

## Tests

```bash
uv run ruff check .
uv run mypy
uv run pytest
npm run lint --prefix apps/web
npm run typecheck --prefix apps/web
npm test --prefix apps/web
```

## What works now

- Email/password auth, CSRF, RBAC, tenant isolation tests
- Resume upload sessions + outbox processing model
- PDF/DOCX text parsing
- Job profiles, weight validation, deterministic scoring
- Evaluation runs with evidence assessment via mock provider
- Usage ledger and CSV export
- Basic dashboard UI
- Goals Library Localization (`/goals-localization`) — CSV → XLSX via Azure Translator + protected terminology + Python QA; optional Foundry semantic QA toggle (see `docs/goals-localization.md`)

## What does not work / is not deployed

- Azure AI Foundry
- Azure AI Search
- Paid Azure infrastructure
- OCR for scanned PDFs
- Playwright end-to-end suite
- Full 200,000-resume corpus processing

See `docs/implementation-plan.md`.


https://meridian-web.gentledune-3dfe117d.eastus.azurecontainerapps.io/
