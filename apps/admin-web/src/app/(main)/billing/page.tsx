"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/ui/primitives";
import { useCurrency } from "@/lib/currency-context";
import { formatMoney } from "@/lib/format";

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
};

type Usage = { shops_used: number; shops_limit: number; employees_used: number; employees_limit: number; storage_used_mb: number; storage_limit_mb: number };

type PlanOption = { id: string; codename: string; display_name: string; description: string | null; base_price_cents: number; currency_code: string; yearly_discount_pct: number; max_shops: number; max_employees: number; storage_limit_mb: number };

type AddonOption = { id: string; codename: string; display_name: string; description: string | null; price_cents: number; currency_code: string; is_active_on_subscription: boolean };

type BillingDetails = { company_name: string | null; gstin: string | null; address_line1: string | null; address_line2: string | null; city: string | null; state: string | null; postal_code: string | null; country: string | null };

function statusBadge(status: string) {
  const s = status.toLowerCase();
  if (s === "active") return "bg-tertiary-fixed text-on-tertiary-fixed-variant";
  if (s === "trial") return "bg-primary/10 text-primary";
  if (s === "past_due" || s === "expired") return "bg-error-container text-on-error-container";
  return "bg-surface-container-highest text-on-surface";
}

function statusLabel(s: string) { return s.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase()); }

function UsageMeter({ label, used, limit, icon }: { label: string; used: number; limit: number; icon: string }) {
  const pct = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
  const warn = pct >= 80;
  return (
    <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-5 shadow-sm">
      <div className="flex items-center gap-2">
        <span className="material-symbols-outlined text-lg text-on-surface-variant">{icon}</span>
        <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">{label}</p>
      </div>
      <div className="mt-3 flex items-end justify-between">
        <p className="font-headline text-2xl font-extrabold text-on-surface">{used} <span className="text-base font-normal text-on-surface-variant">/ {limit}</span></p>
        <p className={`text-sm font-bold ${warn ? "text-error" : "text-on-surface-variant"}`}>{pct}%</p>
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-surface-container-high">
        <div className={`h-full rounded-full transition-all ${warn ? "bg-error" : "bg-primary"}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default function BillingPage() {
  const currency = useCurrency();
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [plans, setPlans] = useState<PlanOption[]>([]);
  const [addons, setAddons] = useState<AddonOption[]>([]);
  const [details, setDetails] = useState<BillingDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [showCancel, setShowCancel] = useState(false);
  const [showDetails, setShowDetails] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [bRes, uRes, pRes, aRes, dRes] = await Promise.all([
        fetch("/api/ims/v1/admin/billing/status"),
        fetch("/api/ims/v1/admin/billing/usage"),
        fetch("/api/ims/v1/admin/billing/plans"),
        fetch("/api/ims/v1/admin/billing/addons"),
        fetch("/api/ims/v1/admin/billing/details"),
      ]);
      if (bRes.ok) setBilling(await bRes.json());
      if (uRes.ok) setUsage(await uRes.json());
      if (pRes.ok) setPlans(await pRes.json());
      if (aRes.ok) setAddons(await aRes.json());
      if (dRes.ok) setDetails(await dRes.json());
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  async function doAction(url: string, method = "POST", body?: object) {
    setActionLoading(url);
    try {
      const r = await fetch(`/api/ims${url}`, {
        method,
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        alert(d.detail || `Failed (${r.status})`);
      }
      void load();
    } finally {
      setActionLoading(null);
    }
  }

  function fmtPrice(cents: number, code: string) {
    return `${code} ${(cents / 100).toLocaleString()}`;
  }

  if (loading) return <div className="flex justify-center py-16"><div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" /></div>;
  if (err) return <div className="rounded-xl border border-error/20 bg-error-container/30 p-8 text-center"><p className="text-sm text-on-error-container">{err}</p></div>;

  const currentPlan = plans.find(p => p.codename === billing?.plan_codename);

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="Subscription & usage"
        title="Billing"
        subtitle="View your plan, manage add-ons, and configure billing details."
        action={
          <div className="flex gap-2">
            <Link href="/billing/invoices" className="inline-flex items-center gap-2 rounded-lg border border-outline-variant/20 bg-surface-container px-5 py-2.5 text-sm font-semibold text-on-surface transition hover:bg-surface-container-high">
              <span className="material-symbols-outlined text-lg">receipt_long</span>Invoices
            </Link>
            <Link href="/billing/downloads" className="inline-flex items-center gap-2 rounded-lg border border-outline-variant/20 bg-surface-container px-5 py-2.5 text-sm font-semibold text-on-surface transition hover:bg-surface-container-high">
              <span className="material-symbols-outlined text-lg">phone_android</span>App Downloads
            </Link>
          </div>
        }
      />

      {/* Current plan card */}
      {billing ? (
        <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Current plan</p>
              <h2 className="mt-1 font-headline text-2xl font-extrabold text-on-surface capitalize">{billing.plan_codename}</h2>
              <div className="mt-2 flex items-center gap-3">
                <span className={`inline-flex rounded-full px-3 py-1 text-xs font-bold uppercase ${statusBadge(billing.subscription_status)}`}>{statusLabel(billing.subscription_status)}</span>
                {billing.billing_cycle ? <span className="text-sm text-on-surface-variant capitalize">{billing.billing_cycle} billing</span> : null}
              </div>
            </div>
            <div className="text-right">
              {billing.subscription_status === "trial" && billing.trial_ends_at ? (
                <div>
                  <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Trial ends</p>
                  <p className="mt-1 text-sm font-semibold text-on-surface">{new Date(billing.trial_ends_at).toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" })}</p>
                </div>
              ) : billing.current_period_end ? (
                <div>
                  <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Renews</p>
                  <p className="mt-1 text-sm font-semibold text-on-surface">{new Date(billing.current_period_end).toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" })}</p>
                </div>
              ) : null}
            </div>
          </div>

          {billing.is_in_grace_period ? (
            <div className="mt-4 rounded-lg border border-error/20 bg-error-container/30 px-4 py-3 flex items-center gap-2">
              <span className="material-symbols-outlined text-error">warning</span>
              <p className="text-sm font-semibold text-on-error-container">Payment overdue — your subscription will expire in {billing.grace_period_days} days.</p>
            </div>
          ) : null}

          {billing.active_addons.length > 0 ? (
            <div className="mt-4">
              <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Active add-ons</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {billing.active_addons.map(a => (
                  <span key={a} className="inline-flex rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary capitalize">{a.replace(/_/g, " ")}</span>
                ))}
              </div>
            </div>
          ) : null}

          {/* Quick actions */}
          <div className="mt-5 flex flex-wrap gap-2 border-t border-outline-variant/10 pt-4">
            {billing.billing_cycle === "monthly" ? (
              <button onClick={() => doAction("/v1/admin/billing/change-cycle", "POST", { billing_cycle: "yearly" })} disabled={!!actionLoading} className="inline-flex items-center gap-1.5 rounded-lg border border-outline-variant/20 px-4 py-2 text-sm font-semibold text-on-surface transition hover:bg-surface-container-high disabled:opacity-50">
                <span className="material-symbols-outlined text-lg">calendar_month</span>Switch to yearly{currentPlan && currentPlan.yearly_discount_pct > 0 ? ` (save ${currentPlan.yearly_discount_pct}%)` : ""}
              </button>
            ) : billing.billing_cycle === "yearly" ? (
              <button onClick={() => doAction("/v1/admin/billing/change-cycle", "POST", { billing_cycle: "monthly" })} disabled={!!actionLoading} className="inline-flex items-center gap-1.5 rounded-lg border border-outline-variant/20 px-4 py-2 text-sm font-semibold text-on-surface transition hover:bg-surface-container-high disabled:opacity-50">
                <span className="material-symbols-outlined text-lg">calendar_month</span>Switch to monthly
              </button>
            ) : null}
            <button onClick={() => setShowDetails(true)} className="inline-flex items-center gap-1.5 rounded-lg border border-outline-variant/20 px-4 py-2 text-sm font-semibold text-on-surface transition hover:bg-surface-container-high">
              <span className="material-symbols-outlined text-lg">edit</span>Billing details
            </button>
            {billing.subscription_status !== "cancelled" && billing.subscription_status !== "expired" ? (
              <button onClick={() => setShowCancel(true)} className="inline-flex items-center gap-1.5 rounded-lg border border-error/30 px-4 py-2 text-sm font-semibold text-error transition hover:bg-error-container/30">
                <span className="material-symbols-outlined text-lg">cancel</span>Cancel subscription
              </button>
            ) : null}
            {billing.subscription_status === "expired" || billing.subscription_status === "cancelled" ? (
              <button onClick={() => doAction("/v1/admin/billing/renew")} disabled={!!actionLoading} className="ink-gradient inline-flex items-center gap-1.5 rounded-lg px-5 py-2 text-sm font-semibold text-on-primary transition hover:opacity-90 disabled:opacity-50">
                <span className="material-symbols-outlined text-lg">refresh</span>Renew subscription
              </button>
            ) : null}
            <a href="#payment" className="inline-flex items-center gap-1.5 rounded-lg border border-outline-variant/20 px-4 py-2 text-sm font-semibold text-on-surface-variant transition hover:bg-surface-container-high">
              <span className="material-symbols-outlined text-lg">credit_card</span>Payment method
            </a>
          </div>
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

      {/* Available plans */}
      {plans.length > 0 ? (
        <section>
          <h3 className="mb-4 text-xs font-bold uppercase tracking-widest text-on-surface-variant">Available plans</h3>
          <div className="grid gap-4 lg:grid-cols-3">
            {plans.map(p => {
              const isCurrent = p.codename === billing?.plan_codename;
              return (
                <div key={p.id} className={`rounded-xl border p-5 shadow-sm ${isCurrent ? "border-primary/30 bg-primary/5" : "border-outline-variant/10 bg-surface-container-lowest"}`}>
                  <div className="flex items-center justify-between">
                    <h4 className="font-headline text-lg font-bold text-on-surface">{p.display_name}</h4>
                    {isCurrent ? <span className="rounded-full bg-primary px-2.5 py-0.5 text-[10px] font-bold uppercase text-on-primary">Current</span> : null}
                  </div>
                  <p className="mt-1 text-xs text-on-surface-variant">{p.description}</p>
                  <p className="mt-3 font-headline text-xl font-extrabold text-primary">{fmtPrice(p.base_price_cents, p.currency_code)}<span className="text-sm font-normal text-on-surface-variant">/mo</span></p>
                  {p.yearly_discount_pct > 0 ? <p className="text-xs text-on-surface-variant">{p.yearly_discount_pct}% off yearly</p> : null}
                  <p className="mt-2 text-xs text-on-surface-variant">{p.max_shops} shop{p.max_shops > 1 ? "s" : ""} · {p.max_employees} employees · {p.storage_limit_mb} MB</p>
                  {!isCurrent && billing?.subscription_status !== "cancelled" ? (
                    <button onClick={() => alert("Plan upgrade requires payment integration. Contact support to change plans.")} className="mt-3 w-full rounded-lg border border-primary/30 py-2 text-sm font-semibold text-primary transition hover:bg-primary/10">
                      {(currentPlan?.base_price_cents ?? 0) < p.base_price_cents ? "Upgrade" : "Downgrade"} to {p.display_name}
                    </button>
                  ) : null}
                </div>
              );
            })}
          </div>
        </section>
      ) : null}

      {/* Add-ons */}
      {addons.length > 0 ? (
        <section>
          <h3 className="mb-4 text-xs font-bold uppercase tracking-widest text-on-surface-variant">Add-ons</h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {addons.map(a => (
              <div key={a.id} className="flex items-center justify-between rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-4 shadow-sm">
                <div>
                  <p className="font-semibold text-on-surface">{a.display_name}</p>
                  <p className="text-xs text-on-surface-variant">{fmtPrice(a.price_cents, a.currency_code)}/mo</p>
                </div>
                {a.is_active_on_subscription ? (
                  <span className="inline-flex rounded-full bg-tertiary-fixed px-2.5 py-0.5 text-[10px] font-bold uppercase text-on-tertiary-fixed-variant">Active</span>
                ) : (
                  <button onClick={() => alert("Add-on activation requires payment integration. Contact support.")} className="rounded-lg border border-primary/30 px-3 py-1.5 text-xs font-semibold text-primary transition hover:bg-primary/10">
                    Add
                  </button>
                )}
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {/* Payment method placeholder */}
      <section id="payment" className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
        <h3 className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Payment method</h3>
        <div className="mt-4 flex items-center gap-4 rounded-lg border border-outline-variant/10 bg-surface-container px-5 py-4">
          <span className="material-symbols-outlined text-2xl text-on-surface-variant">credit_card</span>
          <div>
            <p className="text-sm font-semibold text-on-surface">No payment method configured</p>
            <p className="text-xs text-on-surface-variant">Contact support to set up automated billing via Razorpay or Stripe.</p>
          </div>
        </div>
      </section>

      {/* Cancel confirmation modal */}
      {showCancel ? (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4" onClick={() => setShowCancel(false)}>
          <div className="w-full max-w-sm rounded-2xl bg-surface p-6 shadow-xl" onClick={e => e.stopPropagation()}>
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-error-container">
                <span className="material-symbols-outlined text-error">warning</span>
              </div>
              <h3 className="font-headline text-lg font-bold text-on-surface">Cancel subscription?</h3>
            </div>
            <p className="mt-3 text-sm text-on-surface-variant">This will cancel your subscription. You will lose access to features at the end of your current billing period.</p>
            <div className="mt-5 flex justify-end gap-3">
              <button onClick={() => setShowCancel(false)} className="rounded-lg border border-outline-variant/20 px-5 py-2 text-sm font-semibold text-on-surface-variant">Keep subscription</button>
              <button onClick={() => { setShowCancel(false); doAction("/v1/admin/billing/cancel"); }} className="rounded-lg bg-error px-5 py-2 text-sm font-semibold text-on-error">Cancel subscription</button>
            </div>
          </div>
        </div>
      ) : null}

      {/* Billing details modal */}
      {showDetails ? (
        <BillingDetailsModal initial={details} onClose={() => setShowDetails(false)} onSaved={() => { setShowDetails(false); void load(); }} />
      ) : null}
    </div>
  );
}


function BillingDetailsModal({ initial, onClose, onSaved }: { initial: BillingDetails | null; onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState<BillingDetails>({
    company_name: initial?.company_name ?? "",
    gstin: initial?.gstin ?? "",
    address_line1: initial?.address_line1 ?? "",
    address_line2: initial?.address_line2 ?? "",
    city: initial?.city ?? "",
    state: initial?.state ?? "",
    postal_code: initial?.postal_code ?? "",
    country: initial?.country ?? "",
  });
  const [saving, setSaving] = useState(false);

  const set = (k: keyof BillingDetails, v: string) => setForm(prev => ({ ...prev, [k]: v }));

  async function handleSave() {
    setSaving(true);
    const r = await fetch("/api/ims/v1/admin/billing/details", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form),
    });
    setSaving(false);
    if (r.ok) onSaved();
    else alert("Failed to save billing details");
  }

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="w-full max-w-lg rounded-2xl bg-surface p-6 shadow-xl" onClick={e => e.stopPropagation()}>
        <h3 className="font-headline text-lg font-bold text-on-surface">Billing details</h3>
        <p className="mt-1 text-sm text-on-surface-variant">These details appear on your invoices.</p>
        <div className="mt-4 space-y-3">
          <Field label="Company name" value={form.company_name ?? ""} onChange={v => set("company_name", v)} />
          <Field label="GSTIN" value={form.gstin ?? ""} onChange={v => set("gstin", v)} placeholder="e.g. 29AABCU9603R1ZM" />
          <Field label="Address line 1" value={form.address_line1 ?? ""} onChange={v => set("address_line1", v)} />
          <Field label="Address line 2" value={form.address_line2 ?? ""} onChange={v => set("address_line2", v)} />
          <div className="grid grid-cols-2 gap-3">
            <Field label="City" value={form.city ?? ""} onChange={v => set("city", v)} />
            <Field label="State" value={form.state ?? ""} onChange={v => set("state", v)} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Postal code" value={form.postal_code ?? ""} onChange={v => set("postal_code", v)} />
            <Field label="Country" value={form.country ?? ""} onChange={v => set("country", v)} />
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-3">
          <button onClick={onClose} className="rounded-lg border border-outline-variant/20 px-5 py-2 text-sm font-semibold text-on-surface-variant">Cancel</button>
          <button onClick={handleSave} disabled={saving} className="ink-gradient rounded-lg px-6 py-2 text-sm font-semibold text-on-primary disabled:opacity-50">{saving ? "Saving..." : "Save"}</button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <div>
      <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">{label}</label>
      <input
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full rounded-lg border border-outline-variant/30 bg-surface-container-lowest px-4 py-2.5 text-sm text-on-surface outline-none transition focus:border-primary focus:ring-1 focus:ring-primary"
      />
    </div>
  );
}
