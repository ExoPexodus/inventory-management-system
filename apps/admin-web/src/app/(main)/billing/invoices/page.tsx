"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ErrorState, LoadingRow, PageHeader } from "@/components/ui/primitives";
import { useCurrency } from "@/lib/currency-context";
import { formatMoney } from "@/lib/format";

type Invoice = {
  id: string;
  invoice_number: string;
  status: string;
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
  currency_code: string;
  issued_at: string | null;
  due_at: string | null;
  line_items: { description: string; unit_price_cents: number; tax_cents: number; total_cents: number }[];
  seller_gstin: string | null;
  buyer_gstin: string | null;
};

function statusClasses(s: string) {
  if (s === "issued" || s === "paid") return "bg-tertiary-fixed text-on-tertiary-fixed-variant";
  if (s === "void") return "bg-surface-container-highest text-on-surface";
  return "bg-secondary-container text-on-secondary-container";
}

export default function InvoicesPage() {
  const currency = useCurrency();
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [detail, setDetail] = useState<Invoice | null>(null);

  useEffect(() => {
    async function load() {
      try {
        // Invoices are proxied from the platform service through the main API
        // For now, fall back to an empty list if the endpoint isn't ready
        const r = await fetch("/api/ims/v1/admin/billing/status");
        if (!r.ok) throw new Error("Failed to load");
        // Invoice listing will be added when platform proxy is wired
        setInvoices([]);
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Failed");
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, []);

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="Payment history"
        title="Invoices"
        subtitle="View and download invoices for your subscription payments."
        action={
          <Link
            href="/billing"
            className="inline-flex items-center gap-2 rounded-lg border border-outline-variant/20 bg-surface-container px-5 py-2.5 text-sm font-semibold text-on-surface transition hover:bg-surface-container-high"
          >
            <span className="material-symbols-outlined text-lg">arrow_back</span>
            Back to Billing
          </Link>
        }
      />

      {err ? <ErrorState detail={err} /> : null}

      <section className="overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm">
        <div className="border-b border-outline-variant/10 px-6 py-4">
          <h3 className="font-headline text-lg font-bold text-on-surface">Invoice history</h3>
          <p className="mt-0.5 text-sm text-on-surface-variant">All invoices for your subscription.</p>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-outline-variant/10">
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Invoice #</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Date</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Status</th>
                <th className="px-6 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Amount</th>
                <th className="px-6 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Tax</th>
                <th className="px-6 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Total</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {loading ? (
                <LoadingRow colSpan={6} />
              ) : invoices.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center">
                    <span className="material-symbols-outlined mb-2 block text-4xl text-on-surface-variant">receipt_long</span>
                    <p className="text-sm text-on-surface-variant">No invoices yet. Invoices will appear here after your first payment.</p>
                  </td>
                </tr>
              ) : (
                invoices.map((inv) => (
                  <tr key={inv.id} className="group hover:bg-surface-container-low/60">
                    <td className="px-6 py-3 font-mono text-xs font-bold text-on-surface">{inv.invoice_number}</td>
                    <td className="px-6 py-3 text-xs text-on-surface-variant">
                      {inv.issued_at ? new Date(inv.issued_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "—"}
                    </td>
                    <td className="px-6 py-3">
                      <span className={`inline-flex rounded-full px-2.5 py-1 text-[10px] font-bold uppercase ${statusClasses(inv.status)}`}>
                        {inv.status}
                      </span>
                    </td>
                    <td className="px-6 py-3 text-right tabular-nums text-on-surface">{formatMoney(inv.subtotal_cents, currency)}</td>
                    <td className="px-6 py-3 text-right tabular-nums text-on-surface-variant">{formatMoney(inv.tax_cents, currency)}</td>
                    <td className="px-6 py-3 text-right tabular-nums font-semibold text-on-surface">{formatMoney(inv.total_cents, currency)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {detail ? (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4" onClick={() => setDetail(null)}>
          <div className="w-full max-w-md rounded-2xl bg-surface p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-headline text-lg font-bold">{detail.invoice_number}</h3>
            <pre className="mt-4 max-h-64 overflow-auto rounded bg-surface-container-high p-3 text-xs">{JSON.stringify(detail.line_items, null, 2)}</pre>
            <button type="button" onClick={() => setDetail(null)} className="mt-4 w-full rounded-lg border border-outline-variant/20 py-2 text-sm font-semibold">Close</button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
