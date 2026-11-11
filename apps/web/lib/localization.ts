"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { API_BASE } from "@/lib/api";

export type StageInfo = { status?: string; detail?: string; started_at?: string; updated_at?: string };

export type LocalizationJob = {
  id: string;
  status: string;
  target_language: string;
  current_stage?: string | null;
  stage_progress?: Record<string, StageInfo>;
  stages?: string[];
  options?: Record<string, unknown>;
  summary?: Record<string, unknown>;
  cost_estimate?: Record<string, unknown>;
  total_records: number;
  processed_records?: number;
  failed_records?: number;
  production_ready: boolean;
  error_message: string | null;
  source_filename: string;
  has_output?: boolean;
  has_report?: boolean;
  created_at?: string | null;
  completed_at?: string | null;
};

export type Language = { code: string; name: string };

export const TERMINAL = new Set(["COMPLETED", "NEEDS_REVIEW", "FAILED", "CANCELLED"]);

export const STAGE_LABELS: Record<string, string> = {
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
};

export const STAGE_ORDER = Object.keys(STAGE_LABELS);

export function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "—";
  if (ms < 1000) return "<1s";
  const totalSec = Math.round(ms / 1000);
  if (totalSec < 60) return `${totalSec}s`;
  const mins = Math.floor(totalSec / 60);
  const secs = totalSec % 60;
  if (mins < 60) return `${mins}m ${secs}s`;
  const hours = Math.floor(mins / 60);
  return `${hours}h ${mins % 60}m`;
}

export function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString();
}

export function formatUpdated(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  const time = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (date.toDateString() === today.toDateString()) return `Today, ${time}`;
  if (date.toDateString() === yesterday.toDateString()) return `Yesterday, ${time}`;
  return `${date.toLocaleDateString()}, ${time}`;
}

export function jobFileUrl(jobId: string, kind: "download" | "report" | "issue-rows"): string {
  return `${API_BASE}/api/v1/goals-localization/jobs/${jobId}/${kind}`;
}

export function outputFilename(job: LocalizationJob): string {
  if (!job.has_output) return job.source_filename;
  const language = job.target_language.split("-")[0];
  return `Goals_${language}_${job.production_ready ? "PRODUCTION" : "NOT_PRODUCTION_READY"}.xlsx`;
}

export function jobDurationMs(job: LocalizationJob, nowMs: number): number {
  if (!job.created_at) return NaN;
  const end = job.completed_at && TERMINAL.has(job.status) ? Date.parse(job.completed_at) : nowMs;
  return end - Date.parse(job.created_at);
}

export type BadgeTone = "success" | "warning" | "danger" | "running" | "muted";

export function jobBadge(job: Pick<LocalizationJob, "status" | "production_ready">): {
  label: string;
  tone: BadgeTone;
} {
  const upper = job.status.toUpperCase();
  if (upper === "COMPLETED" || job.production_ready) return { label: "Completed", tone: "success" };
  if (upper === "NEEDS_REVIEW") return { label: "Needs Review", tone: "warning" };
  if (upper === "FAILED") return { label: "Failed", tone: "danger" };
  if (upper === "CANCELLED") return { label: "Cancelled", tone: "muted" };
  if (upper === "UPLOADED") return { label: "Queued", tone: "running" };
  return { label: "In Progress", tone: "running" };
}

export const BADGE_TONE_CLASS: Record<BadgeTone, string> = {
  success: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  warning: "bg-amber-50 text-amber-800 ring-amber-200",
  danger: "bg-rose-50 text-rose-700 ring-rose-200",
  running: "bg-indigo-50 text-indigo-700 ring-indigo-200",
  muted: "bg-slate-100 text-slate-600 ring-slate-200",
};

export function useSessionInfo(nextPath: string): {
  email: string | null;
  role: string | null;
  orgName: string | null;
} {
  const router = useRouter();
  const [info, setInfo] = useState<{ email: string | null; role: string | null; orgName: string | null }>({
    email: null,
    role: null,
    orgName: null,
  });
  useEffect(() => {
    void fetch(`${API_BASE}/api/v1/auth/me`, { credentials: "include" })
      .then(async (response) => {
        if (response.status === 401) {
          router.replace(`/login?next=${encodeURIComponent(nextPath)}`);
          return null;
        }
        return response.ok ? response.json() : null;
      })
      .then((body) => {
        if (!body) return;
        setInfo({
          email: body.email ?? null,
          role: body.memberships?.[0]?.role ?? null,
          orgName: body.memberships?.[0]?.tenant_name ?? null,
        });
      });
  }, [router, nextPath]);
  return info;
}

export function useLanguageNames(): Record<string, string> {
  const [names, setNames] = useState<Record<string, string>>({});
  useEffect(() => {
    void fetch(`${API_BASE}/api/v1/goals-localization/languages`, { credentials: "include" })
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => {
        const languages = (body?.languages ?? []) as Language[];
        setNames(Object.fromEntries(languages.map((language) => [language.code, language.name])));
      });
  }, []);
  return names;
}
