"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { SideDrawer } from "@/components/SideDrawer";
import { API_BASE, readApiError } from "@/lib/api";

type PreviewRow = { excel_row: number; cells: string[] };

type IssueRowMeta = {
  excel_row: number;
  issue_count: number;
  issue_types: string[];
};

type PreviewResponse = {
  filename: string;
  sheet_name: string;
  headers: string[];
  rows: PreviewRow[];
  total_rows: number;
  offset: number;
  limit: number;
  q: string;
  issues_only?: boolean;
  issue_rows?: IssueRowMeta[];
};

const PAGE_SIZE = 50;

export function ExcelViewerDrawer({
  open,
  onClose,
  jobId,
  filename,
  focusExcelRow,
  issuesOnlyDefault = false,
}: {
  open: boolean;
  onClose: () => void;
  jobId: string;
  filename?: string;
  /** Jump to a specific Excel row (1-based, header = 1). */
  focusExcelRow?: number | null;
  issuesOnlyDefault?: boolean;
}) {
  const [headers, setHeaders] = useState<string[]>([]);
  const [rows, setRows] = useState<PreviewRow[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [query, setQuery] = useState("");
  const [draftQuery, setDraftQuery] = useState("");
  const [issuesOnly, setIssuesOnly] = useState(issuesOnlyDefault);
  const [issueRows, setIssueRows] = useState<IssueRowMeta[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState(filename ?? "Workbook");
  const [highlightRow, setHighlightRow] = useState<number | null>(null);

  const issueByRow = useMemo(() => {
    const map = new Map<number, IssueRowMeta>();
    for (const item of issueRows) map.set(item.excel_row, item);
    return map;
  }, [issueRows]);

  const load = useCallback(
    async (
      nextOffset: number,
      nextQuery: string,
      nextIssuesOnly: boolean,
    ): Promise<PreviewResponse | null> => {
      setLoading(true);
      setError(null);
      try {
        const params = new URLSearchParams({
          offset: String(nextOffset),
          limit: String(PAGE_SIZE),
          issues_only: nextIssuesOnly ? "true" : "false",
        });
        if (nextQuery.trim()) params.set("q", nextQuery.trim());
        const response = await fetch(
          `${API_BASE}/api/v1/goals-localization/jobs/${jobId}/workbook-preview?${params}`,
          { credentials: "include" },
        );
        if (!response.ok) throw new Error(await readApiError(response, "Could not load workbook."));
        const body = (await response.json()) as PreviewResponse;
        setHeaders(body.headers ?? []);
        setRows(body.rows ?? []);
        setTotal(body.total_rows ?? 0);
        setOffset(body.offset ?? nextOffset);
        setTitle(body.filename || filename || "Workbook");
        setIssueRows(body.issue_rows ?? []);
        return body;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not load workbook.");
        setRows([]);
        setTotal(0);
        return null;
      } finally {
        setLoading(false);
      }
    },
    [jobId, filename],
  );

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setDraftQuery("");
    setQuery("");
    setIssuesOnly(issuesOnlyDefault);
    setHighlightRow(focusExcelRow ?? null);

    void (async () => {
      let pageOffset =
        !issuesOnlyDefault && focusExcelRow != null && focusExcelRow >= 2
          ? Math.max(0, Math.floor((focusExcelRow - 2) / PAGE_SIZE) * PAGE_SIZE)
          : 0;
      setOffset(pageOffset);
      const body = await load(pageOffset, "", issuesOnlyDefault);
      if (cancelled || !body || focusExcelRow == null) return;
      if (issuesOnlyDefault) {
        const idx = (body.issue_rows ?? []).findIndex((item) => item.excel_row === focusExcelRow);
        if (idx >= 0) {
          pageOffset = Math.floor(idx / PAGE_SIZE) * PAGE_SIZE;
          if (pageOffset !== (body.offset ?? 0)) {
            await load(pageOffset, "", true);
          }
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [open, jobId, load, focusExcelRow, issuesOnlyDefault]);

  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + rows.length, total);
  const canPrev = offset > 0;
  const canNext = offset + rows.length < total;
  const issueCount = issueRows.length;

  return (
    <SideDrawer
      open={open}
      onClose={onClose}
      side="left"
      showBackdrop={false}
      widthClassName="w-[min(72vw,56rem)] max-w-none border-r border-slate-200"
    >
      <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-4">
        <div className="min-w-0">
          <h2 className="text-lg font-semibold text-slate-950">Excel viewer</h2>
          <p className="mt-1 truncate text-sm text-slate-500">{title}</p>
        </div>
        <button
          type="button"
          className="rounded-lg px-2 py-1 text-sm text-slate-500 hover:bg-slate-100"
          onClick={onClose}
        >
          Close
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-5 py-3">
        <form
          className="flex min-w-0 flex-1 items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            setQuery(draftQuery);
            void load(0, draftQuery, issuesOnly);
          }}
        >
          <input
            type="search"
            value={draftQuery}
            onChange={(event) => setDraftQuery(event.target.value)}
            placeholder="Search rows…"
            className="min-w-0 flex-1 rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-800 outline-none focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100"
          />
          <button type="submit" className="rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-semibold text-white">
            Search
          </button>
        </form>
        <button
          type="button"
          className={`rounded-lg border px-3 py-1.5 text-sm font-semibold transition ${
            issuesOnly
              ? "border-amber-400 bg-amber-100 text-amber-950"
              : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
          }`}
          onClick={() => {
            const next = !issuesOnly;
            setIssuesOnly(next);
            setOffset(0);
            void load(0, query, next);
          }}
        >
          Issue rows{issueCount ? ` (${issueCount})` : ""}
        </button>
        <p className="text-xs tabular-nums text-slate-500">
          {loading ? "Loading…" : total ? `${pageStart}–${pageEnd} of ${total.toLocaleString()}` : "0 rows"}
          {query ? ` · “${query}”` : ""}
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {error ? (
          <p className="m-5 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
            {error}
          </p>
        ) : null}
        {!error && !loading && !rows.length ? (
          <p className="m-5 text-sm text-slate-500">
            {issuesOnly ? "No open issue rows for this job." : "No rows to show."}
          </p>
        ) : null}
        {headers.length ? (
          <table className="min-w-full border-collapse text-left text-xs">
            <thead className="sticky top-0 z-[1] bg-slate-50">
              <tr>
                <th className="whitespace-nowrap border-b border-slate-200 px-3 py-2 font-semibold text-slate-500">
                  Row
                </th>
                {headers.map((header) => (
                  <th
                    key={header || "col"}
                    className="whitespace-nowrap border-b border-slate-200 px-3 py-2 font-semibold text-slate-600"
                  >
                    {header || "—"}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const issue = issueByRow.get(row.excel_row);
                const focused = highlightRow === row.excel_row;
                const hasIssue = Boolean(issue);
                return (
                  <tr
                    key={row.excel_row}
                    className={
                      focused
                        ? "bg-indigo-50 ring-2 ring-inset ring-indigo-300"
                        : hasIssue
                          ? "bg-amber-50"
                          : "odd:bg-white even:bg-slate-50/60"
                    }
                    ref={
                      focused
                        ? (node) => {
                            node?.scrollIntoView({ block: "center" });
                          }
                        : undefined
                    }
                  >
                    <td className="whitespace-nowrap border-b border-slate-100 px-3 py-2 align-top font-mono tabular-nums text-slate-400">
                      <div className="flex flex-col gap-1">
                        <span>{row.excel_row}</span>
                        {issue ? (
                          <span
                            className="inline-flex w-fit rounded bg-amber-200 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-amber-950"
                            title={issue.issue_types.join(", ")}
                          >
                            {issue.issue_count} issue{issue.issue_count === 1 ? "" : "s"}
                          </span>
                        ) : null}
                      </div>
                    </td>
                    {row.cells.map((cell, index) => (
                      <td
                        key={`${row.excel_row}-${index}`}
                        className="max-w-[18rem] border-b border-slate-100 px-3 py-2 align-top text-slate-800"
                        title={cell}
                      >
                        <span className="line-clamp-3 whitespace-pre-wrap break-words">{cell || "—"}</span>
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : null}
      </div>

      <div className="flex items-center justify-between gap-3 border-t border-slate-200 px-5 py-3">
        <button
          type="button"
          disabled={!canPrev || loading}
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-semibold text-slate-700 disabled:opacity-40"
          onClick={() => void load(Math.max(0, offset - PAGE_SIZE), query, issuesOnly)}
        >
          Previous
        </button>
        <button
          type="button"
          disabled={!canNext || loading}
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-semibold text-slate-700 disabled:opacity-40"
          onClick={() => void load(offset + PAGE_SIZE, query, issuesOnly)}
        >
          Next
        </button>
      </div>
    </SideDrawer>
  );
}
