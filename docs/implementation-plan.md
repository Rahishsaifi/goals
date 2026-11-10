# Implementation plan — Recruitment Intelligence Platform

Status: Phases 1–11 implemented locally with an explicit mock model provider. Azure paid resources are not deployed.

Date: 2026-10-10

## Governing constraint

Use only Azure free tier. Subscription is pay-as-you-go with spending limit Off. No paid SKU has been created.

## Checkpoint

### Done and verified

- Phase 1 foundation: health endpoints, Compose Postgres, Alembic, CI workflow file, Next.js app
- Phase 2 auth/tenancy: Argon2id, cookies, CSRF, invitations, verification, password reset, RBAC, cross-tenant tests
- Phase 3 upload/outbox model and Azurite-oriented blob helper
- Phase 4 local PDF/DOCX parser
- Phase 5 explicit mock model provider (Foundry not connected)
- Phase 6 job profiles, weight validation, deterministic scoring
- Phase 7 local retrieval scope is DB `ready` resumes (Search free tier not deployed)
- Phase 8 evaluation orchestration with outbox + inline local processing path
- Phase 9 usage ledger with idempotency and unavailable-vs-zero distinction
- Phase 10 basic real UI screens: login, dashboard, jobs, resumes, evaluations, usage
- Phase 11 CSV export endpoint with formula-injection neutralization

### Commands run

- `uv run ruff check .` — passed
- `uv run mypy` — passed, 49 source files
- `uv run pytest` — 34 passed
- `npm run lint|typecheck|test` in `apps/web` — passed
- `alembic upgrade head` — `0003_domain_core`
- `scripts/seed_demo_data.py` — demo tenant + admin seeded

### Seed credentials (local only)

- tenant slug: `demo`
- email: `demo@demo.com`
- password: `admin123`

### Not done / not claimed

- Azure AI Foundry live deployments
- Azure AI Search free SKU deployment
- Playwright end-to-end suite
- Malware scanning
- Full FORCE RLS with non-owner DB role
- Production HTTPS deployment
- Load benchmarks against 1k/10k corpora
- Labelled fairness/quality report with measured metrics
- GitHub Actions remote execution
- Docker image builds
- Recruiter review/override persistence UI
- OCR for scanned PDFs

### Next action

1. Start Azurite (`docker compose up -d azurite`) and exercise the full upload → worker → evaluation path with a real DOCX/PDF.
2. Optionally deploy Azure AI Search SKU `free` only after an explicit SKU confirmation.
3. Do not create Foundry model deployments unless the user authorizes pay-per-token spend.

### Azure

Resource group: `rg-meridian-poc`

Always free:

- Azure AI Search `meridian-ri-poc-free` (SKU `free`)

Paid 10-day POC (operator-authorized after cost review; est. ~$11–15 / 10 days):

- PostgreSQL Flexible Server `meridian-pg-2610100151` (`Standard_B1ms`, West US 2)
- Storage `meridianst2610100151` (`Standard_LRS`)
- Service Bus `meridian-sb-2610100151` (Standard)
- ACR `mac2610100151` (Basic)
- Key Vault `meridiankv2610100151` (standard)

Foundry/OpenAI: `meridiana0aipoc` + deployment `gpt-4.1-mini` (GlobalStandard capacity 1), budget alert USD $10. Container Apps public URL may still be pending.

Local secrets file: `.env.azure` (gitignored). Details: `infrastructure/environments/poc/PAID_POC.md`.

Cleanup when done: `az group delete -n rg-meridian-poc --yes`.
