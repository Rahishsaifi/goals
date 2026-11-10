"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { CandidateResultsTable } from "@/components/CandidateResultsTable";
import { SideDrawer } from "@/components/SideDrawer";
import { StatusPill } from "@/components/StatusPill";
import { API_BASE, csrfToken, readApiError } from "@/lib/api";
import { formatPercent, formatStatus, relativeTime } from "@/lib/format";

type Job = { id: string; title: string; current_version_id?: string };
type ResumeOption = { id: string; status: string; candidate_label: string | null };
type Evaluation = {
  id: string;
  status: string;
  job_title: string;
  result_count: number;
  selected_count?: number;
  failure_count: number;
  top_match_score: string | null;
  created_at: string | null;
  model_provider: string;
  eta_seconds?: number | null;
};
type ScoreBreakdown = {
  key: string;
  display_name: string;
  description: string;
  weight: string;
  score: string;
  contribution: string;
  status: string;
  mandatory: boolean;
  passage: string | null;
  page_number: number | null;
};
type ResultRow = {
  id: string;
  resume_id: string;
  candidate_label: string | null;
  overall_score: string;
  mandatory_status: string;
  review_required: boolean;
  score_breakdown?: ScoreBreakdown[];
  scoring_formula?: string;
};

function EvaluationsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [orgName, setOrgName] = useState<string | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [readyResumes, setReadyResumes] = useState<ResumeOption[]>([]);
  const [selectedResumeIds, setSelectedResumeIds] = useState<string[]>([]);
  const [rows, setRows] = useState<Evaluation[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [results, setResults] = useState<ResultRow[]>([]);
  const [jobId, setJobId] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Evaluation | null>(null);

  async function loadReadyResumes() {
    const response = await fetch(`${API_BASE}/api/v1/resumes`, { credentials: "include" });
    if (!response.ok) {
      setReadyResumes([]);
      setSelectedResumeIds([]);
      return;
    }
    const items = ((await response.json()) as ResumeOption[]).filter(
      (item) => item.status === "ready",
    );
    setReadyResumes(items);
    setSelectedResumeIds(items.map((item) => item.id));
  }

  async function refreshList(): Promise<Evaluation[]> {
    const response = await fetch(`${API_BASE}/api/v1/evaluations`, { credentials: "include" });
    if (!response.ok) return [];
    const items = (await response.json()) as Evaluation[];
    setRows(items);
    return items;
  }

  function isRunActive(status: string) {
    return !["completed", "completed_with_warnings", "cancelled", "failed"].includes(status);
  }

  async function loadResults(runId: string) {
    setSelectedId(runId);
    const response = await fetch(`${API_BASE}/api/v1/evaluations/${runId}/results`, {
      credentials: "include",
    });
    if (response.ok) {
      setResults((await response.json()) as ResultRow[]);
    } else {
      setResults([]);
      setError("Unable to load matching results.");
    }
  }

  useEffect(() => {
    void fetch(`${API_BASE}/api/v1/auth/me`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((body) => {
        setEmail(body?.email ?? null);
        setRole(body?.memberships?.[0]?.role ?? null);
        setOrgName(body?.memberships?.[0]?.tenant_name ?? null);
      });
    void fetch(`${API_BASE}/api/v1/job-profiles`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then((items: Job[]) => {
        setJobs(items);
        if (items[0]) setJobId(items[0].id);
      });
    void loadReadyResumes();
    void refreshList();
  }, []);

  useEffect(() => {
    if (searchParams.get("new") === "1") {
      setShowForm(true);
      void loadReadyResumes();
    }
    const run = searchParams.get("run");
    if (run) {
      void loadResults(run);
    }
  }, [searchParams]);

  function toggleResume(id: string) {
    setSelectedResumeIds((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );
  }

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    if (!jobId) {
      setError("Select a job profile first.");
      return;
    }
    if (selectedResumeIds.length === 0) {
      setError("Select at least one ready resume to match.");
      return;
    }
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const response = await fetch(`${API_BASE}/api/v1/evaluations`, {
        method: "POST",
        credentials: "include",
        headers: {
          "content-type": "application/json",
          "x-csrf-token": csrfToken(),
        },
        body: JSON.stringify({ job_profile_id: jobId, resume_ids: selectedResumeIds }),
      });
      if (!response.ok) {
        setError(await readApiError(response, "Unable to start AI matching."));
        return;
      }
      const created = (await response.json()) as { id: string; status?: string };
      setShowForm(false);
      setMessage("AI matching started. Results will appear as scoring finishes.");
      router.replace(`/evaluations?run=${created.id}`);
      await refreshList();
      setSelectedId(created.id);
      setResults([]);
    } catch {
      setError("Cannot reach the API. Confirm it is running, then try again.");
    } finally {
      setBusy(false);
    }
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setBusy(true);
    setError(null);
    const response = await fetch(`${API_BASE}/api/v1/evaluations/${deleteTarget.id}`, {
      method: "DELETE",
      credentials: "include",
      headers: { "x-csrf-token": csrfToken() },
    });
    setBusy(false);
    if (!response.ok) {
      setError(await readApiError(response, "Unable to delete this matching run."));
      setDeleteTarget(null);
      return;
    }
    const removedId = deleteTarget.id;
    const title = deleteTarget.job_title;
    setDeleteTarget(null);
    setMessage(`Deleted matching run for “${title}”.`);
    if (selectedId === removedId) {
      setSelectedId(null);
      setResults([]);
      router.replace("/evaluations");
    }
    await refreshList();
  }

  async function onExport(runId: string) {
    setBusy(true);
    setError(null);
    const response = await fetch(`${API_BASE}/api/v1/evaluations/${runId}/export`, {
      method: "POST",
      credentials: "include",
      headers: { "x-csrf-token": csrfToken() },
    });
    setBusy(false);
    if (!response.ok) {
      setError("Export failed.");
      return;
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `ai-matching-${runId}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  const selected = rows.find((row) => row.id === selectedId) ?? null;

  function openPanel() {
    setShowForm(true);
    setError(null);
    void loadReadyResumes();
  }

  function closePanel() {
    setShowForm(false);
    setError(null);
    if (searchParams.get("new") === "1") {
      const run = searchParams.get("run");
      router.replace(run ? `/evaluations?run=${run}` : "/evaluations");
    }
  }

  function openReport(runId: string) {
    void loadResults(runId);
    router.replace(`/evaluations?run=${runId}`);
  }

  function closeReport() {
    setSelectedId(null);
    setResults([]);
    if (searchParams.get("run")) {
      router.replace("/evaluations");
    }
  }

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      const items = await refreshList();
      if (cancelled) return;
      const active = items.some((item) => isRunActive(item.status));
      if (selectedId) {
        const current = items.find((item) => item.id === selectedId);
        if (current) {
          if (isRunActive(current.status) || current.result_count > 0) {
            const response = await fetch(
              `${API_BASE}/api/v1/evaluations/${selectedId}/results`,
              { credentials: "include" },
            );
            if (!cancelled && response.ok) {
              setResults((await response.json()) as ResultRow[]);
            }
          }
          if (!isRunActive(current.status)) {
            setMessage((prev) => prev ?? "AI matching completed.");
          }
        }
      }
      if (!active && !selectedId) {
        return;
      }
    };
    const timer = window.setInterval(() => {
      void tick();
    }, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [selectedId]);

  return (
    <AppShell
      email={email}
      role={role}
      orgName={orgName}
      title="Run AI matching"
      action={
        <button type="button" className="tm-btn tm-btn-primary" onClick={openPanel}>
          New match
        </button>
      }
    >
      {message ? <p className="mb-4 text-sm text-emerald-700">{message}</p> : null}
      {error && !showForm ? <p className="mb-4 text-sm text-rose-600">{error}</p> : null}

      {rows.some((row) => isRunActive(row.status)) ? (
        <div className="mb-4 flex flex-wrap items-center gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
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
          <div className="min-w-0 flex-1">
            <p className="font-semibold">
              {
                rows.filter((row) => isRunActive(row.status)).length
              }{" "}
              matching{" "}
              {rows.filter((row) => isRunActive(row.status)).length === 1 ? "run" : "runs"}{" "}
              still in the queue or scoring
            </p>
            <p className="text-xs text-amber-800/80">
              {rows
                .filter((row) => isRunActive(row.status))
                .map((row) => {
                  const eta =
                    typeof row.eta_seconds === "number" && row.eta_seconds > 0
                      ? row.eta_seconds < 60
                        ? `~${Math.round(row.eta_seconds)}s`
                        : `~${Math.ceil(row.eta_seconds / 60)}m`
                      : null;
                  return `${row.job_title} (${formatStatus(row.status)}${eta ? `, ETA ${eta}` : ""})`;
                })
                .join(" · ")}
            </p>
          </div>
        </div>
      ) : null}

      <div className="tm-card overflow-hidden">
          <div className="border-b border-slate-100 px-5 py-4">
            <h2 className="font-semibold">Matching runs</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <th className="px-5 py-3 font-semibold">Job profile</th>
                  <th className="px-5 py-3 font-semibold">Candidates</th>
                  <th className="px-5 py-3 font-semibold">Status</th>
                  <th className="px-5 py-3 font-semibold">Top match</th>
                  <th className="px-5 py-3 font-semibold">Created</th>
                  <th className="px-5 py-3 text-right font-semibold">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.length === 0 ? (
                  <tr>
                    <td className="px-5 py-8 text-slate-500" colSpan={6}>
                      No matches yet. Create a job profile, upload resumes, then run AI matching.
                    </td>
                  </tr>
                ) : (
                  rows.map((row) => (
                    <tr
                      key={row.id}
                      className={`border-t border-slate-100 ${
                        selectedId === row.id ? "bg-indigo-50/50" : ""
                      }`}
                    >
                      <td className="px-5 py-3 font-medium text-slate-900">{row.job_title}</td>
                      <td className="px-5 py-3">
                        {isRunActive(row.status)
                          ? `${row.selected_count ?? row.result_count} selected`
                          : row.result_count}
                      </td>
                      <td className="px-5 py-3">
                        <StatusPill status={row.status} />
                      </td>
                      <td className="px-5 py-3 font-semibold">
                        {formatPercent(row.top_match_score)}
                      </td>
                      <td className="px-5 py-3 text-slate-500">{relativeTime(row.created_at)}</td>
                      <td className="px-5 py-3 text-right">
                        <div className="flex justify-end gap-2">
                          <button
                            type="button"
                            className="tm-btn-ghost"
                            onClick={() => openReport(row.id)}
                          >
                            View report
                          </button>
                          <button
                            type="button"
                            className="tm-btn-ghost tm-btn-ghost-danger"
                            disabled={busy}
                            onClick={() => setDeleteTarget(row)}
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
      </div>

      <SideDrawer
        open={Boolean(selectedId)}
        onClose={closeReport}
        widthClassName="w-[min(96vw,72rem)]"
      >
        <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
          <div>
            <h2 className="font-semibold">
              {selected ? selected.job_title : "Candidate results"}
            </h2>
            <p className="text-xs text-slate-500">
              {selected
                ? isRunActive(selected.status)
                  ? `${formatStatus(selected.status)} · ${selected.selected_count ?? selected.result_count} selected · ${selected.model_provider}`
                  : `${results.length || selected.result_count} scored · provider ${selected.model_provider}`
                : "Candidate results"}
            </p>
          </div>
          <div className="flex gap-2">
            {selected ? (
              <button
                type="button"
                className="tm-btn tm-btn-danger !px-3 !py-2 text-sm"
                disabled={busy}
                onClick={() => setDeleteTarget(selected)}
              >
                Delete
              </button>
            ) : null}
            <button
              type="button"
              className="tm-btn tm-btn-ghost !px-2.5 !py-1.5"
              onClick={closeReport}
              aria-label="Close report"
            >
              ✕
            </button>
          </div>
        </div>
        {selected ? (
          <CandidateResultsTable
            jobTitle={selected.job_title}
            provider={selected.model_provider}
            results={results}
            busy={busy}
            runStatus={selected.status}
            selectedCount={selected.selected_count ?? selected.result_count}
            scoredCount={results.length || selected.result_count}
            etaSeconds={selected.eta_seconds}
            onExportCsv={() => void onExport(selected.id)}
          />
        ) : null}
      </SideDrawer>

      <SideDrawer open={showForm} onClose={closePanel} widthClassName="w-full max-w-md">
        <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
          <div>
            <h2 className="text-lg font-bold text-slate-950">Run AI matching</h2>
            <p className="mt-1 text-sm text-slate-500">
              Choose a job profile and the ready resumes to score.
            </p>
          </div>
          <button
            type="button"
            className="tm-btn tm-btn-ghost !px-2.5 !py-1.5"
            onClick={closePanel}
          >
            ✕
          </button>
        </div>

        <form className="flex min-h-0 flex-1 flex-col" onSubmit={onCreate}>
          <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
            {error ? <p className="text-sm text-rose-600">{error}</p> : null}

            <label className="block text-sm font-semibold">
              Job profile
              <select
                className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5"
                value={jobId}
                onChange={(e) => setJobId(e.target.value)}
                required
              >
                {jobs.length === 0 ? <option value="">No job profiles available</option> : null}
                {jobs.map((job) => (
                  <option key={job.id} value={job.id}>
                    {job.title}
                  </option>
                ))}
              </select>
            </label>

            <div>
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-semibold text-slate-900">
                  Candidates ({selectedResumeIds.length} selected)
                </p>
                <div className="flex gap-2 text-xs">
                  <button
                    type="button"
                    className="font-semibold text-indigo-600 hover:text-indigo-800"
                    onClick={() => setSelectedResumeIds(readyResumes.map((item) => item.id))}
                    disabled={readyResumes.length === 0}
                  >
                    Select all
                  </button>
                  <button
                    type="button"
                    className="font-semibold text-slate-500 hover:text-slate-800"
                    onClick={() => setSelectedResumeIds([])}
                    disabled={selectedResumeIds.length === 0}
                  >
                    Clear
                  </button>
                </div>
              </div>
              {readyResumes.length === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50 px-4 py-5 text-sm text-slate-500">
                  No ready resumes yet. Upload and wait for processing before running a match.
                </div>
              ) : (
                <ul className="max-h-[50vh] space-y-1 overflow-y-auto rounded-xl border border-slate-200 p-2">
                  {readyResumes.map((resume) => {
                    const checked = selectedResumeIds.includes(resume.id);
                    return (
                      <li key={resume.id}>
                        <label className="flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2.5 transition hover:bg-indigo-50/60">
                          <input
                            type="checkbox"
                            className="h-4 w-4 rounded border-slate-300 text-indigo-600"
                            checked={checked}
                            onChange={() => toggleResume(resume.id)}
                          />
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-sm font-medium text-slate-900">
                              {resume.candidate_label ?? "Unnamed resume"}
                            </span>
                            <span className="block font-mono text-xs text-slate-400">
                              {resume.id.slice(0, 8)}…
                            </span>
                          </span>
                        </label>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>

          <div className="flex flex-wrap gap-2 border-t border-slate-100 px-5 py-4">
            <button
              className="tm-btn tm-btn-primary"
              disabled={busy || !jobId || selectedResumeIds.length === 0}
              type="submit"
            >
              {busy ? "Running…" : "Start matching"}
            </button>
            <Link href="/resumes" className="tm-btn tm-btn-secondary" onClick={closePanel}>
              Upload resumes
            </Link>
          </div>
        </form>
      </SideDrawer>

      {deleteTarget ? (
        <div className="fixed inset-0 z-[60] grid place-items-center bg-slate-950/40 p-4 backdrop-blur-[2px] animate-[tm-fade-in_200ms_ease-out]">
          <div className="tm-card w-full max-w-md p-6 shadow-xl animate-[tm-scale-in_220ms_ease-out]">
            <h3 className="text-lg font-bold text-slate-950">Delete matching run?</h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              This permanently removes the run for{" "}
              <span className="font-semibold text-slate-900">“{deleteTarget.job_title}”</span> and
              its candidate scores. Token usage already recorded stays on the usage ledger.
            </p>
            <div className="mt-6 flex flex-wrap justify-end gap-2">
              <button
                type="button"
                className="tm-btn tm-btn-secondary"
                onClick={() => setDeleteTarget(null)}
                disabled={busy}
              >
                Cancel
              </button>
              <button
                type="button"
                className="tm-btn tm-btn-danger"
                disabled={busy}
                onClick={() => void confirmDelete()}
              >
                {busy ? "Deleting…" : "Delete run"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </AppShell>
  );
}

export default function EvaluationsPage() {
  return (
    <Suspense
      fallback={
        <AppShell title="Run AI matching">
          <div className="tm-skeleton h-64" />
        </AppShell>
      }
    >
      <EvaluationsContent />
    </Suspense>
  );
}
