# Paid 10-day POC stack

Authorized after cost review. Estimated **~$11–15 for 10 days**.

## Created in `rg-meridian-poc`

| Resource | Name | SKU / note | Region |
| --- | --- | --- | --- |
| PostgreSQL Flexible Server | `meridian-pg-2610100151` | Burstable `Standard_B1ms`, 32 GB, DB `recruitment` | West US 2 |
| Storage Account | `meridianst2610100151` | `Standard_LRS` Hot; containers `resumes`, `exports` | East US |
| Service Bus | `meridian-sb-2610100151` | Standard; queues `resume-ingestion`, `evaluation-runs` | East US |
| Container Registry | `mac2610100151` | Basic | East US |
| Key Vault | `meridiankv2610100151` | standard (RBAC) | East US |
| AI Search (earlier) | `meridian-ri-poc-free` | free | East US |

## Foundry / Azure OpenAI (operator-authorized, max ~USD $10)

| Resource | Name | SKU / note | Region |
| --- | --- | --- | --- |
| Azure OpenAI | `meridiana0aipoc` | kind `OpenAI`, SKU `S0` | East US |
| Deployment | `gpt-4.1-mini` | `GlobalStandard` capacity `200` (200 RPM / 200K TPM; was 10; stay inside USD $10 budget) | East US |
| Budget | `meridian-foundry-10usd` | USD 10 alerts at 80%/100% | RG scope |

## Previously not created / separate

- Container Apps (optional separate deploy)
- Higher-cost Foundry models beyond the authorized mini deployment

## Local connection file

Secrets were written to `.env.azure` (gitignored). Copy values into a local `.env` only if you want the app to use Azure Postgres/Storage instead of Docker Compose.

## Cleanup (stop billing)

```bash
az group delete --name rg-meridian-poc --yes --no-wait
```

Or delete only the paid resources and keep free Search.
