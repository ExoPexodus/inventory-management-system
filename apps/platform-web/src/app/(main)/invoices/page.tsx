"use client";

import { useEffect, useState } from "react";

type Invoice = { id: string; tenant_id: string; invoice_number: string; status: string; total_cents: number; tax_cents: number; currency_code: string; issued_at: string | null; seller_gstin: string | null };

export default function InvoicesPage() {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/platform/v1/platform/invoices")
      .then((r) => r.ok ? r.json() : [])
      .then(setInvoices)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Financial records</p>
        <h1 className="mt-1 font-headline text-3xl font-extrabold text-on-surface">Invoices</h1>
      </div>

      <div className="overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm">
        <table className="min-w-full text-left text-sm">
          <thead>
            <tr className="border-b border-outline-variant/10">
              <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Invoice #</th>
              <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Date</th>
              <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Tenant</th>
              <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">GSTIN</th>
              <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Status</th>
              <th className="px-6 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Tax</th>
              <th className="px-6 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Total</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-outline-variant/10">
            {loading ? (
              <tr><td colSpan={7} className="px-6 py-12 text-center text-on-surface-variant">Loading...</td></tr>
            ) : invoices.length === 0 ? (
              <tr><td colSpan={7} className="px-6 py-12 text-center text-on-surface-variant">No invoices yet.</td></tr>
            ) : invoices.map((inv) => (
              <tr key={inv.id} className="hover:bg-surface-container-low/60">
                <td className="px-6 py-3 font-mono text-xs font-bold text-on-surface">{inv.invoice_number}</td>
                <td className="px-6 py-3 text-xs text-on-surface-variant">{inv.issued_at ? new Date(inv.issued_at).toLocaleDateString() : "—"}</td>
                <td className="px-6 py-3 font-mono text-xs text-on-surface">{inv.tenant_id.slice(0, 8)}...</td>
                <td className="px-6 py-3 text-xs text-on-surface-variant">{inv.seller_gstin ?? "—"}</td>
                <td className="px-6 py-3">
                  <span className={`inline-flex rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase ${inv.status === "issued" || inv.status === "paid" ? "bg-tertiary-fixed text-on-tertiary-fixed-variant" : "bg-surface-container-highest text-on-surface"}`}>
                    {inv.status}
                  </span>
                </td>
                <td className="px-6 py-3 text-right tabular-nums text-on-surface-variant">{inv.currency_code} {(inv.tax_cents / 100).toFixed(2)}</td>
                <td className="px-6 py-3 text-right tabular-nums font-semibold">{inv.currency_code} {(inv.total_cents / 100).toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
