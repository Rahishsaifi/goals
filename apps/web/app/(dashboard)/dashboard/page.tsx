"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { BarChart, DonutChart, MatchBar, StatusBreakdown } from "@/components/charts";
import { StatusPill } from "@/components/StatusPill";
import { API_BASE } from "@/lib/api";
import {
  displayNameFromEmail,
  formatPercent,
  formatStatus,
  relativeTime,
} from "@/lib/format";

type Me = {
  email: string;
  memberships: Array<{ tenant_name: string; role: string }>;
};

type Resume = { id: string; status: string; candidate_label: string | null };
type Job = { id: string; title: string };
type Evaluation = {
  id: string;
  status: string;
  job_title: string;
  result_count: number;
  top_match_score: string | null;
  created_at: string | null;
};
type UsageSummary = {
  model_calls: number;
  estimated_total_cost: string;
  input_tokens: number;
  output_tokens: number;
};
type UsageEvent = {
  id: string;
  operation_type: string;
  status: string;
};
type CandidateResult = {
  id: string;
  candidate_label: string | null;
  resume_id: string;
  overall_score: string;
};

const CREDIT_BUDGET = 1000;

export default function DashboardPage() {
  const [me, setMe] = useState<Me | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [evaluations, setEvaluations] = useState<Evaluation[]>([]);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [events, setEvents] = useState<UsageEvent[]>([]);
  const [topMatches, setTopMatches] = useState<CandidateResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  async function load(isRefresh = false) {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    const meResponse = await fetch(`${API_BASE}/api/v1/auth/me`, { credentials: "include" });
    if (!meResponse.ok) {
      setError("Sign in required.");
      setLoading(false);
      setRefreshing(false);
      return;
    }
    const meBody = (await meResponse.json()) as Me;
    setMe(meBody);
    setError(null);

    const [jobsRes, resumesRes, evalsRes, usageRes, eventsRes] = await Promise.all([
      fetch(`${API_BASE}/api/v1/job-profiles`, { credentials: "include" }),
      fetch(`${API_BASE}/api/v1/resumes`, { credentials: "include" }),
      fetch(`${API_BASE}/api/v1/evaluations`, { credentials: "include" }),
      fetch(`${API_BASE}/api/v1/usage/summary`, { credentials: "include" }),
      fetch(`${API_BASE}/api/v1/usage/events`, { credentials: "include" }),
    ]);

    const nextJobs: Job[] = jobsRes.ok ? await jobsRes.json() : [];
    const nextResumes: Resume[] = resumesRes.ok ? await resumesRes.json() : [];
    const nextEvals: Evaluation[] = evalsRes.ok ? await evalsRes.json() : [];
    setJobs(nextJobs);
    setResumes(nextResumes);
    setEvaluations(nextEvals);
    setUsage(usageRes.ok ? await usageRes.json() : null);
    setEvents(eventsRes.ok ? await eventsRes.json() : []);

    const completed = nextEvals.find((item) =>
      ["completed", "completed_with_warnings"].includes(item.status),
    );
    if (completed) {
      const resultsRes = await fetch(
        `${API_BASE}/api/v1/evaluations/${completed.id}/results`,
        { credentials: "include" },
      );
      if (resultsRes.ok) {
        const results = (await resultsRes.json()) as CandidateResult[];
        setTopMatches(results.slice(0, 5));
      } else {
        setTopMatches([]);
      }
    } else {
      setTopMatches([]);
    }

    setLoading(false);
    setRefreshing(false);
  }

  useEffect(() => {
    void load();
  }, []);

  const processed = resumes.filter((r) => r.status === "ready").length;
  const failed = resumes.filter((r) => r.status === "failed").length;
  const pending = Math.max(0, resumes.length - processed - failed);
  const readyRate = resumes.length ? Math.round((processed / resumes.length) * 100) : null;
  const modelCalls = usage?.model_calls ?? 0;
  const creditPercent = Math.min(100, Math.round((modelCalls / CREDIT_BUDGET) * 100));
  const membership = me?.memberships?.[0];

  const bars = useMemo(() => {
    const buckets = [
      { label: "Processed", processed, failed: 0, pending: 0 },
      { label: "Failed", processed: 0, failed, pending: 0 },
      { label: "Pending", processed: 0, failed: 0, pending },
      {
        label: "Total",
        processed,
        failed,
        pending,
      },
    ];
    return buckets;
  }, [processed, failed, pending]);

  if (error) {
    return (
      <main className="mx-auto flex min-h-screen max-w-lg flex-col justify-center px-6">
        <h1 className="text-2xl font-bold">Session expired</h1>
        <p className="mt-2 text-sm text-slate-500">{error}</p>
        <Link href="/login" className="tm-btn tm-btn-primary mt-6 w-fit">
          Sign In
        </Link>
      </main>
    );
  }

  const firstName = displayNameFromEmail(me?.email).split(" ")[0] ?? "there";

  return (
    <AppShell
      email={me?.email}
      role={membership?.role}
      orgName={membership?.tenant_name}
      title={`Welcome back, ${firstName}!`}
      action={
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="tm-btn tm-btn-secondary"
            disabled={refreshing || loading}
            onClick={() => void load(true)}
          >
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
          <Link href="/evaluations?new=1" className="tm-btn tm-btn-primary">
            Run AI matching
          </Link>
        </div>
      }
    >
      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="tm-skeleton h-28" />
          ))}
        </div>
      ) : (
        <>
          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[
              {
                label: "Total Resumes",
                value: resumes.length,
                hint: `${pending} in progress`,
                href: "/resumes",
              },
              {
                label: "Job Profiles",
                value: jobs.length,
                hint: "Active roles",
                href: "/jobs",
              },
              {
                label: "AI matching",
                value: evaluations.length,
                hint: evaluations[0] ? formatStatus(evaluations[0].status) : "None yet",
                href: "/evaluations",
              },
              {
                label: "Ready Rate",
                value: readyRate === null ? "—" : `${readyRate}%`,
                hint: `${processed} ready / ${failed} failed`,
                href: "/resumes",
              },
            ].map((stat) => (
              <Link key={stat.label} href={stat.href} className="tm-card p-5 transition hover:border-indigo-200">
                <p className="text-sm text-slate-500">{stat.label}</p>
                <p className="mt-3 text-3xl font-bold tracking-tight text-slate-950">{stat.value}</p>
                <p className="mt-2 text-xs capitalize text-slate-400">{stat.hint}</p>
              </Link>
            ))}
          </section>

          <section className="mt-4 grid gap-3 sm:grid-cols-3">
            <Link href="/jobs" className="tm-card px-4 py-3 text-sm font-semibold text-slate-800 hover:border-indigo-200">
              Manage job profiles →
            </Link>
            <Link href="/resumes" className="tm-card px-4 py-3 text-sm font-semibold text-slate-800 hover:border-indigo-200">
              Upload resumes →
            </Link>
            <Link href="/evaluations?new=1" className="tm-card px-4 py-3 text-sm font-semibold text-slate-800 hover:border-indigo-200">
              Run AI matching →
            </Link>
          </section>

          <section className="mt-4 grid gap-4 xl:grid-cols-2">
            <div className="tm-card p-5">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <h2 className="font-semibold text-slate-900">Resume Processing</h2>
                  <p className="text-xs text-slate-500">Live status from your workspace</p>
                </div>
                <div className="flex gap-3 text-[11px] text-slate-500">
                  <span className="inline-flex items-center gap-1">
                    <i className="h-2 w-2 rounded-full bg-indigo-500" /> Processed
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <i className="h-2 w-2 rounded-full bg-rose-400" /> Failed
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <i className="h-2 w-2 rounded-full bg-amber-300" /> Pending
                  </span>
                </div>
              </div>
              <BarChart values={bars} />
              <div className="mt-4">
                <StatusBreakdown processed={processed} failed={failed} pending={pending} />
              </div>
            </div>

            <div className="tm-card p-5">
              <div className="mb-2 flex items-center justify-between">
                <div>
                  <h2 className="font-semibold text-slate-900">Usage Overview</h2>
                  <p className="text-xs text-slate-500">
                    Mock provider · budget {CREDIT_BUDGET.toLocaleString()} units
                  </p>
                </div>
                <Link href="/usage" className="text-sm font-semibold text-indigo-600">
                  Details
                </Link>
              </div>
              <div className="mt-4 grid items-center gap-6 sm:grid-cols-[160px_1fr]">
                <DonutChart percent={creditPercent} label="Budget used" />
                <div className="space-y-3 text-sm">
                  <div className="flex justify-between border-b border-slate-100 pb-2">
                    <span className="text-slate-500">Model calls</span>
                    <span className="font-semibold">
                      {modelCalls} / {CREDIT_BUDGET.toLocaleString()}
                    </span>
                  </div>
                  <div className="flex justify-between border-b border-slate-100 pb-2">
                    <span className="text-slate-500">Estimated spend</span>
                    <span className="font-semibold">{usage?.estimated_total_cost ?? "0"}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Token units</span>
                    <span className="font-semibold">
                      {(usage?.input_tokens ?? 0) + (usage?.output_tokens ?? 0)}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section className="mt-4 grid gap-4 xl:grid-cols-2">
            <div className="tm-card overflow-hidden">
              <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
                <h2 className="font-semibold">Recent AI matching</h2>
                <Link href="/evaluations" className="text-sm font-semibold text-indigo-600">
                  View all
                </Link>
              </div>
              {evaluations.length === 0 ? (
                <div className="px-5 py-8 text-sm text-slate-500">
                  No AI matching runs yet.{" "}
                  <Link href="/evaluations?new=1" className="font-semibold text-indigo-600">
                    Start one
                  </Link>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-slate-50 text-slate-500">
                      <tr>
                        <th className="px-5 py-2 font-semibold">Job profile</th>
                        <th className="px-5 py-2 font-semibold">Candidates</th>
                        <th className="px-5 py-2 font-semibold">Status</th>
                        <th className="px-5 py-2 font-semibold">Top match</th>
                      </tr>
                    </thead>
                    <tbody>
                      {evaluations.slice(0, 5).map((item) => (
                        <tr key={item.id} className="border-t border-slate-100">
                          <td className="px-5 py-3">
                            <Link
                              href={`/evaluations?run=${item.id}`}
                              className="font-medium text-slate-900 hover:text-indigo-600"
                            >
                              {item.job_title}
                            </Link>
                            <p className="text-xs text-slate-400">{relativeTime(item.created_at)}</p>
                          </td>
                          <td className="px-5 py-3">{item.result_count}</td>
                          <td className="px-5 py-3">
                            <StatusPill status={item.status} />
                          </td>
                          <td className="px-5 py-3 font-semibold">
                            {formatPercent(item.top_match_score)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            <div className="tm-card overflow-hidden">
              <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
                <h2 className="font-semibold">Recent Resumes</h2>
                <Link href="/resumes" className="text-sm font-semibold text-indigo-600">
                  Upload
                </Link>
              </div>
              <div className="divide-y divide-slate-100">
                {resumes.length === 0 ? (
                  <p className="px-5 py-8 text-sm text-slate-500">No resumes uploaded yet.</p>
                ) : (
                  resumes.slice(0, 6).map((resume) => (
                    <div
                      key={resume.id}
                      className="flex items-center justify-between gap-3 px-5 py-3 text-sm"
                    >
                      <div className="min-w-0">
                        <p className="truncate font-medium text-slate-900">
                          {resume.candidate_label ?? `Resume ${resume.id.slice(0, 8)}`}
                        </p>
                        <p className="text-xs text-slate-400">{resume.id.slice(0, 8)}</p>
                      </div>
                      <StatusPill status={resume.status} />
                    </div>
                  ))
                )}
              </div>
            </div>
          </section>

          <section className="mt-4 grid gap-4 xl:grid-cols-2">
            <div className="tm-card overflow-hidden">
              <div className="border-b border-slate-100 px-5 py-4">
                <h2 className="font-semibold">Top Matching Candidates</h2>
                <p className="text-xs text-slate-500">From the latest completed match</p>
              </div>
              <div className="divide-y divide-slate-100">
                {topMatches.length === 0 ? (
                  <p className="px-5 py-8 text-sm text-slate-500">
                    Run AI matching against ready resumes to see ranked matches.
                  </p>
                ) : (
                  topMatches.map((match) => {
                    const score = Math.round(Number(match.overall_score));
                    const initials = (match.candidate_label ?? "C")
                      .split(/\s+/)
                      .slice(0, 2)
                      .map((part) => part[0]?.toUpperCase() ?? "")
                      .join("");
                    return (
                      <div key={match.id} className="flex items-center gap-3 px-5 py-3">
                        <div className="grid h-10 w-10 place-items-center rounded-full bg-indigo-50 text-xs font-bold text-indigo-700">
                          {initials || "C"}
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-semibold text-slate-900">
                            {match.candidate_label ?? match.resume_id.slice(0, 8)}
                          </p>
                          <MatchBar score={Number.isNaN(score) ? 0 : score} />
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>

            <div className="tm-card overflow-hidden">
              <div className="border-b border-slate-100 px-5 py-4">
                <h2 className="font-semibold">Activity Feed</h2>
              </div>
              <div className="space-y-0 px-5 py-2">
                {events.length === 0 && evaluations.length === 0 && resumes.length === 0 ? (
                  <p className="py-6 text-sm text-slate-500">No recent activity.</p>
                ) : (
                  <>
                    {evaluations.slice(0, 3).map((item) => (
                      <div
                        key={`eval-${item.id}`}
                        className="border-l-2 border-indigo-200 py-3 pl-4 text-sm"
                      >
                        <p className="font-medium text-slate-900">
                          AI matching {formatStatus(item.status)} · {item.job_title}
                        </p>
                        <p className="text-xs text-slate-400">{relativeTime(item.created_at)}</p>
                      </div>
                    ))}
                    {events.slice(0, 4).map((event) => (
                      <div
                        key={event.id}
                        className="border-l-2 border-slate-200 py-3 pl-4 text-sm"
                      >
                        <p className="font-medium capitalize text-slate-900">
                          {formatStatus(event.operation_type)}
                        </p>
                        <p className="text-xs capitalize text-slate-400">
                          {formatStatus(event.status)}
                        </p>
                      </div>
                    ))}
                    {resumes.slice(0, 2).map((resume) => (
                      <div
                        key={`resume-${resume.id}`}
                        className="border-l-2 border-amber-200 py-3 pl-4 text-sm"
                      >
                        <p className="font-medium text-slate-900">
                          Resume {formatStatus(resume.status)} ·{" "}
                          {resume.candidate_label ?? resume.id.slice(0, 8)}
                        </p>
                      </div>
                    ))}
                  </>
                )}
              </div>
            </div>
          </section>
        </>
      )}
    </AppShell>
  );
}
