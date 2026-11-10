#!/usr/bin/env bash
set -euo pipefail

# Operator-authorized Foundry/OpenAI POC. Pay-per-token, hard budget target: USD $10.
# SKUs:
#   - Cognitive Services account kind OpenAI, SKU S0
#   - Model deployment gpt-4o-mini Standard capacity 1 (1K TPM)
#   - Cost Management budget amount 10 USD on rg-meridian-poc

RG_NAME="${RG_NAME:-rg-meridian-poc}"
LOCATION="${LOCATION:-eastus}"
ACCOUNT_NAME="${ACCOUNT_NAME:-meridiana0aipoc}"
DEPLOYMENT_NAME="${DEPLOYMENT_NAME:-gpt-4.1-mini}"
MODEL_NAME="${MODEL_NAME:-gpt-4.1-mini}"
MODEL_VERSION="${MODEL_VERSION:-2025-04-14}"
MODEL_SKU="${MODEL_SKU:-GlobalStandard}"
BUDGET_NAME="${BUDGET_NAME:-meridian-foundry-10usd}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "Pre-flight Foundry/OpenAI POC"
echo "  RG:           $RG_NAME"
echo "  Account:      $ACCOUNT_NAME"
echo "  Kind/SKU:     OpenAI / S0 (pay-per-token)"
echo "  Model:        $MODEL_NAME $MODEL_VERSION ($DEPLOYMENT_NAME)"
echo "  Capacity:     $MODEL_SKU 1 (1K TPM)"
echo "  Budget alert: USD 10 on resource group"
echo

az provider register --namespace Microsoft.CognitiveServices --wait >/dev/null
az provider register --namespace Microsoft.CostManagementExports --wait >/dev/null || true

az cognitiveservices account create \
  --name "$ACCOUNT_NAME" \
  --resource-group "$RG_NAME" \
  --location "$LOCATION" \
  --kind OpenAI \
  --sku S0 \
  --custom-domain "$ACCOUNT_NAME" \
  --yes

az cognitiveservices account deployment create \
  --name "$ACCOUNT_NAME" \
  --resource-group "$RG_NAME" \
  --deployment-name "$DEPLOYMENT_NAME" \
  --model-name "$MODEL_NAME" \
  --model-version "$MODEL_VERSION" \
  --model-format OpenAI \
  --sku-name "$MODEL_SKU" \
  --sku-capacity 1

ENDPOINT="$(az cognitiveservices account show \
  --name "$ACCOUNT_NAME" \
  --resource-group "$RG_NAME" \
  --query properties.endpoint -o tsv)"
KEY="$(az cognitiveservices account keys list \
  --name "$ACCOUNT_NAME" \
  --resource-group "$RG_NAME" \
  --query key1 -o tsv)"

START_DATE="$(date -u +%Y-%m-01T00:00:00Z)"
# Budget API often wants end date at least one full period out.
END_DATE="$(date -u -v+2m +%Y-%m-01T00:00:00Z 2>/dev/null || date -u -d '+2 months' +%Y-%m-01T00:00:00Z)"
SUB_ID="$(az account show --query id -o tsv)"

# Best-effort $10 budget (CLI shape varies by extension version).
az consumption budget create \
  --budget-name "$BUDGET_NAME" \
  --amount 10 \
  --category Cost \
  --time-grain Monthly \
  --start-date "$START_DATE" \
  --end-date "$END_DATE" \
  --resource-group "$RG_NAME" \
  >/dev/null 2>&1 \
  || az rest --method put \
    --url "https://management.azure.com/subscriptions/${SUB_ID}/resourceGroups/${RG_NAME}/providers/Microsoft.CostManagement/budgets/${BUDGET_NAME}?api-version=2023-11-01" \
    --body "{\"properties\":{\"amount\":10,\"category\":\"Cost\",\"timeGrain\":\"Monthly\",\"timePeriod\":{\"startDate\":\"${START_DATE}\",\"endDate\":\"${END_DATE}\"},\"filter\":{\"dimensions\":{\"name\":\"ResourceGroupName\",\"operator\":\"In\",\"values\":[\"${RG_NAME}\"]}},\"notifications\":{\"Actual_GreaterThan_80_Percent\":{\"enabled\":true,\"operator\":\"GreaterThan\",\"threshold\":80,\"thresholdType\":\"Actual\",\"contactEmails\":[\"rahishcode@gmail.com\"],\"contactRoles\":[\"Owner\"]}}}}" \
    >/dev/null 2>&1 \
  || echo "WARN: Could not create Cost Management budget via CLI; set a \$10 budget alert in Azure Portal for ${RG_NAME}."

ENV_FILE="$ROOT/.env.azure"
touch "$ENV_FILE"
python3 - "$ENV_FILE" "$ENDPOINT" "$KEY" "$DEPLOYMENT_NAME" "$ACCOUNT_NAME" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
endpoint, key, deployment, account = sys.argv[2:6]
updates = {
    "MODEL_PROVIDER": "foundry",
    "AZURE_OPENAI_ENDPOINT": endpoint.rstrip("/"),
    "AZURE_OPENAI_API_KEY": key,
    "AZURE_OPENAI_DEPLOYMENT": deployment,
    "AZURE_OPENAI_API_VERSION": "2024-08-01-preview",
    "FOUNDRY_ACCOUNT_NAME": account,
}
text = path.read_text() if path.exists() else ""
lines: list[str] = []
seen: set[str] = set()
for line in text.splitlines():
    if not line or line.startswith("#") or "=" not in line:
        lines.append(line)
        continue
    key_name = line.split("=", 1)[0]
    if key_name in updates:
        lines.append(f"{key_name}={updates[key_name]}")
        seen.add(key_name)
    else:
        lines.append(line)
for key_name, value in updates.items():
    if key_name not in seen:
        lines.append(f"{key_name}={value}")
path.write_text("\n".join(lines).rstrip() + "\n")
print({"endpoint": endpoint, "deployment": deployment, "model_provider": "foundry", "budget_usd": 10})
PY

echo
echo "Foundry/OpenAI POC ready. Secrets written to .env.azure (gitignored)."
echo "Restart the API with MODEL_PROVIDER=foundry to use live calls."