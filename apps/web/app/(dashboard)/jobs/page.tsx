"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { API_BASE, csrfToken } from "@/lib/api";

type Profile = { id: string; title: string; current_version_id?: string };
type Criterion = {
  key?: string;
  display_name?: string;
  weight?: number;
  mandatory?: boolean;
  severity?: string;
  description?: string;
};
type ProfileDetail = {
  id: string;
  title: string;
  current_version_id: string | null;
  source_text: string | null;
  criteria: Criterion[];
};

export default function JobsPage() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [title, setTitle] = useState("");
  const [sourceText, setSourceText] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [orgName, setOrgName] = useState<string | null>(null);
  const [mode, setMode] = useState<"list" | "create" | "view" | "edit">("list");
  const [selected, setSelected] = useState<ProfileDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<Profile | null>(null);
  const [editCriteria, setEditCriteria] = useState<Criterion[]>([]);

  async function refresh() {
    setLoading(true);
    const response = await fetch(`${API_BASE}/api/v1/job-profiles`, { credentials: "include" });
    if (response.ok) setProfiles(await response.json());
    setLoading(false);
  }

  useEffect(() => {
    void fetch(`${API_BASE}/api/v1/auth/me`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((body) => {
        setEmail(body?.email ?? null);
        setRole(body?.memberships?.[0]?.role ?? null);
        setOrgName(body?.memberships?.[0]?.tenant_name ?? null);
      });
    void refresh();
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return profiles;
    return profiles.filter((profile) => profile.title.toLowerCase().includes(q));
  }, [profiles, query]);

  async function openProfile(id: string, nextMode: "view" | "edit") {
    setError(null);
    setMessage(null);
    setBusy(true);
    const response = await fetch(`${API_BASE}/api/v1/job-profiles/${id}`, {
      credentials: "include",
    });
    setBusy(false);
    if (!response.ok) {
      setError("Unable to load this job profile.");
      return;
    }
    const detail = (await response.json()) as ProfileDetail;
    setSelected(detail);
    setTitle(detail.title);
    setSourceText(detail.source_text ?? "");
    setMode(nextMode);
  }

  function resetForm() {
    setTitle("");
    setSourceText("");
    setSelected(null);
    setEditCriteria([]);
    setMode("list");
  }

  function startCreate() {
    setTitle("");
    setSourceText("");
    setSelected(null);
    setEditCriteria([]);
    setMode("create");
    setMessage(null);
    setError(null);
  }

  function updateCriterionWeight(index: number, weight: number) {
    setEditCriteria((current) =>
      current.map((item, i) => (i === index ? { ...item, weight } : item)),
    );
  }

  function toggleCriterionMandatory(index: number) {
    setEditCriteria((current) =>
      current.map((item, i) => {
        if (i !== index) return item;
        const mandatory = !item.mandatory;
        return {
          ...item,
          mandatory,
          severity: mandatory ? "mandatory" : item.severity === "mandatory" ? "preferred" : item.severity,
        };
      }),
    );
  }

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const response = await fetch(`${API_BASE}/api/v1/job-profiles`, {
      method: "POST",
      credentials: "include",
      headers: {
        "content-type": "application/json",
        "x-csrf-token": csrfToken(),
      },
      body: JSON.stringify({ title, source_text: sourceText || null }),
    });
    setBusy(false);
    if (!response.ok) {
      setError("Unable to save this job profile.");
      return;
    }
    setMessage("Job profile saved.");
    resetForm();
    await refresh();
  }

  async function onUpdate(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    const total = editCriteria.reduce((sum, item) => sum + Number(item.weight ?? 0), 0);
    if (Math.abs(total - 100) > 0.01) {
      setError(`Criteria weights must sum to 100 (currently ${total}).`);
      return;
    }
    setBusy(true);
    setError(null);
    const response = await fetch(`${API_BASE}/api/v1/job-profiles/${selected.id}`, {
      method: "PATCH",
      credentials: "include",
      headers: {
        "content-type": "application/json",
        "x-csrf-token": csrfToken(),
      },
      body: JSON.stringify({
        title,
        source_text: sourceText,
        criteria: editCriteria.map((item) => ({
          key: item.key,
          display_name: item.display_name,
          weight: Number(item.weight ?? 0),
          mandatory: Boolean(item.mandatory),
          severity: item.severity ?? (item.mandatory ? "mandatory" : "preferred"),
          description: item.description ?? "",
        })),
      }),
    });
    setBusy(false);
    if (!response.ok) {
      setError("Unable to update this job profile. Check that weights sum to 100.");
      return;
    }
    const detail = (await response.json()) as ProfileDetail;
    setSelected(detail);
    setEditCriteria(detail.criteria);
    setMessage("Job profile and scoring weights updated.");
    setMode("view");
    await refresh();
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setBusy(true);
    setError(null);
    const response = await fetch(`${API_BASE}/api/v1/job-profiles/${deleteTarget.id}`, {
      method: "DELETE",
      credentials: "include",
      headers: { "x-csrf-token": csrfToken() },
    });
    setBusy(false);
    if (!response.ok) {
      setError("Unable to delete this job profile.");
      setDeleteTarget(null);
      return;
    }
    setMessage(`Deleted “${deleteTarget.title}”.`);
    setDeleteTarget(null);
    resetForm();
    await refresh();
  }

  const weightTotal =
    (mode === "edit" ? editCriteria : selected?.criteria ?? []).reduce(
      (sum, item) => sum + Number(item.weight ?? 0),
      0,
    );

  return (
    <AppShell
      email={email}
      role={role}
      orgName={orgName}
      title="Job Profiles"
      action={
        mode === "list" ? (
          <button type="button" className="tm-btn tm-btn-primary" onClick={startCreate}>
            + New Job Profile
          </button>
        ) : (
          <button type="button" className="tm-btn tm-btn-secondary" onClick={resetForm}>
            ← Back to list
          </button>
        )
      }
    >
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

      {mode === "create" || mode === "edit" ? (
        <form
          className="tm-card mb-6 space-y-5 p-6"
          onSubmit={mode === "create" ? onCreate : onUpdate}
        >
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600">
              {mode === "create" ? "Create" : "Edit"}
            </p>
            <h2 className="mt-1 text-xl font-bold text-slate-950">
              {mode === "create" ? "New job profile" : "Edit job profile"}
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              Title and description feed scoring criteria extraction for evaluations.
            </p>
          </div>
          <label className="block text-sm font-semibold text-slate-700">
            Role title
            <input
              className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 outline-none transition focus:border-indigo-400 focus:ring-4 focus:ring-indigo-50"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Senior Software Developer"
              required
            />
          </label>
          <label className="block text-sm font-semibold text-slate-700">
            Job description
            <textarea
              className="mt-1.5 h-44 w-full resize-y rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 outline-none transition focus:border-indigo-400 focus:ring-4 focus:ring-indigo-50"
              value={sourceText}
              onChange={(e) => setSourceText(e.target.value)}
              placeholder="Paste the full JD, required skills, and experience expectations…"
            />
          </label>

          {mode === "edit" ? (
            <section className="rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h3 className="font-semibold text-slate-900">Scoring formula weights</h3>
                  <p className="text-xs text-slate-500">
                    Fit score = Σ (weight × criterion_score ÷ 100). Weights must total 100.
                  </p>
                </div>
                <p
                  className={`text-sm font-bold ${
                    Math.abs(weightTotal - 100) < 0.01 ? "text-emerald-600" : "text-rose-600"
                  }`}
                >
                  Total {weightTotal}%
                </p>
              </div>
              <div className="space-y-3">
                {editCriteria.map((criterion, index) => (
                  <div
                    key={criterion.key ?? index}
                    className="grid gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 sm:grid-cols-[1fr_auto_auto] sm:items-center"
                  >
                    <div>
                      <p className="font-semibold text-slate-900">
                        {criterion.display_name ?? criterion.key ?? "Criterion"}
                      </p>
                      {criterion.description ? (
                        <p className="mt-0.5 text-xs text-slate-500">{criterion.description}</p>
                      ) : null}
                    </div>
                    <label className="flex items-center gap-2 text-xs font-semibold text-slate-600">
                      Weight
                      <input
                        type="number"
                        min={0}
                        max={100}
                        step={1}
                        className="w-20 rounded-lg border border-slate-200 px-2 py-1.5 text-sm"
                        value={Number(criterion.weight ?? 0)}
                        onChange={(e) => updateCriterionWeight(index, Number(e.target.value))}
                      />
                    </label>
                    <label className="flex items-center gap-2 text-xs font-semibold text-slate-600">
                      <input
                        type="checkbox"
                        checked={Boolean(criterion.mandatory)}
                        onChange={() => toggleCriterionMandatory(index)}
                      />
                      Mandatory
                    </label>
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-4">
            <button
              className="tm-btn tm-btn-primary"
              disabled={busy || (mode === "edit" && Math.abs(weightTotal - 100) > 0.01)}
              type="submit"
            >
              {busy ? "Saving…" : mode === "create" ? "Save profile" : "Save changes"}
            </button>
            <button className="tm-btn tm-btn-secondary" type="button" onClick={resetForm}>
              Cancel
            </button>
          </div>
        </form>
      ) : null}

      {mode === "view" && selected ? (
        <div className="mb-6 grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
          <div className="tm-card space-y-5 p-6">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-2xl font-bold tracking-tight text-slate-950">
                    {selected.title}
                  </h2>
                  <span className="tm-pill tm-pill-success">Active</span>
                </div>
                <p className="mt-2 font-mono text-xs text-slate-400">{selected.id}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="tm-btn tm-btn-primary"
                  onClick={() => {
                    setTitle(selected.title);
                    setSourceText(selected.source_text ?? "");
                    setEditCriteria(selected.criteria.map((item) => ({ ...item })));
                    setMode("edit");
                  }}
                >
                  Edit
                </button>
                <button
                  type="button"
                  className="tm-btn tm-btn-danger"
                  disabled={busy}
                  onClick={() =>
                    setDeleteTarget({ id: selected.id, title: selected.title })
                  }
                >
                  Delete
                </button>
              </div>
            </div>
            <section>
              <h3 className="text-sm font-semibold text-slate-700">Job description</h3>
              <p className="mt-2 whitespace-pre-wrap rounded-2xl border border-slate-100 bg-slate-50 px-4 py-4 text-sm leading-7 text-slate-700">
                {selected.source_text?.trim() || "No description provided."}
              </p>
            </section>
          </div>

          <div className="tm-card overflow-hidden">
            <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
              <div>
                <h3 className="font-semibold text-slate-900">Scoring criteria</h3>
                <p className="text-xs text-slate-500">Weights total {weightTotal}%</p>
              </div>
            </div>
            <div className="divide-y divide-slate-100">
              {selected.criteria.length === 0 ? (
                <p className="px-5 py-8 text-sm text-slate-500">No criteria on this version.</p>
              ) : (
                selected.criteria.map((criterion, index) => (
                  <div key={criterion.key ?? index} className="px-5 py-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-semibold text-slate-900">
                          {criterion.display_name ?? criterion.key ?? "Criterion"}
                        </p>
                        {criterion.description ? (
                          <p className="mt-1 text-xs leading-5 text-slate-500">
                            {criterion.description}
                          </p>
                        ) : null}
                      </div>
                      <div className="text-right">
                        <p className="text-sm font-bold text-indigo-600">
                          {criterion.weight ?? 0}%
                        </p>
                        <p className="mt-1 text-[11px] capitalize text-slate-400">
                          {criterion.severity ??
                            (criterion.mandatory ? "mandatory" : "preferred")}
                        </p>
                      </div>
                    </div>
                    <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-100">
                      <div
                        className="h-full rounded-full bg-indigo-500"
                        style={{ width: `${Math.min(100, Number(criterion.weight ?? 0))}%` }}
                      />
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      ) : null}

      {mode === "list" ? (
        <>
          <section className="mb-4 grid gap-3 sm:grid-cols-3">
            <div className="tm-card px-5 py-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Total roles
              </p>
              <p className="mt-1 text-2xl font-bold text-slate-950">{profiles.length}</p>
            </div>
            <div className="tm-card px-5 py-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Showing
              </p>
              <p className="mt-1 text-2xl font-bold text-slate-950">{filtered.length}</p>
            </div>
            <div className="tm-card px-5 py-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Status
              </p>
              <p className="mt-1 text-2xl font-bold text-emerald-600">Active</p>
            </div>
          </section>

          <div className="tm-card overflow-hidden">
            <div className="flex flex-col gap-3 border-b border-slate-100 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="font-semibold text-slate-900">All profiles</h2>
                <p className="text-xs text-slate-500">
                  Search, open, edit, or remove roles used in evaluations
                </p>
              </div>
              <div className="relative w-full sm:max-w-xs">
                <input
                  className="w-full rounded-xl border border-slate-200 bg-slate-50 py-2.5 pl-3 pr-3 text-sm outline-none transition focus:border-indigo-400 focus:bg-white focus:ring-4 focus:ring-indigo-50"
                  placeholder="Search roles…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  aria-label="Search job profiles"
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
                  ☰
                </div>
                <h3 className="mt-4 text-lg font-semibold text-slate-900">
                  {profiles.length === 0 ? "No job profiles yet" : "No matching roles"}
                </h3>
                <p className="mx-auto mt-2 max-w-md text-sm text-slate-500">
                  {profiles.length === 0
                    ? "Create your first role profile to start matching candidates against weighted criteria."
                    : "Try a different search term."}
                </p>
                {profiles.length === 0 ? (
                  <button
                    type="button"
                    className="tm-btn tm-btn-primary mt-6"
                    onClick={startCreate}
                  >
                    Create job profile
                  </button>
                ) : null}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] text-left text-sm">
                  <thead className="border-b border-slate-100 bg-slate-50/80 text-slate-500">
                    <tr>
                      <th className="px-5 py-3 font-semibold">Role</th>
                      <th className="px-5 py-3 font-semibold">Status</th>
                      <th className="px-5 py-3 text-right font-semibold">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((profile) => (
                      <tr
                        key={profile.id}
                        className="border-t border-slate-100 transition hover:bg-indigo-50/40"
                      >
                        <td className="px-5 py-4">
                          <button
                            type="button"
                            className="text-left"
                            onClick={() => void openProfile(profile.id, "view")}
                          >
                            <p className="font-semibold text-slate-900 hover:text-indigo-700">
                              {profile.title}
                            </p>
                            <p className="mt-0.5 font-mono text-[11px] text-slate-400">
                              {profile.id.slice(0, 8)}…
                            </p>
                          </button>
                        </td>
                        <td className="px-5 py-4">
                          <span className="tm-pill tm-pill-success">Active</span>
                        </td>
                        <td className="px-5 py-4">
                          <div className="flex flex-wrap justify-end gap-2">
                            <button
                              type="button"
                              className="tm-btn-ghost"
                              onClick={() => void openProfile(profile.id, "view")}
                            >
                              View
                            </button>
                            <button
                              type="button"
                              className="tm-btn-ghost"
                              onClick={() => void openProfile(profile.id, "edit")}
                            >
                              Edit
                            </button>
                            <button
                              type="button"
                              className="tm-btn-ghost tm-btn-ghost-danger"
                              disabled={busy}
                              onClick={() => setDeleteTarget(profile)}
                            >
                              Delete
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      ) : null}

      {deleteTarget ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/40 p-4 backdrop-blur-[2px] animate-[tm-fade-in_200ms_ease-out]">
          <div className="tm-card w-full max-w-md p-6 shadow-xl animate-[tm-scale-in_220ms_ease-out]">
            <h3 className="text-lg font-bold text-slate-950">Delete job profile?</h3>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              This permanently removes{" "}
              <span className="font-semibold text-slate-900">“{deleteTarget.title}”</span> and
              its scoring versions. This cannot be undone.
            </p>
            <div className="mt-6 flex flex-wrap justify-end gap-2">
              <button
                type="button"
                className="tm-btn tm-btn-secondary"
                onClick={() => setDeleteTarget(null)}
                disabled={busy}
              >
                Cancel
              </button>
              <button
                type="button"
                className="tm-btn tm-btn-danger"
                disabled={busy}
                onClick={() => void confirmDelete()}
              >
                {busy ? "Deleting…" : "Delete profile"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </AppShell>
  );
}
