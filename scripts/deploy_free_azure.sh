#!/usr/bin/env bash
set -euo pipefail

# Deploys only always-free Azure resources for this project.
# Aborts if the Search SKU is anything other than "free".

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RG_NAME="${RG_NAME:-rg-meridian-poc}"
LOCATION="${LOCATION:-eastus}"
PARAMS_FILE="${PARAMS_FILE:-$ROOT/infrastructure/environments/poc/parameters.json}"
TEMPLATE_FILE="${TEMPLATE_FILE:-$ROOT/infrastructure/main.bicep}"

SEARCH_SKU="$(python3 - <<'PY' "$PARAMS_FILE"
import json, sys
with open(sys.argv[1]) as f:
    data = json.load(f)
print(data["parameters"]["searchSku"]["value"])
PY
)"

if [[ "$SEARCH_SKU" != "free" ]]; then
  echo "ABORT: searchSku must be 'free'. Got: $SEARCH_SKU"
  exit 1
fi

echo "Pre-flight"
echo "  resource group: $RG_NAME"
echo "  location:       $LOCATION"
echo "  search SKU:     $SEARCH_SKU (always free)"
echo "  template:       $TEMPLATE_FILE"
echo

az group create --name "$RG_NAME" --location "$LOCATION" --tags project=recruitment-intelligence cost=always-free >/dev/null

echo "Ensuring Microsoft.Search provider is registered..."
az provider register --namespace Microsoft.Search --wait >/dev/null

az deployment group create \
  --resource-group "$RG_NAME" \
  --template-file "$TEMPLATE_FILE" \
  --parameters @"$PARAMS_FILE" \
  --name "meridian-free-$(date +%Y%m%d%H%M%S)"

echo
echo "Done. Only free-tier Search was requested. Verify SKU with:"
echo "  az search service show -g $RG_NAME -n meridian-ri-poc-free --query \"{name:name,sku:sku.name,status:status}\" -o json"
