"use client";

import { useCallback, useEffect, useState } from "react";

import { API_BASE, csrfToken, readApiError } from "@/lib/api";
import { STAGE_LABELS } from "@/lib/localization";

export type QueueState = {
  busy: boolean;
  waiting: number;
  active_count: number;
  active_job_id?: string | null;
  processing: {
    id: string;
    status: string;
    source_filename: string;
    processed_records: number;
    total_records: number;
    current_stage: string | null;
  } | null;
};

export function useWorkerQueue(intervalMs = 4000): { queue: QueueState | null; refresh: () => Promise<void> } {
  const [queue, setQueue] = useState<QueueState | null>(null);
  const refresh = useCallback(async () => {
    const response = await fetch(`${API_BASE}/api/v1/goals-localization/queue`, { credentials: "include" });
    if (!response.ok) return;
    setQueue((await response.json()) as QueueState);
  }, []);
  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), intervalMs);
    return () => window.clearInterval(timer);
  }, [refresh, intervalMs]);
  return { queue, refresh };
}

export function WorkerQueueBanner({
  queue,
  onChanged,
  className = "",
}: {
  queue: QueueState | null;
  onChanged: () => void | Promise<void>;
  className?: string;
}) {
  const [cancelBusy, setCancelBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onCancelQueue() {
    if (!window.confirm("Cancel the file in the worker queue? Its progress is discarded.")) return;
    if (!csrfToken()) {
      setError("Session expired. Sign in again, then retry.");
      return;
    }
    setCancelBusy(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/v1/goals-localization/queue/clear`, {
        method: "POST",
        credentials: "include",
        headers: { "x-csrf-token": csrfToken() },
      });
      if (!response.ok) throw new Error(await readApiError(response, "Could not cancel the worker queue."));
      await onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not cancel the worker queue.");
    } finally {
      setCancelBusy(false);
    }
  }

  return (
    <div className={className}>
      <div
        className={`flex items-center justify-between gap-3 rounded-xl border px-4 py-2.5 text-sm ${
          queue?.busy
            ? "border-emerald-200 bg-emerald-50 text-emerald-900"
            : "border-slate-200 bg-slate-100 text-slate-600"
        }`}
      >
        {queue?.busy && queue.processing ? (
          <p className="flex min-w-0 items-center gap-2">
            <span className="relative flex h-2.5 w-2.5 shrink-0">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
            </span>
            <span className="min-w-0">
              Worker is processing <span className="font-semibold">{queue.processing.source_filename}</span>
              {" · "}
              {STAGE_LABELS[queue.processing.current_stage ?? ""] ?? queue.processing.status.replaceAll("_", " ")}
              {": "}
              {queue.processing.processed_records.toLocaleString()} of{" "}
              {queue.processing.total_records.toLocaleString()} rows.
              {queue.waiting > 0 ? ` ${queue.waiting} more file${queue.waiting === 1 ? "" : "s"} waiting.` : ""}
            </span>
          </p>
        ) : queue && queue.waiting > 0 ? (
          <p className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-slate-400" />
            {queue.waiting} file{queue.waiting === 1 ? "" : "s"} waiting for the worker to pick up.
          </p>
        ) : (
          <p className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-slate-400" />
            No file is in the worker queue.
          </p>
        )}
        {queue?.busy ? (
          <button
            type="button"
            className="shrink-0 rounded-lg border border-rose-200 bg-white px-3 py-1 text-xs font-semibold text-rose-700 transition hover:bg-rose-50 disabled:opacity-50"
            disabled={cancelBusy}
            onClick={() => void onCancelQueue()}
          >
            {cancelBusy ? "Cancelling…" : "Cancel"}
          </button>
        ) : null}
      </div>
      {error ? <p className="mt-1.5 text-xs text-rose-700">{error}</p> : null}
    </div>
  );
}
