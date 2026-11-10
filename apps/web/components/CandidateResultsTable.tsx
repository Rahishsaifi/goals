"use client";

import { useMemo, useState } from "react";

import { ScoreReport, type ScoreBreakdownItem } from "@/components/ScoreReport";
import { SideDrawer } from "@/components/SideDrawer";
import { openResultsPdf } from "@/lib/export-results-pdf";
import { formatStatus } from "@/lib/format";

function formatEta(seconds: number | null | undefined): string | null {
  if (seconds == null || Number.isNaN(seconds) || seconds <= 0) return null;
  if (seconds < 60) return `~${Math.max(1, Math.round(seconds))}s left`;
  const minutes = Math.ceil(seconds / 60);
  if (minutes < 60) return `~${minutes}m left`;
  return `~${Math.ceil(minutes / 60)}h left`;
}

function isActiveRun(status: string | undefined): boolean {
  if (!status) return false;
  return !["completed", "completed_with_warnings", "cancelled", "failed"].includes(status);
}

export type CandidateResult = {
  id: string;
  resume_id: string;
  candidate_label: string | null;
  overall_score: string;
  mandatory_status: string;
  review_required: boolean;
  score_breakdown?: ScoreBreakdownItem[];
};

type ScoreBand = "all" | "strong" | "good" | "partial" | "weak";
type MandatoryFilter = "all" | "satisfied" | "not_satisfied" | "unknown";
type ReviewFilter = "all" | "required" | "clear";

const PAGE_SIZE = 50;

function scoreOf(row: CandidateResult): number {
  const value = Math.round(Number(row.overall_score));
  return Number.isNaN(value) ? -1 : value;
}

function bandOf(score: number): Exclude<ScoreBand, "all"> {
  if (score >= 80) return "strong";
  if (score >= 60) return "good";
  if (score >= 40) return "partial";
  return "weak";
}

function bandLabel(band: Exclude<ScoreBand, "all">): string {
  if (band === "strong") return "Strong";
  if (band === "good") return "Good";
  if (band === "partial") return "Partial";
  return "Weak";
}

function bandClass(band: Exclude<ScoreBand, "all">): string {
  if (band === "strong") return "text-emerald-700";
  if (band === "good") return "text-indigo-700";
  if (band === "partial") return "text-amber-700";
  return "text-rose-700";
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return `${parts[0]!.slice(0, 1)}${parts[1]!.slice(0, 1)}`.toUpperCase();
}

export function CandidateResultsTable({
  jobTitle,
  provider,
  results,
  busy,
  onExportCsv,
  runStatus,
  selectedCount,
  scoredCount,
  etaSeconds,
}: {
  jobTitle: string;
  provider?: string;
  results: CandidateResult[];
  busy?: boolean;
  onExportCsv: () => void;
  runStatus?: string;
  selectedCount?: number;
  scoredCount?: number;
  etaSeconds?: number | null;
}) {
  const [query, setQuery] = useState("");
  const [scoreBand, setScoreBand] = useState<ScoreBand>("all");
  const [mandatory, setMandatory] = useState<MandatoryFilter>("all");
  const [review, setReview] = useState<ReviewFilter>("all");
  const [page, setPage] = useState(1);
  const [reportId, setReportId] = useState<string | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return results
      .map((row, index) => ({ row, rank: index + 1, score: scoreOf(row) }))
      .filter(({ row, score }) => {
        if (q) {
          const name = (row.candidate_label ?? "").toLowerCase();
          const hay = `${name} ${row.resume_id.toLowerCase()} ${row.mandatory_status}`;
          if (!hay.includes(q)) return false;
        }
        if (scoreBand !== "all" && bandOf(Math.max(score, 0)) !== scoreBand) return false;
        if (mandatory !== "all" && row.mandatory_status.toLowerCase() !== mandatory) return false;
        if (review === "required" && !row.review_required) return false;
        if (review === "clear" && row.review_required) return false;
        return true;
      });
  }, [results, query, scoreBand, mandatory, review]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount);
  const pageRows = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);
  const selectedReport = results.find((row) => row.id === reportId) ?? null;
  const runActive = isActiveRun(runStatus);
  const targetCount = Math.max(selectedCount ?? 0, scoredCount ?? results.length, 1);
  const doneCount = Math.max(scoredCount ?? results.length, results.length);
  const progressPct = runActive
    ? Math.min(95, Math.round((doneCount / targetCount) * 100))
    : 100;
  const etaLabel = formatEta(etaSeconds);

  function resetPage() {
    setPage(1);
  }

  function exportPdf(detailed: boolean) {
    setExportError(null);
    setExportOpen(false);
    try {
      openResultsPdf({
        jobTitle,
        provider,
        rows: filtered.map((item) => item.row),
        detailed,
      });
    } catch (err) {
      setExportError(err instanceof Error ? err.message : "PDF export failed.");
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {runActive ? (
        <div className="border-b border-amber-100 bg-amber-50 px-5 py-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-sm text-amber-950">
              <span className="tm-status-spin text-amber-600" aria-hidden>
                <svg viewBox="0 0 16 16" fill="none" className="h-3.5 w-3.5">
                  <circle
                    cx="8"
                    cy="8"
                    r="6"
                    stroke="currentColor"
                    strokeOpacity="0.25"
                    strokeWidth="2"
                  />
                  <path
                    d="M14 8a6 6 0 0 0-6-6"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                  />
                </svg>
              </span>
              <div>
                <p className="font-semibold">
                  Matching {formatStatus(runStatus ?? "queued")}
                </p>
                <p className="text-xs text-amber-800/80">
                  {doneCount} of {targetCount} candidates scored
                  {etaLabel ? ` · ${etaLabel}` : ""}
                  {provider ? ` · ${provider}` : ""}
                </p>
              </div>
            </div>
            <span className="text-sm font-bold text-amber-900">{progressPct}%</span>
          </div>
          <div className="mt-2.5 h-2 overflow-hidden rounded-full bg-amber-100">
            <div
              className="h-full rounded-full bg-amber-500 transition-all duration-500"
              style={{ width: `${Math.max(8, progressPct)}%` }}
            />
          </div>
        </div>
      ) : null}

      <div className="space-y-3 border-b border-slate-100 px-5 py-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="min-w-[12rem] flex-1 text-sm font-semibold text-slate-700">
            Search
            <input
              className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-normal outline-none focus:border-indigo-400"
              placeholder="Name, resume id, mandatory…"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                resetPage();
              }}
            />
          </label>
          <label className="text-sm font-semibold text-slate-700">
            Score
            <select
              className="mt-1.5 block rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-normal"
              value={scoreBand}
              onChange={(event) => {
                setScoreBand(event.target.value as ScoreBand);
                resetPage();
              }}
            >
              <option value="all">All scores</option>
              <option value="strong">Strong (80+)</option>
              <option value="good">Good (60–79)</option>
              <option value="partial">Partial (40–59)</option>
              <option value="weak">Weak (&lt;40)</option>
            </select>
          </label>
          <label className="text-sm font-semibold text-slate-700">
            Mandatory
            <select
              className="mt-1.5 block rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-normal"
              value={mandatory}
              onChange={(event) => {
                setMandatory(event.target.value as MandatoryFilter);
                resetPage();
              }}
            >
              <option value="all">All</option>
              <option value="satisfied">Satisfied</option>
              <option value="not_satisfied">Not satisfied</option>
              <option value="unknown">Unknown</option>
            </select>
          </label>
          <label className="text-sm font-semibold text-slate-700">
            Review
            <select
              className="mt-1.5 block rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-normal"
              value={review}
              onChange={(event) => {
                setReview(event.target.value as ReviewFilter);
                resetPage();
              }}
            >
              <option value="all">All</option>
              <option value="required">Review required</option>
              <option value="clear">No review flag</option>
            </select>
          </label>
          <div className="relative self-end">
            <button
              type="button"
              className="tm-btn tm-btn-primary inline-flex items-center gap-2 !px-3.5 !py-2.5 text-sm"
              disabled={busy || filtered.length === 0}
              aria-expanded={exportOpen}
              onClick={() => setExportOpen((value) => !value)}
            >
              <svg viewBox="0 0 20 20" fill="none" className="h-4 w-4" aria-hidden>
                <path
                  d="M10 3v9m0 0 3.5-3.5M10 12 6.5 8.5"
                  stroke="currentColor"
                  strokeWidth="1.75"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M4 14.5V16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-1.5"
                  stroke="currentColor"
                  strokeWidth="1.75"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              Export
              <svg viewBox="0 0 12 12" fill="none" className="h-3 w-3 opacity-90" aria-hidden>
                <path
                  d="M3 4.5 6 7.5 9 4.5"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
            {exportOpen ? (
              <div className="absolute right-0 z-20 mt-2 w-60 overflow-hidden rounded-xl border border-slate-200 bg-white py-1 shadow-lg">
                <button
                  type="button"
                  className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-sm hover:bg-indigo-50"
                  onClick={() => {
                    setExportOpen(false);
                    onExportCsv();
                  }}
                >
                  <span className="grid h-7 w-7 place-items-center rounded-lg bg-slate-100 text-[10px] font-bold text-slate-600">
                    CSV
                  </span>
                  Export CSV
                </button>
                <button
                  type="button"
                  className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-sm hover:bg-indigo-50"
                  onClick={() => exportPdf(false)}
                >
                  <span className="grid h-7 w-7 place-items-center rounded-lg bg-indigo-50 text-[10px] font-bold text-indigo-700">
                    PDF
                  </span>
                  Export PDF
                </button>
                <button
                  type="button"
                  className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-sm hover:bg-indigo-50"
                  onClick={() => exportPdf(true)}
                >
                  <span className="grid h-7 w-7 place-items-center rounded-lg bg-indigo-50 text-[10px] font-bold text-indigo-700">
                    PDF
                  </span>
                  Export PDF with details
                </button>
              </div>
            ) : null}
          </div>
        </div>
        <p className="text-xs text-slate-500">
          Showing {filtered.length} of {results.length} candidates
          {filtered.length !== results.length ? " (filtered)" : ""}
        </p>
        {exportError ? <p className="text-sm text-rose-600">{exportError}</p> : null}
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {results.length === 0 ? (
          <div className="px-5 py-10 text-center">
            {runActive ? (
              <>
                <div className="mx-auto mb-3 grid h-12 w-12 place-items-center rounded-2xl bg-amber-100 text-amber-700">
                  <span className="tm-status-spin" aria-hidden>
                    <svg viewBox="0 0 16 16" fill="none" className="h-5 w-5">
                      <circle
                        cx="8"
                        cy="8"
                        r="6"
                        stroke="currentColor"
                        strokeOpacity="0.25"
                        strokeWidth="2"
                      />
                      <path
                        d="M14 8a6 6 0 0 0-6-6"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                      />
                    </svg>
                  </span>
                </div>
                <p className="text-sm font-semibold text-slate-900">
                  Scoring in progress…
                </p>
                <p className="mx-auto mt-1 max-w-sm text-sm text-slate-500">
                  Results will appear here as candidates finish. You can leave this
                  panel open — it updates automatically.
                </p>
              </>
            ) : (
              <p className="text-sm text-slate-500">
                No scored candidates. Ensure resumes are in ready status before matching.
              </p>
            )}
          </div>
        ) : filtered.length === 0 ? (
          <p className="px-5 py-8 text-sm text-slate-500">No candidates match these filters.</p>
        ) : (
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="sticky top-0 bg-slate-50 text-slate-500">
              <tr>
                <th className="px-4 py-3 font-semibold">#</th>
                <th className="px-4 py-3 font-semibold">Candidate</th>
                <th className="px-4 py-3 font-semibold">Score</th>
                <th className="px-4 py-3 font-semibold">Mandatory</th>
                <th className="px-4 py-3 font-semibold">Review</th>
                <th className="px-4 py-3 text-right font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map(({ row, rank, score }) => {
                const name = row.candidate_label?.trim() || `Candidate ${row.resume_id.slice(0, 8)}`;
                const open = reportId === row.id;
                const band = bandOf(Math.max(score, 0));
                return (
                  <tr
                    key={row.id}
                    className={`border-t border-slate-100 hover:bg-slate-50/80 ${
                      open ? "bg-indigo-50/40" : ""
                    }`}
                  >
                    <td className="px-4 py-3 text-slate-500">{rank}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-slate-100 text-xs font-bold text-slate-700">
                          {initials(name)}
                        </span>
                        <div className="min-w-0">
                          <p className="truncate font-semibold text-slate-900">{name}</p>
                          <p className="font-mono text-[11px] text-slate-400">
                            {row.resume_id.slice(0, 8)}…
                          </p>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <p className={`text-base font-bold ${bandClass(band)}`}>
                        {score < 0 ? "—" : `${score}%`}
                      </p>
                      <p className="text-[11px] text-slate-500">{bandLabel(band)}</p>
                      <div
                        className={`mt-1 h-1.5 w-24 overflow-hidden rounded-full bg-slate-100 ${bandClass(band)}`}
                      >
                        <div
                          className="h-full rounded-full bg-current opacity-70"
                          style={{ width: `${Math.max(0, score)}%` }}
                        />
                      </div>
                    </td>
                    <td className="px-4 py-3 capitalize text-slate-700">
                      {formatStatus(row.mandatory_status)}
                    </td>
                    <td className="px-4 py-3">
                      {row.review_required ? (
                        <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-800">
                          Required
                        </span>
                      ) : (
                        <span className="text-xs text-slate-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        type="button"
                        className="text-sm font-semibold text-indigo-600 hover:text-indigo-800"
                        onClick={() => setReportId(row.id)}
                      >
                        View report
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {filtered.length > PAGE_SIZE ? (
        <div className="flex items-center justify-between gap-3 border-t border-slate-100 px-5 py-3 text-sm">
          <p className="text-slate-500">
            Page {safePage} of {pageCount}
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              className="tm-btn tm-btn-secondary !px-3 !py-1.5 text-sm"
              disabled={safePage <= 1}
              onClick={() => setPage((value) => Math.max(1, value - 1))}
            >
              Previous
            </button>
            <button
              type="button"
              className="tm-btn tm-btn-secondary !px-3 !py-1.5 text-sm"
              disabled={safePage >= pageCount}
              onClick={() => setPage((value) => Math.min(pageCount, value + 1))}
            >
              Next
            </button>
          </div>
        </div>
      ) : null}

      <SideDrawer
        nested
        open={Boolean(selectedReport)}
        onClose={() => setReportId(null)}
        widthClassName="w-[min(96vw,40rem)]"
      >
        {selectedReport ? (
          <>
            <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
              <div className="min-w-0">
                <h2 className="truncate text-base font-bold text-slate-950">
                  {selectedReport.candidate_label?.trim() ||
                    `Candidate ${selectedReport.resume_id.slice(0, 8)}`}
                </h2>
                <p className="truncate text-xs text-slate-500">
                  {Math.round(Number(selectedReport.overall_score))}% · {jobTitle}
                </p>
              </div>
              <button
                type="button"
                className="tm-btn tm-btn-ghost !px-2 !py-1"
                onClick={() => setReportId(null)}
                aria-label="Close report"
              >
                ✕
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto px-3 py-3">
              <ScoreReport
                overallScore={Number(selectedReport.overall_score)}
                mandatoryStatus={selectedReport.mandatory_status}
                reviewRequired={selectedReport.review_required}
                breakdown={selectedReport.score_breakdown ?? []}
              />
            </div>
          </>
        ) : null}
      </SideDrawer>
    </div>
  );
}
