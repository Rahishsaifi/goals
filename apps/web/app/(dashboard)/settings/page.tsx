"use client";

import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { JobEmailSettings } from "@/components/settings/JobEmailSettings";
import { API_BASE, csrfToken, readApiError } from "@/lib/api";

export default function SettingsPage() {
  const [email, setEmail] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [org, setOrg] = useState<string>("");
  const [paidEnabled, setPaidEnabled] = useState(false);
  const [paidConfigured, setPaidConfigured] = useState(false);
  const [paidNote, setPaidNote] = useState<string | null>(null);
  useEffect(() => {
    void fetch(`${API_BASE}/api/v1/auth/me`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((body) => {
        setEmail(body?.email ?? null);
        setRole(body?.memberships?.[0]?.role ?? null);
        setOrg(body?.memberships?.[0]?.tenant_name ?? "");
      });
    void fetch(`${API_BASE}/api/v1/goals-localization/translator-fallback`, { credentials: "include" })
      .then(async (response) => {
        if (!response.ok) return;
        const body = await response.json();
        setPaidEnabled(Boolean(body.enabled));
        setPaidConfigured(Boolean(body.configured));
      })
      .catch(() => undefined);
  }, []);

  async function togglePaid(next: boolean) {
    setPaidNote(null);
    const response = await fetch(`${API_BASE}/api/v1/goals-localization/translator-fallback`, {
      method: "PUT",
      credentials: "include",
      headers: { "content-type": "application/json", "x-csrf-token": csrfToken() },
      body: JSON.stringify({ enabled: next }),
    });
    if (!response.ok) {
      setPaidNote(await readApiError(response, "Could not update Translator fallback."));
      return;
    }
    const body = await response.json();
    setPaidEnabled(Boolean(body.enabled));
    setPaidNote(body.enabled ? "Paid Translator is on." : "Paid Translator is off.");
  }

  return (
    <AppShell email={email} role={role} orgName={org} title="Settings">
      <div className="tm-card space-y-4 p-6 text-sm">
        <div className="flex justify-between border-b border-slate-100 pb-3">
          <span className="text-slate-500">Signed-in user</span>
          <span className="font-semibold">{email ?? "—"}</span>
        </div>
        <div className="flex justify-between border-b border-slate-100 pb-3">
          <span className="text-slate-500">Organization</span>
          <span className="font-semibold">{org || "—"}</span>
        </div>
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="font-semibold text-slate-900">Paid Translator fallback</p>
            <p className="mt-1 max-w-xl text-xs leading-5 text-slate-500">
              The free Translator account stops at 2 million characters a month and does not upgrade itself.
              When this is on, a job that hits that limit continues on the paid Translator account
              (about $10 per million characters). When this is off, the job stops instead.
            </p>
            {!paidConfigured ? (
              <p className="mt-1 text-xs text-amber-700">Paid Translator keys are not configured on the server.</p>
            ) : null}
            {paidNote ? <p className="mt-1 text-xs text-slate-600">{paidNote}</p> : null}
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={paidEnabled}
            aria-label="Toggle paid Translator fallback"
            disabled={role !== "tenant_admin"}
            onClick={() => void togglePaid(!paidEnabled)}
            className={`relative mt-1 h-6 w-11 shrink-0 rounded-full transition ${
              paidEnabled ? "bg-indigo-600" : "bg-slate-300"
            } disabled:cursor-not-allowed disabled:opacity-60`}
          >
            <span
              className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition ${
                paidEnabled ? "translate-x-5" : "translate-x-0"
              }`}
            />
          </button>
        </div>
        <JobEmailSettings isAdmin={role === "tenant_admin"} />
      </div>
    </AppShell>
  );
}
