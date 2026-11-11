"use client";

import { useEffect, useState } from "react";

import { SideDrawer } from "@/components/SideDrawer";
import { API_BASE, csrfToken, readApiError } from "@/lib/api";

const PROMPT_URL = `${API_BASE}/api/v1/goals-localization/prompt`;

export function PromptDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [promptText, setPromptText] = useState("");
  const [promptDefault, setPromptDefault] = useState("");
  const [promptCustomized, setPromptCustomized] = useState(false);
  const [promptBusy, setPromptBusy] = useState(false);
  const [promptNote, setPromptNote] = useState<string | null>(null);
  const [promptNoteOk, setPromptNoteOk] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setPromptNote(null);
    setPromptNoteOk(false);
    void (async () => {
      const response = await fetch(PROMPT_URL, { credentials: "include" });
      if (cancelled) return;
      if (!response.ok) {
        setPromptNote(await readApiError(response, "Could not load the prompt."));
        return;
      }
      const body = await response.json();
      if (cancelled) return;
      setPromptText(String(body.prompt ?? ""));
      setPromptDefault(String(body.default_prompt ?? ""));
      setPromptCustomized(Boolean(body.customized));
    })();
    return () => {
      cancelled = true;
    };
  }, [open]);

  async function savePrompt(next: string, mode: "save" | "reset" = "save") {
    if (!csrfToken()) {
      setPromptNoteOk(false);
      setPromptNote("Session expired. Sign in again.");
      return;
    }
    setPromptBusy(true);
    setPromptNote(null);
    setPromptNoteOk(false);
    try {
      const response = await fetch(PROMPT_URL, {
        method: "PUT",
        credentials: "include",
        headers: { "content-type": "application/json", "x-csrf-token": csrfToken() },
        body: JSON.stringify({ prompt: next }),
      });
      if (!response.ok) {
        throw new Error(await readApiError(response, "Could not save the prompt."));
      }
      const body = await response.json();
      setPromptText(String(body.prompt ?? next));
      setPromptDefault(String(body.default_prompt ?? promptDefault));
      setPromptCustomized(Boolean(body.customized));
      setPromptNoteOk(true);
      setPromptNote(mode === "reset" ? "Reset to the built-in prompt." : "Saved. The next Foundry job uses this prompt.");
    } catch (err) {
      setPromptNoteOk(false);
      setPromptNote(err instanceof Error ? err.message : "Could not save the prompt.");
    } finally {
      setPromptBusy(false);
    }
  }

  return (
    <SideDrawer open={open} onClose={onClose} widthClassName="w-full max-w-md">
      <div className="flex items-start justify-between gap-3 border-b border-slate-200 px-4 py-3">
        <div>
          <h2 className="text-base font-bold text-slate-950">Foundry prompt</h2>
          <p className="mt-1 text-xs text-slate-500">
            Used when Foundry is on. It revises Goal, Description, and KRA only where the meaning differs from the
            English.
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
      <div className="flex min-h-0 flex-1 flex-col gap-3 p-4">
        <p className="text-[11px] font-semibold tracking-wide text-slate-500 uppercase">
          {promptCustomized ? "Custom prompt" : "Built-in prompt"}
        </p>
        <textarea
          value={promptText}
          onChange={(event) => {
            setPromptText(event.target.value);
            setPromptNote(null);
            setPromptNoteOk(false);
          }}
          className="min-h-0 flex-1 resize-none rounded-xl border border-slate-200 px-3 py-2 font-mono text-xs leading-5 outline-none focus:border-indigo-400"
          spellCheck={false}
        />
        <p className="text-[11px] text-slate-400">{promptText.length.toLocaleString()} / 200,000 characters</p>
        {promptNote ? (
          <p
            role="status"
            className={`rounded-lg px-3 py-2 text-sm font-medium ${
              promptNoteOk
                ? "border border-emerald-200 bg-emerald-50 text-emerald-800"
                : "border border-rose-200 bg-rose-50 text-rose-700"
            }`}
          >
            {promptNote}
          </p>
        ) : null}
        <div className="flex gap-2">
          <button
            type="button"
            className="tm-btn tm-btn-primary !px-3 !py-2 text-sm"
            disabled={promptBusy || !promptText.trim()}
            onClick={() => void savePrompt(promptText, "save")}
          >
            {promptBusy ? "Saving…" : "Save"}
          </button>
          <button
            type="button"
            className="tm-btn tm-btn-secondary !px-3 !py-2 text-sm"
            disabled={promptBusy}
            onClick={() => void savePrompt(promptDefault, "reset")}
          >
            Reset
          </button>
        </div>
      </div>
    </SideDrawer>
  );
}
