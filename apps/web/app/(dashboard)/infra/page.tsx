"use client";

import { useEffect, useState, type ReactNode } from "react";

import { AppShell } from "@/components/AppShell";
import { ProductionForecast } from "@/components/ProductionForecast";
import { API_BASE } from "@/lib/api";
import {
  INFRA_SERVICES,
  INFRA_SNAPSHOT,
  MONTHLY_ACTIVE_USD,
  MONTHLY_FIXED_USD,
  POSTED_USD,
  RESOURCE_GROUP,
  TEN_DAY_FIXED_USD,
  money,
  type InfraService,
} from "@/lib/azure-infra";

const BILLING_LABEL: Record<InfraService["billing"], string> = {
  free: "Free",
  fixed: "Fixed SKU",
  usage: "Usage",
};

type InfraTab = "current" | "production";

export default function InfraPage() {
  const [email, setEmail] = useState<string | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [orgName, setOrgName] = useState<string | null>(null);
  const [tab, setTab] = useState<InfraTab>("current");
  const [selectedId, setSelectedId] = useState(INFRA_SERVICES[0]?.id ?? "");

  useEffect(() => {
    void fetch(`${API_BASE}/api/v1/auth/me`, { credentials: "include" })
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => {
        setEmail(body?.email ?? null);
        setRole(body?.memberships?.[0]?.role ?? null);
        setOrgName(body?.memberships?.[0]?.tenant_name ?? null);
      });
  }, []);

  const selected = INFRA_SERVICES.find((row) => row.id === selectedId) ?? INFRA_SERVICES[0];

  const tabs = (
    <div
      className="inline-flex rounded-xl border border-slate-200 bg-slate-50 p-1"
      role="tablist"
      aria-label="Infra views"
    >
      <TabButton active={tab === "current"} onClick={() => setTab("current")}>
        Current
      </TabButton>
      <TabButton active={tab === "production"} onClick={() => setTab("production")}>
        Production
      </TabButton>
    </div>
  );

  return (
    <AppShell email={email} role={role} orgName={orgName} title="Infra" action={tabs}>
      <p className="-mt-3 mb-3 max-w-3xl text-sm leading-5 text-slate-500">
        {tab === "current"
          ? `What is running in ${RESOURCE_GROUP} as of ${INFRA_SNAPSHOT}, with list-price estimates and Cost Management postings.`
          : "Quote a production month from the resumes and job profiles a client wants scored."}
      </p>

      {tab === "production" ? <ProductionForecast /> : null}

      {tab === "current" ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <div className="tm-card p-5">
              <p className="text-sm text-slate-500">Services</p>
              <p className="mt-3 text-3xl font-bold">{INFRA_SERVICES.length}</p>
              <p className="mt-1 text-xs text-slate-500">{RESOURCE_GROUP}</p>
            </div>
            <div className="tm-card p-5">
              <p className="text-sm text-slate-500">Monthly estimate</p>
              <p className="mt-3 text-3xl font-bold">{money(MONTHLY_FIXED_USD)}</p>
              <p className="mt-1 text-xs text-slate-500">Fixed SKUs, containers idle</p>
            </div>
            <div className="tm-card p-5">
              <p className="text-sm text-slate-500">10-day estimate</p>
              <p className="mt-3 text-3xl font-bold">{money(TEN_DAY_FIXED_USD)}</p>
              <p className="mt-1 text-xs text-slate-500">Same rates for 240 hours</p>
            </div>
            <div className="tm-card p-5">
              <p className="text-sm text-slate-500">October posted</p>
              <p className="mt-3 text-3xl font-bold">{money(POSTED_USD)}</p>
              <p className="mt-1 text-xs text-slate-500">Cost Management, still posting</p>
            </div>
          </div>

          <div className="tm-card mt-4 overflow-hidden">
            <div className="border-b border-slate-100 px-5 py-4">
              <h2 className="font-semibold">Services</h2>
              <p className="text-xs text-slate-500">Select a row for size, meters, and hosts.</p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-50 text-slate-500">
                  <tr>
                    <th className="px-5 py-3 font-semibold">Service</th>
                    <th className="px-5 py-3 font-semibold">Name</th>
                    <th className="px-5 py-3 font-semibold">Region</th>
                    <th className="px-5 py-3 font-semibold">Size</th>
                    <th className="px-5 py-3 font-semibold">Billing</th>
                    <th className="px-5 py-3 text-right font-semibold">Monthly</th>
                    <th className="px-5 py-3 text-right font-semibold">10 days</th>
                  </tr>
                </thead>
                <tbody>
                  {INFRA_SERVICES.map((row) => {
                    const active = row.id === selected?.id;
                    return (
                      <tr
                        key={row.id}
                        className={`cursor-pointer border-t border-slate-100 ${active ? "bg-indigo-50" : "hover:bg-slate-50"}`}
                        onClick={() => setSelectedId(row.id)}
                      >
                        <td className="px-5 py-3 font-medium text-slate-900">{row.service}</td>
                        <td className="px-5 py-3 text-slate-600">{row.name}</td>
                        <td className="px-5 py-3 text-slate-600">{row.region}</td>
                        <td className="px-5 py-3 text-slate-600">{row.size}</td>
                        <td className="px-5 py-3 text-slate-600">{BILLING_LABEL[row.billing]}</td>
                        <td className="px-5 py-3 text-right font-semibold">{money(row.monthlyUsd)}</td>
                        <td className="px-5 py-3 text-right">{money(row.tenDayUsd)}</td>
                      </tr>
                    );
                  })}
                  <tr className="border-t border-slate-200 bg-slate-50 font-semibold">
                    <td className="px-5 py-3" colSpan={5}>
                      Total fixed estimate
                    </td>
                    <td className="px-5 py-3 text-right">{money(MONTHLY_FIXED_USD)}</td>
                    <td className="px-5 py-3 text-right">{money(TEN_DAY_FIXED_USD)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {selected ? (
            <div className="tm-card mt-4 p-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-indigo-600">
                    {selected.service}
                  </p>
                  <h2 className="mt-1 text-lg font-semibold text-slate-950">{selected.name}</h2>
                  <p className="mt-1 text-sm text-slate-500">
                    {selected.region} · {selected.sku} · {selected.size}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-xs text-slate-500">Monthly list price</p>
                  <p className="text-2xl font-bold">{money(selected.monthlyUsd)}</p>
                </div>
              </div>
              <dl className="mt-5 grid gap-3 sm:grid-cols-2">
                {selected.details.map((item) => (
                  <div
                    key={item.label}
                    className="rounded-xl border border-slate-100 bg-slate-50 px-4 py-3"
                  >
                    <dt className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                      {item.label}
                    </dt>
                    <dd className="mt-1 text-sm text-slate-800">{item.value}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ) : null}

          <div className="tm-card mt-4 p-5 text-sm leading-6 text-slate-600">
            <h2 className="font-semibold text-slate-900">How the total is built</h2>
            <p className="mt-2">
              PostgreSQL $16.09 + Service Bus $9.81 + Container Registry $5.07 + Container Apps $16.12
              = {money(MONTHLY_FIXED_USD)} per month. The 10-day figure is {money(TEN_DAY_FIXED_USD)}.
            </p>
            <p className="mt-2">
              If the three container apps stay active for the whole month, Container Apps rises to
              $53.73 and the fixed total rises to {money(MONTHLY_ACTIVE_USD)}.
            </p>
            <p className="mt-2">
              Blob storage, Key Vault operations, Log Analytics past 5 GB, Service Bus messages, and
              gpt-4.1-mini tokens are usage charges. Foundry has a $10 monthly budget alert. October
              Cost Management has posted {money(POSTED_USD)} so far, including $0.0011 for a registry
              named meridianacr2610100151 that is no longer in the group. Container Apps and Key Vault
              have not posted a charge yet.
            </p>
          </div>
        </>
      ) : null}
    </AppShell>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      className={`rounded-lg px-4 py-2 text-sm font-semibold transition ${
        active
          ? "bg-white text-slate-950 shadow-sm"
          : "text-slate-500 hover:text-slate-800"
      }`}
      onClick={onClick}
    >
      {children}
    </button>
  );
}
