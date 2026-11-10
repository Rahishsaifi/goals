"use client";

import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { API_BASE } from "@/lib/api";
import { relativeTime } from "@/lib/format";

type Me = { email: string; memberships: Array<{ tenant_name: string; role: string }> };
type AuditRow = {
  id: string;
  action: string;
  actor_email: string | null;
  resource_type: string | null;
  resource_id: string | null;
  created_at: string | null;
};

const ACTION_LABELS: Record<string, string> = {
  "auth.login": "Signed in",
  "auth.logout": "Signed out",
};

export default function AuditPage() {
  const [email, setEmail] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [orgName, setOrgName] = useState<string | null>(null);
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void fetch(`${API_BASE}/api/v1/auth/me`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((body: Me | null) => {
        setEmail(body?.email ?? null);
        setRole(body?.memberships?.[0]?.role ?? null);
        setOrgName(body?.memberships?.[0]?.tenant_name ?? null);
      });
    void fetch(`${API_BASE}/api/v1/audit`, { credentials: "include" }).then(async (response) => {
      if (!response.ok) {
        setError("Unable to load audit logs.");
        return;
      }
      setRows((await response.json()) as AuditRow[]);
    });
  }, []);

  return (
    <AppShell email={email} role={role} orgName={orgName} title="Audit Logs">
      {error ? <p className="mb-4 text-sm text-rose-600">{error}</p> : null}
      <div className="tm-card overflow-hidden">
        <div className="border-b border-slate-100 px-5 py-4">
          <h2 className="font-semibold">Activity</h2>
          <p className="text-xs text-slate-500">{rows.length} recorded events</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-500">
              <tr>
                <th className="px-5 py-3 font-semibold">When</th>
                <th className="px-5 py-3 font-semibold">Action</th>
                <th className="px-5 py-3 font-semibold">Actor</th>
                <th className="px-5 py-3 font-semibold">Resource</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 ? (
                <tr>
                  <td className="px-5 py-8 text-slate-500" colSpan={4}>
                    No audit events yet.
                  </td>
                </tr>
              ) : (
                rows.map((row) => (
                  <tr key={row.id} className="border-t border-slate-100">
                    <td className="px-5 py-3 text-slate-500">{relativeTime(row.created_at)}</td>
                    <td className="px-5 py-3 font-medium text-slate-900">
                      {ACTION_LABELS[row.action] ?? row.action}
                    </td>
                    <td className="px-5 py-3">{row.actor_email ?? "—"}</td>
                    <td className="px-5 py-3 text-slate-600">{row.resource_type ?? "—"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </AppShell>
  );
}
