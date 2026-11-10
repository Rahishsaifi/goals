import Link from "next/link";

import { GraphField } from "@/components/GraphField";
import { Logo } from "@/components/Logo";
import { Reveal } from "@/components/Reveal";
import { SiteHeader } from "@/components/SiteHeader";
import { productTagline } from "@/lib/status-label";

const features = [
  {
    title: "Intelligent matching",
    body: "Rank every ready resume against a role, with the weights your team set.",
    nodes: ["#f6c56b", "#ffffff", "#8ee7dc"],
  },
  {
    title: "Evidence you can open",
    body: "Each criterion keeps the passage it came from. Missing evidence stays unknown.",
    nodes: ["#c4b5fd", "#ffffff", "#93c5fd"],
  },
  {
    title: "Controls that stay with you",
    body: "Mandatory rules, review policies, audit history, and access by role.",
    nodes: ["#fb923c", "#ffffff", "#8ee7dc"],
  },
];

const steps = [
  { title: "Upload", body: "Bring in job descriptions and resumes. Parsing stays in your workspace." },
  { title: "Configure", body: "Set weights and mark what a hire must show." },
  { title: "Match", body: "Score the pool. The model assesses evidence. The score itself is deterministic." },
  { title: "Review", body: "Open the shortlist, check the passages, and export the decision." },
];

const ribbon = [
  "Job profiles",
  "Weighted criteria",
  "Resume evidence",
  "Mandatory rules",
  "Ranked shortlists",
  "Audit history",
  "Tenant isolation",
  "Role-based access",
];

export default function HomePage() {
  const words = productTagline().split(" ");

  return (
    <div className="overflow-x-hidden bg-black text-white">
      <SiteHeader />

      <section className="relative min-h-[100svh]">
        <GraphField className="absolute inset-0 h-full w-full" />
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_72%_38%,rgba(56,90,140,0.28),transparent_36%),linear-gradient(180deg,rgba(0,0,0,0.2),rgba(0,0,0,0.78))]" />
        <div className="pointer-events-none absolute inset-y-0 left-0 w-full bg-gradient-to-r from-black via-black/75 to-transparent md:w-[68%]" />
        <div className="relative z-10 flex min-h-[100svh] items-end">
          <div className="tm-container pb-16 pt-28 sm:pb-20">
            <p className="tm-fade text-sm font-medium tracking-[0.18em] text-white/70 uppercase">
              Recruitment intelligence
            </p>
            <h1 className="mt-5 max-w-5xl text-5xl leading-[0.96] font-medium tracking-[-0.045em] sm:text-7xl lg:text-8xl">
              {words.map((word, index) => (
                <span key={`${word}-${index}`} className="tm-word" style={{ animationDelay: `${120 + index * 90}ms` }}>
                  {word}
                </span>
              ))}
            </h1>
            <p className="tm-fade mt-6 max-w-xl text-base leading-7 text-white/75 sm:text-lg" style={{ animationDelay: "640ms" }}>
              Analyze job requirements, score candidates against your criteria, and review evidence-backed
              shortlists in one secure workspace.
            </p>
            <div className="tm-fade mt-8 flex flex-wrap gap-3" style={{ animationDelay: "760ms" }}>
              <Link href="/login" className="rounded-full bg-white px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-slate-100">
                Get started
              </Link>
              <Link
                href="/dashboard"
                className="rounded-full border border-white/30 px-5 py-3 text-sm font-semibold text-white transition hover:bg-white/10"
              >
                Open workspace
              </Link>
            </div>
          </div>
        </div>
      </section>

      <section className="border-y border-white/10 bg-black py-5" aria-label="Product areas">
        <div className="tm-marquee">
          <div className="tm-marquee-track">
            {[...ribbon, ...ribbon].map((item, index) => (
              <span key={`${item}-${index}`} className="mx-8 text-sm font-medium tracking-wide text-white/70">
                {item}
                <span className="ml-8 inline-block h-1.5 w-1.5 rounded-full bg-amber-200/80 align-middle" />
              </span>
            ))}
          </div>
        </div>
      </section>

      <section id="product" className="bg-white py-24 text-slate-950">
        <div className="tm-container">
          <Reveal>
            <p className="text-sm font-semibold tracking-[0.16em] text-slate-500 uppercase">The shortlist layer</p>
            <h2 className="mt-4 max-w-3xl text-4xl leading-[1.05] font-medium tracking-[-0.04em] sm:text-6xl">
              Every match keeps the relationship that produced it.
            </h2>
          </Reveal>
          <div className="mt-14 grid gap-5 lg:grid-cols-3">
            {features.map((feature, index) => (
              <Reveal key={feature.title} delay={index * 90}>
                <article className="group relative h-full overflow-hidden rounded-3xl border border-slate-200 bg-slate-50 p-6 transition duration-300 hover:-translate-y-1 hover:shadow-xl hover:shadow-slate-200/80">
                  <Constellation colors={feature.nodes} />
                  <h3 className="relative mt-16 text-2xl font-medium tracking-tight">{feature.title}</h3>
                  <p className="relative mt-3 text-sm leading-6 text-slate-600">{feature.body}</p>
                </article>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section id="how" className="relative overflow-hidden bg-[#071018] py-24 text-white">
        <GraphField className="absolute inset-0 h-full w-full opacity-50" />
        <div className="absolute inset-0 bg-[#071018]/75" />
        <div className="tm-container relative">
          <Reveal>
            <p className="text-sm font-semibold tracking-[0.16em] text-white/60 uppercase">How it works</p>
            <h2 className="mt-4 max-w-2xl text-4xl leading-[1.05] font-medium tracking-[-0.04em] sm:text-5xl">
              From upload to a shortlist you can defend.
            </h2>
          </Reveal>
          <div className="mt-14 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {steps.map((step, index) => (
              <Reveal key={step.title} delay={index * 80}>
                <article className="h-full rounded-3xl border border-white/10 bg-white/5 p-6 backdrop-blur-sm">
                  <p className="text-sm font-semibold text-amber-200">0{index + 1}</p>
                  <h3 className="mt-6 text-2xl font-medium">{step.title}</h3>
                  <p className="mt-3 text-sm leading-6 text-white/70">{step.body}</p>
                </article>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      <section id="trust" className="bg-white py-24 text-slate-950">
        <div className="tm-container grid items-center gap-12 lg:grid-cols-[1.1fr_0.9fr]">
          <Reveal>
            <p className="text-sm font-semibold tracking-[0.16em] text-slate-500 uppercase">Built to be checked</p>
            <h2 className="mt-4 text-4xl leading-[1.05] font-medium tracking-[-0.04em] sm:text-6xl">
              A score without a source is not a decision.
            </h2>
            <ul className="mt-8 space-y-4 text-base leading-7 text-slate-600">
              <li>Tenant, role, and ownership come from the server session.</li>
              <li>Weighted scores are computed in deterministic code.</li>
              <li>Models extract and assess evidence. They do not invent the final rank.</li>
            </ul>
            <Link href="/login" className="mt-8 inline-flex rounded-full bg-slate-950 px-5 py-3 text-sm font-semibold text-white transition hover:bg-slate-800">
              Get started
            </Link>
          </Reveal>
          <Reveal delay={120}>
            <ScorePreview />
          </Reveal>
        </div>
      </section>

      <section className="relative overflow-hidden bg-black py-28">
        <GraphField className="absolute inset-0 h-full w-full opacity-80" />
        <div className="absolute inset-0 bg-gradient-to-b from-black/30 via-black/55 to-black" />
        <div className="tm-container relative text-center">
          <Reveal>
            <h2 className="mx-auto max-w-4xl text-4xl leading-[1.02] font-medium tracking-[-0.045em] sm:text-6xl">
              Go from a pile of resumes to a shortlist with a trail.
            </h2>
            <div className="mt-8 flex flex-wrap justify-center gap-3">
              <Link href="/login" className="rounded-full bg-white px-5 py-3 text-sm font-semibold text-slate-950 transition hover:bg-slate-100">
                Get started
              </Link>
              <Link href="/login" className="rounded-full border border-white/30 px-5 py-3 text-sm font-semibold text-white transition hover:bg-white/10">
                Sign in
              </Link>
            </div>
          </Reveal>
        </div>
      </section>

      <footer className="border-t border-white/10 bg-black py-8">
        <div className="tm-container flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <Logo light />
          <p className="text-sm text-white/50">© {new Date().getFullYear()} TalentMatch AI</p>
        </div>
      </footer>
    </div>
  );
}

function Constellation({ colors }: { colors: string[] }) {
  return (
    <svg viewBox="0 0 280 120" className="h-28 w-full" aria-hidden>
      <line x1="36" y1="78" x2="120" y2="36" className="tm-edge" stroke={colors[0]} />
      <line x1="120" y1="36" x2="210" y2="70" className="tm-edge" stroke={colors[1]} style={{ animationDelay: "0.4s" }} />
      <line x1="210" y1="70" x2="246" y2="28" className="tm-edge" stroke={colors[2]} style={{ animationDelay: "0.8s" }} />
      <line x1="120" y1="36" x2="168" y2="96" className="tm-edge" stroke={colors[0]} style={{ animationDelay: "1.1s" }} />
      {[
        [36, 78, colors[0]],
        [120, 36, colors[1]],
        [210, 70, colors[2]],
        [246, 28, colors[0]],
        [168, 96, colors[1]],
      ].map(([x, y, color], index) => (
        <circle
          key={`${x}-${y}`}
          cx={Number(x)}
          cy={Number(y)}
          r={index === 1 ? 7 : 4}
          fill={String(color)}
          className="tm-node"
          style={{ animationDelay: `${index * 0.25}s` }}
        />
      ))}
    </svg>
  );
}

function ScorePreview() {
  const bars = [
    ["Technical skills", 95],
    ["Experience", 88],
    ["Domain fit", 90],
  ];
  return (
    <div className="tm-float rounded-[28px] border border-slate-200 bg-white p-6 shadow-2xl shadow-slate-200/70">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold tracking-wide text-slate-500 uppercase">Sample shortlist</p>
          <p className="mt-3 text-lg font-semibold">Priya Sharma</p>
          <p className="text-sm text-slate-500">Senior Python Developer</p>
        </div>
        <div className="grid h-16 w-16 place-items-center rounded-full border-4 border-slate-950 text-sm font-bold">
          92%
        </div>
      </div>
      <div className="mt-6 space-y-3">
        {bars.map(([label, value], index) => (
          <div key={String(label)}>
            <div className="mb-1 flex justify-between text-xs text-slate-500">
              <span>{label}</span>
              <span>{value}%</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-slate-100">
              <div
                className="tm-bar h-1.5 rounded-full bg-slate-950"
                style={{ width: `${value}%`, animationDelay: `${index * 180}ms` }}
              />
            </div>
          </div>
        ))}
      </div>
      <p className="mt-5 text-xs leading-5 text-slate-500">
        FastAPI · PostgreSQL · evidence linked back to the resume passage.
      </p>
    </div>
  );
}
