export function BarChart({
  values,
}: {
  values: Array<{ label: string; processed: number; failed: number; pending: number }>;
}) {
  const max = Math.max(1, ...values.flatMap((v) => [v.processed, v.failed, v.pending]));
  const empty = values.every((v) => v.processed + v.failed + v.pending === 0);

  if (empty) {
    return (
      <div className="grid h-52 place-items-center rounded-xl bg-slate-50 text-sm text-slate-500">
        No resume activity yet
      </div>
    );
  }

  return (
    <div className="flex h-52 items-end gap-3">
      {values.map((value) => {
        const total = value.processed + value.failed + value.pending;
        return (
          <div key={value.label} className="flex min-w-0 flex-1 flex-col items-center gap-2">
            <div className="flex h-40 w-full items-end justify-center gap-1">
              <div
                className="w-2.5 rounded-t bg-indigo-500 transition-all"
                style={{ height: `${(value.processed / max) * 100}%`, minHeight: value.processed ? 4 : 0 }}
                title={`Processed ${value.processed}`}
              />
              <div
                className="w-2.5 rounded-t bg-rose-400 transition-all"
                style={{ height: `${(value.failed / max) * 100}%`, minHeight: value.failed ? 4 : 0 }}
                title={`Failed ${value.failed}`}
              />
              <div
                className="w-2.5 rounded-t bg-amber-300 transition-all"
                style={{ height: `${(value.pending / max) * 100}%`, minHeight: value.pending ? 4 : 0 }}
                title={`Pending ${value.pending}`}
              />
            </div>
            <div className="text-center">
              <span className="block text-[11px] font-medium text-slate-600">{value.label}</span>
              <span className="block text-[10px] text-slate-400">{total}</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function StatusBreakdown({
  processed,
  failed,
  pending,
}: {
  processed: number;
  failed: number;
  pending: number;
}) {
  const total = Math.max(1, processed + failed + pending);
  return (
    <div className="space-y-3">
      <div className="flex h-3 overflow-hidden rounded-full bg-slate-100">
        <div className="bg-indigo-500" style={{ width: `${(processed / total) * 100}%` }} />
        <div className="bg-rose-400" style={{ width: `${(failed / total) * 100}%` }} />
        <div className="bg-amber-300" style={{ width: `${(pending / total) * 100}%` }} />
      </div>
      <div className="grid grid-cols-3 gap-2 text-sm">
        <div>
          <p className="text-xs text-slate-500">Processed</p>
          <p className="font-semibold text-slate-900">{processed}</p>
        </div>
        <div>
          <p className="text-xs text-slate-500">Failed</p>
          <p className="font-semibold text-slate-900">{failed}</p>
        </div>
        <div>
          <p className="text-xs text-slate-500">Pending</p>
          <p className="font-semibold text-slate-900">{pending}</p>
        </div>
      </div>
    </div>
  );
}

export function DonutChart({
  percent,
  label = "Credits used",
}: {
  percent: number;
  label?: string;
}) {
  const clamped = Math.max(0, Math.min(100, Math.round(percent)));
  const angle = clamped * 3.6;
  return (
    <div className="relative mx-auto grid h-40 w-40 place-items-center">
      <div
        className="absolute inset-0 rounded-full"
        style={{
          background: `conic-gradient(#6366f1 ${angle}deg, #e2e8f0 0deg)`,
        }}
      />
      <div className="absolute inset-4 rounded-full bg-white" />
      <div className="relative text-center">
        <p className="text-2xl font-bold text-slate-900">{clamped}%</p>
        <p className="text-xs text-slate-500">{label}</p>
      </div>
    </div>
  );
}

export function MatchBar({ score }: { score: number }) {
  const clamped = Math.max(0, Math.min(100, score));
  return (
    <div className="flex items-center gap-3">
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full bg-indigo-500"
          style={{ width: `${clamped}%` }}
        />
      </div>
      <span className="w-10 text-right text-sm font-semibold text-slate-900">{clamped}%</span>
    </div>
  );
}
