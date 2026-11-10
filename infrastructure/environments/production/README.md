# Production stack (200k resumes / month)

**Status: undeployed future option. Not for this subscription.**

This folder describes the production Azure footprint for ~200,000 resumes processed per month (parse + score against a small set of job profiles). It is **IaC and documentation only**.

This subscription is pay-as-you-go with spending limit Off. Do **not** run `az deployment` against these templates here. Paid POC resources, if any, stay limited to `rg-meridian-poc` under the existing time-boxed exception.

## Target shape

| Layer | Production SKU | Notes |
| --- | --- | --- |
| Web / API | Container Apps Consumption | Web ~0.5 vCPU / 1 Gi; API ~1 vCPU / 2 Gi |
| Workers | Container Apps Consumption | 1–2 replicas at 1 vCPU / 2 Gi; scale for bursts |
| PostgreSQL | Flexible Server General Purpose ~4 vCore / 16 Gi | ≥32 GB storage; 2 vCore only if ~1 job profile |
| Queue | Service Bus Standard | Backpressure for large upload batches |
| Blob | StorageV2 Hot LRS | ~40 GB at ~200 KB/file |
| Search | AI Search **Basic** | Free tier cannot hold 200k documents |
| Images | ACR Basic | web / api / worker |
| Secrets | Key Vault standard | |
| Logs | Log Analytics PerGB2018 | Cap ingest; first 5 GB/month free |
| AI | Azure OpenAI `gpt-4.1-mini` Global Standard | ~50k–100k TPM; token $ dominates |

## Files

- [`production-200k.bicep`](production-200k.bicep) — data plane (Postgres, storage, bus, ACR, Key Vault, Search Basic)
- [`container-apps-200k.bicep`](container-apps-200k.bicep) — web / api / worker sizing for this volume
- [`parameters.json`](parameters.json) — example parameters (no secrets)
- [`../../../docs/production-infra-200k.md`](../../../docs/production-infra-200k.md) — cost ballpark and rollout

## Deploy guard

```bash
# Always refuses on this subscription after printing SKUs.
bash scripts/deploy_production_200k.sh
```

## Cost reminder

At 200k resumes × 5 jobs over 30 days, list-price planning is roughly **~$2.1k** for the heavy month (~$1.5k OpenAI) and ~**$550** for a quiet later month. Numbers come from [`apps/web/lib/production-forecast.ts`](../../../apps/web/lib/production-forecast.ts) (Infra → Production tab).
