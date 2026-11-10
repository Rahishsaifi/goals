import { StatusPill } from "@/components/StatusPill";
import { formatStatus } from "@/lib/format";

export type ScoreBreakdownItem = {
  key: string;
  display_name: string;
  description: string;
  weight: string;
  score: string;
  contribution: string;
  status: string;
  mandatory: boolean;
  passage: string | null;
  page_number: number | null;
};

const SEGMENT_COLORS = [
  "#4f46e5",
  "#0891b2",
  "#059669",
  "#d97706",
  "#db2777",
  "#7c3aed",
  "#0d9488",
  "#ea580c",
];

function strengthLabel(score: number): string {
  if (score >= 85) return "Strong";
  if (score >= 65) return "Good";
  if (score >= 40) return "Partial";
  return "Weak";
}

export function ScoreReport({
  overallScore,
  mandatoryStatus,
  reviewRequired,
  breakdown,
}: {
  overallScore: number;
  mandatoryStatus: string;
  reviewRequired: boolean;
  breakdown: ScoreBreakdownItem[];
}) {
  const items = breakdown.map((item, index) => ({
    ...item,
    weightNum: Number(item.weight),
    scoreNum: Number(item.score),
    contributionNum: Number(item.contribution),
    color: SEGMENT_COLORS[index % SEGMENT_COLORS.length]!,
  }));

  const sortedByScore = [...items].sort((a, b) => b.scoreNum - a.scoreNum);
  const strongest = sortedByScore[0];
  const weakest = sortedByScore[sortedByScore.length - 1];

  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-slate-200 bg-white p-3">
        <div className="flex items-baseline justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
              Match score
            </p>
            <p className="text-2xl font-bold text-slate-950">
              {Number.isNaN(overallScore) ? "—" : Math.round(overallScore)}
              <span className="text-sm font-semibold text-slate-400"> / 100</span>
            </p>
          </div>
          <p className="max-w-[14rem] text-right text-[11px] leading-snug text-slate-500">
            Mandatory{" "}
            <span className="font-semibold capitalize text-slate-800">
              {formatStatus(mandatoryStatus)}
            </span>
            {reviewRequired ? " · Review needed" : ""}
          </p>
        </div>

        {items.length > 0 ? (
          <div className="mt-2.5">
            <div className="flex h-2.5 overflow-hidden rounded-full bg-slate-100">
              {items.map((item) => {
                const width = Math.max(0, Math.min(100, item.contributionNum));
                if (width <= 0) return null;
                return (
                  <div
                    key={item.key}
                    title={`${item.display_name}: ${item.contributionNum.toFixed(1)} pts`}
                    style={{ width: `${width}%`, backgroundColor: item.color }}
                  />
                );
              })}
            </div>
            <div className="mt-1.5 flex flex-wrap gap-x-2.5 gap-y-0.5">
              {items.map((item) => (
                <span
                  key={item.key}
                  className="inline-flex items-center gap-1 text-[10px] text-slate-600"
                >
                  <i
                    className="inline-block h-1.5 w-1.5 rounded-full"
                    style={{ backgroundColor: item.color }}
                  />
                  {item.display_name}
                  <span className="font-semibold text-slate-800">
                    {item.contributionNum.toFixed(1)}
                  </span>
                </span>
              ))}
            </div>
          </div>
        ) : null}

        {strongest && weakest && items.length > 1 ? (
          <div className="mt-2 grid grid-cols-2 gap-1.5 text-[11px]">
            <div className="rounded-lg bg-emerald-50 px-2 py-1.5">
              <p className="font-semibold text-emerald-700">Strongest</p>
              <p className="truncate text-slate-900">{strongest.display_name}</p>
              <p className="text-slate-600">
                {Math.round(strongest.scoreNum)}% · +{strongest.contributionNum.toFixed(1)}
              </p>
            </div>
            <div className="rounded-lg bg-amber-50 px-2 py-1.5">
              <p className="font-semibold text-amber-700">Needs work</p>
              <p className="truncate text-slate-900">{weakest.display_name}</p>
              <p className="text-slate-600">
                {Math.round(weakest.scoreNum)}% · +{weakest.contributionNum.toFixed(1)}
              </p>
            </div>
          </div>
        ) : null}
      </div>

      <div className="space-y-2">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
          Requirements
        </p>
        {items.map((item) => {
          const matchPct = Math.max(0, Math.min(100, item.scoreNum));
          return (
            <div
              key={item.key}
              className="rounded-xl border border-slate-200 bg-white px-3 py-2.5"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <i
                      className="inline-block h-2 w-2 shrink-0 rounded-full"
                      style={{ backgroundColor: item.color }}
                    />
                    <p className="text-sm font-semibold text-slate-900">{item.display_name}</p>
                    {item.mandatory ? (
                      <span className="rounded-full bg-rose-50 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-rose-600">
                        Must
                      </span>
                    ) : null}
                    <StatusPill status={item.status} />
                  </div>
                </div>
                <p className="shrink-0 text-sm font-bold text-slate-900">
                  +{item.contributionNum.toFixed(1)}
                </p>
              </div>

              <div className="mt-1.5 flex items-center gap-2">
                <div className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${matchPct}%`, backgroundColor: item.color }}
                  />
                </div>
                <span className="shrink-0 text-[11px] text-slate-600">
                  {Math.round(matchPct)}% · {strengthLabel(matchPct)} · wt {item.weightNum}
                </span>
              </div>

              {item.passage ? (
                <p className="mt-1.5 line-clamp-2 text-[11px] leading-snug text-slate-600">
                  <span className="font-semibold text-slate-400">Evidence · </span>
                  “{item.passage}”
                </p>
              ) : (
                <p className="mt-1.5 text-[11px] text-slate-400">No evidence recorded.</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
