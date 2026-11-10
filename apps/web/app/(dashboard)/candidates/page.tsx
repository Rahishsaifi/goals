"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import { AppShell } from "@/components/AppShell";
import { StatusPill } from "@/components/StatusPill";
import { API_BASE } from "@/lib/api";

type Candidate = {
  id: string;
  status: string;
  candidate_label: string | null;
  full_name?: string | null;
  email?: string | null;
  phone?: string | null;
  location?: string | null;
  headline?: string | null;
  original_filename?: string | null;
};

function CandidatesContent() {
  const searchParams = useSearchParams();
  const q = (searchParams.get("q") ?? "").trim().toLowerCase();
  const [email, setEmail] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [orgName, setOrgName] = useState<string | null>(null);
  const [rows, setRows] = useState<Candidate[]>([]);

  useEffect(() => {
    void fetch(`${API_BASE}/api/v1/auth/me`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((body) => {
        setEmail(body?.email ?? null);
        setRole(body?.memberships?.[0]?.role ?? null);
        setOrgName(body?.memberships?.[0]?.tenant_name ?? null);
      });
    void fetch(`${API_BASE}/api/v1/resumes`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : []))
      .then(setRows);
  }, []);

  const filtered = useMemo(() => {
    if (!q) return rows;
    return rows.filter((row) => {
      const haystack = [
        row.full_name,
        row.candidate_label,
        row.email,
        row.phone,
        row.location,
        row.headline,
        row.original_filename,
        row.id,
        row.status,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [q, rows]);

  return (
    <AppShell email={email} role={role} orgName={orgName} title="Candidates">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2 text-sm text-slate-500">
        <p>
          Details extracted from resumes
          {q ? (
            <>
              {" "}
              · filtered by <span className="font-semibold text-slate-800">“{q}”</span>
            </>
          ) : null}
        </p>
        <p>
          Showing <span className="font-semibold text-slate-800">{filtered.length}</span> of{" "}
          {rows.length}
        </p>
      </div>
      <div className="tm-card overflow-hidden">
        <table className="w-full min-w-[720px] text-left text-sm">
          <thead className="border-b border-slate-100 bg-slate-50 text-slate-500">
            <tr>
              <th className="px-5 py-3 font-semibold">Candidate</th>
              <th className="px-5 py-3 font-semibold">Contact</th>
              <th className="px-5 py-3 font-semibold">Location</th>
              <th className="px-5 py-3 font-semibold">Status</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td className="px-5 py-8 text-slate-500" colSpan={4}>
                  {rows.length === 0
                    ? "No candidates yet. Upload resumes to populate this directory."
                    : "No candidates match this search."}
                </td>
              </tr>
            ) : (
              filtered.map((row) => {
                const name = row.full_name || row.candidate_label || "Unnamed candidate";
                return (
                  <tr key={row.id} className="border-t border-slate-100">
                    <td className="px-5 py-3">
                      <p className="font-semibold text-slate-900">{name}</p>
                      <p className="mt-0.5 text-xs text-slate-500">
                        {row.headline || row.original_filename || `${row.id.slice(0, 8)}…`}
                      </p>
                    </td>
                    <td className="px-5 py-3 text-slate-600">
                      <p>{row.email || "—"}</p>
                      <p className="text-xs text-slate-400">{row.phone || ""}</p>
                    </td>
                    <td className="px-5 py-3 text-slate-600">{row.location || "—"}</td>
                    <td className="px-5 py-3">
                      <StatusPill status={row.status} />
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </AppShell>
  );
}

export default function CandidatesPage() {
  return (
    <Suspense
      fallback={
        <AppShell title="Candidates">
          <div className="tm-skeleton h-64" />
        </AppShell>
      }
    >
      <CandidatesContent />
    </Suspense>
  );
}
