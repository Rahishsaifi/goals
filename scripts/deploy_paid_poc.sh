#!/usr/bin/env bash
set -euo pipefail

# Deploys the temporary paid POC stack into rg-meridian-poc.
# Estimated ~$11-15 for 10 days. Does NOT create Container Apps or Foundry.

RG_NAME="${RG_NAME:-rg-meridian-poc}"
LOCATION="${LOCATION:-eastus}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SUFFIX="${NAME_SUFFIX:-$(date +%y%m%d)}"
PASSWORD="${POSTGRES_ADMIN_PASSWORD:-$(openssl rand -base64 24 | tr -d '/+=' | cut -c1-24)!aA1}"
CLIENT_IP="$(curl -sS https://api.ipify.org)"
PRINCIPAL_ID="$(az ad signed-in-user show --query id -o tsv)"

echo "Pre-flight paid POC SKUs"
echo "  RG:                $RG_NAME"
echo "  Postgres:          Standard_B1ms / Burstable / 32GB"
echo "  Storage:           Standard_LRS Hot"
echo "  Service Bus:       Standard"
echo "  ACR:               Basic"
echo "  Key Vault:         standard"
echo "  Client IP allow:   $CLIENT_IP"
echo "  Suffix:            $SUFFIX"
echo "  NOT creating:      Container Apps, Foundry"
echo

for ns in Microsoft.DBforPostgreSQL Microsoft.Storage Microsoft.ServiceBus Microsoft.ContainerRegistry Microsoft.KeyVault; do
  echo "Registering $ns..."
  az provider register --namespace "$ns" --wait >/dev/null
done

az deployment group create \
  --resource-group "$RG_NAME" \
  --template-file "$ROOT/infrastructure/paid-poc.bicep" \
  --name "paid-poc-$SUFFIX" \
  --parameters \
    nameSuffix="$SUFFIX" \
    clientIp="$CLIENT_IP" \
    postgresAdminPassword="$PASSWORD" \
    principalId="$PRINCIPAL_ID"

echo
echo "Deployment submitted. Collect connection values with scripts/write_paid_poc_env.sh"
echo "Postgres admin password was generated for this run; save it securely if you did not set POSTGRES_ADMIN_PASSWORD."
