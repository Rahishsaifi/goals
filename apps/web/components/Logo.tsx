export function Logo({ light = false }: { light?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <span
        className="grid h-8 w-8 place-items-center rounded-lg"
        style={{ background: "linear-gradient(135deg, #818cf8, #6366f1)" }}
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
          <path d="M8 2L14 13H2L8 2Z" fill="white" />
        </svg>
      </span>
      <span className={`text-[1.05rem] font-bold tracking-tight ${light ? "text-white" : "text-slate-900"}`}>
        TalentMatch AI
      </span>
    </span>
  );
}
