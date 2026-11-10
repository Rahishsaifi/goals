"use client";

import { useEffect, useState, type ReactNode } from "react";

export function SideDrawer({
  open,
  onClose,
  children,
  widthClassName = "w-full max-w-md",
  side = "right",
  dark = false,
  nested = false,
}: {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  widthClassName?: string;
  side?: "left" | "right";
  dark?: boolean;
  /** Stack above another drawer and claim Escape first. */
  nested?: boolean;
}) {
  const [mounted, setMounted] = useState(open);
  const [entered, setEntered] = useState(false);

  useEffect(() => {
    if (open) {
      setMounted(true);
      const id = window.requestAnimationFrame(() => {
        window.requestAnimationFrame(() => setEntered(true));
      });
      return () => window.cancelAnimationFrame(id);
    }
    setEntered(false);
    const timer = window.setTimeout(() => setMounted(false), 280);
    return () => window.clearTimeout(timer);
  }, [open]);

  useEffect(() => {
    if (!mounted) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (nested) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
      onClose();
    };
    window.addEventListener("keydown", onKey, nested);
    return () => window.removeEventListener("keydown", onKey, nested);
  }, [mounted, onClose, nested]);

  if (!mounted) return null;

  const panelFrom =
    side === "right"
      ? entered
        ? "translate-x-0"
        : "translate-x-full"
      : entered
        ? "translate-x-0"
        : "-translate-x-full";

  return (
    <div
      className={`tm-drawer fixed inset-0 flex ${nested ? "z-[60]" : "z-50"}`}
      data-side={side}
    >
      <button
        type="button"
        className={`tm-drawer-backdrop absolute inset-0 bg-slate-950/45 backdrop-blur-[2px] transition-opacity ease-out ${
          entered ? "opacity-100" : "opacity-0"
        }`}
        aria-label="Close panel"
        onClick={onClose}
      />
      <aside
        className={`tm-drawer-panel relative z-10 flex h-full min-w-0 flex-col shadow-2xl transition-transform ease-[cubic-bezier(0.22,1,0.36,1)] ${
          dark ? "bg-[var(--sidebar)] text-slate-200" : "bg-white"
        } ${side === "right" ? "ml-auto" : "mr-auto"} ${widthClassName} ${panelFrom}`}
        role="dialog"
        aria-modal="true"
      >
        {children}
      </aside>
    </div>
  );
}
