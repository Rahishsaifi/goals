/** Snapshot of rg-meridian-poc on 10 Oct 2026. List prices are Azure Retail Prices. */

export const INFRA_SNAPSHOT = "10 Oct 2026";
export const RESOURCE_GROUP = "rg-meridian-poc";
export const MONTH_HOURS = 730;

export type InfraBilling = "free" | "fixed" | "usage";

export type InfraService = {
  id: string;
  service: string;
  name: string;
  region: string;
  sku: string;
  size: string;
  billing: InfraBilling;
  /** Fixed list-price for a 730-hour month. Null when the charge depends on usage. */
  monthlyUsd: number | null;
  /** Same rates for a 240-hour (10-day) window. */
  tenDayUsd: number | null;
  /** Cost Management actuals posted for October, when a charge has appeared. */
  postedUsd: number | null;
  details: { label: string; value: string }[];
};

export const INFRA_SERVICES: InfraService[] = [
  {
    id: "postgres",
    service: "PostgreSQL Flexible Server",
    name: "meridian-pg-2610100151",
    region: "West US 2",
    sku: "Burstable Standard_B1ms",
    size: "1 vCore, 2 GiB, 32 GB storage",
    billing: "fixed",
    monthlyUsd: 16.09,
    tenDayUsd: 5.29,
    postedUsd: 0.13,
    details: [
      { label: "Resource type", value: "Microsoft.DBforPostgreSQL/flexibleServers" },
      { label: "State", value: "Ready" },
      { label: "Version", value: "PostgreSQL 16" },
      { label: "Database", value: "recruitment" },
      { label: "Host", value: "meridian-pg-2610100151.postgres.database.azure.com" },
      { label: "High availability", value: "Disabled" },
      { label: "Backup", value: "7 days, geo-redundant backup off" },
      { label: "Compute meter", value: "$0.017 per hour → $12.41 / 730 hours" },
      { label: "Storage meter", value: "$0.115 per GB-month × 32 GB → $3.68" },
      { label: "Backup overage", value: "$0.095 per GB-month past the 32 GB provisioned size" },
      { label: "10-day split", value: "Compute $4.08 + storage $1.21" },
    ],
  },
  {
    id: "storage",
    service: "Blob Storage",
    name: "meridianst2610100151",
    region: "East US",
    sku: "Standard_LRS, Hot",
    size: "StorageV2, containers resumes and exports",
    billing: "usage",
    monthlyUsd: null,
    tenDayUsd: null,
    postedUsd: 0.000037,
    details: [
      { label: "Resource type", value: "Microsoft.Storage/storageAccounts" },
      { label: "Kind", value: "StorageV2" },
      { label: "Access", value: "HTTPS only, public blob access off" },
      { label: "Containers", value: "resumes, exports" },
      { label: "Data stored", value: "$0.0208 per GB-month (Hot LRS, General Block Blob v2)" },
      { label: "Writes", value: "$0.05 per 10,000 operations" },
      { label: "Reads", value: "$0.004 per 10,000 operations" },
      { label: "October posted", value: "$0.000037" },
    ],
  },
  {
    id: "service-bus",
    service: "Service Bus",
    name: "meridian-sb-2610100151",
    region: "East US",
    sku: "Standard",
    size: "2 queues",
    billing: "fixed",
    monthlyUsd: 9.81,
    tenDayUsd: 3.23,
    postedUsd: 0,
    details: [
      { label: "Resource type", value: "Microsoft.ServiceBus/namespaces" },
      { label: "Status", value: "Active" },
      { label: "Queues", value: "resume-ingestion, evaluation-runs" },
      { label: "Base meter", value: "$0.013441 per hour → $9.81 / 730 hours" },
      { label: "Messages", value: "Extra per million operations, tiered from $0.20" },
      { label: "10-day base", value: "$0.013441 × 240 hours → $3.23" },
    ],
  },
  {
    id: "acr",
    service: "Container Registry",
    name: "mac2610100151",
    region: "East US",
    sku: "Basic",
    size: "1.02 GiB stored of 10 GiB included",
    billing: "fixed",
    monthlyUsd: 5.07,
    tenDayUsd: 1.67,
    postedUsd: 0.05,
    details: [
      { label: "Resource type", value: "Microsoft.ContainerRegistry/registries" },
      { label: "Login server", value: "mac2610100151.azurecr.io" },
      { label: "Stored images", value: "1,099,045,442 bytes (1.02 GiB)" },
      { label: "Included storage", value: "10 GiB on Basic. Extra storage is $0.10 per GB-month" },
      { label: "Registry meter", value: "$0.1666 per day → $5.07 / 730-hour month" },
      { label: "10-day registry", value: "$0.1666 × 10 days → $1.67" },
      { label: "Images", value: "recruitment-api, recruitment-worker, recruitment-web (tag poc)" },
    ],
  },
  {
    id: "key-vault",
    service: "Key Vault",
    name: "meridiankv2610100151",
    region: "East US",
    sku: "Standard",
    size: "RBAC, 7-day soft delete",
    billing: "usage",
    monthlyUsd: null,
    tenDayUsd: null,
    postedUsd: null,
    details: [
      { label: "Resource type", value: "Microsoft.KeyVault/vaults" },
      { label: "SKU", value: "standard" },
      { label: "Authorization", value: "RBAC" },
      { label: "Soft delete", value: "On, 7-day retention" },
      { label: "Operations", value: "$0.03 per 10,000 operations. No hourly base fee" },
      { label: "October posted", value: "No Key Vault charge has posted yet" },
    ],
  },
  {
    id: "search",
    service: "Azure AI Search",
    name: "meridian-ri-poc-free",
    region: "East US",
    sku: "Free",
    size: "50 MB, 1 replica, 1 partition",
    billing: "free",
    monthlyUsd: 0,
    tenDayUsd: 0,
    postedUsd: 0,
    details: [
      { label: "Resource type", value: "Microsoft.Search/searchServices" },
      { label: "SKU", value: "free" },
      { label: "Replicas", value: "1" },
      { label: "Partitions", value: "1" },
      { label: "Quota", value: "50 MB, 10,000 documents, 3 indexes, one free service per subscription" },
      { label: "Meter", value: "$0 per hour" },
    ],
  },
  {
    id: "logs",
    service: "Log Analytics",
    name: "meridian-logs-poc",
    region: "East US",
    sku: "PerGB2018",
    size: "30-day retention",
    billing: "usage",
    monthlyUsd: null,
    tenDayUsd: null,
    postedUsd: 0,
    details: [
      { label: "Resource type", value: "Microsoft.OperationalInsights/workspaces" },
      { label: "Retention", value: "30 days (included up to 31 days)" },
      { label: "Ingestion", value: "First 5 GB each month free, then $2.30 per GB" },
      { label: "Extra retention", value: "$0.10 per GB-month after 31 days" },
      { label: "October posted", value: "$0.00" },
    ],
  },
  {
    id: "aca-env",
    service: "Container Apps environment",
    name: "meridian-cae-poc",
    region: "East US",
    sku: "Consumption",
    size: "Shared environment for 3 apps",
    billing: "free",
    monthlyUsd: 0,
    tenDayUsd: 0,
    postedUsd: null,
    details: [
      { label: "Resource type", value: "Microsoft.App/managedEnvironments" },
      { label: "Plan", value: "Consumption. No dedicated workload profile" },
      { label: "Logs", value: "meridian-logs-poc" },
      { label: "Environment fee", value: "$0 on Consumption. The $0.10/hour fee is for dedicated plans" },
    ],
  },
  {
    id: "aca",
    service: "Container Apps",
    name: "meridian-api, meridian-worker, meridian-web",
    region: "East US",
    sku: "Consumption",
    size: "3 × 0.25 vCPU, 0.5 Gi, 1 replica",
    billing: "fixed",
    monthlyUsd: 16.12,
    tenDayUsd: 4.21,
    postedUsd: null,
    details: [
      { label: "Resource type", value: "Microsoft.App/containerApps" },
      { label: "meridian-api", value: "0.25 vCPU, 0.5 Gi, 1 replica. Internal ingress" },
      { label: "API host", value: "meridian-api.internal.gentledune-3dfe117d.eastus.azurecontainerapps.io" },
      { label: "meridian-worker", value: "0.25 vCPU, 0.5 Gi, 1 replica. No ingress" },
      { label: "meridian-web", value: "0.25 vCPU, 0.5 Gi, 1 replica. Public ingress" },
      { label: "Web host", value: "meridian-web.gentledune-3dfe117d.eastus.azurecontainerapps.io" },
      { label: "Images", value: "mac2610100151.azurecr.io/recruitment-*:poc" },
      { label: "Free grant", value: "180,000 vCPU-seconds, 360,000 GiB-seconds, and 2 million requests per month" },
      { label: "Idle vCPU", value: "$0.000003 per second after the free grant" },
      { label: "Active vCPU", value: "$0.000024 per second after the free grant" },
      { label: "Memory", value: "$0.000003 per GiB-second, idle or active" },
      { label: "Monthly idle", value: "Replicas stay up and idle: $16.12" },
      { label: "Monthly active ceiling", value: "Replicas active all month: $53.73" },
      { label: "10-day idle", value: "$4.21 after the monthly free grant" },
      { label: "October posted", value: "No Container Apps charge has posted yet" },
    ],
  },
  {
    id: "openai",
    service: "Azure OpenAI",
    name: "meridiana0aipoc",
    region: "East US",
    sku: "S0",
    size: "gpt-4.1-mini, GlobalStandard, capacity 200",
    billing: "usage",
    monthlyUsd: null,
    tenDayUsd: null,
    postedUsd: 0.00019,
    details: [
      { label: "Resource type", value: "Microsoft.CognitiveServices/accounts" },
      { label: "Kind", value: "OpenAI" },
      { label: "Deployment", value: "gpt-4.1-mini" },
      { label: "Model version", value: "2025-04-14" },
      { label: "SKU", value: "GlobalStandard, capacity 200 (200 RPM / 200K TPM)" },
      { label: "Input", value: "$0.40 per million tokens" },
      { label: "Output", value: "$1.60 per million tokens" },
      { label: "Cached input", value: "$0.10 per million tokens" },
      { label: "Budget alert", value: "meridian-foundry-10usd at $10 per month" },
      { label: "October posted", value: "$0.00019" },
    ],
  },
];

export function money(value: number | null | undefined, digits = 2): string {
  if (value == null || Number.isNaN(value)) return "Usage";
  return value.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function roundUsd(value: number): number {
  return Math.round(value * 100) / 100;
}

export function sumUsd(key: "monthlyUsd" | "tenDayUsd"): number {
  return roundUsd(INFRA_SERVICES.reduce((total, row) => total + (row[key] ?? 0), 0));
}

export const MONTHLY_FIXED_USD = sumUsd("monthlyUsd");
export const TEN_DAY_FIXED_USD = sumUsd("tenDayUsd");

/** Container Apps row swapped from the idle estimate to the always-active ceiling. */
export const MONTHLY_ACTIVE_USD = roundUsd(MONTHLY_FIXED_USD - 16.12 + 53.73);

export const POSTED_USD = 0.18;
