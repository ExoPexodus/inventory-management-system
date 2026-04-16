"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/ui/primitives";

type Invoice = {
  id: string;
  invoice_number: string;
  status: string;
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
  currency_code: string;
  issued_at: string | null;
  line_items: { description: string; unit_price_cents: number; tax_cents: number; total_cents: number }[];
};

function statusClasses(s: string) {
  if (s === "issued" || s === "paid") return "bg-tertiary-fixed text-on-tertiary-fixed-variant";
  if (s === "void") return "bg-surface-container-highest text-on-surface";
  return "bg-secondary-container text-on-secondary-container";
}

function fmtMoney(cents: number, code: string) { return `${code} ${(cents / 100).toLocaleString(undefined, { minimumFractionDigits: 2 })}`; }

export default function InvoicesPage() {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState<Invoice | null>(null);

  useEffect(() => {
    fetch("/api/ims/v1/admin/billing/invoices")
      .then(r => r.ok ? r.json() : [])
      .then(setInvoices)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="Payment history"
        title="Invoices"
        subtitle="View and download invoices for your subscription payments."
        action={
          <Link href="/billing" className="inline-flex items-center gap-2 rounded-lg border border-outline-variant/20 bg-surface-container px-5 py-2.5 text-sm font-semibold text-on-surface transition hover:bg-surface-container-high">
            <span className="material-symbols-outlined text-lg">arrow_back</span>Back to Billing
          </Link>
        }
      />

      <section className="overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm">
        <div className="border-b border-outline-variant/10 px-6 py-4">
          <h3 className="font-headline text-lg font-bold text-on-surface">Invoice history</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-outline-variant/10">
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Invoice #</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Date</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Status</th>
                <th className="px-6 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Subtotal</th>
                <th className="px-6 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Tax</th>
                <th className="px-6 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Total</th>
                <th className="px-6 py-3 text-center text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {loading ? (
                <tr><td colSpan={7} className="px-6 py-12 text-center text-on-surface-variant">Loading...</td></tr>
              ) : invoices.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-6 py-12 text-center">
                    <span className="material-symbols-outlined mb-2 block text-4xl text-on-surface-variant">receipt_long</span>
                    <p className="text-sm text-on-surface-variant">No invoices yet. Invoices will appear here after your first payment.</p>
                  </td>
                </tr>
              ) : invoices.map(inv => (
                <tr key={inv.id} className="group hover:bg-surface-container-low/60">
                  <td className="px-6 py-3 font-mono text-xs font-bold text-on-surface">{inv.invoice_number}</td>
                  <td className="px-6 py-3 text-xs text-on-surface-variant">
                    {inv.issued_at ? new Date(inv.issued_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "—"}
                  </td>
                  <td className="px-6 py-3">
                    <span className={`inline-flex rounded-full px-2.5 py-1 text-[10px] font-bold uppercase ${statusClasses(inv.status)}`}>{inv.status}</span>
                  </td>
                  <td className="px-6 py-3 text-right tabular-nums text-on-surface">{fmtMoney(inv.subtotal_cents, inv.currency_code)}</td>
                  <td className="px-6 py-3 text-right tabular-nums text-on-surface-variant">{fmtMoney(inv.tax_cents, inv.currency_code)}</td>
                  <td className="px-6 py-3 text-right tabular-nums font-semibold text-on-surface">{fmtMoney(inv.total_cents, inv.currency_code)}</td>
                  <td className="px-6 py-3 text-center">
                    <button onClick={() => setDetail(inv)} className="inline-flex rounded-lg p-2 text-on-surface-variant opacity-0 transition group-hover:opacity-100 hover:bg-surface-container">
                      <span className="material-symbols-outlined text-xl">visibility</span>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Invoice detail modal */}
      {detail ? (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4" onClick={() => setDetail(null)}>
          <div className="w-full max-w-md rounded-2xl bg-surface shadow-xl" onClick={e => e.stopPropagation()}>
            <div className="ink-gradient rounded-t-2xl px-6 py-5">
              <p className="text-xs font-bold uppercase tracking-widest text-on-primary/80">Invoice</p>
              <p className="mt-1 font-mono text-sm text-on-primary/90">{detail.invoice_number}</p>
              <p className="mt-1 text-xs text-on-primary/70">
                {detail.issued_at ? new Date(detail.issued_at).toLocaleDateString(undefined, { dateStyle: "medium" }) : ""}
              </p>
            </div>
            <div className="max-h-64 overflow-y-auto px-6 py-4">
              <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Line items</p>
              {detail.line_items.length === 0 ? (
                <p className="text-sm text-on-surface-variant">No line items.</p>
              ) : (
                <table className="w-full text-sm">
                  <tbody className="divide-y divide-outline-variant/10">
                    {detail.line_items.map((li, i) => (
                      <tr key={i}>
                        <td className="py-2 text-on-surface">{li.description}</td>
                        <td className="py-2 text-right tabular-nums font-semibold">{fmtMoney(li.total_cents, detail.currency_code)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
            <div className="border-t border-outline-variant/10 px-6 py-4 space-y-1.5">
              <div className="flex justify-between text-sm text-on-surface-variant"><span>Subtotal</span><span className="tabular-nums">{fmtMoney(detail.subtotal_cents, detail.currency_code)}</span></div>
              <div className="flex justify-between text-sm text-on-surface-variant"><span>Tax (GST)</span><span className="tabular-nums">{fmtMoney(detail.tax_cents, detail.currency_code)}</span></div>
              <div className="flex justify-between font-bold text-base text-on-surface border-t border-outline-variant/10 pt-2"><span>Total</span><span className="tabular-nums">{fmtMoney(detail.total_cents, detail.currency_code)}</span></div>
            </div>
            <div className="border-t border-outline-variant/10 px-6 py-4">
              <button onClick={() => setDetail(null)} className="w-full rounded-lg border border-outline-variant/20 py-2 text-sm font-semibold text-on-surface-variant transition hover:bg-surface-container">Close</button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
