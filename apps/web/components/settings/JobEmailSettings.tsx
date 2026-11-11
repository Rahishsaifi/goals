"use client";

import { useEffect, useState } from "react";

import { API_BASE, csrfToken, readApiError } from "@/lib/api";

const EVENTS = [
  { id: "started", label: "Job starts" },
  { id: "completed", label: "Completed" },
  { id: "needs_review", label: "Needs Review" },
  { id: "failed", label: "Failed" },
] as const;

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const ENDPOINT = `${API_BASE}/api/v1/goals-localization/job-emails`;

export function JobEmailSettings({ isAdmin }: { isAdmin: boolean }) {
  const [enabled, setEnabled] = useState(true);
  const [configured, setConfigured] = useState(true);
  const [recipients, setRecipients] = useState<string[]>([]);
  const [events, setEvents] = useState<string[]>(EVENTS.map((event) => event.id));
  const [draft, setDraft] = useState("");
  const [note, setNote] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    void fetch(ENDPOINT, { credentials: "include" })
      .then(async (response) => {
        if (!response.ok) return;
        const body = await response.json();
        setEnabled(Boolean(body.enabled));
        setConfigured(Boolean(body.configured));
        setRecipients(Array.isArray(body.recipients) ? body.recipients : []);
        setEvents(Array.isArray(body.events) ? body.events : []);
      })
      .catch(() => undefined);
  }, []);

  function change<T>(setter: (value: T) => void, value: T) {
    setter(value);
    setDirty(true);
    setNote(null);
  }

  function addRecipient() {
    const address = draft.trim().toLowerCase();
    if (!address) return;
    if (!EMAIL_PATTERN.test(address)) {
      setNote({ tone: "error", text: `"${address}" is not a valid email address.` });
      return;
    }
    if (!recipients.includes(address)) change(setRecipients, [...recipients, address]);
    setDraft("");
  }

  async function save() {
    setSaving(true);
    setNote(null);
    try {
      const response = await fetch(ENDPOINT, {
        method: "PUT",
        credentials: "include",
        headers: { "content-type": "application/json", "x-csrf-token": csrfToken() },
        body: JSON.stringify({ enabled, recipients, events }),
      });
      if (!response.ok) {
        setNote({ tone: "error", text: await readApiError(response, "Could not save job email settings.") });
        return;
      }
      const body = await response.json();
      setEnabled(Boolean(body.enabled));
      setRecipients(body.recipients ?? []);
      setEvents(body.events ?? []);
      setDirty(false);
      setNote({ tone: "ok", text: "Job email settings saved." });
    } finally {
      setSaving(false);
    }
  }

  const controlsDisabled = !isAdmin || !enabled;

  return (
    <div className="space-y-4 border-t border-slate-100 pt-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="font-semibold text-slate-900">Localization job emails</p>
          <p className="mt-1 max-w-xl text-xs leading-5 text-slate-500">
            Email the people below when a localization job starts or finishes. Sent through Azure Communication
            Services, about $0.00025 per email.
          </p>
          {!configured ? (
            <p className="mt-1 text-xs text-amber-700">Email sending is not configured on the server.</p>
          ) : null}
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          aria-label="Toggle localization job emails"
          disabled={!isAdmin}
          onClick={() => change(setEnabled, !enabled)}
          className={`relative mt-1 h-6 w-11 shrink-0 rounded-full transition ${
            enabled ? "bg-indigo-600" : "bg-slate-300"
          } disabled:cursor-not-allowed disabled:opacity-60`}
        >
          <span
            className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition ${
              enabled ? "translate-x-5" : "translate-x-0"
            }`}
          />
        </button>
      </div>

      <div className={controlsDisabled ? "opacity-60" : ""}>
        <p className="text-xs font-semibold tracking-wide text-slate-500 uppercase">Send to</p>
        {isAdmin ? (
          <>
            <div className="mt-2 flex flex-wrap gap-2">
              {recipients.length === 0 ? (
                <span className="text-xs text-slate-500">No recipients yet. No job emails will be sent.</span>
              ) : null}
              {recipients.map((address) => (
                <span
                  key={address}
                  className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 py-1 pr-1.5 pl-3 text-xs font-medium text-slate-700"
                >
                  {address}
                  <button
                    type="button"
                    aria-label={`Remove ${address}`}
                    disabled={controlsDisabled}
                    onClick={() =>
                      change(
                        setRecipients,
                        recipients.filter((item) => item !== address),
                      )
                    }
                    className="flex h-4 w-4 items-center justify-center rounded-full text-slate-500 hover:bg-slate-300 hover:text-slate-800 disabled:cursor-not-allowed"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
            <div className="mt-2 flex max-w-md gap-2">
              <input
                type="email"
                value={draft}
                disabled={controlsDisabled}
                placeholder="name@company.com"
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    addRecipient();
                  }
                }}
                className="tm-input flex-1 !py-1.5 text-sm"
              />
              <button
                type="button"
                disabled={controlsDisabled || !draft.trim()}
                onClick={addRecipient}
                className="tm-btn tm-btn-secondary !px-3 !py-1.5 text-xs"
              >
                Add
              </button>
            </div>
          </>
        ) : (
          <p className="mt-2 text-xs text-slate-500">Only an admin can see and change the recipients.</p>
        )}
      </div>

      <div className={controlsDisabled ? "opacity-60" : ""}>
        <p className="text-xs font-semibold tracking-wide text-slate-500 uppercase">When</p>
        <div className="mt-2 flex flex-wrap gap-x-5 gap-y-2">
          {EVENTS.map((event) => (
            <label key={event.id} className="inline-flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-slate-300 text-indigo-600"
                disabled={controlsDisabled}
                checked={events.includes(event.id)}
                onChange={(change_event) =>
                  change(
                    setEvents,
                    change_event.target.checked
                      ? [...events, event.id]
                      : events.filter((item) => item !== event.id),
                  )
                }
              />
              {event.label}
            </label>
          ))}
        </div>
      </div>

      {isAdmin ? (
        <div className="flex items-center gap-3">
          <button
            type="button"
            disabled={!dirty || saving}
            onClick={() => void save()}
            className="tm-btn tm-btn-primary !px-4 !py-1.5 text-xs disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save email settings"}
          </button>
          {note ? (
            <span className={`text-xs ${note.tone === "error" ? "text-rose-600" : "text-emerald-700"}`}>
              {note.text}
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
