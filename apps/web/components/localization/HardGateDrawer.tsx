"use client";

import { useEffect, useMemo, useState } from "react";

import { SideDrawer } from "@/components/SideDrawer";
import { API_BASE, readApiError } from "@/lib/api";

export type HardGateCheck = {
  name: string;
  required: string;
  actual: string;
  passed: boolean;
};

export type LocalizationIssue = {
  id: string;
  record_id: string;
  excel_row?: number | null;
  field_name: string;
  issue_type: string;
  severity: string;
  original_text: string | null;
  translated_text: string | null;
  proposed_correction: string | null;
  explanation: string | null;
  reviewer_status: string | null;
};

const ISSUE_TYPES_FOR_CHECK: Record<string, string[]> = {
  "Unresolved untranslated English": ["UNTRANSLATED_ENGLISH"],
  "Unresolved material terminology issues": ["TERMINOLOGY_MISSING"],
  "Unresolved high-severity semantic issues": ["FOUNDRY_UNAVAILABLE"],
  "Numeric discrepancies": ["NUMERIC_DISCREPANCY"],
  "Percentage discrepancies": ["NUMERIC_DISCREPANCY"],
  "Quarter discrepancies": ["QUARTER_DISCREPANCY"],
  "Date/deadline discrepancies": ["DATE_DISCREPANCY"],
};

function issueTypesForFailedChecks(checks: HardGateCheck[]): Set<string> | null {
  const failed = checks.filter((check) => !check.passed);
  if (!failed.length) return null;
  const types = new Set<string>();
  for (const check of failed) {
    for (const type of ISSUE_TYPES_FOR_CHECK[check.name] ?? []) types.add(type);
  }
  return types.size ? types : null;
}

function truncate(text: string | null | undefined, max = 160): string {
  if (!text) return "—";
  const compact = text.replace(/\s+/g, " ").trim();
  return compact.length > max ? `${compact.slice(0, max - 1)}…` : compact;
}

export function HardGateDrawer({
  open,
  onClose,
  jobId,
  checks,
  showBackdrop = true,
  nested = false,
  onShowInExcel,
}: {
  open: boolean;
  onClose: () => void;
  jobId: string;
  checks: HardGateCheck[];
  showBackdrop?: boolean;
  nested?: boolean;
  onShowInExcel?: (excelRow: number) => void;
}) {
  const [issues, setIssues] = useState<LocalizationIssue[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedCheck, setSelectedCheck] = useState<string | null>(null);

  const failed = useMemo(() => checks.filter((check) => !check.passed), [checks]);
  const passedCount = checks.length - failed.length;

  useEffect(() => {
    if (!open) return;
    setSelectedCheck((current) => {
      if (current && checks.some((check) => check.name === current)) return current;
      return failed[0]?.name ?? checks[0]?.name ?? null;
    });
  }, [open, checks, failed]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    void fetch(`${API_BASE}/api/v1/goals-localization/jobs/${jobId}/issues`, {
      credentials: "include",
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(await readApiError(response, "Could not load issues."));
        return response.json();
      })
      .then((body) => {
        if (cancelled) return;
        setIssues((body.issues ?? []) as LocalizationIssue[]);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Could not load issues.");
        setIssues([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, jobId]);

  const relevantTypes = useMemo(() => {
    if (selectedCheck) {
      const mapped = ISSUE_TYPES_FOR_CHECK[selectedCheck];
      if (mapped?.length) return new Set(mapped);
    }
    return issueTypesForFailedChecks(checks);
  }, [selectedCheck, checks]);

  const visibleIssues = useMemo(() => {
    const openIssues = issues.filter(
      (issue) => !issue.reviewer_status || issue.reviewer_status === "open",
    );
    if (!relevantTypes) {
      // Fall back to anything that is not a Foundry revision note.
      return openIssues.filter(
        (issue) =>
          issue.issue_type !== "SEMANTIC_REVISION" &&
          issue.issue_type !== "RESIDUAL_ENGLISH_REWORK",
      );
    }
    return openIssues.filter((issue) => relevantTypes.has(issue.issue_type));
  }, [issues, relevantTypes]);

  return (
    <SideDrawer
      open={open}
      onClose={onClose}
      widthClassName="w-full max-w-lg"
      showBackdrop={showBackdrop}
      nested={nested}
    >
      <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-950">Hard gate</h2>
          <p className="mt-1 text-sm text-slate-500">
            {failed.length
              ? `${failed.length} check${failed.length === 1 ? "" : "s"} failed · ${passedCount} passed`
              : checks.length
                ? "All checks passed"
                : "No hard-gate results yet"}
          </p>
        </div>
        <button
          type="button"
          className="rounded-lg px-2 py-1 text-sm text-slate-500 hover:bg-slate-100"
          onClick={onClose}
        >
          Close
        </button>
      </div>

      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-4">
        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Checks</h3>
          {checks.length ? (
            <ul className="space-y-2">
              {(failed.length ? [...failed, ...checks.filter((c) => c.passed)] : checks).map((check) => {
                const active = selectedCheck === check.name;
                return (
                  <li key={check.name}>
                    <button
                      type="button"
                      className={`w-full rounded-xl border px-3 py-2.5 text-left transition ${
                        active
                          ? "border-indigo-300 bg-indigo-50"
                          : check.passed
                            ? "border-slate-200 bg-white hover:bg-slate-50"
                            : "border-amber-200 bg-amber-50/60 hover:bg-amber-50"
                      }`}
                      onClick={() => setSelectedCheck(check.name)}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <span className="text-sm font-medium text-slate-900">{check.name}</span>
                        <span
                          className={`shrink-0 rounded px-1.5 py-0.5 text-[11px] font-bold ${
                            check.passed
                              ? "bg-emerald-100 text-emerald-700"
                              : "bg-rose-100 text-rose-700"
                          }`}
                        >
                          {check.passed ? "PASS" : "FAIL"}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-slate-500">
                        Required {check.required} · Actual {check.actual}
                      </p>
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="text-sm text-slate-500">Hard-gate checks are not available for this job.</p>
          )}
        </section>

        <section>
          <div className="mb-2 flex items-center justify-between gap-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              {selectedCheck ? `Issues · ${selectedCheck}` : "Related issues"}
            </h3>
            <span className="text-xs tabular-nums text-slate-400">{visibleIssues.length}</span>
          </div>
          {loading ? <p className="text-sm text-slate-500">Loading issues…</p> : null}
          {error ? (
            <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
              {error}
            </p>
          ) : null}
          {!loading && !error && !visibleIssues.length ? (
            <p className="text-sm text-slate-500">
              {failed.length
                ? "No row-level issue samples for this check. The count above is from the hard-gate summary."
                : "No open issues."}
            </p>
          ) : null}
          <ul className="space-y-3">
            {visibleIssues.map((issue) => (
              <li key={issue.id} className="rounded-xl border border-slate-200 bg-white p-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-slate-600">
                    {issue.field_name}
                  </span>
                  <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[11px] font-semibold text-amber-800">
                    {issue.issue_type.replaceAll("_", " ")}
                  </span>
                  <span className="text-[11px] font-medium text-slate-400">{issue.severity}</span>
                  {issue.excel_row ? (
                    <span className="text-[11px] font-medium tabular-nums text-slate-400">
                      Excel row {issue.excel_row}
                    </span>
                  ) : null}
                  {issue.excel_row && onShowInExcel ? (
                    <button
                      type="button"
                      className="ml-auto rounded-md border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-800 hover:bg-emerald-100"
                      onClick={() => onShowInExcel(issue.excel_row as number)}
                    >
                      Show in Excel
                    </button>
                  ) : null}
                </div>
                <p className="mt-2 text-sm text-slate-800">{issue.explanation || "No explanation."}</p>
                <dl className="mt-2 space-y-1.5 text-xs text-slate-500">
                  <div>
                    <dt className="font-semibold text-slate-400">Source</dt>
                    <dd className="mt-0.5 text-slate-700">{truncate(issue.original_text)}</dd>
                  </div>
                  <div>
                    <dt className="font-semibold text-slate-400">Translated</dt>
                    <dd className="mt-0.5 text-slate-700">{truncate(issue.translated_text)}</dd>
                  </div>
                </dl>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </SideDrawer>
  );
}
