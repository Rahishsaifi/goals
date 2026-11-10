"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useState } from "react";

import { Logo } from "@/components/Logo";
import { API_BASE } from "@/lib/api";

function safeNextPath(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) {
    return "/dashboard";
  }
  return raw;
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [organization, setOrganization] = useState("demo");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/v1/auth/login`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          email,
          password,
          tenant_slug: organization.trim().toLowerCase(),
        }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        setError(body?.error?.message ?? "Sign-in failed.");
        return;
      }
      router.push(safeNextPath(searchParams.get("next")));
    } catch {
      setError("Unable to reach the server. Try again in a moment.");
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="grid min-h-screen lg:grid-cols-2">
      <section className="relative hidden overflow-hidden bg-slate-950 px-12 py-16 text-white lg:flex lg:flex-col lg:justify-between">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-70"
          style={{
            background:
              "radial-gradient(circle at 20% 20%, rgba(99,102,241,0.45), transparent 42%), radial-gradient(circle at 80% 80%, rgba(79,70,229,0.35), transparent 40%)",
          }}
        />
        <div className="relative">
          <Logo light />
          <h1 className="mt-10 max-w-md text-4xl font-bold tracking-tight">
            Find the right talent, faster.
          </h1>
          <p className="mt-4 max-w-sm text-sm leading-6 text-slate-300">
            Secure organization sign-in for recruiters and hiring teams.
          </p>
        </div>
        <p className="relative text-sm text-slate-400">Enterprise recruitment workspace</p>
      </section>

      <section className="flex items-center justify-center bg-white px-6 py-16">
        <div className="w-full max-w-md">
          <div className="lg:hidden">
            <Logo />
          </div>
          <h1 className="mt-6 text-3xl font-bold tracking-tight text-slate-950">Sign in</h1>
          <p className="mt-2 text-sm text-slate-500">Use your work email and organization code.</p>
          <form className="mt-8 space-y-4" onSubmit={onSubmit}>
            <label className="block text-sm font-semibold text-slate-700">
              Work email
              <input
                className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 outline-none focus:border-indigo-400"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </label>
            <label className="block text-sm font-semibold text-slate-700">
              Password
              <input
                className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 outline-none focus:border-indigo-400"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </label>
            <label className="block text-sm font-semibold text-slate-700">
              Organization
              <input
                className="mt-1.5 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 outline-none focus:border-indigo-400 focus:bg-white"
                value={organization}
                onChange={(e) => setOrganization(e.target.value)}
                placeholder="demo"
                required
              />
              <span className="mt-1 block text-xs font-normal text-slate-500">
                Default workspace: demo
              </span>
            </label>
            {error ? <p className="text-sm text-rose-600">{error}</p> : null}
            <button className="tm-btn tm-btn-primary w-full" disabled={pending} type="submit">
              {pending ? "Signing in…" : "Continue"}
            </button>
          </form>
          <p className="mt-6 text-sm text-slate-500">
            <Link href="/" className="font-semibold text-indigo-600 hover:text-indigo-700">
              Back to home
            </Link>
          </p>
        </div>
      </section>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<main className="min-h-screen bg-white" />}>
      <LoginForm />
    </Suspense>
  );
}
