"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Badge, Breadcrumbs, Timeline } from "@/components/ui/primitives";
import { formatMoneyUSD } from "@/lib/format";

type Tx = { id: string; status: string; total_cents: number; tax_cents: number; created_at: string; cashier_name?: string | null };
type Event = { event_type: string; created_at: string; payload?: Record<string, unknown> };

const STATUS_COLORS: Record<string, string> = {
  posted: "bg-tertiary-fixed text-on-tertiary-fixed-variant",
  pending: "bg-secondary-container/60 text-on-secondary-container",
  refunded: "bg-surface-container-highest text-on-surface-variant",
  flagged: "bg-error-container text-on-error-container",
  voided: "bg-surface-container-highest text-on-surface-variant",
};

export default function OrderDetailPage() {
  const params = useParams<{ id: string }>();
  const orderId = params?.id ?? "";
  const [tx, setTx] = useState<Tx | null>(null);
  const [events, setEvents] = useState<Event[]>([]);

  useEffect(() => {
    if (!orderId) return;
    void (async () => {
      const t = await fetch(`/api/ims/v1/admin/transactions?limit=1&q=${orderId}`);
      if (t.ok) {
        const items = ((await t.json()) as { items: Tx[] }).items;
        setTx(items[0] ?? null);
      }
      const e = await fetch(`/api/ims/v1/admin/transactions/${orderId}/timeline`);
      if (e.ok) setEvents((await e.json()) as Event[]);
    })();
  }, [orderId]);

  const statusCls = tx ? (STATUS_COLORS[tx.status] ?? "bg-surface-container text-on-surface-variant") : "";

  return (
    <div className="space-y-8">
      <Breadcrumbs items={[{ label: "Orders", href: "/orders" }, { label: `#${orderId.slice(0, 8).toUpperCase()}` }]} />
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Order audit ledger</p>
          <h2 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">#{orderId.slice(0, 8).toUpperCase()}</h2>
          {tx ? <p className="mt-2 text-on-surface-variant">Created {new Date(tx.created_at).toLocaleString()}</p> : null}
        </div>
        {tx ? (
          <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-bold ${statusCls}`}>
            <span className="h-1.5 w-1.5 rounded-full bg-current" />
            {tx.status.toUpperCase()}
          </span>
        ) : null}
      </div>
      {tx ? (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
          <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
            <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Total</p>
            <h3 className="mt-3 font-headline text-3xl font-extrabold text-primary">{formatMoneyUSD(tx.total_cents)}</h3>
          </div>
          <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
            <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Tax</p>
            <h3 className="mt-3 font-headline text-3xl font-extrabold text-primary">{formatMoneyUSD(tx.tax_cents)}</h3>
          </div>
          <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
            <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Cashier</p>
            <h3 className="mt-3 font-headline text-lg font-bold text-primary">{tx.cashier_name ?? "N/A"}</h3>
          </div>
        </div>
      ) : (
        <div className="flex h-32 items-center justify-center rounded-xl border border-outline-variant/10 bg-surface-container-lowest">
          <p className="text-sm text-on-surface-variant">Loading transaction...</p>
        </div>
      )}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="lg:col-span-7">
          {tx ? (
            <div className="overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm">
              <div className="border-b border-outline-variant/10 px-6 py-4">
                <h3 className="font-headline text-lg font-bold text-primary">Transaction Detail</h3>
              </div>
              <div className="divide-y divide-outline-variant/10">
                {[
                  { label: "Transaction ID", value: tx.id },
                  { label: "Status", value: <Badge tone={tx.status === "posted" ? "good" : tx.status === "flagged" ? "danger" : "default"}>{tx.status}</Badge> },
                  { label: "Amount", value: formatMoneyUSD(tx.total_cents) },
                  { label: "Tax", value: formatMoneyUSD(tx.tax_cents) },
                  { label: "Subtotal", value: formatMoneyUSD(tx.total_cents - tx.tax_cents) },
                  { label: "Created", value: new Date(tx.created_at).toLocaleString() },
                ].map((row) => (
                  <div key={row.label} className="flex items-center justify-between px-6 py-4">
                    <span className="text-sm text-on-surface-variant">{row.label}</span>
                    <span className="text-sm font-semibold text-on-surface">{row.value}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
        <div className="lg:col-span-5">
          <div className="overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm">
            <div className="border-b border-outline-variant/10 px-6 py-4">
              <h3 className="font-headline text-lg font-bold text-primary">Event Timeline</h3>
            </div>
            <div className="p-6">
              {events.length > 0 ? (
                <Timeline items={events.map((e) => ({ title: e.event_type, detail: new Date(e.created_at).toLocaleString() }))} />
              ) : (
                <p className="text-center text-sm text-on-surface-variant">No events recorded.</p>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
