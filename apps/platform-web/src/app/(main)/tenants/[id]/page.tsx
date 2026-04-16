"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

type Tenant = { id: string; name: string; slug: string; region: string; api_base_url: string; download_token: string; notes: string | null; created_at: string };
type Sub = { id: string; status: string; plan_codename: string; plan_display_name: string; billing_cycle: string; trial_ends_at: string | null; current_period_end: string; grace_period_days: number; addons: { codename: string; display_name: string }[] };
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

export default function TenantDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [sub, setSub] = useState<Sub | null>(null);
  const [payments, setPayments] = useState<PaymentRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      const [tRes, sRes, pRes] = await Promise.all([
        fetch(`/api/platform/v1/platform/tenants/${id}`),
        fetch(`/api/platform/v1/platform/tenants/${id}/subscription`).catch(() => null),
        fetch(`/api/platform/v1/platform/tenants/${id}/payments`).catch(() => null),
      ]);
      if (tRes.ok) setTenant(await tRes.json());
      if (sRes && sRes.ok) setSub(await sRes.json());
      if (pRes && pRes.ok) setPayments(await pRes.json());
      setLoading(false);
    }
    void load();
  }, [id]);

  if (loading) return <div className="flex justify-center py-16"><div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" /></div>;
  if (!tenant) return <p className="py-8 text-center text-on-surface-variant">Tenant not found.</p>;

  return (
    <div className="space-y-8">
      <div className="flex items-start justify-between">
        <div>
          <Link href="/tenants" className="text-xs font-semibold text-primary hover:underline">&larr; All tenants</Link>
          <h1 className="mt-2 font-headline text-3xl font-extrabold text-on-surface">{tenant.name}</h1>
          <p className="mt-1 text-sm text-on-surface-variant">
            <span className="font-mono">{tenant.slug}</span> &middot; {tenant.region.toUpperCase()} &middot; Created {new Date(tenant.created_at).toLocaleDateString()}
          </p>
        </div>
      </div>

      {/* Subscription */}
      <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
        <h2 className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Subscription</h2>
        {sub ? (
          <div className="mt-3 space-y-2">
            <div className="flex items-center gap-3">
              <p className="font-headline text-xl font-extrabold text-on-surface capitalize">{sub.plan_display_name}</p>
              <Badge text={sub.status.replace(/_/g, " ")} color={statusColor(sub.status)} />
              <span className="text-sm text-on-surface-variant capitalize">{sub.billing_cycle}</span>
            </div>
            {sub.trial_ends_at ? <p className="text-sm text-on-surface-variant">Trial ends: {new Date(sub.trial_ends_at).toLocaleDateString()}</p> : null}
            <p className="text-sm text-on-surface-variant">Period ends: {new Date(sub.current_period_end).toLocaleDateString()}</p>
            {sub.addons.length > 0 ? (
              <div className="flex flex-wrap gap-2 pt-1">
                {sub.addons.map((a) => (
                  <span key={a.codename} className="rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">{a.display_name}</span>
                ))}
              </div>
            ) : null}
          </div>
        ) : (
          <p className="mt-3 text-sm text-on-surface-variant">No subscription.</p>
        )}
      </section>

      {/* Payments */}
      <section className="overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm">
        <div className="border-b border-outline-variant/10 px-6 py-4">
          <h2 className="font-headline text-lg font-bold text-on-surface">Payment history</h2>
        </div>
        <table className="min-w-full text-left text-sm">
          <thead>
            <tr className="border-b border-outline-variant/10">
              <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Date</th>
              <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Gateway</th>
              <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Method</th>
              <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Status</th>
              <th className="px-6 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Amount</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-outline-variant/10">
            {payments.length === 0 ? (
              <tr><td colSpan={5} className="px-6 py-8 text-center text-sm text-on-surface-variant">No payments recorded.</td></tr>
            ) : payments.map((p) => (
              <tr key={p.id}>
                <td className="px-6 py-3 text-xs text-on-surface-variant">{p.paid_at ? new Date(p.paid_at).toLocaleDateString() : new Date(p.created_at).toLocaleDateString()}</td>
                <td className="px-6 py-3 text-xs capitalize">{p.gateway}</td>
                <td className="px-6 py-3 text-xs text-on-surface-variant capitalize">{p.method?.replace(/_/g, " ") ?? "—"}</td>
                <td className="px-6 py-3"><Badge text={p.status} color={p.status === "succeeded" ? "bg-tertiary-fixed text-on-tertiary-fixed-variant" : "bg-surface-container-highest text-on-surface"} /></td>
                <td className="px-6 py-3 text-right tabular-nums font-semibold">{p.currency_code} {(p.amount_cents / 100).toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {/* Download token */}
      <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
        <h2 className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Download token</h2>
        <p className="mt-2 font-mono text-sm text-on-surface">{tenant.download_token}</p>
        <p className="mt-1 text-xs text-on-surface-variant">Public link: /downloads/{tenant.download_token}</p>
      </section>
    </div>
  );
}
