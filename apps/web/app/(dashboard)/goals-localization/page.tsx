"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type ReactNode } from "react";

import { AppShell } from "@/components/AppShell";
import { API_BASE, csrfToken, readApiError } from "@/lib/api";
import { formatStatus } from "@/lib/format";

type Language = {
  code: string;
  name: string;
  sheet_code?: string;
  azure_translator_code: string;
  rtl: boolean;
  translate?: boolean;
};

type JobPayload = {
  id: string;
  status: string;
  target_language: string;
  current_stage: string | null;
  stage_progress: Record<
    string,
    { status?: string; detail?: string; started_at?: string; updated_at?: string }
  >;
  stages: string[];
  options: Record<string, boolean | string>;
  summary: Record<string, unknown>;
  total_records: number;
  processed_records: number;
  failed_records: number;
  production_ready: boolean;
  error_message: string | null;
  source_filename: string;
  template_filename: string;
  cost_estimate?: Record<string, unknown>;
  has_output?: boolean;
  has_report?: boolean;
  created_at?: string | null;
  completed_at?: string | null;
};

type JobEvent = {
  at: string;
  level: "info" | "success" | "warning" | "error" | string;
  stage?: string | null;
  message: string;
  count?: number;
};

type QueueState = {
  busy: boolean;
  waiting: number;
  active_count: number;
  active_job_id?: string | null;
  processing: {
    id: string;
    status: string;
    target_language: string;
    source_filename: string;
    processed_records: number;
    total_records: number;
    current_stage: string | null;
  } | null;
};

const TERMINAL = new Set(["COMPLETED", "NEEDS_REVIEW", "FAILED", "CANCELLED"]);

const LAST_JOB_KEY = "goals-localization:last-job";
const CLEARED_JOB = "cleared";

const LOG_LEVEL_STYLE: Record<string, string> = {
  info: "bg-slate-400",
  success: "bg-emerald-500",
  warning: "bg-amber-500",
  error: "bg-rose-500",
};

const FALLBACK_LANGUAGES: Language[] = [
  { code: "zh", name: "Simplified Chinese", sheet_code: "zh", azure_translator_code: "zh-Hans", rtl: false },
  { code: "ja", name: "Japanese", sheet_code: "ja", azure_translator_code: "ja", rtl: false },
  { code: "nl", name: "Dutch", sheet_code: "nl", azure_translator_code: "nl", rtl: false },
  { code: "de", name: "German", sheet_code: "de", azure_translator_code: "de", rtl: false },
  { code: "fr", name: "European French", sheet_code: "fr", azure_translator_code: "fr", rtl: false },
  { code: "es", name: "European Spanish", sheet_code: "es", azure_translator_code: "es", rtl: false },
  { code: "es-latam", name: "Latam Spanish", sheet_code: "es", azure_translator_code: "es", rtl: false },
  { code: "pt", name: "Brazilian Portuguese", sheet_code: "pt", azure_translator_code: "pt", rtl: false },
  { code: "cs", name: "Czech", sheet_code: "cs", azure_translator_code: "cs", rtl: false },
  { code: "pl", name: "Polish", sheet_code: "pl", azure_translator_code: "pl", rtl: false },
  { code: "it", name: "Italian", sheet_code: "it", azure_translator_code: "it", rtl: false },
  { code: "en-gb", name: "English UK", sheet_code: "en", azure_translator_code: "en", rtl: false, translate: false },
  { code: "fr-ca", name: "Canadian French", sheet_code: "fr", azure_translator_code: "fr-ca", rtl: false },
];

const OPTION_LABELS: Record<string, string> = {
  translate_goal: "Translate Goal",
  translate_description: "Translate Description",
  translate_kra: "Translate KRA",
  preserve_technical_fields: "Preserve technical fields",
  preserve_formatting: "Preserve formatting",
  run_numerical_validation: "Run numerical validation",
  run_structural_reconciliation: "Run structural reconciliation",
  run_category_specific_qa: "Run category-specific QA",
};

const DEFAULT_OPTIONS = Object.keys(OPTION_LABELS);

type QaMode = "classic" | "foundry";

type GlossaryTerm = { term: string; action: "preserve" | "allow" };

const DEFAULT_GLOSSARY: GlossaryTerm[] = [
  ...["BCD", "NDC", "EBITDA", "TripSource", "GetGoing", "Advito", "Mission Possible", "Performance Solutions"].map(
    (term) => ({ term, action: "preserve" as const }),
  ),
  ...["SAP", "SuccessFactors", "KPI", "KRA", "Q1", "Q2", "Q3", "Q4", "FY", "OKR", "HR", "IT", "CEO", "CFO", "CTO"].map(
    (term) => ({ term, action: "allow" as const }),
  ),
];

const STAGE_LABELS: Record<string, string> = {
  file_validation: "File validation",
  english_extraction: "English source extraction",
  record_reconciliation: "Record reconciliation",
  translation: "Translation",
  semantic_qa: "Semantic QA (meaning & quality)",
  automatic_correction: "Automatic correction",
  technical_validation: "Technical validation",
  special_category_validation: "Special category validation",
  excel_reconstruction: "Excel reconstruction",
  final_hard_gate: "Final hard gate",
  english_issue_repair: "Repair untranslated English",
};

const WIZARD_STEPS = [
  { id: 1, label: "Upload & Configure" },
  { id: 2, label: "Process & Validate" },
  { id: 3, label: "Review & Download" },
] as const;

const PAID_USD_PER_MILLION = 10;

function parseCsvRows(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (quoted) {
      if (char === '"' && text[index + 1] === '"') {
        cell += '"';
        index += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        cell += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(cell);
      cell = "";
    } else if (char === "\n") {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else if (char !== "\r") {
      cell += char;
    }
  }
  if (cell.length || row.length) {
    row.push(cell);
    rows.push(row);
  }
  return rows;
}

function estimateTranslation(text: string): {
  rows: number;
  characters: number;
  uniqueCharacters: number;
  costUsd: number;
} {
  const table = parseCsvRows(text.replace(/^\uFEFF/, ""));
  const headers = (table[0] ?? []).map((header) => header.replace(/[^a-z]/gi, "").toLowerCase());
  const columns = ["goal", "description", "kra"]
    .map((name) => headers.indexOf(name))
    .filter((index) => index >= 0);
  const unique = new Map<string, number>();
  let characters = 0;
  let rows = 0;
  for (const record of table.slice(1)) {
    const values = columns.map((index) => (record[index] ?? "").trim()).filter(Boolean);
    if (!values.length) continue;
    rows += 1;
    for (const value of values) {
      characters += value.length;
      if (!unique.has(value)) unique.set(value, value.length);
    }
  }
  const uniqueCharacters = [...unique.values()].reduce((sum, length) => sum + length, 0);
  return {
    rows,
    characters,
    uniqueCharacters,
    costUsd: (uniqueCharacters / 1_000_000) * PAID_USD_PER_MILLION,
  };
}

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function jobBadge(status: string, productionReady: boolean): { label: string; className: string } {
  if (productionReady) {
    return { label: "Production ready", className: "bg-emerald-50 text-emerald-700 ring-emerald-200" };
  }
  const upper = status.toUpperCase();
  if (upper === "FAILED") {
    return { label: "Failed", className: "bg-rose-50 text-rose-700 ring-rose-200" };
  }
  if (upper === "NEEDS_REVIEW") {
    return { label: "Needs review", className: "bg-amber-50 text-amber-800 ring-amber-200" };
  }
  if (upper === "COMPLETED") {
    return { label: "Completed", className: "bg-emerald-50 text-emerald-700 ring-emerald-200" };
  }
  if (TERMINAL.has(upper)) {
    return { label: formatStatus(status), className: "bg-slate-100 text-slate-600 ring-slate-200" };
  }
  return { label: "In Progress", className: "bg-emerald-50 text-emerald-700 ring-emerald-200" };
}

function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "—";
  const totalSec = Math.round(ms / 1000);
  if (totalSec < 60) return `${totalSec}s`;
  const mins = Math.floor(totalSec / 60);
  const secs = totalSec % 60;
  if (mins < 60) return `${mins}m ${secs}s`;
  const hours = Math.floor(mins / 60);
  return `${hours}h ${mins % 60}m`;
}

function StageIcon({ status }: { status: string }) {
  if (status === "completed") {
    return (
      <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-emerald-500 text-white">
        <svg viewBox="0 0 20 20" className="h-2.5 w-2.5" fill="currentColor" aria-hidden>
          <path
            fillRule="evenodd"
            d="M16.704 4.153a.75.75 0 0 1 .143 1.052l-8 10.5a.75.75 0 0 1-1.127.075l-4.5-4.5a.75.75 0 0 1 1.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 0 1 1.05-.143Z"
            clipRule="evenodd"
          />
        </svg>
      </span>
    );
  }
  if (status === "running" || status === "queued") {
    return (
      <span className="relative flex h-4 w-4 shrink-0 items-center justify-center">
        <span className="relative h-4 w-4 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin bg-white" />
      </span>
    );
  }
  if (status === "failed") {
    return (
      <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-rose-500 text-[10px] font-bold text-white">
        ×
      </span>
    );
  }
  if (status === "cancelled") {
    return (
      <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-slate-400 text-[10px] font-bold text-white">
        –
      </span>
    );
  }
  return <span className="h-4 w-4 shrink-0 rounded-full border-2 border-slate-200 bg-white" />;
}

function SideDrawer({
  title,
  subtitle,
  onClose,
  children,
  wide = false,
}: {
  title: string;
  subtitle?: ReactNode;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <button
        type="button"
        className="absolute inset-0 bg-slate-900/30"
        aria-label={`Close ${title}`}
        onClick={onClose}
      />
      <aside
        className={`relative flex h-full w-full flex-col border-l border-slate-200 bg-white shadow-xl ${
          wide ? "max-w-xl" : "max-w-md"
        }`}
      >
        <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-4 py-3">
          <div className="min-w-0">
            <h2 className="text-base font-bold text-slate-950">{title}</h2>
            {subtitle ? <div className="mt-1 text-xs text-slate-500">{subtitle}</div> : null}
          </div>
          <button
            type="button"
            className="rounded-lg px-2 py-1 text-sm text-slate-500 hover:bg-slate-100"
            onClick={onClose}
          >
            Close
          </button>
        </div>
        <div className="flex min-h-0 flex-1 flex-col">{children}</div>
      </aside>
    </div>
  );
}

function jobFileUrl(jobId: string, kind: "download" | "report"): string {
  return `${API_BASE}/api/v1/goals-localization/jobs/${jobId}/${kind}`;
}

function formatTime(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
}

export default function GoalsLocalizationPage() {
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [orgName, setOrgName] = useState<string | null>(null);
  const [languages, setLanguages] = useState<Language[]>(FALLBACK_LANGUAGES);
  const [mandatoryOptions, setMandatoryOptions] = useState<string[]>(DEFAULT_OPTIONS);
  const [stages, setStages] = useState<string[]>([]);
  const [targetLanguage, setTargetLanguage] = useState("zh");
  const [qaMode, setQaMode] = useState<QaMode>("classic");
  const [glossary, setGlossary] = useState<GlossaryTerm[]>(DEFAULT_GLOSSARY);
  const [glossaryDraft, setGlossaryDraft] = useState("");
  const [glossaryAction, setGlossaryAction] = useState<GlossaryTerm["action"]>("preserve");
  const [glossaryBusy, setGlossaryBusy] = useState(false);
  const [glossaryNote, setGlossaryNote] = useState<string | null>(null);
  const [promptOpen, setPromptOpen] = useState(false);
  const [promptText, setPromptText] = useState("");
  const [promptDefault, setPromptDefault] = useState("");
  const [promptCustomized, setPromptCustomized] = useState(false);
  const [promptBusy, setPromptBusy] = useState(false);
  const [promptNote, setPromptNote] = useState<string | null>(null);
  const [promptNoteOk, setPromptNoteOk] = useState(false);
  const [englishFile, setEnglishFile] = useState<File | null>(null);
  const [fileEstimate, setFileEstimate] = useState<{
    rows: number;
    characters: number;
    uniqueCharacters: number;
    costUsd: number;
  } | null>(null);
  const [estimateAccepted, setEstimateAccepted] = useState(false);
  const [queue, setQueue] = useState<QueueState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<JobPayload | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [cancelBusy, setCancelBusy] = useState(false);
  const [logsOpen, setLogsOpen] = useState(false);
  const [logEvents, setLogEvents] = useState<JobEvent[]>([]);
  const [logsError, setLogsError] = useState<string | null>(null);
  const [filesOpen, setFilesOpen] = useState(false);
  const [files, setFiles] = useState<JobPayload[]>([]);
  const [filesLoading, setFilesLoading] = useState(false);
  const [filesError, setFilesError] = useState<string | null>(null);
  const restoredRef = useRef(false);
  const seenActiveRef = useRef<string | null>(null);
  const logEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    void fetch(`${API_BASE}/api/v1/auth/me`, { credentials: "include" })
      .then(async (response) => {
        if (response.status === 401) {
          router.replace(`/login?next=${encodeURIComponent("/goals-localization")}`);
          return null;
        }
        if (!response.ok) return null;
        return response.json();
      })
      .then((body) => {
        if (!body) return;
        setEmail(body.email ?? null);
        setRole(body.memberships?.[0]?.role ?? null);
        setOrgName(body.memberships?.[0]?.tenant_name ?? null);
      });
    void fetch(`${API_BASE}/api/v1/goals-localization/languages`, { credentials: "include" })
      .then(async (response) => {
        if (!response.ok) return;
        const body = await response.json();
        const nextLanguages = (body.languages ?? []) as Language[];
        if (nextLanguages.length) {
          setLanguages(nextLanguages);
          if (!nextLanguages.some((lang) => lang.code === targetLanguage)) {
            setTargetLanguage(nextLanguages[0].code);
          }
        }
        if (Array.isArray(body.mandatory_options) && body.mandatory_options.length) {
          setMandatoryOptions(body.mandatory_options as string[]);
        }
        if (Array.isArray(body.stages) && body.stages.length) {
          setStages(body.stages as string[]);
        }
        if (body.default_qa_mode === "classic" || body.default_qa_mode === "foundry") {
          setQaMode(body.default_qa_mode);
        }
      })
      .catch(() => undefined);
    void fetch(`${API_BASE}/api/v1/goals-localization/glossary`, { credentials: "include" })
      .then(async (response) => {
        if (!response.ok) return;
        const body = await response.json();
        if (Array.isArray(body.terms) && body.terms.length) {
          setGlossary(body.terms as GlossaryTerm[]);
        }
      })
      .catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshQueue = useCallback(async () => {
    const response = await fetch(`${API_BASE}/api/v1/goals-localization/queue`, { credentials: "include" });
    if (!response.ok) return;
    setQueue(await response.json());
  }, []);

  useEffect(() => {
    void refreshQueue();
    const timer = window.setInterval(() => void refreshQueue(), 4000);
    return () => window.clearInterval(timer);
  }, [refreshQueue]);

  const refreshJob = useCallback(async (jobId: string) => {
    const response = await fetch(`${API_BASE}/api/v1/goals-localization/jobs/${jobId}`, {
      credentials: "include",
    });
    if (response.status === 404) {
      window.localStorage.removeItem(LAST_JOB_KEY);
      return;
    }
    if (!response.ok) return;
    const body = await response.json();
    setJob(body.job as JobPayload);
  }, []);

  // After a reload with nothing in the worker, show the last job opened here,
  // or the newest job on the server if this browser has none.
  useEffect(() => {
    if (!queue || restoredRef.current) return;
    restoredRef.current = true;
    if (job || queue.active_job_id) return;
    const jobId = window.localStorage.getItem(LAST_JOB_KEY);
    if (jobId === CLEARED_JOB) return;
    if (jobId) {
      void refreshJob(jobId);
      return;
    }
    void fetch(`${API_BASE}/api/v1/goals-localization/jobs`, { credentials: "include" })
      .then(async (response) => (response.ok ? response.json() : null))
      .then((body) => {
        const latest = (body?.jobs as JobPayload[] | undefined)?.[0];
        if (latest) void refreshJob(latest.id);
      })
      .catch(() => undefined);
  }, [queue, job, refreshJob]);

  // Whenever the worker gets a new job (after a reload, or started in another tab), show it.
  useEffect(() => {
    const activeId = queue?.active_job_id ?? null;
    if (activeId === seenActiveRef.current) return;
    seenActiveRef.current = activeId;
    if (!activeId || job?.id === activeId) return;
    if (job && !TERMINAL.has(job.status)) return;
    void refreshJob(activeId);
  }, [queue?.active_job_id, job, refreshJob]);

  useEffect(() => {
    if (job?.id) window.localStorage.setItem(LAST_JOB_KEY, job.id);
  }, [job?.id]);

  const loadLogs = useCallback(async (jobId: string) => {
    const response = await fetch(`${API_BASE}/api/v1/goals-localization/jobs/${jobId}/logs`, {
      credentials: "include",
    });
    if (!response.ok) {
      setLogsError(await readApiError(response, "Could not load logs."));
      return;
    }
    const body = await response.json();
    setLogsError(null);
    setLogEvents((body.events ?? []) as JobEvent[]);
  }, []);

  useEffect(() => {
    if (!logsOpen || !job?.id) return;
    void loadLogs(job.id);
    if (TERMINAL.has(job.status)) return;
    const timer = window.setInterval(() => void loadLogs(job.id), 2000);
    return () => window.clearInterval(timer);
  }, [logsOpen, job?.id, job?.status, loadLogs]);

  useEffect(() => {
    if (logsOpen) logEndRef.current?.scrollIntoView({ block: "end" });
  }, [logsOpen, logEvents]);

  const loadFiles = useCallback(async () => {
    setFilesLoading(true);
    setFilesError(null);
    try {
      const response = await fetch(`${API_BASE}/api/v1/goals-localization/jobs`, { credentials: "include" });
      if (!response.ok) {
        throw new Error(await readApiError(response, "Could not load processed files."));
      }
      const body = await response.json();
      setFiles((body.jobs ?? []) as JobPayload[]);
    } catch (err) {
      setFilesError(err instanceof Error ? err.message : "Could not load processed files.");
    } finally {
      setFilesLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!filesOpen) return;
    void loadFiles();
    const timer = window.setInterval(() => void loadFiles(), 10000);
    return () => window.clearInterval(timer);
  }, [filesOpen, loadFiles]);

  useEffect(() => {
    if (!job?.id || TERMINAL.has(job.status)) return;
    const timer = window.setInterval(() => {
      void refreshJob(job.id);
    }, 1200);
    return () => window.clearInterval(timer);
  }, [job?.id, job?.status, refreshJob]);

  useEffect(() => {
    if (!job?.id || TERMINAL.has(job.status)) return;
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [job?.id, job?.status]);

  const selectedLanguage = languages.find((lang) => lang.code === targetLanguage);
  const optionList = mandatoryOptions.length ? mandatoryOptions : DEFAULT_OPTIONS;
  const workerBusy = Boolean(queue?.busy) || Boolean(job && !TERMINAL.has(job.status));
  const canStart = Boolean(englishFile && targetLanguage && estimateAccepted && !busy && !workerBusy);
  const processedFiles = useMemo(() => files.filter((item) => item.has_output), [files]);
  const stageList = job?.stages?.length ? job.stages : stages.length ? stages : Object.keys(STAGE_LABELS);

  const stageStatuses = useMemo(() => {
    const progress = job?.stage_progress ?? {};
    const statuses: Record<string, string> = {};
    for (const stage of stageList) {
      statuses[stage] = progress[stage]?.status ?? "pending";
    }
    if (!job || TERMINAL.has(job.status)) return statuses;
    const upper = job.status.toUpperCase();
    if (upper === "UPLOADED" || upper === "QUEUED") {
      const first = stageList[0] ?? "file_validation";
      statuses[first] = "queued";
      return statuses;
    }
    if (job.current_stage) {
      const currentStatus = statuses[job.current_stage];
      if (currentStatus !== "completed" && currentStatus !== "failed") {
        statuses[job.current_stage] = currentStatus === "running" ? "running" : "running";
      }
    }
    return statuses;
  }, [job, stageList]);

  const completedStages = useMemo(
    () => Object.values(stageStatuses).filter((status) => status === "completed").length,
    [stageStatuses],
  );

  const activeStage = useMemo(() => {
    const running = stageList.find((stage) => stageStatuses[stage] === "running");
    if (running) return running;
    const queued = stageList.find((stage) => stageStatuses[stage] === "queued");
    if (queued) return queued;
    return job?.current_stage ?? null;
  }, [stageList, stageStatuses, job?.current_stage]);

  const activeStepNumber = useMemo(() => {
    if (!activeStage) return Math.min(completedStages + 1, stageList.length);
    const idx = stageList.indexOf(activeStage);
    return idx >= 0 ? idx + 1 : Math.min(completedStages + 1, stageList.length);
  }, [activeStage, completedStages, stageList]);

  const wizardStep = useMemo(() => {
    if (!job) return 1;
    if (TERMINAL.has(job.status) || job.production_ready) return 3;
    return 2;
  }, [job]);

  const progressPct = Math.round(
    (completedStages / Math.max(stageList.length, 1)) * 100,
  );

  const elapsedLabel = useMemo(() => {
    if (!job?.created_at) return "—";
    const elapsedMs = Math.max(0, nowMs - Date.parse(job.created_at));
    return formatDuration(elapsedMs);
  }, [job, nowMs]);

  const totalLabel = useMemo(() => {
    if (!job?.created_at || !job.completed_at || !TERMINAL.has(job.status)) return null;
    return formatDuration(Date.parse(job.completed_at) - Date.parse(job.created_at));
  }, [job]);

  const rowCounts = useMemo(() => {
    const total = job?.total_records ?? 0;
    const processed = Math.min(job?.processed_records ?? 0, total || job?.processed_records || 0);
    const pending = Math.max(total - processed, 0);
    return { total, processed, pending };
  }, [job?.total_records, job?.processed_records]);

  const qaMetrics = useMemo(() => {
    const s = job?.summary ?? {};
    const shown = (value: unknown, fallback?: unknown) => {
      if (value != null && value !== "") return String(value);
      if (fallback != null && fallback !== "") return String(fallback);
      return "—";
    };
    const flag = (value: unknown) => {
      if (!job || !TERMINAL.has(job.status) || value == null) return "—";
      return value ? "PASS" : "FAIL";
    };
    const numeric = Number(s.numeric_discrepancies ?? 0) + Number(s.percentage_discrepancies ?? 0);
    const dates = Number(s.quarter_discrepancies ?? 0) + Number(s.date_discrepancies ?? 0);
    return [
      { label: "Source row count", value: shown(s.source_record_count, job?.total_records || undefined) },
      { label: "Output row count", value: shown(s.output_record_count) },
      { label: "Unmatched records", value: shown(s.unmatched_records) },
      { label: "Blank Goal cells", value: shown(s.blank_goal_violations) },
      { label: "Blank Description cells", value: shown(s.blank_description_violations) },
      { label: "Blank KRA cells", value: shown(s.blank_kra_violations) },
      {
        label: "Numeric / percentage mismatches",
        value: job && (s.numeric_discrepancies != null || s.percentage_discrepancies != null) ? String(numeric) : "—",
      },
      {
        label: "Quarter / date mismatches",
        value: job && (s.quarter_discrepancies != null || s.date_discrepancies != null) ? String(dates) : "—",
      },
      { label: "Suspicious untranslated text", value: shown(s.unresolved_untranslated_english) },
      { label: "Hotel Revenue Growth QA", value: flag(s.hotel_revenue_growth_qa_pass) },
      { label: "Operational Productivity QA", value: flag(s.operational_productivity_qa_pass) },
    ];
  }, [job]);

  async function saveGlossary(next: GlossaryTerm[]) {
    setGlossaryNote(null);
    if (!csrfToken()) {
      setGlossaryNote("Session expired. Sign in again.");
      return;
    }
    setGlossaryBusy(true);
    try {
      const response = await fetch(`${API_BASE}/api/v1/goals-localization/glossary`, {
        method: "PUT",
        credentials: "include",
        headers: { "content-type": "application/json", "x-csrf-token": csrfToken() },
        body: JSON.stringify({ terms: next }),
      });
      if (!response.ok) {
        throw new Error(await readApiError(response, "Could not save terminology."));
      }
      const body = await response.json();
      setGlossary((body.terms ?? next) as GlossaryTerm[]);
      setGlossaryNote("Saved. The next job uses this list.");
    } catch (err) {
      setGlossaryNote(err instanceof Error ? err.message : "Could not save terminology.");
    } finally {
      setGlossaryBusy(false);
    }
  }

  function addGlossaryTerm() {
    const term = glossaryDraft.trim();
    if (!term) return;
    if (glossary.some((item) => item.term.toLowerCase() === term.toLowerCase())) {
      setGlossaryNote("That term is already in the list.");
      return;
    }
    const next = [...glossary, { term, action: glossaryAction }];
    setGlossaryDraft("");
    void saveGlossary(next);
  }

  async function onStart() {
    setError(null);
    if (!englishFile) {
      setError("Upload the English Goals Library CSV.");
      return;
    }
    if (!targetLanguage) {
      setError("Select a target language.");
      return;
    }
    if (!csrfToken()) {
      setError("Session expired. Sign in again, then retry.");
      router.replace(`/login?next=${encodeURIComponent("/goals-localization")}`);
      return;
    }
    setBusy(true);
    try {
      const form = new FormData();
      form.append("target_language", targetLanguage);
      form.append("qa_mode", qaMode);
      form.append("english_csv", englishFile, englishFile.name);
      const response = await fetch(`${API_BASE}/api/v1/goals-localization/jobs`, {
        method: "POST",
        credentials: "include",
        headers: { "x-csrf-token": csrfToken() },
        body: form,
      });
      if (response.status === 401) {
        router.replace(`/login?next=${encodeURIComponent("/goals-localization")}`);
        throw new Error("Authentication required. Please sign in and retry.");
      }
      if (!response.ok) {
        throw new Error(await readApiError(response, "Could not start localization."));
      }
      const body = await response.json();
      setJob(body.job as JobPayload);
      void refreshQueue();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start localization.");
    } finally {
      setBusy(false);
    }
  }

  async function onCancelQueue() {
    if (!window.confirm("Cancel the file in the worker queue? Its progress is discarded.")) return;
    if (!csrfToken()) {
      setError("Session expired. Sign in again, then retry.");
      return;
    }
    setCancelBusy(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/v1/goals-localization/queue/clear`, {
        method: "POST",
        credentials: "include",
        headers: { "x-csrf-token": csrfToken() },
      });
      if (!response.ok) {
        throw new Error(await readApiError(response, "Could not cancel the worker queue."));
      }
      await refreshQueue();
      if (job) await refreshJob(job.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not cancel the worker queue.");
    } finally {
      setCancelBusy(false);
    }
  }

  function onClear() {
    setEnglishFile(null);
    setFileEstimate(null);
    setEstimateAccepted(false);
    setError(null);
    // A running job stays on screen; only a finished one is cleared.
    if (!job || TERMINAL.has(job.status)) {
      setJob(null);
      window.localStorage.setItem(LAST_JOB_KEY, CLEARED_JOB);
    }
  }

  async function openJob(jobId: string, showLogs = false) {
    await refreshJob(jobId);
    setFilesOpen(false);
    if (showLogs) setLogsOpen(true);
  }

  async function onPickFile(file: File | null) {
    setEnglishFile(file);
    setEstimateAccepted(false);
    setFileEstimate(null);
    if (!file) return;
    const estimate = estimateTranslation(await file.text());
    setFileEstimate(estimate);
  }

  async function openPrompt() {
    setPromptOpen(true);
    setPromptNote(null);
    setPromptNoteOk(false);
    const response = await fetch(`${API_BASE}/api/v1/goals-localization/prompt`, { credentials: "include" });
    if (!response.ok) {
      setPromptNote(await readApiError(response, "Could not load the prompt."));
      return;
    }
    const body = await response.json();
    setPromptText(String(body.prompt ?? ""));
    setPromptDefault(String(body.default_prompt ?? ""));
    setPromptCustomized(Boolean(body.customized));
  }

  async function savePrompt(next: string, mode: "save" | "reset" = "save") {
    if (!csrfToken()) {
      setPromptNoteOk(false);
      setPromptNote("Session expired. Sign in again.");
      return;
    }
    setPromptBusy(true);
    setPromptNote(null);
    setPromptNoteOk(false);
    try {
      const response = await fetch(`${API_BASE}/api/v1/goals-localization/prompt`, {
        method: "PUT",
        credentials: "include",
        headers: { "content-type": "application/json", "x-csrf-token": csrfToken() },
        body: JSON.stringify({ prompt: next }),
      });
      if (!response.ok) {
        throw new Error(await readApiError(response, "Could not save the prompt."));
      }
      const body = await response.json();
      setPromptText(String(body.prompt ?? next));
      setPromptDefault(String(body.default_prompt ?? promptDefault));
      setPromptCustomized(Boolean(body.customized));
      setPromptNoteOk(true);
      setPromptNote(
        mode === "reset"
          ? "Reset to the built-in prompt."
          : "Saved. The next Foundry job uses this prompt.",
      );
    } catch (err) {
      setPromptNoteOk(false);
      setPromptNote(err instanceof Error ? err.message : "Could not save the prompt.");
    } finally {
      setPromptBusy(false);
    }
  }

  function downloadUrl(kind: "download" | "report") {
    if (!job) return "#";
    return `${API_BASE}/api/v1/goals-localization/jobs/${job.id}/${kind}`;
  }

  const badge = job ? jobBadge(job.status, job.production_ready) : null;
  const excelAvailable = Boolean(job?.has_output);
  const reportAvailable = Boolean(job?.has_report);
  const languageName = (code: string) => languages.find((lang) => lang.code === code)?.name ?? code;

  return (
    <AppShell email={email} role={role} orgName={orgName}>
      <div className="mb-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-950">
            Goals Library Localization & Validation
          </h1>
          <p className="mt-1 max-w-3xl text-sm text-slate-500">
            Translate the Goals Library from English, validate it, and generate a SuccessFactors-ready workbook.
          </p>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3">
        <ol className="flex items-center gap-1.5 text-sm">
          {WIZARD_STEPS.map((step, index) => {
            const active = wizardStep === step.id;
            const done = wizardStep > step.id;
            return (
              <li key={step.id} className="flex items-center gap-1.5">
                {index > 0 ? <span className="text-slate-300">›</span> : null}
                <span
                  className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold ${
                    active
                      ? "bg-indigo-600 text-white"
                      : done
                        ? "bg-emerald-500 text-white"
                        : "bg-slate-100 text-slate-500"
                  }`}
                >
                  {done ? "✓" : step.id}
                </span>
                <span className={`font-medium ${active ? "text-indigo-950" : "text-slate-500"}`}>
                  {step.label}
                </span>
              </li>
            );
          })}
        </ol>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="tm-btn tm-btn-secondary !px-3 !py-2 text-sm"
            onClick={() => setFilesOpen(true)}
          >
            Processed Excel files
          </button>
          <button
            type="button"
            className="tm-btn tm-btn-secondary !px-3 !py-2 text-sm"
            onClick={() => setLogsOpen(true)}
          >
            Logs
            {job && !TERMINAL.has(job.status) ? (
              <span className="ml-1.5 inline-block h-2 w-2 animate-pulse rounded-full bg-emerald-500" aria-hidden />
            ) : null}
          </button>
          <button
            type="button"
            className="tm-btn tm-btn-secondary !px-3 !py-2 text-sm"
            onClick={() => void openPrompt()}
          >
            Manage prompt
          </button>
        </div>
        </div>
      </div>

      {error ? (
        <div className="mb-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
          {error}
        </div>
      ) : null}

      <div className="grid items-start gap-3 lg:grid-cols-2">
        <section className="tm-card overflow-hidden">
          <div className="border-b border-slate-100 px-4 py-2.5">
            <h2 className="text-sm font-semibold text-slate-950">Upload & configure</h2>
          </div>

          <div className="space-y-3 px-4 py-3">
            <div>
              <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                Upload files
              </p>
              <div>
                <label className="flex cursor-pointer items-start gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2.5 transition hover:border-indigo-300">
                  <span
                    className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-[10px] font-bold ${
                      englishFile ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"
                    }`}
                  >
                    CSV
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-xs font-semibold text-slate-900">
                      English Goals Library
                      <span className="text-rose-500"> *</span>
                    </span>
                    {englishFile ? (
                      <>
                        <span className="mt-0.5 block truncate text-xs text-slate-700">{englishFile.name}</span>
                        <span className="text-[11px] text-emerald-700">{formatBytes(englishFile.size)} · ready</span>
                      </>
                    ) : (
                      <span className="mt-0.5 block text-[11px] text-slate-500">Choose the source CSV</span>
                    )}
                  </span>
                  {englishFile ? (
                    <button
                      type="button"
                      className="text-xs text-slate-400 hover:text-rose-600"
                      aria-label="Remove CSV"
                      onClick={(event) => {
                        event.preventDefault();
                        event.stopPropagation();
                        void onPickFile(null);
                      }}
                    >
                      ✕
                    </button>
                  ) : null}
                  <input
                    type="file"
                    accept=".csv,text/csv"
                    className="sr-only"
                    onChange={(event: ChangeEvent<HTMLInputElement>) => {
                      void onPickFile(event.target.files?.[0] ?? null);
                      event.target.value = "";
                    }}
                  />
                </label>
              </div>
              {fileEstimate && !estimateAccepted ? (
                <div className="mt-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-950">
                  <p className="font-semibold">
                    {fileEstimate.rows.toLocaleString()} rows · {fileEstimate.characters.toLocaleString()} characters in the file
                  </p>
                  <p className="mt-1">
                    {fileEstimate.uniqueCharacters.toLocaleString()} unique characters will be sent. Repeated Goal, Description, and KRA text is translated once and reused.
                  </p>
                  <p className="mt-1">
                    Estimated paid cost ${fileEstimate.costUsd.toFixed(2)} at $10 per million unique characters.
                    The free account stops at 2 million characters a month and does not upgrade itself.
                  </p>
                  <div className="mt-2 flex gap-2">
                    <button
                      type="button"
                      className="tm-btn tm-btn-primary !px-2.5 !py-1.5 text-xs"
                      onClick={() => setEstimateAccepted(true)}
                    >
                      Continue
                    </button>
                    <button
                      type="button"
                      className="tm-btn tm-btn-secondary !px-2.5 !py-1.5 text-xs"
                      onClick={() => void onPickFile(null)}
                    >
                      Skip
                    </button>
                  </div>
                </div>
              ) : null}
            </div>

            <label className="block">
              <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                Target language
              </span>
              <select
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none transition focus:border-indigo-400 focus:ring-2 focus:ring-indigo-50"
                value={targetLanguage}
                onChange={(event) => setTargetLanguage(event.target.value)}
                disabled={Boolean(job) && !TERMINAL.has(job?.status ?? "")}
              >
                {languages.map((lang) => (
                  <option key={lang.code} value={lang.code}>
                    {lang.name} ({lang.sheet_code ?? lang.code})
                  </option>
                ))}
              </select>
            </label>

            <div>
              <div className="mb-1.5 flex items-center justify-between gap-2">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                  Terminology
                </p>
                <span className="text-[11px] text-slate-400">{glossary.length} terms</span>
              </div>
              <div className="mb-2 flex gap-1.5">
                <input
                  value={glossaryDraft}
                  onChange={(event) => setGlossaryDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      addGlossaryTerm();
                    }
                  }}
                  placeholder="Add a term"
                  className="min-w-0 flex-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs outline-none focus:border-indigo-400"
                />
                <select
                  value={glossaryAction}
                  onChange={(event) => setGlossaryAction(event.target.value as GlossaryTerm["action"])}
                  className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs"
                >
                  <option value="preserve">Preserve</option>
                  <option value="allow">Allow English</option>
                </select>
                <button
                  type="button"
                  className="tm-btn tm-btn-secondary !px-2.5 !py-1.5 text-xs"
                  disabled={glossaryBusy || !glossaryDraft.trim()}
                  onClick={addGlossaryTerm}
                >
                  Add
                </button>
              </div>
              <div className="max-h-36 overflow-auto rounded-lg border border-slate-200">
                <table className="w-full text-left text-xs">
                  <thead className="sticky top-0 bg-slate-50 text-[10px] uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-2 py-1 font-semibold">Term</th>
                      <th className="px-2 py-1 font-semibold">Action</th>
                      <th className="px-2 py-1" />
                    </tr>
                  </thead>
                  <tbody>
                    {glossary.map((item) => (
                      <tr key={item.term} className="border-t border-slate-100">
                        <td className="px-2 py-1 font-medium text-slate-800">{item.term}</td>
                        <td className="px-2 py-1 text-slate-500">
                          {item.action === "preserve" ? "Preserve" : "Allow English"}
                        </td>
                        <td className="px-2 py-1 text-right">
                          <button
                            type="button"
                            className="text-slate-400 hover:text-rose-600"
                            disabled={glossaryBusy}
                            aria-label={`Remove ${item.term}`}
                            onClick={() => void saveGlossary(glossary.filter((row) => row.term !== item.term))}
                          >
                            ✕
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {glossaryNote ? <p className="mt-1 text-[11px] text-slate-500">{glossaryNote}</p> : null}
              <p className="mt-1 text-[11px] leading-4 text-slate-400">
                Preserve keeps the exact term untranslated. Allow English may be translated; leftover English for that term is not flagged.
              </p>
            </div>

            <div>
              <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                Translation & validation options
              </p>
              <div className="grid gap-x-3 gap-y-1.5 sm:grid-cols-2">
                {optionList
                  .filter((option) => option !== "run_semantic_qa" && option !== "qa_mode")
                  .map((option) => (
                  <label key={option} className="flex items-center gap-2 text-xs text-slate-700">
                    <input type="checkbox" checked disabled className="h-3.5 w-3.5 rounded border-slate-300 text-indigo-600" />
                    <span>{OPTION_LABELS[option] ?? option.replaceAll("_", " ")}</span>
                  </label>
                ))}
                <label className="flex items-center justify-between gap-2 text-xs text-slate-800 sm:col-span-2">
                  <span className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={qaMode === "foundry"}
                      disabled={Boolean(job) && !TERMINAL.has(job?.status ?? "")}
                      onChange={() => setQaMode((prev) => (prev === "foundry" ? "classic" : "foundry"))}
                      className="h-3.5 w-3.5 rounded border-slate-300 text-indigo-600"
                    />
                    <span>Run semantic QA with Azure AI Foundry</span>
                  </span>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={qaMode === "foundry"}
                    aria-label="Toggle Azure AI Foundry semantic QA"
                    disabled={Boolean(job) && !TERMINAL.has(job?.status ?? "")}
                    onClick={() => setQaMode((prev) => (prev === "foundry" ? "classic" : "foundry"))}
                    className={`relative h-5 w-9 shrink-0 rounded-full transition ${
                      qaMode === "foundry" ? "bg-indigo-600" : "bg-slate-300"
                    } disabled:cursor-not-allowed disabled:opacity-60`}
                  >
                    <span
                      className={`absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow transition ${
                        qaMode === "foundry" ? "translate-x-4" : "translate-x-0"
                      }`}
                    />
                  </button>
                </label>
              </div>
              <p className="mt-1.5 text-[11px] leading-4 text-slate-500">
                {qaMode === "foundry"
                  ? "Foundry is on. Meaning checks use Azure OpenAI and can be rate limited."
                  : selectedLanguage?.translate === false
                    ? "English is copied through and the workbook Code column is set to en."
                    : "Foundry is off. Translator, protected terms, and Python checks. Semantic accuracy still needs human review."}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 px-4 py-2.5">
            <button
              type="button"
              className="tm-btn tm-btn-primary !px-3 !py-2 text-sm"
              disabled={!canStart}
              title={workerBusy ? "The worker is busy with another file." : undefined}
              onClick={() => void onStart()}
            >
              {busy ? "Starting…" : workerBusy ? "Worker busy" : "Start Localization"}
            </button>
            <button type="button" className="tm-btn tm-btn-ghost !px-3 !py-2 text-sm" onClick={onClear}>
              Clear
            </button>
            {workerBusy ? (
              <p className="text-[11px] text-slate-500">
                One file at a time. Wait for the current file to finish, or cancel it.
              </p>
            ) : null}
          </div>
        </section>

        {/* Job status */}
        <section className="tm-card overflow-hidden">
          <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-2.5">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-semibold text-slate-950">Localization Job</h2>
                {badge ? (
                  <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ${badge.className}`}>
                    {badge.label}
                  </span>
                ) : (
                  <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-500 ring-1 ring-slate-200">
                    Waiting
                  </span>
                )}
              </div>
              <p className="mt-0.5 truncate text-[11px] text-slate-500">
                {job
                  ? `Job ${job.id.slice(0, 8)} · ${
                      languages.find((l) => l.code === job.target_language)?.name ?? job.target_language
                    } · ${
                      (job.options?.qa_mode as string) === "foundry" ? "Foundry" : "Classic"
                    }${job.created_at ? ` · ${new Date(job.created_at).toLocaleString()}` : ""}`
                  : "Upload the CSV and start to see progress here."}
              </p>
            </div>
            <p className="shrink-0 text-right text-[11px] font-medium text-slate-500">
              Step {job ? (TERMINAL.has(job.status) ? completedStages : activeStepNumber) : 0} of {stageList.length}
              <span className="mt-0.5 block tabular-nums text-slate-700">{job ? `${progressPct}%` : "0%"}</span>
            </p>
          </div>

          <div className="px-4 py-3">
            <div
              className={`mb-2 rounded-lg px-3 py-2 text-xs ${
                queue?.busy ? "bg-indigo-50 text-indigo-950" : "bg-slate-50 text-slate-600"
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                {queue?.busy && queue.processing ? (
                  <p className="min-w-0">
                    Worker is processing <span className="font-semibold">{queue.processing.source_filename}</span>
                    {" · "}
                    {STAGE_LABELS[queue.processing.current_stage ?? ""] ?? formatStatus(queue.processing.status)}
                    {": "}
                    {queue.processing.processed_records.toLocaleString()} of{" "}
                    {queue.processing.total_records.toLocaleString()} rows.
                    {queue.waiting > 0 ? ` ${queue.waiting} more file${queue.waiting === 1 ? "" : "s"} waiting.` : ""}
                  </p>
                ) : queue && queue.waiting > 0 ? (
                  <p className="min-w-0">
                    {queue.waiting} file{queue.waiting === 1 ? "" : "s"} waiting for the worker to pick up.
                  </p>
                ) : (
                  <p>No file is in the worker queue.</p>
                )}
                {queue?.busy ? (
                  <button
                    type="button"
                    className="shrink-0 rounded-lg border border-rose-200 bg-white px-2.5 py-1 text-[11px] font-semibold text-rose-700 transition hover:bg-rose-50 disabled:opacity-50"
                    disabled={cancelBusy}
                    onClick={() => void onCancelQueue()}
                  >
                    {cancelBusy ? "Cancelling…" : "Cancel"}
                  </button>
                ) : null}
              </div>
            </div>
            {job?.error_message && (job.status === "FAILED" || job.status === "CANCELLED") ? (
              <div className="mb-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-xs text-rose-700">
                {job.error_message}
              </div>
            ) : null}
            <div className="mb-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-indigo-500 transition-all duration-500"
                style={{
                  width: `${
                    job
                      ? Math.max(progressPct, !TERMINAL.has(job.status) ? Math.max(6, activeStepNumber * 3) : 0)
                      : 0
                  }%`,
                }}
              />
            </div>
            <p className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-600">
              <span>
                <span className="font-semibold tabular-nums text-slate-900">{rowCounts.processed}</span> processed
              </span>
              <span>
                <span className="font-semibold tabular-nums text-slate-900">{rowCounts.pending}</span> pending
              </span>
              <span>
                <span className="font-semibold tabular-nums text-slate-900">{rowCounts.total}</span> total rows
              </span>
              {job && !TERMINAL.has(job.status) ? (
                <span className="text-indigo-700">
                  {job.status.toUpperCase() === "UPLOADED"
                    ? "Queued — waiting for worker"
                    : STAGE_LABELS[activeStage ?? ""] ?? activeStage}
                  {" · "}
                  {elapsedLabel}
                </span>
              ) : totalLabel ? (
                <span className="text-slate-700">
                  Total time <span className="font-semibold tabular-nums text-slate-900">{totalLabel}</span>
                </span>
              ) : null}
            </p>
            <ol>
              {stageList.map((stage, index) => {
                const info = job?.stage_progress?.[stage];
                const status = stageStatuses[stage] ?? "pending";
                const isActive = status === "running" || status === "queued";
                const statusLabel =
                  status === "completed"
                    ? "Completed"
                    : status === "failed"
                      ? "Failed"
                      : status === "cancelled"
                        ? "Cancelled"
                      : status === "queued"
                        ? "Queued"
                        : isActive
                          ? "In Progress"
                          : "Pending";
                const startedMs = info?.started_at ? Date.parse(info.started_at) : NaN;
                const stageMs =
                  status === "running" && !TERMINAL.has(job?.status ?? "")
                    ? Math.max(0, nowMs - startedMs)
                    : info?.updated_at
                      ? Date.parse(info.updated_at) - startedMs
                      : NaN;
                const stageTime = status !== "pending" && Number.isFinite(stageMs) ? formatDuration(stageMs) : null;
                return (
                  <li
                    key={stage}
                    className={`flex items-center gap-2 rounded-md px-1.5 py-1 ${
                      isActive ? "bg-indigo-50" : ""
                    }`}
                  >
                    <StageIcon status={status} />
                    <p
                      className={`min-w-0 flex-1 truncate text-xs ${
                        status === "failed"
                          ? "font-medium text-rose-700"
                          : status === "pending"
                            ? "text-slate-400"
                            : isActive
                              ? "font-medium text-indigo-950"
                              : "text-slate-800"
                      }`}
                    >
                      {STAGE_LABELS[stage] ?? stage.replaceAll("_", " ")}
                      {info?.detail ? <span className="ml-1 font-normal text-slate-400">· {info.detail}</span> : null}
                    </p>
                    <span
                      className={`shrink-0 text-[11px] ${
                        status === "completed"
                          ? "text-emerald-600"
                          : status === "failed"
                            ? "text-rose-600"
                            : isActive
                              ? "font-medium text-indigo-600"
                              : "text-slate-400"
                      }`}
                    >
                      {statusLabel}
                    </span>
                    <span className="w-12 shrink-0 text-right text-[11px] tabular-nums text-slate-500">
                      {stageTime ?? ""}
                    </span>
                    <span className="sr-only">{index + 1}</span>
                  </li>
                );
              })}
            </ol>
          </div>
        </section>
      </div>

      <div className="mt-3 grid items-start gap-3 lg:grid-cols-[minmax(0,1fr)_220px]">
        <section className="tm-card overflow-hidden">
          <div className="border-b border-slate-100 px-4 py-2.5">
            <h2 className="text-sm font-semibold text-slate-950">
              QA Summary
              <span className="ml-2 font-normal text-slate-400">
                {job && TERMINAL.has(job.status) ? "Results for this job" : "Fills in when the job finishes"}
              </span>
            </h2>
          </div>
          <dl className="grid sm:grid-cols-2 lg:grid-cols-3">
            {qaMetrics.map((metric) => (
              <div key={metric.label} className="flex items-baseline justify-between gap-3 border-b border-slate-100 px-4 py-2">
                <dt className="text-[11px] text-slate-500">{metric.label}</dt>
                <dd className="text-sm font-semibold tabular-nums text-slate-950">{metric.value}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section className="tm-card overflow-hidden">
          <div className="border-b border-slate-100 px-4 py-2.5">
            <h2 className="text-sm font-semibold text-slate-950">Downloads</h2>
          </div>
          <div className="flex flex-col gap-2 px-4 py-3">
            <a
              className={`tm-btn !px-3 !py-2 text-sm ${
                excelAvailable
                  ? job?.production_ready
                    ? "tm-btn-primary"
                    : "tm-btn-secondary"
                  : "pointer-events-none opacity-40 tm-btn-secondary"
              }`}
              href={excelAvailable ? downloadUrl("download") : undefined}
              aria-disabled={!excelAvailable}
            >
              {job?.production_ready ? "Download Final Excel" : excelAvailable ? "Download diagnostic Excel" : "Download Final Excel"}
            </a>
            <a
              className={`tm-btn tm-btn-secondary !px-3 !py-2 text-sm ${reportAvailable ? "" : "pointer-events-none opacity-40"}`}
              href={reportAvailable ? downloadUrl("report") : undefined}
              aria-disabled={!reportAvailable}
            >
              Download QA Report
            </a>
            {job?.production_ready ? (
              <p className="text-[11px] text-emerald-700">Hard gate passed.</p>
            ) : job && TERMINAL.has(job.status) ? (
              <p className="text-[11px] text-amber-700">Hard gate did not pass.</p>
            ) : (
              <p className="text-[11px] text-slate-400">Available after the job finishes.</p>
            )}
          </div>
        </section>
      </div>
      {logsOpen ? (
        <SideDrawer
          title="Activity log"
          wide
          onClose={() => setLogsOpen(false)}
          subtitle={
            job ? (
              <>
                <span className="font-medium text-slate-700">{job.source_filename}</span>
                {" · "}
                {languageName(job.target_language)}
                {" · "}
                {jobBadge(job.status, job.production_ready).label}
                {" · "}
                {job.processed_records.toLocaleString()} of {job.total_records.toLocaleString()} rows
                {!TERMINAL.has(job.status) ? " · updates every 2s" : ""}
              </>
            ) : (
              "No job selected."
            )
          }
        >
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
            {!job ? (
              <p className="text-sm text-slate-500">
                Start a file, or open one from Processed Excel files, to see what the worker is doing.
              </p>
            ) : logsError ? (
              <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{logsError}</p>
            ) : logEvents.length === 0 ? (
              <p className="text-sm text-slate-500">No activity recorded for this job yet.</p>
            ) : (
              <ol className="space-y-1.5">
                {logEvents.map((event, index) => (
                  <li key={`${event.at}-${index}`} className="flex gap-2.5 rounded-md px-1.5 py-1 text-xs hover:bg-slate-50">
                    <span
                      className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${LOG_LEVEL_STYLE[event.level] ?? "bg-slate-400"}`}
                      aria-hidden
                    />
                    <div className="min-w-0 flex-1">
                      <p
                        className={`break-words leading-5 ${
                          event.level === "error"
                            ? "text-rose-700"
                            : event.level === "warning"
                              ? "text-amber-800"
                              : "text-slate-800"
                        }`}
                      >
                        {event.message}
                        {event.count && event.count > 1 ? (
                          <span className="ml-1.5 rounded bg-slate-100 px-1 text-[10px] font-semibold text-slate-500">
                            ×{event.count}
                          </span>
                        ) : null}
                      </p>
                      <p className="text-[10px] text-slate-400">
                        {new Date(event.at).toLocaleTimeString()}
                        {event.stage ? ` · ${STAGE_LABELS[event.stage] ?? event.stage}` : ""}
                      </p>
                    </div>
                  </li>
                ))}
              </ol>
            )}
            <div ref={logEndRef} />
          </div>
          {job && queue?.busy && queue.active_job_id === job.id ? (
            <div className="border-t border-slate-200 px-4 py-3">
              <button
                type="button"
                className="tm-btn tm-btn-secondary !px-3 !py-2 text-sm text-rose-700"
                disabled={cancelBusy}
                onClick={() => void onCancelQueue()}
              >
                {cancelBusy ? "Cancelling…" : "Cancel this job"}
              </button>
            </div>
          ) : null}
        </SideDrawer>
      ) : null}

      {filesOpen ? (
        <SideDrawer
          title="Processed Excel files"
          wide
          onClose={() => setFilesOpen(false)}
          subtitle="Finished jobs for your organization. Files stay here after you close the page."
        >
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
            {filesError ? (
              <p className="mb-2 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{filesError}</p>
            ) : null}
            {filesLoading && files.length === 0 ? (
              <p className="text-sm text-slate-500">Loading…</p>
            ) : processedFiles.length === 0 ? (
              <p className="text-sm text-slate-500">No processed Excel files yet.</p>
            ) : (
              <ul className="space-y-2.5">
                {processedFiles.map((item) => {
                  const itemBadge = jobBadge(item.status, item.production_ready);
                  const summary = item.summary ?? {};
                  const cost = item.cost_estimate ?? {};
                  const durationMs =
                    item.created_at && item.completed_at
                      ? Date.parse(item.completed_at) - Date.parse(item.created_at)
                      : NaN;
                  const facts: Array<[string, string]> = [
                    ["Language", languageName(item.target_language)],
                    ["Mode", (item.options?.qa_mode as string) === "foundry" ? "Foundry" : "Classic"],
                    ["Rows", item.total_records.toLocaleString()],
                    ["Started", formatTime(item.created_at)],
                    ["Finished", formatTime(item.completed_at)],
                    ["Duration", formatDuration(durationMs)],
                    [
                      "Translator characters",
                      cost.translator_characters_sent != null
                        ? Number(cost.translator_characters_sent).toLocaleString()
                        : "—",
                    ],
                    [
                      "Foundry revisions",
                      summary.corrected_records != null ? String(summary.corrected_records) : "—",
                    ],
                    [
                      "Open issues",
                      summary.unresolved_issues != null ? String(summary.unresolved_issues) : "—",
                    ],
                  ];
                  return (
                    <li key={item.id} className="rounded-xl border border-slate-200 p-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-slate-950">
                            Goals_{item.target_language}_{item.production_ready ? "PRODUCTION" : "NOT_PRODUCTION_READY"}.xlsx
                          </p>
                          <p className="truncate text-[11px] text-slate-500">
                            From {item.source_filename} · Job {item.id.slice(0, 8)}
                          </p>
                        </div>
                        <span
                          className={`inline-flex shrink-0 items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ${itemBadge.className}`}
                        >
                          {itemBadge.label}
                        </span>
                      </div>
                      <dl className="mt-2 grid grid-cols-3 gap-x-3 gap-y-1">
                        {facts.map(([label, value]) => (
                          <div key={label} className="min-w-0">
                            <dt className="text-[10px] uppercase tracking-wide text-slate-400">{label}</dt>
                            <dd className="truncate text-xs text-slate-800">{value}</dd>
                          </div>
                        ))}
                      </dl>
                      <div className="mt-2.5 flex flex-wrap gap-1.5">
                        <a
                          className={`tm-btn !px-2.5 !py-1.5 text-xs ${item.production_ready ? "tm-btn-primary" : "tm-btn-secondary"}`}
                          href={jobFileUrl(item.id, "download")}
                        >
                          Download Excel
                        </a>
                        {item.has_report ? (
                          <a className="tm-btn tm-btn-secondary !px-2.5 !py-1.5 text-xs" href={jobFileUrl(item.id, "report")}>
                            QA report
                          </a>
                        ) : null}
                        <button
                          type="button"
                          className="tm-btn tm-btn-ghost !px-2.5 !py-1.5 text-xs"
                          onClick={() => void openJob(item.id)}
                        >
                          Show details
                        </button>
                        <button
                          type="button"
                          className="tm-btn tm-btn-ghost !px-2.5 !py-1.5 text-xs"
                          onClick={() => void openJob(item.id, true)}
                        >
                          Logs
                        </button>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </SideDrawer>
      ) : null}

      {promptOpen ? (
        <div className="fixed inset-0 z-40 flex justify-end">
          <button
            type="button"
            className="absolute inset-0 bg-slate-900/30"
            aria-label="Close prompt editor"
            onClick={() => setPromptOpen(false)}
          />
          <aside className="relative flex h-full w-full max-w-md flex-col border-l border-slate-200 bg-white shadow-xl">
            <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-4 py-3">
              <div>
                <h2 className="text-base font-bold text-slate-950">Foundry prompt</h2>
                <p className="mt-1 text-xs text-slate-500">
                  Used when Foundry is on. It revises Goal, Description, and KRA only where the meaning differs from the English.
                </p>
              </div>
              <button
                type="button"
                className="rounded-lg px-2 py-1 text-sm text-slate-500 hover:bg-slate-100"
                onClick={() => setPromptOpen(false)}
              >
                Close
              </button>
            </div>
            <div className="flex min-h-0 flex-1 flex-col gap-3 p-4">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                {promptCustomized ? "Custom prompt" : "Built-in prompt"}
              </p>
              <textarea
                value={promptText}
                onChange={(event) => {
                  setPromptText(event.target.value);
                  setPromptNote(null);
                  setPromptNoteOk(false);
                }}
                className="min-h-0 flex-1 resize-none rounded-xl border border-slate-200 px-3 py-2 font-mono text-xs leading-5 outline-none focus:border-indigo-400"
                spellCheck={false}
              />
              <p className="text-[11px] text-slate-400">{promptText.length.toLocaleString()} / 200,000 characters</p>
              {promptNote ? (
                <p
                  role="status"
                  className={`rounded-lg px-3 py-2 text-sm font-medium ${
                    promptNoteOk
                      ? "border border-emerald-200 bg-emerald-50 text-emerald-800"
                      : "border border-rose-200 bg-rose-50 text-rose-700"
                  }`}
                >
                  {promptNote}
                </p>
              ) : null}
              <div className="flex gap-2">
                <button
                  type="button"
                  className="tm-btn tm-btn-primary !px-3 !py-2 text-sm"
                  disabled={promptBusy || !promptText.trim()}
                  onClick={() => void savePrompt(promptText, "save")}
                >
                  {promptBusy ? "Saving…" : "Save"}
                </button>
                <button
                  type="button"
                  className="tm-btn tm-btn-secondary !px-3 !py-2 text-sm"
                  disabled={promptBusy}
                  onClick={() => void savePrompt(promptDefault, "reset")}
                >
                  Reset
                </button>
              </div>
            </div>
          </aside>
        </div>
      ) : null}
    </AppShell>
  );
}
