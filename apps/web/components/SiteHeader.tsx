"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { Logo } from "@/components/Logo";

const LINKS = [
  { href: "#product", label: "Product" },
  { href: "#how", label: "How it works" },
  { href: "#trust", label: "Trust" },
];

export function SiteHeader() {
  const [solid, setSolid] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setSolid(window.scrollY > 20);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`fixed inset-x-0 top-0 z-40 transition-colors duration-300 ${
        solid || open ? "border-b border-slate-200 bg-white/95 text-slate-900 backdrop-blur" : "text-white"
      }`}
    >
      <div className="tm-container flex h-16 items-center justify-between gap-4">
        <Link href="/" aria-label="TalentMatch AI home">
          <Logo light={!solid && !open} />
        </Link>
        <nav className="hidden items-center gap-7 text-sm font-medium md:flex">
          {LINKS.map((link) => (
            <a key={link.href} href={link.href} className="opacity-80 transition hover:opacity-100">
              {link.label}
            </a>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <Link
            href="/login"
            className={`hidden px-3 py-2 text-sm font-semibold sm:inline ${solid ? "text-slate-600" : "text-white/80"}`}
          >
            Sign in
          </Link>
          <Link
            href="/login"
            className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
              solid ? "bg-slate-950 text-white hover:bg-slate-800" : "bg-white text-slate-950 hover:bg-slate-100"
            }`}
          >
            Get started
          </Link>
          <button
            type="button"
            className="rounded-full px-3 py-2 text-sm font-semibold md:hidden"
            aria-expanded={open}
            onClick={() => setOpen((value) => !value)}
          >
            {open ? "Close" : "Menu"}
          </button>
        </div>
      </div>
      {open ? (
        <div className="border-t border-slate-200 px-6 py-3 md:hidden">
          {LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="block py-2 text-sm font-semibold"
              onClick={() => setOpen(false)}
            >
              {link.label}
            </a>
          ))}
        </div>
      ) : null}
    </header>
  );
}
