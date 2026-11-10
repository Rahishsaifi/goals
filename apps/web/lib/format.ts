export function formatPercent(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  const num = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(num)) {
    return "—";
  }
  return `${Math.round(num)}%`;
}

export function formatStatus(status: string): string {
  return status.replaceAll("_", " ");
}

export function statusPillClass(status: string): string {
  const normalized = status.toLowerCase();
  if (
    normalized === "ready" ||
    normalized === "completed" ||
    normalized === "completed_with_warnings" ||
    normalized === "active"
  ) {
    return "tm-pill tm-pill-success";
  }
  if (
    normalized === "running" ||
    normalized === "queued" ||
    normalized === "retrieving" ||
    normalized === "scoring" ||
    normalized === "uploaded" ||
    normalized === "processing"
  ) {
    return "tm-pill tm-pill-running";
  }
  if (normalized === "failed" || normalized === "cancelled") {
    return "tm-pill tm-pill-danger";
  }
  return "tm-pill tm-pill-muted";
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) {
    return "—";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  const deltaMs = Date.now() - date.getTime();
  const minutes = Math.round(deltaMs / 60000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 14) return `${days}d ago`;
  return date.toLocaleDateString();
}

export function displayNameFromEmail(email?: string | null): string {
  if (!email) return "Recruiter";
  const local = email.split("@")[0] ?? "Recruiter";
  return local
    .split(/[._-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
