"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { FormEvent, useState, type ReactNode } from "react";

import { Logo } from "@/components/Logo";
import { NotificationCenter } from "@/components/NotificationCenter";
import { SideDrawer } from "@/components/SideDrawer";
import { API_BASE, csrfToken } from "@/lib/api";
import { displayNameFromEmail } from "@/lib/format";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: "▦" },
  { href: "/jobs", label: "Job Profiles", icon: "☰" },
  { href: "/resumes", label: "Resumes", icon: "📄" },
  { href: "/evaluations", label: "Run AI matching", icon: "◎" },
  { href: "/candidates", label: "Candidates", icon: "◉" },
  { href: "/goals-localization", label: "Goals Translation", icon: "🌐" },
  { href: "/settings", label: "Settings", icon: "⚙" },
  { href: "/usage", label: "Usage & Costs", icon: "◔" },
  { href: "/infra", label: "Infra", icon: "▣" },
];

export function AppShell({
  children,
  email,
  role,
  orgName,
  title,
  action,
}: {
  children: ReactNode;
  email?: string | null;
  role?: string | null;
  orgName?: string | null;
  title?: string;
  action?: ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [loggingOut, setLoggingOut] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [query, setQuery] = useState("");
  const displayName = displayNameFromEmail(email);
  const roleLabel = role ? role.replaceAll("_", " ") : "Signed out";

  async function handleLogout() {
    setLoggingOut(true);
    try {
      await fetch(`${API_BASE}/api/v1/auth/logout`, {
        method: "POST",
        credentials: "include",
        headers: { "x-csrf-token": csrfToken() },
      });
    } finally {
      router.push("/login");
      router.refresh();
    }
  }

  function onSearch(event: FormEvent) {
    event.preventDefault();
    const q = query.trim();
    if (!q) {
      router.push("/candidates");
      return;
    }
    router.push(`/candidates?q=${encodeURIComponent(q)}`);
  }

  const nav = (
    <nav className="space-y-1 px-3 pb-8">
      {NAV.map((item) => {
        const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={() => setMobileOpen(false)}
            className={`tm-nav-link flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium ${
              active
                ? "bg-indigo-500 text-white shadow-lg shadow-indigo-900/30"
                : "text-slate-400 hover:bg-white/5 hover:text-white"
            }`}
          >
            <span className="w-4 text-center text-xs opacity-80">{item.icon}</span>
            {item.label}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <div className="min-h-screen bg-[var(--paper)] lg:grid lg:grid-cols-[248px_1fr]">
      <aside className="hidden border-r border-[var(--sidebar-border)] bg-[var(--sidebar)] text-slate-200 transition-colors duration-300 lg:block">
        <div className="px-5 py-5">
          <Link href="/dashboard">
            <Logo light />
          </Link>
          {orgName ? (
            <p className="mt-3 truncate text-xs text-slate-500">{orgName}</p>
          ) : null}
        </div>
        {nav}
      </aside>

      <SideDrawer
        open={mobileOpen}
        onClose={() => setMobileOpen(false)}
        side="left"
        dark
        widthClassName="w-72"
      >
        <div className="flex items-center justify-between px-5 py-5">
          <Logo light />
          <button
            type="button"
            className="rounded-lg px-2 py-1 text-slate-400 transition hover:bg-white/10 hover:text-white"
            onClick={() => setMobileOpen(false)}
          >
            ✕
          </button>
        </div>
        {nav}
      </SideDrawer>

      <div className="min-w-0">
        <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur">
          <div className="flex items-center justify-between gap-4 px-5 py-3 lg:px-8">
            <button
              type="button"
              className="rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold transition hover:bg-slate-50 lg:hidden"
              onClick={() => setMobileOpen(true)}
            >
              Menu
            </button>
            <form className="relative min-w-0 flex-1" onSubmit={onSearch}>
              <input
                className="w-full max-w-xl rounded-xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm outline-none transition focus:border-indigo-400 focus:bg-white"
                placeholder="Search candidates..."
                aria-label="Search candidates"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </form>
            <div className="flex items-center gap-3">
              <NotificationCenter />
              <div className="hidden text-right sm:block">
                <p className="text-sm font-semibold text-slate-900">{displayName}</p>
                <p className="text-xs capitalize text-slate-500">{roleLabel}</p>
              </div>
              <div className="grid h-10 w-10 place-items-center rounded-full bg-indigo-100 text-sm font-bold text-indigo-700">
                {displayName.slice(0, 1).toUpperCase()}
              </div>
              <button
                type="button"
                onClick={() => void handleLogout()}
                disabled={loggingOut}
                className="rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:opacity-60"
              >
                {loggingOut ? "Signing out…" : "Log out"}
              </button>
            </div>
          </div>
        </header>

        <main className="px-5 py-6 lg:px-8">
          {(title || action) && (
            <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
              {title ? (
                <h1 className="text-2xl font-bold tracking-tight text-slate-950">{title}</h1>
              ) : (
                <span />
              )}
              {action}
            </div>
          )}
          {children}
        </main>
      </div>
    </div>
  );
}
