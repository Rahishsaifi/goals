import { formatStatus, statusPillClass } from "@/lib/format";

const ACTIVE = new Set([
  "queued",
  "running",
  "retrieving",
  "scoring",
  "uploaded",
  "processing",
]);

function StatusIcon({ status }: { status: string }) {
  const normalized = status.toLowerCase();

  if (ACTIVE.has(normalized)) {
    return (
      <span className="tm-status-spin" aria-hidden>
        <svg viewBox="0 0 16 16" fill="none" className="h-3 w-3">
          <circle
            cx="8"
            cy="8"
            r="6"
            stroke="currentColor"
            strokeOpacity="0.25"
            strokeWidth="2"
          />
          <path
            d="M14 8a6 6 0 0 0-6-6"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
      </span>
    );
  }

  if (
    normalized === "ready" ||
    normalized === "completed" ||
    normalized === "completed_with_warnings" ||
    normalized === "active"
  ) {
    return (
      <span aria-hidden className="inline-flex">
        <svg viewBox="0 0 16 16" fill="none" className="h-3 w-3">
          <path
            d="M3.5 8.5 6.5 11.5 12.5 4.5"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
    );
  }

  if (normalized === "failed" || normalized === "cancelled") {
    return (
      <span aria-hidden className="inline-flex">
        <svg viewBox="0 0 16 16" fill="none" className="h-3 w-3">
          <path
            d="M4 4l8 8M12 4l-8 8"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
      </span>
    );
  }

  return null;
}

export function StatusPill({ status }: { status: string }) {
  return (
    <span className={`${statusPillClass(status)} gap-1.5`}>
      <StatusIcon status={status} />
      {formatStatus(status)}
    </span>
  );
}
