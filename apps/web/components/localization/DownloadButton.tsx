"use client";

import { useEffect, useState, type ReactNode } from "react";

const LOADING_MS = 3000;

export function DownloadButton({
  href,
  icon,
  label,
  className,
}: {
  href: string;
  icon: ReactNode;
  label: string;
  className: string;
}) {
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    if (!downloading) return;
    const timer = setTimeout(() => setDownloading(false), LOADING_MS);
    return () => clearTimeout(timer);
  }, [downloading]);

  return (
    <a
      href={href}
      aria-busy={downloading}
      aria-disabled={downloading}
      onClick={(event) => {
        if (downloading) {
          event.preventDefault();
          return;
        }
        setDownloading(true);
      }}
      className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition duration-150 active:translate-y-px active:scale-[0.97] active:shadow-inner ${className} ${
        downloading ? "pointer-events-none translate-y-px scale-[0.97] cursor-wait opacity-80 shadow-inner" : ""
      }`}
    >
      {downloading ? (
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden="true" />
      ) : (
        icon
      )}
      {downloading ? "Downloading…" : label}
    </a>
  );
}
