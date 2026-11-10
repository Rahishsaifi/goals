# POC environment — free tier only

## Deployed from this folder

| Resource | SKU | Cost |
| --- | --- | --- |
| Resource group `rg-meridian-poc` | n/a | $0 |
| Azure AI Search | `free` | Always free (50 MB / 10k docs / 3 indexes) |

## Not deployed (would cost money on this subscription)

- PostgreSQL Flexible Server
- Blob Storage account
- Service Bus
- Container Apps / ACR
- Key Vault
- Log Analytics / Application Insights
- Azure AI Foundry model deployments

Those stay on local Docker Compose.
