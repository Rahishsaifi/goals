export function ExcelFileIcon({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path d="M6 2h9l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" fill="#21A366" />
      <path d="M15 2v5h5z" fill="#107C41" />
      <rect x="2" y="9" width="11" height="11" rx="1.5" fill="#185C37" />
      <path
        d="M5 11.6l1.6 2.4L5 16.4h1.4l.95-1.5.95 1.5h1.4l-1.6-2.4 1.6-2.4H8.3l-.95 1.5-.95-1.5z"
        fill="#fff"
      />
      <path d="M15 12h3M15 15h3M15 18h3" stroke="#fff" strokeOpacity={0.7} strokeWidth={1.2} strokeLinecap="round" />
    </svg>
  );
}

export function ExcelIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={1.8} aria-hidden="true">
      <rect x="3.5" y="3.5" width="17" height="17" rx="2.5" />
      <path d="M8 8l8 8M16 8l-8 8" strokeLinecap="round" />
    </svg>
  );
}

export function ReportIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={1.8} aria-hidden="true">
      <path d="M7 3h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z" strokeLinejoin="round" />
      <path d="M14 3v5h5" strokeLinejoin="round" />
      <path d="M8.5 14.5l2 2 4-4.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IssueRowsIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={1.8} aria-hidden="true">
      <path d="M12 3.5l9 16H3z" strokeLinejoin="round" />
      <path d="M12 10v4.5M12 17.2v.1" strokeLinecap="round" />
    </svg>
  );
}

export function LogsIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={1.8} aria-hidden="true">
      <rect x="3" y="4" width="18" height="16" rx="2.5" />
      <path d="M7 9l3 3-3 3M12.5 15H17" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
