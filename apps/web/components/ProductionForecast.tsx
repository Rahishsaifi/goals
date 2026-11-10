"use client";

import { useMemo, useState } from "react";

import { money } from "@/lib/azure-infra";
import {
  FORECAST_DEFAULTS,
  GPT41_MINI_DEFAULT_TPM,
  productionForecast,
  type ForecastInput,
} from "@/lib/production-forecast";

const PRESETS: { label: string; resumes: number; jobProfiles: number }[] = [
  { label: "2 lakh × 5 jobs", resumes: 200_000, jobProfiles: 5 },
  { label: "10,000 × 3 jobs", resumes: 10_000, jobProfiles: 3 },
  { label: "1,000 × 1 job", resumes: 1_000, jobProfiles: 1 },
];

function count(value: number): string {
  return Math.round(value).toLocaleString("en-US");
}

export function ProductionForecast() {
  const [input, setInput] = useState<ForecastInput>(FORECAST_DEFAULTS);
  const forecast = useMemo(() => productionForecast(input), [input]);

  function setNumber<K extends keyof ForecastInput>(key: K, value: string) {
    setInput((current) => ({ ...current, [key]: Number(value) }));
  }

  return (
    <section className="tm-card p-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-950">Production month quote</h2>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-slate-500">
            Enter the resumes and job profiles a client wants scored. The matcher parses each resume
            once, then scores all criteria for a job in one profile-based call. Prices are retail
            list prices for a production stack — not the current POC inventory.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {PRESETS.map((preset) => (
            <button
              key={preset.label}
              type="button"
              className="rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
              onClick={() =>
                setInput((current) => ({
                  ...current,
                  resumes: preset.resumes,
                  jobProfiles: preset.jobProfiles,
                }))
              }
            >
              {preset.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <label className="block text-sm font-medium text-slate-700">
          Resumes
          <input
            className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-normal outline-none focus:border-indigo-400"
            type="number"
            min={0}
            step={1000}
            value={input.resumes}
            onChange={(event) => setNumber("resumes", event.target.value)}
          />
        </label>
        <label className="block text-sm font-medium text-slate-700">
          Job profiles
          <input
            className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-normal outline-none focus:border-indigo-400"
            type="number"
            min={1}
            step={1}
            value={input.jobProfiles}
            onChange={(event) => setNumber("jobProfiles", event.target.value)}
          />
        </label>
        <label className="block text-sm font-medium text-slate-700">
          Criteria per job
          <input
            className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-normal outline-none focus:border-indigo-400"
            type="number"
            min={1}
            max={20}
            step={1}
            value={input.criteriaPerJob}
            onChange={(event) => setNumber("criteriaPerJob", event.target.value)}
          />
        </label>
        <label className="block text-sm font-medium text-slate-700">
          Finish within days
          <input
            className="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-normal outline-none focus:border-indigo-400"
            type="number"
            min={1}
            max={365}
            step={1}
            value={input.windowDays}
            onChange={(event) => setNumber("windowDays", event.target.value)}
          />
        </label>
      </div>

      <label className="mt-4 flex items-start gap-2 text-sm text-slate-700">
        <input
          type="checkbox"
          className="mt-1"
          checked={input.rescoreMonthly}
          onChange={(event) => setInput((current) => ({ ...current, rescoreMonthly: event.target.checked }))}
        />
        <span>Score this same batch against these jobs again every month</span>
      </label>

      <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-xl bg-slate-950 p-4 text-white">
          <p className="text-xs text-slate-300">This month</p>
          <p className="mt-2 text-3xl font-bold">{money(forecast.thisMonthUsd)}</p>
          <p className="mt-1 text-xs text-slate-400">Hosting plus this batch</p>
        </div>
        <div className="rounded-xl border border-slate-200 p-4">
          <p className="text-xs text-slate-500">Later months</p>
          <p className="mt-2 text-3xl font-bold text-slate-950">{money(forecast.laterMonthUsd)}</p>
          <p className="mt-1 text-xs text-slate-500">
            {input.rescoreMonthly ? "Hosting plus another full score" : "Hosting while the data stays online"}
          </p>
        </div>
        <div className="rounded-xl border border-slate-200 p-4">
          <p className="text-xs text-slate-500">Model batch</p>
          <p className="mt-2 text-3xl font-bold text-slate-950">{money(forecast.modelBatchUsd)}</p>
          <p className="mt-1 text-xs text-slate-500">gpt-4.1-mini list price</p>
        </div>
        <div className="rounded-xl border border-slate-200 p-4">
          <p className="text-xs text-slate-500">Score calls</p>
          <p className="mt-2 text-3xl font-bold text-slate-950">{count(forecast.scoreCalls)}</p>
          <p className="mt-1 text-xs text-slate-500">{count(forecast.parseCalls)} resume parses</p>
        </div>
      </div>

      <p className="mt-4 text-sm leading-6 text-slate-600">
        {count(input.resumes)} resumes × {count(input.jobProfiles)} job{" "}
        {input.jobProfiles === 1 ? "profile" : "profiles"} = {count(forecast.scoreCalls)} score
        calls ({count(input.criteriaPerJob)}{" "}
        {input.criteriaPerJob === 1 ? "criterion" : "criteria"} batched per call).
        Finishing in {count(input.windowDays)} days needs about {count(forecast.requiredTpm)} tokens per minute
        and {count(forecast.workerReplicas)} worker {forecast.workerReplicas === 1 ? "replica" : "replicas"}.
        gpt-4.1-mini Global Standard default quota is {count(GPT41_MINI_DEFAULT_TPM)} tokens per minute.
        {forecast.quotaCoversWindow
          ? " That quota covers this window."
          : " This window needs a quota increase before it can finish on time."}
      </p>

      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-slate-500">
            <tr>
              <th className="py-2 pr-4 font-semibold">Service</th>
              <th className="py-2 pr-4 font-semibold">Production size</th>
              <th className="py-2 pr-4 text-right font-semibold">This month</th>
              <th className="py-2 text-right font-semibold">Later months</th>
            </tr>
          </thead>
          <tbody>
            {forecast.lines.map((line) => (
              <tr key={line.id} className="border-t border-slate-100 align-top">
                <td className="py-3 pr-4">
                  <p className="font-medium text-slate-900">{line.service}</p>
                  <p className="text-xs text-slate-500">{line.sku}</p>
                </td>
                <td className="py-3 pr-4 text-slate-600">
                  <p>{line.size}</p>
                  <p className="mt-1 text-xs leading-5 text-slate-500">{line.note}</p>
                </td>
                <td className="py-3 pr-4 text-right font-semibold">{money(line.thisMonthUsd)}</td>
                <td className="py-3 text-right">{money(line.laterMonthUsd)}</td>
              </tr>
            ))}
            <tr className="border-t border-slate-200 font-semibold">
              <td className="py-3" colSpan={2}>
                Total
              </td>
              <td className="py-3 text-right">{money(forecast.thisMonthUsd)}</td>
              <td className="py-3 text-right">{money(forecast.laterMonthUsd)}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <details className="mt-4 rounded-xl border border-slate-200 px-4 py-3 text-sm text-slate-600">
        <summary className="cursor-pointer font-semibold text-slate-800">Planning assumptions</summary>
        <p className="mt-2 leading-6">
          Token totals use the prompt caps in the matcher: resume text up to 12,000 characters for a
          parse and 10,000 for each score, plus the system prompt. They are planning inputs, not a
          measured average from the usage ledger. Job-profile extraction is one extra call per job.
        </p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <Assumption
            label="Average file size (KB)"
            value={input.resumeFileKb}
            onChange={(value) => setNumber("resumeFileKb", value)}
          />
          <Assumption
            label="Extracted characters"
            value={input.extractedChars}
            onChange={(value) => setNumber("extractedChars", value)}
          />
          <Assumption
            label="Search document (KB)"
            value={input.searchDocKb}
            onChange={(value) => setNumber("searchDocKb", value)}
          />
          <Assumption
            label="Characters per token"
            value={input.charsPerToken}
            onChange={(value) => setNumber("charsPerToken", value)}
          />
          <Assumption
            label="Parse output tokens"
            value={input.parseOutputTokens}
            onChange={(value) => setNumber("parseOutputTokens", value)}
          />
          <Assumption
            label="Score output tokens"
            value={input.scoreOutputTokens}
            onChange={(value) => setNumber("scoreOutputTokens", value)}
          />
          <Assumption
            label="Seconds per model call"
            value={input.secondsPerCall}
            onChange={(value) => setNumber("secondsPerCall", value)}
          />
        </div>
        <label className="mt-3 flex items-start gap-2">
          <input
            type="checkbox"
            className="mt-1"
            checked={input.zoneRedundantDb}
            onChange={(event) =>
              setInput((current) => ({ ...current, zoneRedundantDb: event.target.checked }))
            }
          />
          <span>Zone-redundant database standby</span>
        </label>
      </details>
    </section>
  );
}

function Assumption({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block text-xs font-semibold uppercase tracking-wide text-slate-500">
      {label}
      <input
        className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-normal normal-case tracking-normal text-slate-800 outline-none focus:border-indigo-400"
        type="number"
        min={0}
        step="any"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}
