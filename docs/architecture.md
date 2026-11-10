# Architecture

Local-first modular monorepo for the recruitment intelligence POC.

## Runtime

- Next.js web app (`apps/web`)
- FastAPI API (`services/api`)
- Worker process (`services/worker`) consuming PostgreSQL outbox events
- PostgreSQL 16 (Docker Compose)
- Azurite for private local blob storage
- Explicit mock model provider (`MODEL_PROVIDER=mock`)

## Trust boundaries

- Tenant id and roles come from the server session, never from the browser.
- Deterministic scoring lives in `packages/scoring`.
- Model providers may extract and assess evidence only.
- Missing evidence is `unknown`, not an automatic failure.
- Mock AI is visible and never used as a silent fallback for a live provider.

## Azure constraint

This subscription is pay-as-you-go with spending limit Off. Paid Azure resources are not deployed. Azure AI Search SKU `free` is the only cloud service considered for a later explicit step.
