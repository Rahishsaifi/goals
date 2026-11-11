"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { AppShell } from "@/components/AppShell";
import { StartLocalizationDrawer } from "@/components/localization/StartLocalizationDrawer";
import { WorkerQueueBanner, useWorkerQueue } from "@/components/localization/WorkerQueueBanner";
import { ExcelFileIcon } from "@/components/localization/icons";
import { API_BASE, readApiError } from "@/lib/api";
import {
  BADGE_TONE_CLASS,
  TERMINAL,
  formatUpdated,
  jobBadge,
  outputFilename,
  useLanguageNames,
  useSessionInfo,
  type LocalizationJob,
} from "@/lib/localization";

const RECENT_LIMIT = 8;

function StatCard({
  icon,
  value,
  label,
  tone,
}: {
  icon: ReactNode;
  value: number | string;
  label: string;
  tone: string;
}) {
  return (
    <div className="flex items-center gap-2.5 px-4 py-1">
      <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-full [&_svg]:h-4 [&_svg]:w-4 ${tone}`}>
        {icon}
      </span>
      <div className="leading-tight">
        <p className="text-base font-bold tabular-nums text-slate-950">{value}</p>
        <p className="text-[11px] text-slate-500">{label}</p>
      </div>
    </div>
  );
}

function Icon({ path }: { path: string }) {
  return (
    <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth={1.8}>
      <path strokeLinecap="round" strokeLinejoin="round" d={path} />
    </svg>
  );
}

const ICONS = {
  folder: "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z",
  play: "M8 5.5v13l10-6.5-10-6.5z",
  check: "M5 12.5l4.5 4.5L19 7.5",
  warning: "M12 4l9 16H3l9-16zm0 6v4m0 3v.01",
  globe:
    "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zm0 0c2.5 2.5 3.5 5.5 3.5 9s-1 6.5-3.5 9m0-18C9.5 5.5 8.5 8.5 8.5 12s1 6.5 3.5 9M3.5 9h17M3.5 15h17",
  plus: "M12 5v14M5 12h14",
  search: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zm9 16-4-4",
  chevron: "M9 6l6 6-6 6",
};

export default function LocalizationJobsPage() {
  const router = useRouter();
  const session = useSessionInfo("/localization");
  const languageNames = useLanguageNames();
  const [jobs, setJobs] = useState<LocalizationJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [startOpen, setStartOpen] = useState(false);
  const closeStart = useCallback(() => setStartOpen(false), []);

  const loadJobs = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/goals-localization/jobs`, { credentials: "include" });
      if (!response.ok) throw new Error(await readApiError(response, "Could not load localization jobs."));
      const body = await response.json();
      setJobs((body.jobs ?? []) as LocalizationJob[]);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load localization jobs.");
    } finally {
      setLoading(false);
    }
  }, []);

  const anyActive = jobs.some((job) => !TERMINAL.has(job.status.toUpperCase()));

  useEffect(() => {
    void loadJobs();
    const timer = window.setInterval(() => void loadJobs(), anyActive ? 5000 : 30000);
    return () => window.clearInterval(timer);
  }, [loadJobs, anyActive]);

  const { queue, refresh: refreshQueue } = useWorkerQueue();
  const onQueueChanged = useCallback(async () => {
    await refreshQueue();
    await loadJobs();
  }, [refreshQueue, loadJobs]);

  const stats = useMemo(() => {
    let inProgress = 0;
    let completed = 0;
    let needsReview = 0;
    for (const job of jobs) {
      const badge = jobBadge(job);
      if (badge.label === "In Progress" || badge.label === "Queued") inProgress += 1;
      else if (badge.label === "Completed") completed += 1;
      else if (badge.label === "Needs Review") needsReview += 1;
    }
    return { total: jobs.length, inProgress, completed, needsReview };
  }, [jobs]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const matches = q
      ? jobs.filter(
          (job) =>
            job.id.toLowerCase().includes(q) ||
            job.source_filename.toLowerCase().includes(q) ||
            outputFilename(job).toLowerCase().includes(q),
        )
      : jobs;
    return showAll || q ? matches : matches.slice(0, RECENT_LIMIT);
  }, [jobs, query, showAll]);

  const startButton = (className: string) => (
    <button
      type="button"
      onClick={() => setStartOpen(true)}
      className={`inline-flex items-center justify-center gap-2 rounded-xl bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-indigo-700 ${className}`}
    >
      <span className="h-4 w-4">
        <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2.2}>
          <path strokeLinecap="round" d={ICONS.plus} />
        </svg>
      </span>
      Start New Localization
    </button>
  );

  return (
    <AppShell email={session.email} role={session.role} orgName={session.orgName}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <span className="grid h-14 w-14 place-items-center rounded-2xl bg-indigo-50 text-indigo-600">
            <Icon path={ICONS.globe} />
          </span>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-950">Goals Library Localization</h1>
            <p className="text-sm text-slate-500">
              Translate, validate, and prepare a SuccessFactors-ready goals library.
            </p>
          </div>
        </div>
        {startButton("")}
      </div>

      <div className="tm-card mb-4 grid grid-cols-2 divide-slate-100 px-2 py-2.5 sm:grid-cols-4 sm:divide-x">
        <StatCard icon={<Icon path={ICONS.folder} />} value={stats.total} label="Total Jobs" tone="bg-indigo-50 text-indigo-600" />
        <StatCard icon={<Icon path={ICONS.play} />} value={stats.inProgress} label="In Progress" tone="bg-violet-50 text-violet-600" />
        <StatCard icon={<Icon path={ICONS.check} />} value={stats.completed} label="Completed" tone="bg-emerald-50 text-emerald-600" />
        <StatCard icon={<Icon path={ICONS.warning} />} value={stats.needsReview} label="Needs Review" tone="bg-amber-50 text-amber-600" />
      </div>

      <WorkerQueueBanner queue={queue} onChanged={onQueueChanged} className="mb-4" />

      <div>
        <section className="tm-card overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
            <h2 className="text-lg font-semibold text-slate-950">Recent Localization Jobs</h2>
            <div className="flex items-center gap-4">
              <label className="relative">
                <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">
                  <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" d={ICONS.search} />
                  </svg>
                </span>
                <input
                  className="w-64 rounded-xl border border-slate-200 bg-white py-2 pl-9 pr-3 text-sm outline-none transition focus:border-indigo-400"
                  placeholder="Search by job ID or file name..."
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </label>
              {jobs.length > RECENT_LIMIT ? (
                <button
                  type="button"
                  className="text-sm font-semibold text-indigo-600 hover:text-indigo-800"
                  onClick={() => setShowAll((value) => !value)}
                >
                  {showAll ? "Show Recent" : "View All Jobs →"}
                </button>
              ) : null}
            </div>
          </div>

          {error ? <p className="mx-5 mb-4 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p> : null}

          <div className="overflow-x-auto px-5 pb-5">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="border-y border-slate-100 bg-slate-50/60 text-left text-xs font-semibold text-slate-600">
                  <th className="px-3 py-2.5">Job ID</th>
                  <th className="px-3 py-2.5">File Name</th>
                  <th className="px-3 py-2.5">Target Language</th>
                  <th className="px-3 py-2.5 text-right">Rows</th>
                  <th className="px-3 py-2.5">Status</th>
                  <th className="px-3 py-2.5">Updated</th>
                  <th className="w-8" />
                </tr>
              </thead>
              <tbody>
                {loading && !jobs.length ? (
                  <tr>
                    <td colSpan={7} className="px-3 py-8 text-center text-slate-400">
                      Loading jobs…
                    </td>
                  </tr>
                ) : !filtered.length ? (
                  <tr>
                    <td colSpan={7} className="px-3 py-8 text-center text-slate-400">
                      {query ? "No jobs match this search." : "No localization jobs yet."}
                    </td>
                  </tr>
                ) : (
                  filtered.map((job) => {
                    const badge = jobBadge(job);
                    return (
                      <tr
                        key={job.id}
                        className="cursor-pointer border-b border-slate-100 transition hover:bg-indigo-50/50"
                        onClick={() => router.push(`/localization/${job.id}`)}
                      >
                        <td className="px-3 py-3 font-mono text-xs text-slate-700">{job.id.slice(0, 8)}</td>
                        <td className="px-3 py-3">
                          <span className="flex items-center gap-2">
                            <ExcelFileIcon className="h-5 w-5 shrink-0" />
                            <span className="truncate text-slate-800">{outputFilename(job)}</span>
                          </span>
                        </td>
                        <td className="px-3 py-3 text-indigo-700">
                          {languageNames[job.target_language] ?? job.target_language}
                        </td>
                        <td className="px-3 py-3 text-right tabular-nums text-slate-800">
                          {job.total_records.toLocaleString()}
                        </td>
                        <td className="px-3 py-3">
                          <span
                            className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ${BADGE_TONE_CLASS[badge.tone]}`}
                          >
                            {badge.label}
                          </span>
                        </td>
                        <td className="whitespace-nowrap px-3 py-3 text-slate-600">
                          {formatUpdated(job.completed_at ?? job.created_at)}
                        </td>
                        <td className="px-1 py-3 text-slate-400">
                          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2}>
                            <path strokeLinecap="round" d={ICONS.chevron} />
                          </svg>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
      <StartLocalizationDrawer open={startOpen} onClose={closeStart} />
    </AppShell>
  );
}
