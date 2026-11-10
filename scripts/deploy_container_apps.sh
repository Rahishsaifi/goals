#!/usr/bin/env bash
set -euo pipefail

# Operator-authorized POC deploy. Billable SKUs:
#   - Log Analytics: PerGB2018
#   - Container Apps Environment: Consumption
#   - 3 apps: Consumption 0.25 vCPU / 0.5 Gi, minReplicas=1
# Estimated extra for ~10 days light use: often within ACA free grant + a few USD logs.
# Does NOT create Foundry.

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/.env.azure"

RG_NAME="${RG_NAME:-rg-meridian-poc}"
IMAGE_TAG="${IMAGE_TAG:-poc}"
API_UPSTREAM_URL="${API_UPSTREAM_URL:-http://meridian-api}"

echo "Deploying Container Apps into $RG_NAME"
echo "  Log Analytics SKU:     PerGB2018"
echo "  Environment:           Consumption"
echo "  Apps:                  meridian-web, meridian-api, meridian-worker"
echo "  Compute each:          0.25 vCPU / 0.5 Gi, min=1 max=1"
echo "  Model provider:        ${MODEL_PROVIDER:-mock}"
echo

az acr login --name "${ACR_USERNAME}" >/dev/null

echo "Building linux/amd64 images (required by Container Apps)..."
docker buildx build --platform linux/amd64 --push \
  -f "$ROOT/services/api/Dockerfile" \
  -t "${ACR_LOGIN_SERVER}/recruitment-api:${IMAGE_TAG}" \
  "$ROOT"
docker buildx build --platform linux/amd64 --push \
  -f "$ROOT/services/worker/Dockerfile" \
  -t "${ACR_LOGIN_SERVER}/recruitment-worker:${IMAGE_TAG}" \
  "$ROOT"
docker buildx build --platform linux/amd64 --push \
  -f "$ROOT/apps/web/Dockerfile" \
  --build-arg "API_UPSTREAM_URL=${API_UPSTREAM_URL}" \
  -t "${ACR_LOGIN_SERVER}/recruitment-web:${IMAGE_TAG}" \
  "$ROOT/apps/web"

# Allow Container Apps (Azure services) to reach Postgres
az postgres flexible-server firewall-rule create \
  --resource-group "$RG_NAME" \
  --name meridian-pg-2610100151 \
  --rule-name AllowAzureServices \
  --start-ip-address 0.0.0.0 \
  --end-ip-address 0.0.0.0 \
  >/dev/null 2>&1 || true

echo "Creating Container Apps..."
az deployment group create \
  --resource-group "$RG_NAME" \
  --template-file "$ROOT/infrastructure/container-apps.bicep" \
  --name "container-apps-${IMAGE_TAG}" \
  --parameters \
    acrLoginServer="$ACR_LOGIN_SERVER" \
    acrUsername="$ACR_USERNAME" \
    acrPassword="$ACR_PASSWORD" \
    imageTag="$IMAGE_TAG" \
    databaseUrl="$DATABASE_URL" \
    storageConnectionString="$AZURE_STORAGE_CONNECTION_STRING" \
    azureOpenAiEndpoint="${AZURE_OPENAI_ENDPOINT:-}" \
    azureOpenAiApiKey="${AZURE_OPENAI_API_KEY:-}" \
    azureOpenAiDeployment="${AZURE_OPENAI_DEPLOYMENT:-gpt-4.1-mini}" \
    azureOpenAiApiVersion="${AZURE_OPENAI_API_VERSION:-2024-12-01-preview}" \
    modelProvider="$MODEL_PROVIDER"

WEB_FQDN="$(az deployment group show \
  --resource-group "$RG_NAME" \
  --name "container-apps-${IMAGE_TAG}" \
  --query properties.outputs.webFqdn.value -o tsv)"

echo
echo "Web URL: https://${WEB_FQDN}"
echo "Run migrations/seed against Azure DB before login if not already done."
