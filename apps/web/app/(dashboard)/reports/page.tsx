"use client";

import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { MatchBar } from "@/components/charts";
import { API_BASE, csrfToken, readApiError } from "@/lib/api";
import { formatPercent, formatStatus, relativeTime, statusPillClass } from "@/lib/format";

type Me = { email: string; memberships: Array<{ tenant_name: string; role: string }> };
type Run = {
  id: string;
  status: string;
  job_title: string;
  result_count: number;
  top_match_score: string | null;
  created_at: string | null;
  model_provider: string;
};
type Breakdown = {
  key: string;
  display_name: string;
  weight: string;
  score: string;
  contribution: string;
  status: string;
  mandatory: boolean;
  passage: string | null;
};
type ResultRow = {
  id: string;
  resume_id: string;
  candidate_label: string | null;
  overall_score: string;
  mandatory_status: string;
  review_required: boolean;
  score_breakdown?: Breakdown[];
};
type Usage = {
  model_calls: number;
  input_tokens: number;
  output_tokens: number;
  list_price_usd: string;
  ai_matching_runs: number;
  ai_matching_scored: number;
};

function money(value: string | number | undefined): string {
  const amount = Number(value ?? 0);
  if (Number.isNaN(amount)) return "—";
  return amount.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 4,
    maximumFractionDigits: 4,
  });
}

export default function ReportsPage() {
  const [email, setEmail] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [orgName, setOrgName] = useState<string | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [selected, setSelected] = useState<Run | null>(null);
  const [results, setResults] = useState<ResultRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void fetch(`${API_BASE}/api/v1/auth/me`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((body: Me | null) => {
        setEmail(body?.email ?? null);
        setRole(body?.memberships?.[0]?.role ?? null);
        setOrgName(body?.memberships?.[0]?.tenant_name ?? null);
      });
    void Promise.all([
      fetch(`${API_BASE}/api/v1/evaluations`, { credentials: "include" }),
      fetch(`${API_BASE}/api/v1/usage/summary`, { credentials: "include" }),
    ]).then(async ([runsRes, usageRes]) => {
      if (!runsRes.ok || !usageRes.ok) {
        setError("Unable to load reports.");
        return;
      }
      setRuns((await runsRes.json()) as Run[]);
      setUsage((await usageRes.json()) as Usage);
    });
  }, []);

  async function openReport(run: Run) {
    setSelected(run);
    setResults([]);
    setError(null);
    const response = await fetch(`${API_BASE}/api/v1/evaluations/${run.id}/results`, {
      credentials: "include",
    });
    if (!response.ok) {
      setError("Unable to load this evaluation report.");
      return;
    }
    setResults((await response.json()) as ResultRow[]);
  }

  async function exportRun(runId: string) {
    setBusy(true);
    setError(null);
    const response = await fetch(`${API_BASE}/api/v1/evaluations/${runId}/export`, {
      method: "POST",
      credentials: "include",
      headers: { "x-csrf-token": csrfToken() },
    });
    setBusy(false);
    if (!response.ok) {
      setError(await readApiError(response, "Export failed."));
      return;
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `evaluation-${runId}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  const completed = runs.filter((run) =>
    ["completed", "completed_with_warnings"].includes(run.status),
  );

  return (
    <AppShell email={email} role={role} orgName={orgName} title="Reports">
      {error ? <p className="mb-4 text-sm text-rose-600">{error}</p> : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="tm-card p-5">
          <p className="text-sm text-slate-500">Evaluation reports</p>
          <p className="mt-3 text-3xl font-bold">{completed.length}</p>
        </div>
        <div className="tm-card p-5">
          <p className="text-sm text-slate-500">AI matching runs</p>
          <p className="mt-3 text-3xl font-bold">{usage?.ai_matching_runs ?? "—"}</p>
          <p className="mt-1 text-xs text-slate-500">{usage?.ai_matching_scored ?? 0} scored</p>
        </div>
        <div className="tm-card p-5">
          <p className="text-sm text-slate-500">Tokens</p>
          <p className="mt-3 text-3xl font-bold">
            {usage ? (usage.input_tokens + usage.output_tokens).toLocaleString("en-US") : "—"}
          </p>
          <p className="mt-1 text-xs text-slate-500">{usage?.model_calls ?? 0} model calls</p>
        </div>
        <div className="tm-card p-5">
          <p className="text-sm text-slate-500">List-price spend</p>
          <p className="mt-3 text-3xl font-bold">{money(usage?.list_price_usd)}</p>
        </div>
      </div>

      <div className="tm-card mt-4 overflow-hidden">
        <div className="border-b border-slate-100 px-5 py-4">
          <h2 className="font-semibold">Evaluation reports</h2>
          <p className="text-xs text-slate-500">Completed matching runs and their top scores.</p>
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
              {completed.length === 0 ? (
                <tr>
                  <td className="px-5 py-8 text-slate-500" colSpan={6}>
                    No completed matching runs yet.
                  </td>
                </tr>
              ) : (
                completed.map((run) => (
                  <tr key={run.id} className="border-t border-slate-100">
                    <td className="px-5 py-3 font-medium text-slate-900">{run.job_title}</td>
                    <td className="px-5 py-3">{run.result_count}</td>
                    <td className="px-5 py-3">
                      <span className={statusPillClass(run.status)}>{formatStatus(run.status)}</span>
                    </td>
                    <td className="px-5 py-3 font-semibold">{formatPercent(run.top_match_score)}</td>
                    <td className="px-5 py-3 text-slate-500">{relativeTime(run.created_at)}</td>
                    <td className="px-5 py-3 text-right">
                      <button
                        type="button"
                        className="tm-btn-ghost"
                        onClick={() => void openReport(run)}
                      >
                        View report
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {selected ? (
        <div className="fixed inset-0 z-40 flex justify-end">
          <button
            type="button"
            className="absolute inset-0 bg-slate-950/40"
            aria-label="Close report"
            onClick={() => setSelected(null)}
          />
          <aside className="relative flex h-full w-[75%] min-w-0 flex-col bg-white shadow-2xl">
            <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-4">
              <div>
                <h2 className="font-semibold">{selected.job_title}</h2>
                <p className="text-xs text-slate-500">
                  {selected.result_count} scored · provider {selected.model_provider}
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  className="tm-btn tm-btn-secondary !px-3 !py-2 text-sm"
                  disabled={busy}
                  onClick={() => void exportRun(selected.id)}
                >
                  Export CSV
                </button>
                <button
                  type="button"
                  className="tm-btn tm-btn-ghost !px-2.5 !py-1.5"
                  onClick={() => setSelected(null)}
                  aria-label="Close report"
                >
                  ✕
                </button>
              </div>
            </div>
            <div className="min-h-0 flex-1 divide-y divide-slate-100 overflow-y-auto">
              {results.length === 0 ? (
                <p className="px-5 py-8 text-sm text-slate-500">No scored candidates in this run.</p>
              ) : (
                results.map((result) => {
                  const score = Math.round(Number(result.overall_score));
                  return (
                    <div key={result.id} className="space-y-3 px-5 py-4">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="font-semibold text-slate-900">
                            {result.candidate_label ?? result.resume_id.slice(0, 8)}
                          </p>
                          <p className="text-xs capitalize text-slate-500">
                            Mandatory: {formatStatus(result.mandatory_status)}
                            {result.review_required ? " · Review required" : ""}
                          </p>
                        </div>
                        <span className="text-sm font-bold text-indigo-600">
                          {Number.isNaN(score) ? "—" : `${score}%`}
                        </span>
                      </div>
                      <MatchBar score={Number.isNaN(score) ? 0 : score} />
                      <div className="space-y-2">
                        {(result.score_breakdown ?? []).map((item) => (
                          <div
                            key={item.key}
                            className="rounded-xl border border-slate-200 px-4 py-3"
                          >
                            <div className="flex items-start justify-between gap-3">
                              <p className="font-medium text-slate-900">
                                {item.display_name}
                                {item.mandatory ? (
                                  <span className="ml-2 text-xs font-semibold text-rose-600">
                                    Mandatory
                                  </span>
                                ) : null}
                              </p>
                              <span className={statusPillClass(item.status)}>
                                {formatStatus(item.status)}
                              </span>
                            </div>
                            <p className="mt-1 text-xs text-slate-500">
                              Weight {item.weight} · score {Number(item.score).toFixed(0)} · points{" "}
                              {Number(item.contribution).toFixed(1)}
                            </p>
                            {item.passage ? (
                              <p className="mt-2 border-l-2 border-indigo-200 pl-3 text-sm text-slate-600">
                                {item.passage}
                              </p>
                            ) : null}
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </aside>
        </div>
      ) : null}
    </AppShell>
  );
}
