# Deployment

## Local

See root `README.md`.

## Goals Library Localization

See `docs/goals-localization.md`. Requires Azure Translator on API and worker. Foundry/OpenAI credentials are optional and only needed when the UI Foundry toggle is on. Local Docker Compose needs no extra services beyond Postgres and Azurite.

## Azure

Do not deploy paid resources on this subscription.

Allowed later, only with an explicit command and SKU check:

- Azure AI Search SKU `free`

Not deployed and not authorized under the free-tier rule:

- PostgreSQL Flexible Server
- Service Bus
- Container Apps
- Container Registry
- Key Vault
- Blob Storage accounts
- Azure AI Foundry model deployments
