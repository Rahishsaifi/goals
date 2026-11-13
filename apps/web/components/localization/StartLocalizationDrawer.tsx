"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState, type ChangeEvent } from "react";

import { SideDrawer } from "@/components/SideDrawer";
import { API_BASE, csrfToken, readApiError } from "@/lib/api";

type Language = { code: string; name: string; sheet_code?: string; translate?: boolean };
type GlossaryTerm = { term: string; action: "preserve" | "allow" };
type QaMode = "classic" | "foundry";
type Estimate = { rows: number; characters: number; uniqueCharacters: number; costUsd: number };

const PAID_USD_PER_MILLION = 10;

const OPTION_LABELS: Record<string, string> = {
  translate_goal: "Translate Goal",
  translate_description: "Translate Description",
  translate_kra: "Translate KRA",
  preserve_technical_fields: "Preserve technical fields",
  preserve_formatting: "Preserve formatting",
  run_numerical_validation: "Run numerical validation",
  run_structural_reconciliation: "Run structural reconciliation",
  run_category_specific_qa: "Run category-specific QA",
};

const DEFAULT_GLOSSARY: GlossaryTerm[] = [
  ...["BCD", "NDC", "EBITDA", "TripSource", "GetGoing", "Advito", "Mission Possible", "Performance Solutions"].map(
    (term) => ({ term, action: "preserve" as const }),
  ),
  ...["SAP", "SuccessFactors", "KPI", "KRA", "Q1", "Q2", "Q3", "Q4", "FY", "OKR", "HR", "IT", "CEO", "CFO", "CTO"].map(
    (term) => ({ term, action: "allow" as const }),
  ),
];

function parseCsvRows(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (quoted) {
      if (char === '"' && text[index + 1] === '"') {
        cell += '"';
        index += 1;
      } else if (char === '"') {
        quoted = false;
      } else {
        cell += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ",") {
      row.push(cell);
      cell = "";
    } else if (char === "\n") {
      row.push(cell);
      rows.push(row);
      row = [];
      cell = "";
    } else if (char !== "\r") {
      cell += char;
    }
  }
  if (cell.length || row.length) {
    row.push(cell);
    rows.push(row);
  }
  return rows;
}

function estimateTranslation(text: string): Estimate {
  const table = parseCsvRows(text.replace(/^\uFEFF/, ""));
  const headers = (table[0] ?? []).map((header) => header.replace(/[^a-z]/gi, "").toLowerCase());
  const columns = ["goal", "description", "kra"]
    .map((name) => headers.indexOf(name))
    .filter((index) => index >= 0);
  const unique = new Map<string, number>();
  let characters = 0;
  let rows = 0;
  for (const record of table.slice(1)) {
    const values = columns.map((index) => (record[index] ?? "").trim()).filter(Boolean);
    if (!values.length) continue;
    rows += 1;
    for (const value of values) {
      characters += value.length;
      if (!unique.has(value)) unique.set(value, value.length);
    }
  }
  const uniqueCharacters = [...unique.values()].reduce((sum, length) => sum + length, 0);
  return { rows, characters, uniqueCharacters, costUsd: (uniqueCharacters / 1_000_000) * PAID_USD_PER_MILLION };
}

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function StartLocalizationDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const [languages, setLanguages] = useState<Language[]>([]);
  const [mandatoryOptions, setMandatoryOptions] = useState<string[]>(Object.keys(OPTION_LABELS));
  const [targetLanguage, setTargetLanguage] = useState("zh");
  const [qaMode, setQaMode] = useState<QaMode>("classic");
  const [nlQualityV2, setNlQualityV2] = useState(false);
  const [glossary, setGlossary] = useState<GlossaryTerm[]>(DEFAULT_GLOSSARY);
  const [glossaryDraft, setGlossaryDraft] = useState("");
  const [glossaryAction, setGlossaryAction] = useState<GlossaryTerm["action"]>("preserve");
  const [glossaryBusy, setGlossaryBusy] = useState(false);
  const [glossaryNote, setGlossaryNote] = useState<string | null>(null);
  const [englishFile, setEnglishFile] = useState<File | null>(null);
  const [fileEstimate, setFileEstimate] = useState<Estimate | null>(null);
  const [estimateAccepted, setEstimateAccepted] = useState(false);
  const [workerBusy, setWorkerBusy] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void fetch(`${API_BASE}/api/v1/goals-localization/languages`, { credentials: "include" })
      .then(async (response) => {
        if (!response.ok) return;
        const body = await response.json();
        const nextLanguages = (body.languages ?? []) as Language[];
        if (nextLanguages.length) {
          setLanguages(nextLanguages);
          setTargetLanguage((current) =>
            nextLanguages.some((lang) => lang.code === current) ? current : nextLanguages[0].code,
          );
        }
        if (Array.isArray(body.mandatory_options) && body.mandatory_options.length) {
          setMandatoryOptions(body.mandatory_options as string[]);
        }
        if (body.default_qa_mode === "classic" || body.default_qa_mode === "foundry") {
          setQaMode(body.default_qa_mode);
        }
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!open) return;
    void fetch(`${API_BASE}/api/v1/goals-localization/glossary`, { credentials: "include" })
      .then(async (response) => {
        if (!response.ok) return;
        const body = await response.json();
        if (Array.isArray(body.terms) && body.terms.length) setGlossary(body.terms as GlossaryTerm[]);
      })
      .catch(() => undefined);
  }, [open]);

  const refreshQueue = useCallback(async () => {
    const response = await fetch(`${API_BASE}/api/v1/goals-localization/queue`, { credentials: "include" });
    if (!response.ok) return;
    const body = await response.json();
    setWorkerBusy(Boolean(body.busy));
  }, []);

  useEffect(() => {
    if (!open) return;
    void refreshQueue();
    const timer = window.setInterval(() => void refreshQueue(), 4000);
    return () => window.clearInterval(timer);
  }, [open, refreshQueue]);

  const selectedLanguage = languages.find((lang) => lang.code === targetLanguage);
  const canStart = Boolean(englishFile && targetLanguage && estimateAccepted && !busy && !workerBusy);

  async function saveGlossary(next: GlossaryTerm[]) {
    setGlossaryNote(null);
    if (!csrfToken()) {
      setGlossaryNote("Session expired. Sign in again.");
      return;
    }
    setGlossaryBusy(true);
    try {
      const response = await fetch(`${API_BASE}/api/v1/goals-localization/glossary`, {
        method: "PUT",
        credentials: "include",
        headers: { "content-type": "application/json", "x-csrf-token": csrfToken() },
        body: JSON.stringify({ terms: next }),
      });
      if (!response.ok) throw new Error(await readApiError(response, "Could not save terminology."));
      const body = await response.json();
      setGlossary((body.terms ?? next) as GlossaryTerm[]);
      setGlossaryNote("Saved. The next job uses this list.");
    } catch (err) {
      setGlossaryNote(err instanceof Error ? err.message : "Could not save terminology.");
    } finally {
      setGlossaryBusy(false);
    }
  }

  function addGlossaryTerm() {
    const term = glossaryDraft.trim();
    if (!term) return;
    if (glossary.some((item) => item.term.toLowerCase() === term.toLowerCase())) {
      setGlossaryNote("That term is already in the list.");
      return;
    }
    const next = [...glossary, { term, action: glossaryAction }];
    setGlossaryDraft("");
    void saveGlossary(next);
  }

  async function onPickFile(file: File | null) {
    setEnglishFile(file);
    setEstimateAccepted(false);
    setFileEstimate(null);
    if (!file) return;
    setFileEstimate(estimateTranslation(await file.text()));
  }

  function onClear() {
    setEnglishFile(null);
    setFileEstimate(null);
    setEstimateAccepted(false);
    setError(null);
  }

  async function onStart() {
    setError(null);
    if (!englishFile) {
      setError("Upload the English Goals Library CSV.");
      return;
    }
    if (!targetLanguage) {
      setError("Select a target language.");
      return;
    }
    if (!csrfToken()) {
      setError("Session expired. Sign in again, then retry.");
      router.replace(`/login?next=${encodeURIComponent("/localization")}`);
      return;
    }
    setBusy(true);
    try {
      const form = new FormData();
      form.append("target_language", targetLanguage);
      form.append("qa_mode", qaMode);
      form.append("nl_quality_v2", nlQualityV2 ? "true" : "false");
      form.append("english_csv", englishFile, englishFile.name);
      const response = await fetch(`${API_BASE}/api/v1/goals-localization/jobs`, {
        method: "POST",
        credentials: "include",
        headers: { "x-csrf-token": csrfToken() },
        body: form,
      });
      if (response.status === 401) {
        router.replace(`/login?next=${encodeURIComponent("/localization")}`);
        throw new Error("Authentication required. Please sign in and retry.");
      }
      if (!response.ok) throw new Error(await readApiError(response, "Could not start localization."));
      const body = await response.json();
      const jobId = (body.job?.id ?? "") as string;
      onClear();
      onClose();
      if (jobId) router.push(`/localization/${jobId}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start localization.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <SideDrawer open={open} onClose={onClose} widthClassName="w-full max-w-lg">
      <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
        <div>
          <h2 className="text-base font-semibold text-slate-950">Start New Localization</h2>
          <p className="text-xs text-slate-500">Upload & configure</p>
        </div>
        <button
          type="button"
          className="rounded-lg px-2 py-1 text-sm text-slate-500 hover:bg-slate-100"
          onClick={onClose}
        >
          Close
        </button>
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-4">
        {error ? (
          <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div>
        ) : null}

        <div>
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Upload files</p>
          <label className="flex cursor-pointer items-start gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2.5 transition hover:border-indigo-300">
            <span
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-[10px] font-bold ${
                englishFile ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"
              }`}
            >
              CSV
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-xs font-semibold text-slate-900">
                English Goals Library
                <span className="text-rose-500"> *</span>
              </span>
              {englishFile ? (
                <>
                  <span className="mt-0.5 block truncate text-xs text-slate-700">{englishFile.name}</span>
                  <span className="text-[11px] text-emerald-700">{formatBytes(englishFile.size)} · ready</span>
                </>
              ) : (
                <span className="mt-0.5 block text-[11px] text-slate-500">Choose the source CSV</span>
              )}
            </span>
            {englishFile ? (
              <button
                type="button"
                className="text-xs text-slate-400 hover:text-rose-600"
                aria-label="Remove CSV"
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  void onPickFile(null);
                }}
              >
                ✕
              </button>
            ) : null}
            <input
              type="file"
              accept=".csv,text/csv"
              className="sr-only"
              onChange={(event: ChangeEvent<HTMLInputElement>) => {
                void onPickFile(event.target.files?.[0] ?? null);
                event.target.value = "";
              }}
            />
          </label>
          {fileEstimate && !estimateAccepted ? (
            <div className="mt-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs text-amber-950">
              <p className="font-semibold">
                {fileEstimate.rows.toLocaleString()} rows · {fileEstimate.characters.toLocaleString()} characters in the file
              </p>
              <p className="mt-1">
                {fileEstimate.uniqueCharacters.toLocaleString()} unique characters will be sent. Repeated Goal,
                Description, and KRA text is translated once and reused.
              </p>
              <p className="mt-1">
                Estimated paid cost ${fileEstimate.costUsd.toFixed(2)} at $10 per million unique characters. The free
                account stops at 2 million characters a month and does not upgrade itself.
              </p>
              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  className="tm-btn tm-btn-primary !px-2.5 !py-1.5 text-xs"
                  onClick={() => setEstimateAccepted(true)}
                >
                  Continue
                </button>
                <button
                  type="button"
                  className="tm-btn tm-btn-secondary !px-2.5 !py-1.5 text-xs"
                  onClick={() => void onPickFile(null)}
                >
                  Skip
                </button>
              </div>
            </div>
          ) : null}
        </div>

        <label className="block">
          <span className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            Target language
          </span>
          <select
            className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none transition focus:border-indigo-400 focus:ring-2 focus:ring-indigo-50"
            value={targetLanguage}
            onChange={(event) => setTargetLanguage(event.target.value)}
          >
            {languages.map((lang) => (
              <option key={lang.code} value={lang.code}>
                {lang.name} ({lang.sheet_code ?? lang.code})
              </option>
            ))}
          </select>
        </label>

        <div>
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">Terminology</p>
            <span className="text-[11px] text-slate-400">{glossary.length} terms</span>
          </div>
          <div className="mb-2 flex gap-1.5">
            <input
              value={glossaryDraft}
              onChange={(event) => setGlossaryDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  addGlossaryTerm();
                }
              }}
              placeholder="Add a term"
              className="min-w-0 flex-1 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs outline-none focus:border-indigo-400"
            />
            <select
              value={glossaryAction}
              onChange={(event) => setGlossaryAction(event.target.value as GlossaryTerm["action"])}
              className="rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs"
            >
              <option value="preserve">Preserve</option>
              <option value="allow">Allow English</option>
            </select>
            <button
              type="button"
              className="tm-btn tm-btn-secondary !px-2.5 !py-1.5 text-xs"
              disabled={glossaryBusy || !glossaryDraft.trim()}
              onClick={addGlossaryTerm}
            >
              Add
            </button>
          </div>
          <div className="max-h-44 overflow-auto rounded-lg border border-slate-200">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-slate-50 text-[10px] uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-2 py-1 font-semibold">Term</th>
                  <th className="px-2 py-1 font-semibold">Action</th>
                  <th className="px-2 py-1" />
                </tr>
              </thead>
              <tbody>
                {glossary.map((item) => (
                  <tr key={item.term} className="border-t border-slate-100">
                    <td className="px-2 py-1 font-medium text-slate-800">{item.term}</td>
                    <td className="px-2 py-1 text-slate-500">
                      {item.action === "preserve" ? "Preserve" : "Allow English"}
                    </td>
                    <td className="px-2 py-1 text-right">
                      <button
                        type="button"
                        className="text-slate-400 hover:text-rose-600"
                        disabled={glossaryBusy}
                        aria-label={`Remove ${item.term}`}
                        onClick={() => void saveGlossary(glossary.filter((row) => row.term !== item.term))}
                      >
                        ✕
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {glossaryNote ? <p className="mt-1 text-[11px] text-slate-500">{glossaryNote}</p> : null}
          <p className="mt-1 text-[11px] leading-4 text-slate-400">
            Preserve keeps the exact term untranslated. Allow English may be translated; leftover English for that
            term is not flagged.
          </p>
        </div>

        <div>
          <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            Translation & validation options
          </p>
          <div className="grid gap-x-3 gap-y-1.5 sm:grid-cols-2">
            {mandatoryOptions
              .filter((option) => option !== "run_semantic_qa" && option !== "qa_mode")
              .map((option) => (
                <label key={option} className="flex items-center gap-2 text-xs text-slate-700">
                  <input type="checkbox" checked disabled className="h-3.5 w-3.5 rounded border-slate-300 text-indigo-600" />
                  <span>{OPTION_LABELS[option] ?? option.replaceAll("_", " ")}</span>
                </label>
              ))}
            <label className="flex items-center justify-between gap-2 text-xs text-slate-800 sm:col-span-2">
              <span className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={qaMode === "foundry"}
                  onChange={() => setQaMode((prev) => (prev === "foundry" ? "classic" : "foundry"))}
                  className="h-3.5 w-3.5 rounded border-slate-300 text-indigo-600"
                />
                <span>Run semantic QA with Azure AI Foundry</span>
              </span>
              <button
                type="button"
                role="switch"
                aria-checked={qaMode === "foundry"}
                aria-label="Toggle Azure AI Foundry semantic QA"
                onClick={() => setQaMode((prev) => (prev === "foundry" ? "classic" : "foundry"))}
                className={`relative h-5 w-9 shrink-0 rounded-full transition ${
                  qaMode === "foundry" ? "bg-indigo-600" : "bg-slate-300"
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow transition ${
                    qaMode === "foundry" ? "translate-x-4" : "translate-x-0"
                  }`}
                />
              </button>
            </label>
            <label className="flex items-center justify-between gap-2 text-xs text-slate-800 sm:col-span-2">
              <span className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={nlQualityV2}
                  onChange={() => setNlQualityV2((prev) => !prev)}
                  className="h-3.5 w-3.5 rounded border-slate-300 text-indigo-600"
                />
                <span>Apply quality fixes (v2)</span>
              </span>
              <button
                type="button"
                role="switch"
                aria-checked={nlQualityV2}
                aria-label="Toggle quality fixes v2"
                onClick={() => setNlQualityV2((prev) => !prev)}
                className={`relative h-5 w-9 shrink-0 rounded-full transition ${
                  nlQualityV2 ? "bg-indigo-600" : "bg-slate-300"
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow transition ${
                    nlQualityV2 ? "translate-x-4" : "translate-x-0"
                  }`}
                />
              </button>
            </label>
          </div>
          <p className="mt-1.5 text-[11px] leading-4 text-slate-500">
            {qaMode === "foundry"
              ? "Foundry is on. Meaning checks use Azure OpenAI and can be rate limited."
              : selectedLanguage?.translate === false
                ? "English is copied through and the workbook Code column is set to en."
                : "Foundry is off. Translator, protected terms, and Python checks. Semantic accuracy still needs human review."}
          </p>
          {nlQualityV2 ? (
            <p className="mt-1 text-[11px] leading-4 text-amber-700">
              Quality v2 restores deadline quarters (including pipe-separated KRAs) and KRA measure
              numbering in code for every language. Dutch also gets stacked-deadline / Losen checks.
            </p>
          ) : null}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 px-5 py-3">
        <button
          type="button"
          className="tm-btn tm-btn-primary !px-3 !py-2 text-sm"
          disabled={!canStart}
          title={workerBusy ? "The worker is busy with another file." : undefined}
          onClick={() => void onStart()}
        >
          {busy ? "Starting…" : workerBusy ? "Worker busy" : "Start Localization"}
        </button>
        <button type="button" className="tm-btn tm-btn-ghost !px-3 !py-2 text-sm" onClick={onClear}>
          Clear
        </button>
        {workerBusy ? (
          <p className="text-[11px] text-slate-500">
            One file at a time. Wait for the current file to finish, or cancel it.
          </p>
        ) : null}
      </div>
    </SideDrawer>
  );
}
