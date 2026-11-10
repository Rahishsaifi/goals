"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { API_BASE } from "@/lib/api";
import { formatStatus, relativeTime } from "@/lib/format";

type EvalRow = {
  id: string;
  status: string;
  job_title: string;
  created_at?: string | null;
  eta_seconds?: number | null;
};

type ResumeRow = {
  id: string;
  status: string;
  candidate_label: string | null;
  original_filename?: string | null;
  created_at?: string | null;
};

type Notice = {
  id: string;
  kind: "resume" | "match";
  title: string;
  status: string;
  href: string;
  at: string;
  phase: "active" | "done" | "failed";
};

const RESUME_ACTIVE = new Set([
  "uploaded",
  "validated",
  "queued",
  "extracting_text",
  "normalizing_profile",
  "embedding",
  "indexing",
  "retry_pending",
]);
const MATCH_ACTIVE = new Set(["queued", "retrieving", "evaluating", "aggregating_results"]);
const STORAGE_KEY = "tm.notifications.v1";

function phaseFor(kind: "resume" | "match", status: string): Notice["phase"] {
  const s = status.toLowerCase();
  if (kind === "resume") {
    if (RESUME_ACTIVE.has(s)) return "active";
    if (s === "failed" || s === "cancelled") return "failed";
    return "done";
  }
  if (MATCH_ACTIVE.has(s)) return "active";
  if (s === "failed" || s === "cancelled") return "failed";
  return "done";
}

function loadStored(): Notice[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Notice[];
    if (!Array.isArray(parsed)) return [];
    const cutoff = Date.now() - 24 * 60 * 60 * 1000;
    return parsed.filter((item) => new Date(item.at).getTime() >= cutoff).slice(0, 40);
  } catch {
    return [];
  }
}

function saveStored(items: Notice[]) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(items.slice(0, 40)));
  } catch {
    /* ignore quota */
  }
}

export function NotificationCenter() {
  const [open, setOpen] = useState(false);
  const [live, setLive] = useState<Notice[]>([]);
  const [history, setHistory] = useState<Notice[]>([]);
  const prevActive = useRef<Map<string, Notice>>(new Map());
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setHistory(loadStored());
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function tick() {
      try {
        const [evalRes, resumeRes] = await Promise.all([
          fetch(`${API_BASE}/api/v1/evaluations`, { credentials: "include" }),
          fetch(`${API_BASE}/api/v1/resumes`, { credentials: "include" }),
        ]);
        if (cancelled) return;

        const notices: Notice[] = [];
        if (evalRes.ok) {
          const rows = (await evalRes.json()) as EvalRow[];
          for (const row of rows) {
            notices.push({
              id: `match:${row.id}`,
              kind: "match",
              title: row.job_title || "AI matching",
              status: row.status,
              href: `/evaluations?run=${row.id}`,
              at: row.created_at ?? new Date().toISOString(),
              phase: phaseFor("match", row.status),
            });
          }
        }
        if (resumeRes.ok) {
          const rows = (await resumeRes.json()) as ResumeRow[];
          for (const row of rows) {
            notices.push({
              id: `resume:${row.id}`,
              kind: "resume",
              title: row.candidate_label || row.original_filename || "Resume upload",
              status: row.status,
              href: "/resumes",
              at: row.created_at ?? new Date().toISOString(),
              phase: phaseFor("resume", row.status),
            });
          }
        }

        const active = notices.filter((item) => item.phase === "active");
        const activeMap = new Map(active.map((item) => [item.id, item]));
        const completedNow: Notice[] = [];
        for (const [id, prev] of prevActive.current) {
          if (activeMap.has(id)) continue;
          const current = notices.find((item) => item.id === id);
          if (!current || current.phase === "active") continue;
          completedNow.push({
            ...current,
            at: new Date().toISOString(),
            title:
              current.phase === "failed"
                ? `${current.title} failed`
                : `${current.title} completed`,
          });
        }
        prevActive.current = activeMap;

        if (completedNow.length) {
          setHistory((prev) => {
            const merged = [...completedNow, ...prev.filter((p) => !completedNow.some((c) => c.id === p.id))];
            saveStored(merged);
            return merged;
          });
        }

        setLive(notices);
      } catch {
        if (!cancelled) setLive([]);
      }
    }

    void tick();
    const timer = window.setInterval(() => {
      void tick();
    }, 3000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    function onPointer(event: MouseEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const active = useMemo(
    () =>
      live
        .filter((item) => item.phase === "active")
        .sort((a, b) => +new Date(b.at) - +new Date(a.at)),
    [live],
  );

  const recentDone = useMemo(() => {
    const fromLive = live
      .filter((item) => item.phase !== "active")
      .sort((a, b) => +new Date(b.at) - +new Date(a.at))
      .slice(0, 8)
      .map((item) => ({
        ...item,
        title:
          item.phase === "failed"
            ? `${item.title} · ${formatStatus(item.status)}`
            : `${item.title} · ${formatStatus(item.status)}`,
      }));
    const ids = new Set(fromLive.map((item) => item.id));
    const fromHistory = history.filter((item) => !ids.has(item.id)).slice(0, 8);
    return [...fromHistory, ...fromLive].slice(0, 12);
  }, [live, history]);

  const badge = active.length;

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        className="relative grid h-10 w-10 place-items-center rounded-xl border border-slate-200 text-slate-700 transition hover:bg-slate-50"
        aria-label="Notifications"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <svg viewBox="0 0 20 20" fill="none" className="h-5 w-5" aria-hidden>
          <path
            d="M10 2.5a4.5 4.5 0 0 0-4.5 4.5v1.2c0 .7-.2 1.4-.6 2L4 12h12l-.9-1.8a3.8 3.8 0 0 1-.6-2V7A4.5 4.5 0 0 0 10 2.5Z"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinejoin="round"
          />
          <path
            d="M8.2 14.5a1.8 1.8 0 0 0 3.6 0"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
        </svg>
        {badge > 0 ? (
          <span className="absolute -right-1 -top-1 grid h-5 min-w-5 place-items-center rounded-full bg-amber-500 px-1 text-[10px] font-bold text-white">
            {badge > 9 ? "9+" : badge}
          </span>
        ) : null}
      </button>

      {open ? (
        <div className="absolute right-0 z-40 mt-2 w-[min(92vw,22rem)] overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl animate-[tm-scale-in_180ms_ease-out]">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
            <div>
              <p className="text-sm font-semibold text-slate-950">Notifications</p>
              <p className="text-xs text-slate-500">
                {badge > 0 ? `${badge} in progress` : "No active jobs"}
              </p>
            </div>
            {history.length > 0 ? (
              <button
                type="button"
                className="text-xs font-semibold text-slate-500 hover:text-slate-800"
                onClick={() => {
                  setHistory([]);
                  saveStored([]);
                }}
              >
                Clear
              </button>
            ) : null}
          </div>

          <div className="max-h-[24rem] overflow-y-auto">
            <Section title="In progress">
              {active.length === 0 ? (
                <Empty text="Nothing queued right now." />
              ) : (
                active.map((item) => <NoticeRow key={item.id} item={item} onNavigate={() => setOpen(false)} />)
              )}
            </Section>
            <Section title="Completed">
              {recentDone.length === 0 ? (
                <Empty text="Completed jobs will show here." />
              ) : (
                recentDone.map((item) => (
                  <NoticeRow key={`${item.id}-${item.at}`} item={item} onNavigate={() => setOpen(false)} />
                ))
              )}
            </Section>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="border-b border-slate-100 last:border-b-0">
      <p className="px-4 pb-1 pt-3 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        {title}
      </p>
      <div className="px-2 pb-2">{children}</div>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="px-2 py-3 text-sm text-slate-500">{text}</p>;
}

function NoticeRow({ item, onNavigate }: { item: Notice; onNavigate: () => void }) {
  const tone =
    item.phase === "active"
      ? "text-amber-700"
      : item.phase === "failed"
        ? "text-rose-700"
        : "text-emerald-700";
  return (
    <Link
      href={item.href}
      onClick={onNavigate}
      className="flex items-start gap-2 rounded-xl px-2 py-2.5 transition hover:bg-slate-50"
    >
      {item.phase === "active" ? (
        <span className="tm-status-spin mt-0.5 text-amber-600" aria-hidden>
          <svg viewBox="0 0 16 16" fill="none" className="h-3.5 w-3.5">
            <circle cx="8" cy="8" r="6" stroke="currentColor" strokeOpacity="0.25" strokeWidth="2" />
            <path d="M14 8a6 6 0 0 0-6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </span>
      ) : (
        <span className={`mt-0.5 text-sm ${tone}`} aria-hidden>
          {item.phase === "failed" ? "!" : "✓"}
        </span>
      )}
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium text-slate-900">{item.title}</span>
        <span className={`block text-xs ${tone}`}>
          {item.kind === "resume" ? "Resume" : "Matching"} · {formatStatus(item.status)}
          {" · "}
          {relativeTime(item.at)}
        </span>
      </span>
    </Link>
  );
}
