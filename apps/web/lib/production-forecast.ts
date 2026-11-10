/**
 * Production list-price forecast.
 * Prices are Azure Retail Prices checked 10 Oct 2026 (Postgres West US 2, other services East US).
 * Token counts follow the live prompt caps in foundry_provider.py and the planning assumptions below.
 * They are not measured averages from the usage ledger.
 */

export const MONTH_HOURS = 730;
export const INPUT_USD_PER_MILLION = 0.4;
export const OUTPUT_USD_PER_MILLION = 1.6;
export const GPT41_MINI_DEFAULT_TPM = 5_000_000;

const PARSE_SYSTEM_CHARS = 370;
const SCORE_SYSTEM_CHARS = 420;
const JOB_SYSTEM_CHARS = 284;
const PROFILE_JSON_CHARS = 1_800;
const CRITERION_JSON_CHARS = 180;
const JOB_TEXT_CHARS = 2_000;
const JOB_OUTPUT_TOKENS = 400;
const PARSE_CHAR_CAP = 12_000;

const POSTGRES_USD_PER_VCORE_HOUR = 0.089;
const POSTGRES_STORAGE_USD_PER_GB = 0.115;
const BLOB_USD_PER_GB = 0.0208;
const BLOB_WRITE_USD_PER_10K = 0.05;
const SEARCH_BASIC_HOUR = 0.101;
const SEARCH_S1_HOUR = 0.336;
const SEARCH_S2_HOUR = 1.344;
const SERVICE_BUS_HOUR = 0.013441;
const ACR_USD_PER_DAY = 0.1666;
const LOG_INGEST_USD_PER_GB = 2.3;
const LOG_FREE_GB = 5;
const LOG_PLAN_GB = 10;
const KEY_VAULT_ALLOWANCE_USD = 1;

const VCPU_ACTIVE_USD_PER_SEC = 0.000024;
const VCPU_IDLE_USD_PER_SEC = 0.000003;
const MEMORY_USD_PER_GIB_SEC = 0.000003;
const FREE_VCPU_SECONDS = 180_000;
const FREE_GIB_SECONDS = 360_000;

export type ForecastInput = {
  resumes: number;
  jobProfiles: number;
  criteriaPerJob: number;
  windowDays: number;
  resumeFileKb: number;
  extractedChars: number;
  searchDocKb: number;
  charsPerToken: number;
  parseOutputTokens: number;
  scoreOutputTokens: number;
  secondsPerCall: number;
  rescoreMonthly: boolean;
  zoneRedundantDb: boolean;
};

export const FORECAST_DEFAULTS: ForecastInput = {
  resumes: 200_000,
  jobProfiles: 5,
  criteriaPerJob: 6,
  windowDays: 30,
  resumeFileKb: 200,
  extractedChars: 6_000,
  searchDocKb: 8,
  charsPerToken: 4,
  parseOutputTokens: 600,
  scoreOutputTokens: 90,
  secondsPerCall: 2,
  rescoreMonthly: false,
  zoneRedundantDb: false,
};

export type ForecastLine = {
  id: string;
  service: string;
  sku: string;
  size: string;
  thisMonthUsd: number;
  laterMonthUsd: number;
  note: string;
};

export type ProductionForecast = {
  lines: ForecastLine[];
  thisMonthUsd: number;
  laterMonthUsd: number;
  parseCalls: number;
  scoreCalls: number;
  jobCalls: number;
  inputTokens: number;
  outputTokens: number;
  requiredTpm: number;
  workerReplicas: number;
  quotaCoversWindow: boolean;
  modelBatchUsd: number;
};

function roundUsd(value: number): number {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

function clamp(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.min(max, Math.max(min, value));
}

function tokensFor(chars: number, charsPerToken: number): number {
  return Math.ceil(chars / Math.max(charsPerToken, 1));
}

function containerUsd(parts: { vcpu: number; gi: number; activeHours: number; idleHours: number }[]): number {
  let activeSeconds = 0;
  let idleSeconds = 0;
  let memorySeconds = 0;
  for (const part of parts) {
    activeSeconds += part.vcpu * part.activeHours * 3600;
    idleSeconds += part.vcpu * part.idleHours * 3600;
    memorySeconds += part.gi * (part.activeHours + part.idleHours) * 3600;
  }
  const activeBillable = Math.max(0, activeSeconds - FREE_VCPU_SECONDS);
  const grantLeft = Math.max(0, FREE_VCPU_SECONDS - activeSeconds);
  const idleBillable = Math.max(0, idleSeconds - grantLeft);
  const memoryBillable = Math.max(0, memorySeconds - FREE_GIB_SECONDS);
  return (
    activeBillable * VCPU_ACTIVE_USD_PER_SEC +
    idleBillable * VCPU_IDLE_USD_PER_SEC +
    memoryBillable * MEMORY_USD_PER_GIB_SEC
  );
}

function postgresPlan(storageGb: number, evidenceRows: number, zoneRedundant: boolean) {
  const vCores = evidenceRows > 20_000_000 || storageGb > 512 ? 8 : evidenceRows > 2_000_000 || storageGb > 128 ? 4 : 2;
  const memoryGi = vCores * 4;
  const computeHours = zoneRedundant ? vCores * 2 : vCores;
  const monthly = computeHours * POSTGRES_USD_PER_VCORE_HOUR * MONTH_HOURS + storageGb * POSTGRES_STORAGE_USD_PER_GB;
  return { vCores, memoryGi, storageGb, monthly, zoneRedundant };
}

function searchPlan(indexGb: number, documents: number) {
  const tiers = [
    { sku: "Free", gb: 0.05, partitions: 1, replicas: 1, maxDocs: 10_000, hourly: 0 },
    { sku: "Basic", gb: 15, partitions: 3, replicas: 3, maxDocs: Number.POSITIVE_INFINITY, hourly: SEARCH_BASIC_HOUR },
    { sku: "Standard S1", gb: 160, partitions: 12, replicas: 12, maxDocs: Number.POSITIVE_INFINITY, hourly: SEARCH_S1_HOUR },
    { sku: "Standard S2", gb: 512, partitions: 12, replicas: 12, maxDocs: Number.POSITIVE_INFINITY, hourly: SEARCH_S2_HOUR },
  ];
  for (const tier of tiers) {
    if (documents > tier.maxDocs || indexGb > tier.gb * tier.partitions) continue;
    const partitionCount = Math.max(1, Math.ceil(indexGb / tier.gb));
    const replicaCount = tier.sku === "Free" ? 1 : Math.min(2, tier.replicas);
    const units = partitionCount * replicaCount;
    return {
      sku: tier.sku,
      partitions: partitionCount,
      replicas: replicaCount,
      units,
      indexGb,
      monthly: units * tier.hourly * MONTH_HOURS,
    };
  }
  const partitions = Math.ceil(indexGb / 512);
  return {
    sku: "Standard S2",
    partitions,
    replicas: 2,
    units: partitions * 2,
    indexGb,
    monthly: partitions * 2 * SEARCH_S2_HOUR * MONTH_HOURS,
  };
}

export function productionForecast(raw: ForecastInput): ProductionForecast {
  const resumes = Math.round(clamp(raw.resumes, 0, 5_000_000));
  const jobProfiles = Math.round(clamp(raw.jobProfiles, 1, 500));
  const criteriaPerJob = Math.round(clamp(raw.criteriaPerJob, 1, 20));
  const windowDays = Math.round(clamp(raw.windowDays, 1, 365));
  const resumeFileKb = clamp(raw.resumeFileKb, 1, 20_000);
  const extractedChars = Math.round(clamp(raw.extractedChars, 500, PARSE_CHAR_CAP));
  const searchDocKb = clamp(raw.searchDocKb, 1, 500);
  const charsPerToken = clamp(raw.charsPerToken, 1, 10);
  const parseOutputTokens = Math.round(clamp(raw.parseOutputTokens, 50, 4_000));
  const scoreOutputTokens = Math.round(clamp(raw.scoreOutputTokens, 20, 2_000));
  const secondsPerCall = clamp(raw.secondsPerCall, 0.2, 120);

  const parseCalls = resumes;
  // One Foundry call per resume × job: all criteria scored from the stored profile.
  const scoreCalls = resumes * jobProfiles;
  const jobCalls = jobProfiles;
  const parseInputTokens = tokensFor(PARSE_SYSTEM_CHARS + Math.min(extractedChars, PARSE_CHAR_CAP), charsPerToken);
  const scoreInputTokens = tokensFor(
    SCORE_SYSTEM_CHARS + PROFILE_JSON_CHARS + criteriaPerJob * CRITERION_JSON_CHARS,
    charsPerToken,
  );
  const jobInputTokens = tokensFor(JOB_SYSTEM_CHARS + JOB_TEXT_CHARS, charsPerToken);
  const inputTokens = parseCalls * parseInputTokens + scoreCalls * scoreInputTokens + jobCalls * jobInputTokens;
  const outputTokens =
    parseCalls * parseOutputTokens +
    scoreCalls * scoreOutputTokens * criteriaPerJob +
    jobCalls * JOB_OUTPUT_TOKENS;
  const modelBatchUsd =
    (inputTokens * INPUT_USD_PER_MILLION + outputTokens * OUTPUT_USD_PER_MILLION) / 1_000_000;

  const windowHours = windowDays * 24;
  const activeHours = Math.min(MONTH_HOURS, windowHours);
  const idleRemainder = Math.max(0, MONTH_HOURS - activeHours);
  const workerReplicas = Math.max(
    1,
    Math.ceil((parseCalls + scoreCalls + jobCalls) * secondsPerCall / (windowHours * 3600)),
  );
  const requiredTpm = windowHours === 0 ? 0 : Math.ceil((inputTokens + outputTokens) / (windowHours * 60));

  const textKb = extractedChars / 1024;
  const perResumeKb = textKb + 2;
  const perJobKb = 1 + criteriaPerJob * 0.4;
  const dataGb = (resumes * (perResumeKb + jobProfiles * perJobKb)) / (1024 * 1024);
  const storageGb = Math.max(32, Math.ceil((dataGb * 2) / 32) * 32);
  const evidenceRows = resumes * jobProfiles * criteriaPerJob;
  const postgres = postgresPlan(storageGb, evidenceRows, raw.zoneRedundantDb);

  const blobGb = (resumes * resumeFileKb) / (1024 * 1024);
  const blobStoredUsd = blobGb * BLOB_USD_PER_GB;
  const blobWriteUsd = (resumes / 10_000) * BLOB_WRITE_USD_PER_10K;

  const search = searchPlan((resumes * searchDocKb) / (1024 * 1024), resumes);

  const busyApps = containerUsd([
    { vcpu: 0.5, gi: 1, activeHours: 0, idleHours: MONTH_HOURS },
    { vcpu: 1, gi: 2, activeHours: MONTH_HOURS, idleHours: 0 },
    { vcpu: 1 * workerReplicas, gi: 2 * workerReplicas, activeHours, idleHours: 0 },
    { vcpu: idleRemainder > 0 ? 1 : 0, gi: idleRemainder > 0 ? 2 : 0, activeHours: 0, idleHours: idleRemainder },
  ]);
  const quietApps = containerUsd([
    { vcpu: 0.5, gi: 1, activeHours: 0, idleHours: MONTH_HOURS },
    { vcpu: 1, gi: 2, activeHours: MONTH_HOURS, idleHours: 0 },
    { vcpu: 1, gi: 2, activeHours: 0, idleHours: MONTH_HOURS },
  ]);

  const serviceBus = SERVICE_BUS_HOUR * MONTH_HOURS;
  const registry = ACR_USD_PER_DAY * (MONTH_HOURS / 24);
  const logs = Math.max(0, LOG_PLAN_GB - LOG_FREE_GB) * LOG_INGEST_USD_PER_GB;
  const modelLater = raw.rescoreMonthly ? modelBatchUsd : 0;

  const lines: ForecastLine[] = [
    {
      id: "openai",
      service: "Azure OpenAI",
      sku: "gpt-4.1-mini Global Standard",
      size: `${(inputTokens + outputTokens).toLocaleString("en-US")} planning tokens`,
      thisMonthUsd: roundUsd(modelBatchUsd),
      laterMonthUsd: roundUsd(modelLater),
      note: "One parse per resume, then one score call per resume×job using the stored profile (all criteria in that call). Input $0.40 and output $1.60 per million tokens.",
    },
    {
      id: "postgres",
      service: "PostgreSQL Flexible Server",
      sku: `General Purpose Ddsv5, ${postgres.vCores} vCore`,
      size: `${postgres.memoryGi} GiB memory, ${postgres.storageGb} GB storage`,
      thisMonthUsd: roundUsd(postgres.monthly),
      laterMonthUsd: roundUsd(postgres.monthly),
      note: postgres.zoneRedundant
        ? "Zone-redundant standby doubles compute. Storage stays a single copy at $0.115 per GB-month."
        : "Sized from stored resume text, one result per job, and one evidence row per criterion, with index headroom. Standby is off.",
    },
    {
      id: "storage",
      service: "Blob Storage",
      sku: "StorageV2 Hot LRS",
      size: `${blobGb.toFixed(1)} GB of resume files`,
      thisMonthUsd: roundUsd(blobStoredUsd + blobWriteUsd),
      laterMonthUsd: roundUsd(blobStoredUsd),
      note: "Stored data is $0.0208 per GB-month. The processing month also includes one write per file at $0.05 per 10,000.",
    },
    {
      id: "search",
      service: "Azure AI Search",
      sku: search.sku,
      size: `${search.replicas} replica${search.replicas === 1 ? "" : "s"}, ${search.partitions} partition${search.partitions === 1 ? "" : "s"}, ${search.indexGb.toFixed(2)} GB index`,
      thisMonthUsd: roundUsd(search.monthly),
      laterMonthUsd: roundUsd(search.monthly),
      note:
        search.sku === "Free"
          ? "Free tier holds 50 MB, 10,000 documents, and 3 indexes."
          : search.sku === "Basic"
            ? "A new Basic service holds 15 GB per partition. Two replicas keep queries available while one replica is updated."
            : `${search.sku} is the smallest tier that holds this index. Two replicas keep queries available while one replica is updated.`,
    },
    {
      id: "apps",
      service: "Container Apps",
      sku: "Consumption",
      size: `Web 0.5 vCPU, API 1 vCPU, ${workerReplicas} worker${workerReplicas === 1 ? "" : "s"} at 1 vCPU / 2 Gi`,
      thisMonthUsd: roundUsd(busyApps),
      laterMonthUsd: roundUsd(quietApps),
      note: "Workers run for the finish window, then one worker stays idle. The monthly free grant is 180,000 vCPU-seconds and 360,000 GiB-seconds.",
    },
    {
      id: "bus",
      service: "Service Bus",
      sku: "Standard",
      size: "resume and evaluation queues",
      thisMonthUsd: roundUsd(serviceBus),
      laterMonthUsd: roundUsd(serviceBus),
      note: "Base charge is $0.013441 per hour. Premium private networking is a separate SKU and is not included.",
    },
    {
      id: "acr",
      service: "Container Registry",
      sku: "Basic",
      size: "10 GiB included",
      thisMonthUsd: roundUsd(registry),
      laterMonthUsd: roundUsd(registry),
      note: "Registry unit is $0.1666 per day.",
    },
    {
      id: "logs",
      service: "Log Analytics",
      sku: "PerGB2018",
      size: `${LOG_PLAN_GB} GB ingestion allowance`,
      thisMonthUsd: roundUsd(logs),
      laterMonthUsd: roundUsd(logs),
      note: "First 5 GB each month is free. This allowance plans for 10 GB at $2.30 per extra GB.",
    },
    {
      id: "vault",
      service: "Key Vault",
      sku: "Standard",
      size: "secrets and RBAC",
      thisMonthUsd: KEY_VAULT_ALLOWANCE_USD,
      laterMonthUsd: KEY_VAULT_ALLOWANCE_USD,
      note: "No hourly fee. $1 covers a planning allowance at $0.03 per 10,000 operations.",
    },
  ];

  const thisMonthUsd = roundUsd(lines.reduce((sum, line) => sum + line.thisMonthUsd, 0));
  const laterMonthUsd = roundUsd(lines.reduce((sum, line) => sum + line.laterMonthUsd, 0));

  return {
    lines,
    thisMonthUsd,
    laterMonthUsd,
    parseCalls,
    scoreCalls,
    jobCalls,
    inputTokens,
    outputTokens,
    requiredTpm,
    workerReplicas,
    quotaCoversWindow: requiredTpm <= GPT41_MINI_DEFAULT_TPM,
    modelBatchUsd: roundUsd(modelBatchUsd),
  };
}
