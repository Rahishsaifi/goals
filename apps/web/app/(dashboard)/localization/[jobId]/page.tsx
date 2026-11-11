"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { AppShell } from "@/components/AppShell";
import { WorkerQueueBanner, useWorkerQueue } from "@/components/localization/WorkerQueueBanner";
import { DownloadButton } from "@/components/localization/DownloadButton";
import {
  ExcelFileIcon,
  ExcelIcon,
  IssueRowsIcon,
  LogsIcon,
  ReportIcon,
} from "@/components/localization/icons";
import { API_BASE, readApiError } from "@/lib/api";
import {
  BADGE_TONE_CLASS,
  STAGE_LABELS,
  STAGE_ORDER,
  TERMINAL,
  formatDateTime,
  formatDuration,
  jobBadge,
  jobDurationMs,
  jobFileUrl,
  outputFilename,
  useLanguageNames,
  useSessionInfo,
  type LocalizationJob,
  type StageInfo,
} from "@/lib/localization";

type JobEvent = { at: string; level: string; message: string };

const MILESTONES: { label: string; stages: string[] }[] = [
  { label: "File Validation", stages: ["file_validation"] },
  { label: "Data Extraction", stages: ["english_extraction", "record_reconciliation"] },
  { label: "Translation", stages: ["translation"] },
  { label: "Semantic QA", stages: ["semantic_qa", "automatic_correction"] },
  { label: "Technical Validation", stages: ["technical_validation", "special_category_validation"] },
  { label: "Excel Reconstruction", stages: ["excel_reconstruction"] },
  { label: "Final Hard Gate", stages: ["final_hard_gate"] },
];

const LOG_DOT: Record<string, string> = {
  info: "bg-slate-400",
  success: "bg-emerald-500",
  warning: "bg-amber-500",
  error: "bg-rose-500",
};

type StepState = "done" | "active" | "warning" | "failed" | "pending";

function stageState(info: StageInfo | undefined): StepState {
  const status = info?.status ?? "pending";
  if (status === "completed") return "done";
  if (status === "running" || status === "queued") return "active";
  if (status === "failed" || status === "cancelled") return "failed";
  return "pending";
}

function StepCircle({ state }: { state: StepState }) {
  const base = "grid h-5 w-5 shrink-0 place-items-center rounded-full text-[10px] font-bold";
  if (state === "done") return <span className={`${base} bg-emerald-500 text-white`}>✓</span>;
  if (state === "warning") return <span className={`${base} bg-amber-400 text-white`}>!</span>;
  if (state === "failed") return <span className={`${base} bg-rose-500 text-white`}>✕</span>;
  if (state === "active")
    return (
      <span className={`${base} border-2 border-indigo-500 bg-white`}>
        <span className="h-2 w-2 animate-pulse rounded-full bg-indigo-500" />
      </span>
    );
  return <span className={`${base} border-2 border-slate-300 bg-white`} />;
}

function Stat({ icon, value, label, tone }: { icon: string; value: string; label: string; tone: string }) {
  return (
    <div className="flex min-w-0 items-center gap-2.5 px-4 py-1">
      <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-full text-sm ${tone}`}>{icon}</span>
      <div className="min-w-0 leading-tight">
        <p className="truncate text-base font-bold tabular-nums text-slate-950">{value}</p>
        <p className="text-[11px] text-slate-500">{label}</p>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <p className="text-xs text-slate-500">{label}</p>
      <div className="mt-0.5 text-lg font-bold tabular-nums text-slate-950">{value}</div>
    </div>
  );
}

function PassFail({ value }: { value: unknown }) {
  if (value == null) return <span className="text-slate-400">—</span>;
  return value ? (
    <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-sm font-bold text-emerald-700">PASS</span>
  ) : (
    <span className="rounded bg-rose-100 px-1.5 py-0.5 text-sm font-bold text-rose-700">FAIL</span>
  );
}

function asNumber(value: unknown): number | null {
  const num = typeof value === "number" ? value : Number(value);
  return value == null || value === "" || Number.isNaN(num) ? null : num;
}

export default function LocalizationJobDetailPage() {
  const params = useParams<{ jobId: string }>();
  const jobId = params.jobId;
  const session = useSessionInfo(`/localization/${jobId}`);
  const languageNames = useLanguageNames();
  const [job, setJob] = useState<LocalizationJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [logsOpen, setLogsOpen] = useState(false);
  const logsRef = useRef<HTMLElement | null>(null);

  function toggleLogs() {
    setLogsOpen((open) => !open);
  }

  useEffect(() => {
    if (!logsOpen) return;
    const id = window.setTimeout(() => logsRef.current?.scrollIntoView({ block: "start" }), 50);
    return () => window.clearTimeout(id);
  }, [logsOpen]);
  const [events, setEvents] = useState<JobEvent[]>([]);

  const terminal = job ? TERMINAL.has(job.status.toUpperCase()) : false;
  const { queue, refresh: refreshQueue } = useWorkerQueue();

  const loadJob = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/goals-localization/jobs/${jobId}`, {
        credentials: "include",
      });
      if (!response.ok) throw new Error(await readApiError(response, "Could not load this job."));
      const body = await response.json();
      setJob((body.job ?? body) as LocalizationJob);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load this job.");
    }
  }, [jobId]);

  useEffect(() => {
    void loadJob();
    if (terminal) return;
    const timer = window.setInterval(() => void loadJob(), 3000);
    return () => window.clearInterval(timer);
  }, [loadJob, terminal]);

  useEffect(() => {
    if (terminal) return;
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [terminal]);

  useEffect(() => {
    if (!logsOpen) return;
    const load = () =>
      void fetch(`${API_BASE}/api/v1/goals-localization/jobs/${jobId}/logs`, { credentials: "include" })
        .then((response) => (response.ok ? response.json() : null))
        .then((body) => {
          if (body) setEvents((body.events ?? []) as JobEvent[]);
        });
    load();
    if (terminal) return;
    const timer = window.setInterval(load, 3000);
    return () => window.clearInterval(timer);
  }, [logsOpen, jobId, terminal]);

  const stages = job?.stages?.length ? job.stages : STAGE_ORDER;
  const progress = useMemo(() => job?.stage_progress ?? {}, [job?.stage_progress]);
  const completedCount = stages.filter((stage) => progress[stage]?.status === "completed").length;
  const progressPct = Math.round((completedCount / Math.max(stages.length, 1)) * 100);
  const gateFailed = Boolean(job && terminal && !job.production_ready && progress.final_hard_gate?.status === "completed");

  const milestones = useMemo(
    () =>
      MILESTONES.map((milestone) => {
        const states = milestone.stages.map((stage) => stageState(progress[stage]));
        let state: StepState = "pending";
        if (states.some((s) => s === "failed")) state = "failed";
        else if (states.some((s) => s === "active")) state = "active";
        else if (states.every((s) => s === "done")) state = "done";
        else if (states.some((s) => s === "done")) state = "active";
        if (milestone.label === "Final Hard Gate" && gateFailed) state = "warning";
        return { ...milestone, state };
      }),
    [progress, gateFailed],
  );

  const summary = job?.summary ?? {};
  const badge = job ? jobBadge(job) : null;
  const languageName = job ? (languageNames[job.target_language] ?? job.target_language) : "";
  const mode = (job?.options?.qa_mode as string) === "foundry" ? "Foundry" : "Classic";
  const totalTime = job ? formatDuration(jobDurationMs(job, nowMs)) : "—";
  const mismatches =
    (asNumber(summary.numeric_discrepancies) ?? 0) + (asNumber(summary.percentage_discrepancies) ?? 0);

  return (
    <AppShell email={session.email} role={session.role} orgName={session.orgName}>
      <div className="mb-5 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-start gap-3">
          <Link
            href="/localization"
            className="mt-1 grid h-9 w-9 place-items-center rounded-xl border border-slate-200 bg-white text-slate-600 transition hover:bg-slate-50"
            aria-label="Back to localization jobs"
          >
            ←
          </Link>
          <div>
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-2xl font-bold tracking-tight text-slate-950">Job {jobId.slice(0, 8)}</h1>
              {badge ? (
                <span className={`rounded-full px-3 py-0.5 text-sm font-medium ring-1 ${BADGE_TONE_CLASS[badge.tone]}`}>
                  {badge.label}
                </span>
              ) : null}
            </div>
            {job ? (
              <p className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-600">
                <span className="flex items-center gap-1.5">
                  <ExcelFileIcon className="h-5 w-5" />
                  {outputFilename(job)}
                </span>
                <span>🌐 {languageName}</span>
                <span>▦ {job.total_records.toLocaleString()} rows</span>
              </p>
            ) : null}
          </div>
        </div>
        {job ? (
          <div className="flex flex-wrap items-center gap-2">
            {!terminal ? (
              <span className="inline-flex items-center gap-2 rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white">
                <span className="h-2 w-2 animate-pulse rounded-full bg-white" /> In Progress
              </span>
            ) : null}
            <button
              type="button"
              className={`inline-flex items-center gap-2 rounded-xl border px-4 py-2 text-sm font-semibold transition ${
                logsOpen
                  ? "border-slate-800 bg-slate-800 text-white hover:bg-slate-900"
                  : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
              }`}
              onClick={toggleLogs}
            >
              <LogsIcon />
              {logsOpen ? "Hide Logs" : "Logs"}
            </button>
            {job.has_report ? (
              <DownloadButton
                href={jobFileUrl(job.id, "report")}
                icon={<ReportIcon />}
                label="Download QA Report"
                className="border border-indigo-200 bg-indigo-50 text-indigo-700 hover:bg-indigo-100"
              />
            ) : null}
            {job.has_output ? (
              <DownloadButton
                href={jobFileUrl(job.id, "download")}
                icon={<ExcelIcon />}
                label="Download Excel File"
                className="bg-emerald-600 text-white shadow-sm hover:bg-emerald-700"
              />
            ) : null}
            {job.has_output && badge?.label === "Needs Review" ? (
              <DownloadButton
                href={jobFileUrl(job.id, "issue-rows")}
                icon={<IssueRowsIcon />}
                label="Download Issue Rows"
                className="bg-yellow-400 text-yellow-950 shadow-sm hover:bg-yellow-500"
              />
            ) : null}
          </div>
        ) : null}
      </div>

      <WorkerQueueBanner
        queue={queue}
        onChanged={async () => {
          await refreshQueue();
          await loadJob();
        }}
        className="mb-4"
      />

      {error ? <p className="mb-4 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p> : null}
      {job?.error_message && ["FAILED", "CANCELLED"].includes(job.status.toUpperCase()) ? (
        <p className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
          {job.error_message}
        </p>
      ) : null}

      {!job && !error ? <p className="text-sm text-slate-500">Loading job…</p> : null}

      {job ? (
        <>
          <section className="tm-card mb-4 px-2 py-3">
            <div className="grid grid-cols-2 divide-slate-100 sm:grid-cols-5 sm:divide-x">
              <Stat icon="▤" value={job.total_records.toLocaleString()} label="Total Rows" tone="bg-indigo-50 text-indigo-600" />
              <Stat
                icon="✓"
                value={(job.processed_records ?? 0).toLocaleString()}
                label="Processed"
                tone="bg-emerald-50 text-emerald-600"
              />
              <Stat icon="◷" value={totalTime} label={terminal ? "Total Time" : "Elapsed"} tone="bg-indigo-50 text-indigo-600" />
              <Stat
                icon="✎"
                value={asNumber(summary.corrected_records)?.toLocaleString() ?? "—"}
                label="Fields Revised"
                tone="bg-violet-50 text-violet-600"
              />
              <Stat
                icon="⚗"
                value={asNumber(summary.unresolved_issues)?.toLocaleString() ?? "—"}
                label="Open Issues"
                tone="bg-violet-50 text-violet-600"
              />
            </div>

            <div className="mx-4 mt-3 border-t border-slate-100 pt-3">
              <div className="mb-2.5 flex items-center gap-3">
                <span className="text-xs font-semibold text-slate-700">Progress</span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className="tm-bar relative h-full overflow-hidden rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-[width] duration-700 ease-out"
                    style={{ width: `${terminal ? progressPct : Math.max(progressPct, 4)}%` }}
                  >
                    {!terminal ? <span className="tm-stripes absolute inset-0" /> : null}
                  </div>
                </div>
                <span className="text-xs font-semibold tabular-nums text-slate-800">{progressPct}%</span>
              </div>
              <ol className="flex items-start">
                {milestones.map((milestone, index) => (
                  <li key={milestone.label} className="relative flex flex-1 flex-col items-center text-center">
                    {index > 0 ? (
                      <span
                        className={`absolute right-1/2 top-2.5 h-0.5 w-full -translate-y-1/2 ${
                          milestone.state === "pending" ? "bg-slate-200" : "bg-indigo-200"
                        }`}
                      />
                    ) : null}
                    <span className="relative z-10">
                      <StepCircle state={milestone.state} />
                    </span>
                    <span
                      className={`mt-1 px-1 text-[11px] leading-tight ${
                        milestone.state === "pending" ? "text-slate-400" : "font-medium text-slate-700"
                      }`}
                    >
                      {milestone.label}
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          </section>

          <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
            <section className="tm-card overflow-hidden">
              <h2 className="px-5 pt-4 text-lg font-semibold text-slate-950">Process Details</h2>
              <div className="overflow-x-auto px-5 pb-4 pt-3">
                <table className="w-full min-w-[560px] text-sm">
                  <thead>
                    <tr className="border-b border-slate-100 text-left text-xs font-semibold text-slate-600">
                      <th className="py-2 pr-3">Step</th>
                      <th className="py-2 pr-3">Details</th>
                      <th className="py-2 pr-4 text-right">Duration</th>
                      <th className="py-2 text-right">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {stages.map((stage, index) => {
                      const info = progress[stage];
                      const state = stageState(info);
                      // Jobs from before per-step start times were recorded: steps run in
                      // order, so the previous step's finish is this step's start.
                      const previousEnd = index > 0 ? progress[stages[index - 1]]?.updated_at : undefined;
                      const startSource = info?.started_at ?? previousEnd;
                      const started = startSource ? Date.parse(startSource) : NaN;
                      const rawDurationMs =
                        state === "active" && !terminal
                          ? Math.max(0, nowMs - started)
                          : info?.updated_at
                            ? Date.parse(info.updated_at) - started
                            : NaN;
                      const durationMs = rawDurationMs >= 0 ? rawDurationMs : NaN;
                      const warn = stage === "final_hard_gate" && gateFailed;
                      const pill =
                        state === "done"
                          ? warn
                            ? "bg-amber-50 text-amber-800"
                            : "bg-emerald-50 text-emerald-700"
                          : state === "active"
                            ? "bg-indigo-50 text-indigo-700"
                            : state === "failed"
                              ? "bg-rose-50 text-rose-700"
                              : "bg-slate-100 text-slate-500";
                      const pillLabel =
                        state === "done"
                          ? warn
                            ? "Not passed"
                            : "Completed"
                          : state === "active"
                            ? "In Progress"
                            : state === "failed"
                              ? info?.status === "cancelled"
                                ? "Cancelled"
                                : "Failed"
                              : "Pending";
                      return (
                        <tr key={stage} className="border-b border-slate-50 last:border-0">
                          <td className="py-2.5 pr-3">
                            <span className="flex items-center gap-2.5">
                              <StepCircle state={warn ? "warning" : state} />
                              <span className={state === "pending" ? "text-slate-400" : "text-slate-800"}>
                                {STAGE_LABELS[stage] ?? stage.replaceAll("_", " ")}
                              </span>
                            </span>
                          </td>
                          <td className="max-w-[280px] truncate py-2.5 pr-3 text-slate-600" title={info?.detail ?? ""}>
                            {info?.detail || "—"}
                          </td>
                          <td className="whitespace-nowrap py-2.5 pr-4 text-right tabular-nums text-slate-700">
                            {state !== "pending" && Number.isFinite(durationMs) ? formatDuration(durationMs) : "—"}
                          </td>
                          <td className="py-2.5 text-right">
                            <span className={`whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-medium ${pill}`}>
                              {pillLabel}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>

            <div className="space-y-5">
              <section className="tm-card px-5 py-4">
                <h2 className="mb-3 text-lg font-semibold text-slate-950">Job Information</h2>
                <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
                  <dt className="text-slate-500">Source file</dt>
                  <dd className="truncate font-medium text-slate-900" title={job.source_filename}>
                    {job.source_filename}
                  </dd>
                  <dt className="text-slate-500">Source Language</dt>
                  <dd className="font-medium text-slate-900">English</dd>
                  <dt className="text-slate-500">Target Language</dt>
                  <dd className="font-medium text-slate-900">{languageName}</dd>
                  <dt className="text-slate-500">Mode</dt>
                  <dd className="font-medium text-slate-900">{mode}</dd>
                  <dt className="text-slate-500">Started</dt>
                  <dd className="font-medium text-slate-900">{formatDateTime(job.created_at)}</dd>
                  <dt className="text-slate-500">Finished</dt>
                  <dd className="font-medium text-slate-900">{terminal ? formatDateTime(job.completed_at) : "—"}</dd>
                  <dt className="text-slate-500">Duration</dt>
                  <dd className="font-medium text-slate-900">{totalTime}</dd>
                </dl>
              </section>

              <section className="tm-card px-5 py-4">
                <div className="mb-3 flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-slate-950">QA Summary</h2>
                  {job.has_report ? (
                    <a
                      href={jobFileUrl(job.id, "report")}
                      className="text-sm font-semibold text-indigo-600 hover:text-indigo-800"
                    >
                      View Full Report →
                    </a>
                  ) : null}
                </div>
                <div className="grid grid-cols-3 gap-4">
                  <Metric label="Source rows" value={asNumber(summary.source_record_count)?.toLocaleString() ?? "—"} />
                  <Metric label="Output rows" value={asNumber(summary.output_record_count)?.toLocaleString() ?? "—"} />
                  <Metric label="Unmatched" value={asNumber(summary.unmatched_records) ?? "—"} />
                  <Metric label="Numeric / % mismatches" value={terminal ? mismatches : "—"} />
                  <Metric label="Suspicious text" value={asNumber(summary.unresolved_untranslated_english) ?? "—"} />
                  <Metric label="Terminology issues" value={asNumber(summary.unresolved_terminology_issues) ?? "—"} />
                  <Metric label="Hotel Revenue QA" value={<PassFail value={summary.hotel_revenue_growth_qa_pass} />} />
                  <Metric
                    label="Operational QA"
                    value={<PassFail value={summary.operational_productivity_qa_pass} />}
                  />
                  <Metric label="Hard gate" value={terminal ? <PassFail value={job.production_ready} /> : "—"} />
                </div>
              </section>
            </div>
          </div>

          {logsOpen ? (
            <section ref={logsRef} className="tm-card mt-5 scroll-mt-20 px-5 py-4">
              <h2 className="mb-3 text-lg font-semibold text-slate-950">Runtime Logs</h2>
              <ol className="max-h-96 space-y-1.5 overflow-y-auto font-mono text-xs">
                {events.length ? (
                  events.map((event, index) => (
                    <li key={`${event.at}-${index}`} className="flex gap-2">
                      <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${LOG_DOT[event.level] ?? "bg-slate-400"}`} />
                      <span className="shrink-0 text-slate-400">
                        {event.at ? new Date(event.at).toLocaleTimeString() : ""}
                      </span>
                      <span className="text-slate-700">{event.message}</span>
                    </li>
                  ))
                ) : (
                  <li className="text-slate-400">No log entries yet.</li>
                )}
              </ol>
            </section>
          ) : null}
        </>
      ) : null}
    </AppShell>
  );
}
