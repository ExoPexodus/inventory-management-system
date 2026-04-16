"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/ui/primitives";

type BillingStatus = {
  subscription_status: string;
  plan_codename: string;
  billing_cycle: string | null;
  active_addons: string[];
  max_shops: number;
  max_employees: number;
  storage_limit_mb: number;
  trial_ends_at: string | null;
  current_period_end: string | null;
  grace_period_days: number;
  is_in_grace_period: boolean;
  last_synced_at: string | null;
};

type Usage = {
  shops_used: number;
  shops_limit: number;
  employees_used: number;
  employees_limit: number;
  storage_used_mb: number;
  storage_limit_mb: number;
};

function statusBadge(status: string) {
  const s = status.toLowerCase();
  if (s === "active") return "bg-tertiary-fixed text-on-tertiary-fixed-variant";
  if (s === "trial") return "bg-primary/10 text-primary";
  if (s === "past_due" || s === "expired") return "bg-error-container text-on-error-container";
  if (s === "suspended" || s === "cancelled") return "bg-surface-container-highest text-on-surface";
  return "bg-surface-container-high text-on-surface-variant";
}

function statusLabel(status: string) {
  return status.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function UsageMeter({ label, used, limit, icon }: { label: string; used: number; limit: number; icon: string }) {
  const pct = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  const isNearLimit = pct >= 80;
  return (
    <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-5 shadow-sm">
      <div className="flex items-center gap-2">
        <span className="material-symbols-outlined text-lg text-on-surface-variant">{icon}</span>
        <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">{label}</p>
      </div>
      <div className="mt-3 flex items-end justify-between">
        <p className="font-headline text-2xl font-extrabold text-on-surface">
          {used} <span className="text-base font-normal text-on-surface-variant">/ {limit}</span>
        </p>
        <p className={`text-sm font-bold ${isNearLimit ? "text-error" : "text-on-surface-variant"}`}>{pct}%</p>
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-surface-container-high">
        <div
          className={`h-full rounded-full transition-all ${isNearLimit ? "bg-error" : "bg-primary"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export default function BillingPage() {
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const [bRes, uRes] = await Promise.all([
          fetch("/api/ims/v1/admin/billing/status"),
          fetch("/api/ims/v1/admin/billing/usage"),
        ]);
        if (!bRes.ok || !uRes.ok) throw new Error("Failed to load billing data");
        setBilling(await bRes.json());
        setUsage(await uRes.json());
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Failed to load");
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, []);

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="Subscription & usage"
        title="Billing"
        subtitle="View your current plan, track resource usage, and manage your subscription."
        action={
          <div className="flex gap-2">
            <Link
              href="/billing/invoices"
              className="inline-flex items-center gap-2 rounded-lg border border-outline-variant/20 bg-surface-container px-5 py-2.5 text-sm font-semibold text-on-surface transition hover:bg-surface-container-high"
            >
              <span className="material-symbols-outlined text-lg">receipt_long</span>
              Invoices
            </Link>
            <Link
              href="/billing/downloads"
              className="inline-flex items-center gap-2 rounded-lg border border-outline-variant/20 bg-surface-container px-5 py-2.5 text-sm font-semibold text-on-surface transition hover:bg-surface-container-high"
            >
              <span className="material-symbols-outlined text-lg">phone_android</span>
              App Downloads
            </Link>
          </div>
        }
      />

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        </div>
      ) : err ? (
        <div className="rounded-xl border border-error/20 bg-error-container/30 p-8 text-center">
          <span className="material-symbols-outlined text-4xl text-error">cloud_off</span>
          <p className="mt-2 text-sm text-on-error-container">{err}</p>
        </div>
      ) : (
        <>
          {/* Subscription status card */}
          {billing ? (
            <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Current plan</p>
                  <h2 className="mt-1 font-headline text-2xl font-extrabold text-on-surface capitalize">
                    {billing.plan_codename}
                  </h2>
                  <div className="mt-2 flex items-center gap-3">
                    <span className={`inline-flex rounded-full px-3 py-1 text-xs font-bold uppercase ${statusBadge(billing.subscription_status)}`}>
                      {statusLabel(billing.subscription_status)}
                    </span>
                    {billing.billing_cycle ? (
                      <span className="text-sm text-on-surface-variant capitalize">{billing.billing_cycle} billing</span>
                    ) : null}
                  </div>
                </div>
                <div className="text-right">
                  {billing.subscription_status === "trial" && billing.trial_ends_at ? (
                    <div>
                      <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Trial ends</p>
                      <p className="mt-1 text-sm font-semibold text-on-surface">
                        {new Date(billing.trial_ends_at).toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" })}
                      </p>
                    </div>
                  ) : billing.current_period_end ? (
                    <div>
                      <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Renews</p>
                      <p className="mt-1 text-sm font-semibold text-on-surface">
                        {new Date(billing.current_period_end).toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" })}
                      </p>
                    </div>
                  ) : null}
                </div>
              </div>

              {billing.is_in_grace_period ? (
                <div className="mt-4 rounded-lg border border-error/20 bg-error-container/30 px-4 py-3">
                  <div className="flex items-center gap-2">
                    <span className="material-symbols-outlined text-error">warning</span>
                    <p className="text-sm font-semibold text-on-error-container">
                      Payment overdue — your subscription will expire in {billing.grace_period_days} days.
                    </p>
                  </div>
                </div>
              ) : null}

              {billing.active_addons.length > 0 ? (
                <div className="mt-4">
                  <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Active add-ons</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {billing.active_addons.map((a) => (
                      <span
                        key={a}
                        className="inline-flex rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary capitalize"
                      >
                        {a.replace(/_/g, " ")}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}
            </section>
          ) : null}

          {/* Usage meters */}
          {usage ? (
            <section>
              <h3 className="mb-4 text-xs font-bold uppercase tracking-widest text-on-surface-variant">Resource usage</h3>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                <UsageMeter label="Shops" used={usage.shops_used} limit={usage.shops_limit} icon="storefront" />
                <UsageMeter label="Employees" used={usage.employees_used} limit={usage.employees_limit} icon="badge" />
                <UsageMeter label="Storage (MB)" used={usage.storage_used_mb} limit={usage.storage_limit_mb} icon="cloud" />
              </div>
            </section>
          ) : null}
        </>
      )}
    </div>
  );
}
