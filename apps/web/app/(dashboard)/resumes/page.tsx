"use client";

import { useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { StatusPill } from "@/components/StatusPill";
import { API_BASE, csrfToken, readApiError } from "@/lib/api";

type Resume = {
  id: string;
  status: string;
  candidate_label: string | null;
  original_filename?: string | null;
  created_at?: string | null;
};

function isPendingStatus(status: string) {
  return !["ready", "failed", "cancelled", "deleted"].includes(status);
}

export default function ResumesPage() {
  const [rows, setRows] = useState<Resume[]>([]);
  const [email, setEmail] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [orgName, setOrgName] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  async function loadResumes(opts?: { silent?: boolean }) {
    if (!opts?.silent) setLoading(true);
    const response = await fetch(`${API_BASE}/api/v1/resumes`, { credentials: "include" });
    if (response.ok) {
      setRows((await response.json()) as Resume[]);
    }
    if (!opts?.silent) setLoading(false);
  }

  useEffect(() => {
    void fetch(`${API_BASE}/api/v1/auth/me`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((body) => {
        setEmail(body?.email ?? null);
        setRole(body?.memberships?.[0]?.role ?? null);
        setOrgName(body?.memberships?.[0]?.tenant_name ?? null);
      });
    void loadResumes();
  }, []);

  const hasPending = rows.some((row) => isPendingStatus(row.status));

  useEffect(() => {
    // Keep polling while work is in flight, and also briefly after empty→upload.
    if (!hasPending && rows.length > 0) return;
    const timer = window.setInterval(() => {
      void loadResumes({ silent: true });
    }, 2500);
    return () => window.clearInterval(timer);
  }, [hasPending, rows.length]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((row) => {
      const label = (row.candidate_label ?? "").toLowerCase();
      return label.includes(q) || row.id.toLowerCase().includes(q) || row.status.includes(q);
    });
  }, [query, rows]);

  const ready = rows.filter((r) => r.status === "ready").length;
  const pending = rows.filter((r) => !["ready", "failed"].includes(r.status)).length;
  const failed = rows.filter((r) => r.status === "failed").length;

  async function onFileSelected(file: File | null) {
    if (!file) return;
    setUploading(true);
    setError(null);
    setMessage(null);
    try {
      const form = new FormData();
      form.append("file", file, file.name);
      form.append("filename", file.name);
      const response = await fetch(`${API_BASE}/api/v1/resumes/upload`, {
        method: "POST",
        credentials: "include",
        headers: { "x-csrf-token": csrfToken() },
        body: form,
      });
      if (!response.ok) {
        throw new Error(await readApiError(response, "Could not upload resume."));
      }
      setMessage(`Uploaded “${file.name}”.`);
      await loadResumes();
    } catch (err) {
      const text = err instanceof Error ? err.message : "Upload failed.";
      setError(
        text === "Failed to fetch"
          ? "Cannot reach the API. Confirm http://127.0.0.1:8000 is running."
          : text,
      );
    } finally {
      setUploading(false);
    }
  }

  const uploadControl = (
    <label className={`tm-btn tm-btn-primary cursor-pointer ${uploading ? "opacity-60" : ""}`}>
      {uploading ? "Uploading…" : "+ Upload resume"}
      <input
        type="file"
        accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        className="hidden"
        disabled={uploading}
        onChange={(event) => {
          const file = event.target.files?.[0] ?? null;
          event.target.value = "";
          void onFileSelected(file);
        }}
      />
    </label>
  );

  return (
    <AppShell email={email} role={role} orgName={orgName} title="Resumes" action={uploadControl}>
      <div className="mb-4 rounded-2xl border border-indigo-100 bg-indigo-50/80 px-4 py-3.5 text-sm text-indigo-950">
        <p className="font-semibold">Coming soon</p>
        <p className="mt-1 leading-6 text-indigo-900/80">
          Later we will add SuccessFactors API integration to fetch candidate resumes directly
          into this workspace.
        </p>
      </div>

      {message ? (
        <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {message}
        </div>
      ) : null}
      {error ? (
        <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {error}
        </div>
      ) : null}

      <section className="mb-4 grid gap-3 sm:grid-cols-3">
        <div className="tm-card px-5 py-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Total</p>
          <p className="mt-1 text-2xl font-bold text-slate-950">{rows.length}</p>
        </div>
        <div className="tm-card px-5 py-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Ready</p>
          <p className="mt-1 text-2xl font-bold text-emerald-600">{ready}</p>
        </div>
        <div className="tm-card px-5 py-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
            Pending / failed
          </p>
          <p className="mt-1 text-2xl font-bold text-slate-950">
            {pending}
            <span className="mx-1 text-slate-300">/</span>
            <span className="text-rose-600">{failed}</span>
          </p>
        </div>
      </section>

      <div className="tm-card overflow-hidden">
        <div className="flex flex-col gap-3 border-b border-slate-100 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="font-semibold text-slate-900">Uploaded files</h2>
            <p className="text-xs text-slate-500">PDF and DOCX only · max size enforced by API</p>
          </div>
          <div className="relative w-full sm:max-w-xs">
            <input
              className="w-full rounded-xl border border-slate-200 bg-slate-50 py-2.5 px-3 text-sm outline-none transition focus:border-indigo-400 focus:bg-white focus:ring-4 focus:ring-indigo-50"
              placeholder="Search candidates or status…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Search resumes"
            />
          </div>
        </div>

        {loading ? (
          <div className="space-y-3 p-5">
            {Array.from({ length: 4 }).map((_, index) => (
              <div key={index} className="tm-skeleton h-12" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="px-5 py-16 text-center">
            <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-indigo-50 text-xl text-indigo-600">
              📄
            </div>
            <h3 className="mt-4 text-lg font-semibold text-slate-900">
              {rows.length === 0 ? "No resumes uploaded yet" : "No matching resumes"}
            </h3>
            <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">
              {rows.length === 0
                ? "Upload a PDF or DOCX to start processing candidates for evaluation matching."
                : "Try a different search term."}
            </p>
            {rows.length === 0 ? <div className="mt-6 inline-flex">{uploadControl}</div> : null}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-left text-sm">
              <thead className="border-b border-slate-100 bg-slate-50/80 text-slate-500">
                <tr>
                  <th className="px-5 py-3 font-semibold">File / candidate</th>
                  <th className="px-5 py-3 font-semibold">Resume ID</th>
                  <th className="px-5 py-3 font-semibold">Status</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((row) => (
                  <tr
                    key={row.id}
                    className="border-t border-slate-100 transition hover:bg-indigo-50/40"
                  >
                    <td className="px-5 py-4">
                      <p className="font-semibold text-slate-900">
                        {row.candidate_label ?? row.original_filename ?? "Unnamed file"}
                      </p>
                      <p className="mt-0.5 text-xs text-slate-400">
                        {row.original_filename && row.candidate_label
                          ? row.original_filename
                          : "Uploaded resume"}
                      </p>
                    </td>
                    <td className="px-5 py-4 font-mono text-xs text-slate-500">
                      {row.id.slice(0, 8)}…
                    </td>
                    <td className="px-5 py-4">
                      <StatusPill status={row.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AppShell>
  );
}

