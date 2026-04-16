"use client";

import { useEffect, useState } from "react";

type Payment = { id: string; tenant_id: string; amount_cents: number; currency_code: string; gateway: string; status: string; method: string | null; paid_at: string | null; created_at: string };

export default function PaymentsPage() {
  const [payments, setPayments] = useState<Payment[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/platform/v1/platform/payments")
      .then((r) => r.ok ? r.json() : [])
      .then(setPayments)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Revenue tracking</p>
        <h1 className="mt-1 font-headline text-3xl font-extrabold text-on-surface">Payments</h1>
      </div>

      <div className="overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm">
        <table className="min-w-full text-left text-sm">
          <thead>
            <tr className="border-b border-outline-variant/10">
              <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Date</th>
              <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Tenant</th>
              <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Gateway</th>
              <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Method</th>
              <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Status</th>
              <th className="px-6 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Amount</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-outline-variant/10">
            {loading ? (
              <tr><td colSpan={6} className="px-6 py-12 text-center text-on-surface-variant">Loading...</td></tr>
            ) : payments.length === 0 ? (
              <tr><td colSpan={6} className="px-6 py-12 text-center text-on-surface-variant">No payments yet.</td></tr>
            ) : payments.map((p) => (
              <tr key={p.id} className="hover:bg-surface-container-low/60">
                <td className="px-6 py-3 text-xs text-on-surface-variant">{new Date(p.paid_at ?? p.created_at).toLocaleDateString()}</td>
                <td className="px-6 py-3 font-mono text-xs text-on-surface">{p.tenant_id.slice(0, 8)}...</td>
                <td className="px-6 py-3 text-xs capitalize">{p.gateway}</td>
                <td className="px-6 py-3 text-xs text-on-surface-variant capitalize">{p.method?.replace(/_/g, " ") ?? "—"}</td>
                <td className="px-6 py-3">
                  <span className={`inline-flex rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase ${p.status === "succeeded" ? "bg-tertiary-fixed text-on-tertiary-fixed-variant" : "bg-surface-container-highest text-on-surface"}`}>
                    {p.status}
                  </span>
                </td>
                <td className="px-6 py-3 text-right tabular-nums font-semibold">{p.currency_code} {(p.amount_cents / 100).toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
