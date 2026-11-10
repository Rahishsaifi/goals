"use client";

import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { API_BASE } from "@/lib/api";

type OperationRow = {
  operation_type: string;
  provider: string;
  model_deployment: string | null;
  calls: number;
  input_tokens: number;
  output_tokens: number;
  list_price_usd: string;
};

type Forecast = {
  days_with_usage: number;
  days_in_month: number;
  days_left_after_today: number;
  rest_of_month_usd: string;
  full_month_if_repeated_usd: string;
  per_resume_parse_usd: string;
  per_candidate_score_usd: string;
};

type Summary = {
  model_calls: number;
  input_tokens: number;
  output_tokens: number;
  embedding_tokens: number;
  list_price_usd: string;
  budget_usd: string;
  input_rate_per_million: string;
  output_rate_per_million: string;
  ai_matching_runs: number;
  ai_matching_scored: number;
  evidence_calls: number;
  by_operation: OperationRow[];
  forecast: Forecast;
  note: string;
};

const OPERATION_LABELS: Record<string, string> = {
  evidence_assessment: "AI matching",
  resume_extraction: "Resume extraction",
  jd_extraction: "Job description extraction",
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

function count(value: number | undefined): string {
  return (value ?? 0).toLocaleString("en-US");
}

export default function UsagePage() {
  const [email, setEmail] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [orgName, setOrgName] = useState<string | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void fetch(`${API_BASE}/api/v1/auth/me`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((body) => {
        setEmail(body?.email ?? null);
        setRole(body?.memberships?.[0]?.role ?? null);
        setOrgName(body?.memberships?.[0]?.tenant_name ?? null);
      });
    void fetch(`${API_BASE}/api/v1/usage/summary`, { credentials: "include" })
      .then(async (response) => {
        if (!response.ok) {
          setError("Unable to load usage.");
          return;
        }
        setSummary((await response.json()) as Summary);
      })
      .catch(() => setError("Unable to load usage."));
  }, []);

  const tokens = (summary?.input_tokens ?? 0) + (summary?.output_tokens ?? 0);
  const budget = Number(summary?.budget_usd ?? 10);
  const spent = Number(summary?.list_price_usd ?? 0);
  const budgetUsed = budget > 0 ? Math.min(100, (spent / budget) * 100) : 0;
  const liveCalls =
    summary?.by_operation
      .filter((row) => row.provider === "foundry")
      .reduce((total, row) => total + row.calls, 0) ?? 0;
  const perResume = Number(summary?.forecast.per_resume_parse_usd ?? 0);
  const perScore = Number(summary?.forecast.per_candidate_score_usd ?? 0);
  const thousandOneJob = perResume * 1000 + perScore * 1000;
  const thousandFiveJobs = perResume * 1000 + perScore * 5000;

  return (
    <AppShell email={email} role={role} orgName={orgName} title="Usage & Costs">
      {error ? <p className="mb-4 text-sm text-rose-600">{error}</p> : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="tm-card p-5">
          <p className="text-sm text-slate-500">Model calls</p>
          <p className="mt-3 text-3xl font-bold">{count(summary?.model_calls)}</p>
          <p className="mt-1 text-xs text-slate-500">{count(liveCalls)} on gpt-4.1-mini</p>
        </div>
        <div className="tm-card p-5">
          <p className="text-sm text-slate-500">Input tokens</p>
          <p className="mt-3 text-3xl font-bold">{count(summary?.input_tokens)}</p>
        </div>
        <div className="tm-card p-5">
          <p className="text-sm text-slate-500">Output tokens</p>
          <p className="mt-3 text-3xl font-bold">{count(summary?.output_tokens)}</p>
          <p className="mt-1 text-xs text-slate-500">{count(tokens)} total tokens</p>
        </div>
        <div className="tm-card p-5">
          <p className="text-sm text-slate-500">List-price spend</p>
          <p className="mt-3 text-3xl font-bold">{money(summary?.list_price_usd)}</p>
          <p className="mt-1 text-xs text-slate-500">of {money(summary?.budget_usd)} budget</p>
        </div>
      </div>

      <div className="tm-card mt-4 p-5">
        <div className="flex items-center justify-between gap-3 text-sm">
          <p className="font-semibold text-slate-800">Foundry budget used</p>
          <p className="text-slate-500">{budgetUsed.toFixed(2)}%</p>
        </div>
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
          <div
            className="h-full rounded-full bg-indigo-500"
            style={{ width: `${budgetUsed}%`, minWidth: spent > 0 ? 4 : 0 }}
          />
        </div>
        <p className="mt-3 text-xs leading-5 text-slate-500">
          gpt-4.1-mini Global Standard is ${summary?.input_rate_per_million ?? "0.40"} per million
          input tokens and ${summary?.output_rate_per_million ?? "1.60"} per million output tokens.
          Mock job-description calls are not billed. This is a list-price estimate, not an Azure
          invoice.
        </p>
      </div>

      <div className="tm-card mt-4 overflow-hidden">
        <div className="border-b border-slate-100 px-5 py-4">
          <h2 className="font-semibold">Calls by model</h2>
          <p className="text-xs text-slate-500">
            {count(summary?.ai_matching_runs)} AI matching runs ·{" "}
            {count(summary?.ai_matching_scored)} scored a candidate ·{" "}
            {count(summary?.evidence_calls)} evidence calls
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <th className="px-5 py-3 font-semibold">Operation</th>
                <th className="px-5 py-3 font-semibold">Model</th>
                <th className="px-5 py-3 text-right font-semibold">Calls</th>
                <th className="px-5 py-3 text-right font-semibold">Input</th>
                <th className="px-5 py-3 text-right font-semibold">Output</th>
                <th className="px-5 py-3 text-right font-semibold">List price</th>
              </tr>
            </thead>
            <tbody>
              {(summary?.by_operation.length ?? 0) === 0 ? (
                <tr>
                  <td className="px-5 py-8 text-slate-500" colSpan={6}>
                    No model calls yet.
                  </td>
                </tr>
              ) : (
                summary?.by_operation.map((row) => (
                  <tr
                    key={`${row.operation_type}-${row.provider}-${row.model_deployment}`}
                    className="border-t border-slate-100"
                  >
                    <td className="px-5 py-3 font-medium text-slate-900">
                      {OPERATION_LABELS[row.operation_type] ?? row.operation_type}
                    </td>
                    <td className="px-5 py-3 text-slate-600">
                      {row.model_deployment ?? row.provider}
                    </td>
                    <td className="px-5 py-3 text-right">{count(row.calls)}</td>
                    <td className="px-5 py-3 text-right">{count(row.input_tokens)}</td>
                    <td className="px-5 py-3 text-right">{count(row.output_tokens)}</td>
                    <td className="px-5 py-3 text-right font-semibold">
                      {money(row.list_price_usd)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="tm-card mt-4 overflow-hidden">
        <div className="border-b border-slate-100 px-5 py-4">
          <h2 className="font-semibold">October forecast</h2>
          <p className="text-xs text-slate-500">
            Based on {summary?.forecast.days_with_usage ?? 0}{" "}
            {(summary?.forecast.days_with_usage ?? 0) === 1 ? "day" : "days"} of usage.{" "}
            {summary?.forecast.days_left_after_today ?? 0} days left in the month.
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <th className="px-5 py-3 font-semibold">Scenario</th>
                <th className="px-5 py-3 text-right font-semibold">List price</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-t border-slate-100">
                <td className="px-5 py-3">Spent so far</td>
                <td className="px-5 py-3 text-right font-semibold">
                  {money(summary?.list_price_usd)}
                </td>
              </tr>
              <tr className="border-t border-slate-100">
                <td className="px-5 py-3">Rest of October if each day matches today</td>
                <td className="px-5 py-3 text-right font-semibold">
                  {money(summary?.forecast.rest_of_month_usd)}
                </td>
              </tr>
              <tr className="border-t border-slate-100">
                <td className="px-5 py-3">Full month at today’s pace</td>
                <td className="px-5 py-3 text-right font-semibold">
                  {money(summary?.forecast.full_month_if_repeated_usd)}
                </td>
              </tr>
              <tr className="border-t border-slate-100">
                <td className="px-5 py-3">1,000 resumes, each scored on 1 job</td>
                <td className="px-5 py-3 text-right font-semibold">{money(thousandOneJob)}</td>
              </tr>
              <tr className="border-t border-slate-100">
                <td className="px-5 py-3">1,000 resumes, each scored on 5 jobs</td>
                <td className="px-5 py-3 text-right font-semibold">{money(thousandFiveJobs)}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="px-5 py-4 text-xs leading-5 text-slate-500">
          One resume parse is about {money(summary?.forecast.per_resume_parse_usd)}. One candidate
          scored on one job is about {money(summary?.forecast.per_candidate_score_usd)}.
        </p>
      </div>
    </AppShell>
  );
}
