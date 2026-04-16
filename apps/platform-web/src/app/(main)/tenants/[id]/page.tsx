"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

type Tenant = { id: string; name: string; slug: string; region: string; api_base_url: string; download_token: string; notes: string | null; created_at: string };
type AddonRow = { addon_id: string; codename: string; display_name: string; added_at: string };
type Sub = { id: string; status: string; plan_id: string; plan_codename: string; plan_display_name: string; billing_cycle: string; trial_ends_at: string | null; current_period_start: string; current_period_end: string; grace_period_days: number; addons: AddonRow[] };
type PlanOpt = { id: string; codename: string; display_name: string; base_price_cents: number; currency_code: string; max_shops: number; max_employees: number; storage_limit_mb: number };
type AddonOpt = { id: string; codename: string; display_name: string; price_cents: number; currency_code: string };
type PaymentRow = { id: string; amount_cents: number; currency_code: string; gateway: string; status: string; method: string | null; paid_at: string | null; created_at: string };

function Badge({ text, color }: { text: string; color: string }) {
  return <span className={`inline-flex rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase ${color}`}>{text}</span>;
}
function statusColor(s: string) {
  if (s === "active") return "bg-tertiary-fixed text-on-tertiary-fixed-variant";
  if (s === "trial") return "bg-primary/10 text-primary";
  if (s === "past_due" || s === "expired") return "bg-error-container text-on-error-container";
  return "bg-surface-container-highest text-on-surface";
}
function fmtPrice(cents: number, code: string) { return `${code} ${(cents / 100).toLocaleString()}`; }

export default function TenantDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [sub, setSub] = useState<Sub | null>(null);
  const [plans, setPlans] = useState<PlanOpt[]>([]);
  const [allAddons, setAllAddons] = useState<AddonOpt[]>([]);
  const [payments, setPayments] = useState<PaymentRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  // Modals
  const [showCreateSub, setShowCreateSub] = useState(false);
  const [showChangePlan, setShowChangePlan] = useState(false);
  const [showManualPay, setShowManualPay] = useState(false);

  async function load() {
    const [tRes, sRes, pRes, plRes, aRes] = await Promise.all([
      fetch(`/api/platform/v1/platform/tenants/${id}`),
      fetch(`/api/platform/v1/platform/tenants/${id}/subscription`).catch(() => null),
      fetch(`/api/platform/v1/platform/tenants/${id}/payments`).catch(() => null),
      fetch("/api/platform/v1/platform/plans"),
      fetch("/api/platform/v1/platform/addons"),
    ]);
    if (tRes.ok) setTenant(await tRes.json());
    if (sRes && sRes.ok) setSub(await sRes.json());
    else setSub(null);
    if (pRes && pRes.ok) setPayments(await pRes.json());
    if (plRes.ok) setPlans(await plRes.json());
    if (aRes.ok) setAllAddons(await aRes.json());
    setLoading(false);
  }

  useEffect(() => { void load(); }, [id]);

  async function action(url: string, method = "POST", body?: object) {
    setBusy(url);
    try {
      const r = await fetch(`/api/platform${url}`, {
        method,
        headers: body ? { "Content-Type": "application/json" } : undefined,
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        alert(d.detail || `Failed (${r.status})`);
      }
      void load();
    } finally { setBusy(null); }
  }

  if (loading) return <div className="flex justify-center py-16"><div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" /></div>;
  if (!tenant) return <p className="py-8 text-center text-on-surface-variant">Tenant not found.</p>;

  const activeAddonCodes = new Set((sub?.addons ?? []).map(a => a.codename));

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <Link href="/tenants" className="text-xs font-semibold text-primary hover:underline">&larr; All tenants</Link>
        <h1 className="mt-2 font-headline text-3xl font-extrabold text-on-surface">{tenant.name}</h1>
        <p className="mt-1 text-sm text-on-surface-variant">
          <span className="font-mono">{tenant.slug}</span> &middot; {tenant.region.toUpperCase()} &middot; Created {new Date(tenant.created_at).toLocaleDateString()}
        </p>
      </div>

      {/* Subscription management */}
      <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Subscription</h2>
          {!sub || sub.status === "cancelled" || sub.status === "expired" ? (
            <button onClick={() => setShowCreateSub(true)} className="ink-gradient rounded-lg px-4 py-2 text-xs font-semibold text-on-primary">
              {sub ? "New subscription" : "Create subscription"}
            </button>
          ) : null}
        </div>

        {sub ? (
          <div className="mt-3 space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <p className="font-headline text-xl font-extrabold text-on-surface capitalize">{sub.plan_display_name}</p>
              <Badge text={sub.status.replace(/_/g, " ")} color={statusColor(sub.status)} />
              <span className="text-sm text-on-surface-variant capitalize">{sub.billing_cycle}</span>
              <span className="text-xs text-on-surface-variant">Grace: {sub.grace_period_days}d</span>
            </div>
            {sub.trial_ends_at ? <p className="text-sm text-on-surface-variant">Trial ends: {new Date(sub.trial_ends_at).toLocaleDateString()}</p> : null}
            <p className="text-sm text-on-surface-variant">Period: {new Date(sub.current_period_start).toLocaleDateString()} — {new Date(sub.current_period_end).toLocaleDateString()}</p>

            {/* Add-ons */}
            {sub.addons.length > 0 ? (
              <div>
                <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Active add-ons</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  {sub.addons.map(a => (
                    <span key={a.codename} className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
                      {a.display_name}
                      <button onClick={() => action(`/v1/platform/tenants/${id}/subscription/addons/${a.addon_id}`, "DELETE")} className="ml-1 text-primary/60 hover:text-error" title="Remove">&times;</button>
                    </span>
                  ))}
                </div>
              </div>
            ) : null}

            {/* Action buttons */}
            <div className="flex flex-wrap gap-2 border-t border-outline-variant/10 pt-4">
              <button onClick={() => setShowChangePlan(true)} className="rounded-lg border border-outline-variant/20 px-4 py-2 text-xs font-semibold text-on-surface hover:bg-surface-container-high" disabled={!!busy}>Change plan</button>
              <button onClick={() => action(`/v1/platform/tenants/${id}/subscription`, "PATCH", { billing_cycle: sub.billing_cycle === "monthly" ? "yearly" : "monthly" })} className="rounded-lg border border-outline-variant/20 px-4 py-2 text-xs font-semibold text-on-surface hover:bg-surface-container-high" disabled={!!busy}>
                Switch to {sub.billing_cycle === "monthly" ? "yearly" : "monthly"}
              </button>
              <button onClick={() => action(`/v1/platform/tenants/${id}/subscription`, "PATCH", { grace_period_days: parseInt(prompt("Grace period (days):", String(sub.grace_period_days)) || String(sub.grace_period_days)) })} className="rounded-lg border border-outline-variant/20 px-4 py-2 text-xs font-semibold text-on-surface hover:bg-surface-container-high" disabled={!!busy}>
                Adjust grace period
              </button>

              {sub.status === "active" || sub.status === "trial" ? (
                <button onClick={() => action(`/v1/platform/tenants/${id}/subscription/suspend`)} className="rounded-lg border border-error/30 px-4 py-2 text-xs font-semibold text-error hover:bg-error-container/30" disabled={!!busy}>Suspend</button>
              ) : null}
              {sub.status === "suspended" || sub.status === "past_due" || sub.status === "expired" ? (
                <button onClick={() => action(`/v1/platform/tenants/${id}/subscription/activate`)} className="ink-gradient rounded-lg px-4 py-2 text-xs font-semibold text-on-primary" disabled={!!busy}>Activate</button>
              ) : null}
              {sub.status !== "cancelled" ? (
                <button onClick={() => { if (confirm("Cancel this subscription?")) action(`/v1/platform/tenants/${id}/subscription/cancel`); }} className="rounded-lg border border-error/30 px-4 py-2 text-xs font-semibold text-error hover:bg-error-container/30" disabled={!!busy}>Cancel</button>
              ) : null}
            </div>

            {/* Add addon */}
            {allAddons.filter(a => !activeAddonCodes.has(a.codename)).length > 0 ? (
              <div className="border-t border-outline-variant/10 pt-4">
                <p className="mb-2 text-xs font-bold uppercase tracking-widest text-on-surface-variant">Add an add-on</p>
                <div className="flex flex-wrap gap-2">
                  {allAddons.filter(a => !activeAddonCodes.has(a.codename)).map(a => (
                    <button key={a.id} onClick={() => action(`/v1/platform/tenants/${id}/subscription/addons`, "POST", { addon_id: a.id })} className="rounded-lg border border-primary/30 px-3 py-1.5 text-xs font-semibold text-primary hover:bg-primary/10" disabled={!!busy}>
                      + {a.display_name} ({fmtPrice(a.price_cents, a.currency_code)}/mo)
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        ) : (
          <p className="mt-3 text-sm text-on-surface-variant">No subscription. Create one to get started.</p>
        )}
      </section>

      {/* Record manual payment */}
      <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Payments</h2>
          <button onClick={() => setShowManualPay(true)} className="rounded-lg border border-outline-variant/20 px-4 py-2 text-xs font-semibold text-on-surface hover:bg-surface-container-high">Record manual payment</button>
        </div>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-outline-variant/10">
                <th className="px-4 py-2 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Date</th>
                <th className="px-4 py-2 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Gateway</th>
                <th className="px-4 py-2 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Method</th>
                <th className="px-4 py-2 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Status</th>
                <th className="px-4 py-2 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Amount</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {payments.length === 0 ? (
                <tr><td colSpan={5} className="px-4 py-6 text-center text-sm text-on-surface-variant">No payments.</td></tr>
              ) : payments.map(p => (
                <tr key={p.id}>
                  <td className="px-4 py-2 text-xs text-on-surface-variant">{new Date(p.paid_at ?? p.created_at).toLocaleDateString()}</td>
                  <td className="px-4 py-2 text-xs capitalize">{p.gateway}</td>
                  <td className="px-4 py-2 text-xs text-on-surface-variant capitalize">{p.method?.replace(/_/g, " ") ?? "—"}</td>
                  <td className="px-4 py-2"><Badge text={p.status} color={p.status === "succeeded" ? "bg-tertiary-fixed text-on-tertiary-fixed-variant" : "bg-surface-container-highest text-on-surface"} /></td>
                  <td className="px-4 py-2 text-right tabular-nums font-semibold">{fmtPrice(p.amount_cents, p.currency_code)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Download token */}
      <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">App distribution</h2>
          <button onClick={() => action(`/v1/platform/tenants/${id}/regenerate-download-token`)} className="rounded-lg border border-outline-variant/20 px-4 py-2 text-xs font-semibold text-on-surface hover:bg-surface-container-high" disabled={!!busy}>Regenerate token</button>
        </div>
        <p className="mt-3 font-mono text-sm text-on-surface">{tenant.download_token}</p>
        <a href={`/api/platform/downloads/${tenant.download_token}`} target="_blank" rel="noopener noreferrer" className="mt-1 text-xs text-primary hover:underline">
          Open public download page &rarr;
        </a>
      </section>

      {/* Create subscription modal */}
      {showCreateSub ? (
        <Modal title="Create subscription" onClose={() => setShowCreateSub(false)}>
          <CreateSubForm tenantId={id} plans={plans} onDone={() => { setShowCreateSub(false); void load(); }} />
        </Modal>
      ) : null}

      {/* Change plan modal */}
      {showChangePlan && sub ? (
        <Modal title="Change plan" onClose={() => setShowChangePlan(false)}>
          <div className="space-y-3">
            {plans.map(p => (
              <button key={p.id} onClick={() => { setShowChangePlan(false); alert("Plan change requires creating a new subscription. Cancel the current one first, then create a new one with the desired plan."); }} className={`w-full rounded-lg border p-4 text-left transition ${p.codename === sub.plan_codename ? "border-primary/30 bg-primary/5" : "border-outline-variant/10 hover:bg-surface-container-high"}`}>
                <div className="flex items-center justify-between">
                  <span className="font-semibold">{p.display_name}</span>
                  {p.codename === sub.plan_codename ? <Badge text="Current" color="bg-primary text-on-primary" /> : null}
                </div>
                <p className="mt-1 text-xs text-on-surface-variant">{fmtPrice(p.base_price_cents, p.currency_code)}/mo &middot; {p.max_shops} shops &middot; {p.max_employees} emp</p>
              </button>
            ))}
          </div>
        </Modal>
      ) : null}

      {/* Manual payment modal */}
      {showManualPay ? (
        <Modal title="Record manual payment" onClose={() => setShowManualPay(false)}>
          <ManualPayForm tenantId={id} onDone={() => { setShowManualPay(false); void load(); }} />
        </Modal>
      ) : null}
    </div>
  );
}

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl bg-surface p-6 shadow-xl" onClick={e => e.stopPropagation()}>
        <h3 className="font-headline text-lg font-bold text-on-surface">{title}</h3>
        <div className="mt-4">{children}</div>
      </div>
    </div>
  );
}

function CreateSubForm({ tenantId, plans, onDone }: { tenantId: string; plans: PlanOpt[]; onDone: () => void }) {
  const [planId, setPlanId] = useState(plans[0]?.id ?? "");
  const [cycle, setCycle] = useState("monthly");
  const [isTrial, setIsTrial] = useState(true);
  const [trialDays, setTrialDays] = useState(14);
  const [grace, setGrace] = useState(7);
  const [saving, setSaving] = useState(false);

  async function handleSubmit() {
    setSaving(true);
    const r = await fetch(`/api/platform/v1/platform/tenants/${tenantId}/subscription`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan_id: planId, billing_cycle: cycle, is_trial: isTrial, trial_days: trialDays, grace_period_days: grace }),
    });
    setSaving(false);
    if (r.ok) onDone();
    else { const d = await r.json().catch(() => ({})); alert(d.detail || "Failed"); }
  }

  return (
    <div className="space-y-4">
      <div>
        <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Plan</label>
        <select value={planId} onChange={e => setPlanId(e.target.value)} className="w-full rounded-lg border border-outline-variant/30 bg-surface-container-lowest px-4 py-2.5 text-sm outline-none focus:border-primary">
          {plans.map(p => <option key={p.id} value={p.id}>{p.display_name} — {fmtPrice(p.base_price_cents, p.currency_code)}/mo</option>)}
        </select>
      </div>
      <div>
        <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Billing cycle</label>
        <select value={cycle} onChange={e => setCycle(e.target.value)} className="w-full rounded-lg border border-outline-variant/30 bg-surface-container-lowest px-4 py-2.5 text-sm outline-none focus:border-primary">
          <option value="monthly">Monthly</option>
          <option value="yearly">Yearly</option>
        </select>
      </div>
      <div className="flex items-center gap-3">
        <input type="checkbox" id="trial" checked={isTrial} onChange={e => setIsTrial(e.target.checked)} className="h-4 w-4" />
        <label htmlFor="trial" className="text-sm text-on-surface">Start as trial</label>
        {isTrial ? <input type="number" value={trialDays} onChange={e => setTrialDays(+e.target.value)} className="w-20 rounded-lg border border-outline-variant/30 px-3 py-1.5 text-sm" min={1} /> : null}
        {isTrial ? <span className="text-xs text-on-surface-variant">days</span> : null}
      </div>
      <div>
        <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Grace period (days)</label>
        <input type="number" value={grace} onChange={e => setGrace(+e.target.value)} className="w-24 rounded-lg border border-outline-variant/30 px-3 py-2.5 text-sm" min={0} />
      </div>
      <button onClick={handleSubmit} disabled={saving} className="ink-gradient w-full rounded-lg py-2.5 text-sm font-semibold text-on-primary disabled:opacity-50">
        {saving ? "Creating..." : "Create subscription"}
      </button>
    </div>
  );
}

function ManualPayForm({ tenantId, onDone }: { tenantId: string; onDone: () => void }) {
  const [amount, setAmount] = useState("");
  const [currency, setCurrency] = useState("INR");
  const [method, setMethod] = useState("bank_transfer");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSubmit() {
    const cents = Math.round(parseFloat(amount) * 100);
    if (isNaN(cents) || cents <= 0) { alert("Enter a valid amount"); return; }
    setSaving(true);
    const r = await fetch(`/api/platform/v1/platform/tenants/${tenantId}/payments/manual`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ amount_cents: cents, currency_code: currency, method, notes: notes || null }),
    });
    setSaving(false);
    if (r.ok) onDone();
    else { const d = await r.json().catch(() => ({})); alert(d.detail || "Failed"); }
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Amount</label>
          <input type="number" value={amount} onChange={e => setAmount(e.target.value)} placeholder="999.00" step="0.01" className="w-full rounded-lg border border-outline-variant/30 px-4 py-2.5 text-sm outline-none focus:border-primary" />
        </div>
        <div>
          <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Currency</label>
          <select value={currency} onChange={e => setCurrency(e.target.value)} className="w-full rounded-lg border border-outline-variant/30 bg-surface-container-lowest px-4 py-2.5 text-sm outline-none focus:border-primary">
            <option value="INR">INR</option><option value="USD">USD</option><option value="IDR">IDR</option>
          </select>
        </div>
      </div>
      <div>
        <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Method</label>
        <select value={method} onChange={e => setMethod(e.target.value)} className="w-full rounded-lg border border-outline-variant/30 bg-surface-container-lowest px-4 py-2.5 text-sm outline-none focus:border-primary">
          <option value="bank_transfer">Bank transfer</option><option value="upi">UPI</option><option value="cash">Cash</option><option value="cheque">Cheque</option>
        </select>
      </div>
      <div>
        <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Notes</label>
        <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={2} placeholder="e.g. NEFT ref #12345" className="w-full rounded-lg border border-outline-variant/30 px-4 py-2.5 text-sm outline-none focus:border-primary" />
      </div>
      <button onClick={handleSubmit} disabled={saving} className="ink-gradient w-full rounded-lg py-2.5 text-sm font-semibold text-on-primary disabled:opacity-50">
        {saving ? "Recording..." : "Record payment"}
      </button>
    </div>
  );
}
