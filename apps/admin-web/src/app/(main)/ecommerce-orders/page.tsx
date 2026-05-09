"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, PageHeader, Panel, PrimaryButton, SecondaryButton, TextInput } from "@/components/ui/primitives";
import { RequiresBusinessType } from "@/components/dashboard/RequiresBusinessType";

type OrderSummary = {
  id: string;
  channel_id: string;
  status: string;
  fulfillment_status: string;
  customer_email: string | null;
  total_cents: number;
  currency_code: string;
  placed_at: string;
  awb_code: string | null;
  tracking_url: string | null;
  carrier_name: string | null;
  shipped_at: string | null;
  delivered_at: string | null;
};

type OrderLine = {
  id: string;
  title: string;
  sku: string | null;
  quantity: number;
  unit_price_cents: number;
  line_total_cents: number;
};

type OrderPayment = {
  id: string;
  provider: string;
  method: string;
  amount_cents: number;
  status: string;
};

type OrderRefund = {
  id: string;
  amount_cents: number;
  currency_code: string;
  reason: string | null;
  status: string;
  created_at: string;
};

type OrderDetail = OrderSummary & {
  discount_cents: number;
  shipping_cents: number;
  tax_cents: number;
  subtotal_cents: number;
  shipping_address: Record<string, string> | null;
  lines: OrderLine[];
  payments: OrderPayment[];
  refunds: OrderRefund[];
};

function statusTone(s: string): "good" | "warn" | "danger" | "default" {
  if (s === "confirmed" || s === "fulfilled") return "good";
  if (s === "partially_refunded") return "warn";
  if (s === "refunded" || s === "cancelled") return "danger";
  return "default";
}

function fulfillmentTone(s: string): "good" | "warn" | "danger" | "default" {
  if (s === "delivered") return "good";
  if (s === "shipped" || s === "out_for_delivery" || s === "processing") return "warn";
  if (s === "failed" || s === "returned" || s === "cancelled") return "danger";
  return "default";
}

function RefundModal({
  order,
  onClose,
  onRefunded,
}: {
  order: OrderDetail;
  onClose: () => void;
  onRefunded: () => void;
}) {
  const alreadyRefunded = order.refunds.reduce((s, r) => s + r.amount_cents, 0);
  const maxRefund = order.total_cents - alreadyRefunded;

  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function handleRefund(e: React.FormEvent) {
    e.preventDefault();
    const amountCents = Math.round(parseFloat(amount) * 100);
    if (!amountCents || amountCents <= 0) { setErr("Enter a valid amount."); return; }
    setSaving(true);
    setErr(null);
    try {
      const r = await fetch(`/api/ims/v1/admin/ecommerce-orders/${order.id}/refund`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ amount_cents: amountCents, reason: reason.trim() || null }),
      });
      if (r.ok) { onRefunded(); onClose(); }
      else {
        const d = await r.json().catch(() => ({})) as { detail?: string };
        setErr(d.detail ?? `Failed (${r.status})`);
      }
    } catch { setErr("Network error. Please try again."); }
    finally { setSaving(false); }
  }

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-md rounded-2xl bg-surface-container-lowest shadow-2xl">
        <div className="flex items-center justify-between rounded-t-2xl bg-gradient-to-r from-error to-error/80 px-6 py-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-widest text-on-error/70">Issue Refund</p>
            <p className="mt-0.5 font-headline text-base font-bold text-on-error">
              Order #{order.id.slice(0, 8).toUpperCase()}
            </p>
          </div>
          <button type="button" onClick={onClose} className="text-on-error/70 hover:text-on-error">
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>
        <div className="p-6 space-y-4">
          <p className="text-sm text-on-surface-variant">
            Max refundable: <strong>{order.currency_code} {(maxRefund / 100).toFixed(2)}</strong>
          </p>
          {order.refunds.length > 0 && (
            <div className="rounded-lg bg-surface-container p-3 space-y-1">
              <p className="text-xs font-bold text-on-surface-variant">Previous refunds</p>
              {order.refunds.map(r => (
                <p key={r.id} className="text-xs text-on-surface">
                  {r.currency_code} {(r.amount_cents / 100).toFixed(2)} — {r.reason ?? "No reason"}
                </p>
              ))}
            </div>
          )}
          <form onSubmit={(e) => void handleRefund(e)} className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-on-surface mb-1">
                Amount ({order.currency_code})
              </label>
              <TextInput
                type="number"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder={`Max ${(maxRefund / 100).toFixed(2)}`}
                step="0.01"
                min="0.01"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-on-surface mb-1">
                Reason (optional)
              </label>
              <TextInput
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="e.g. Damaged item, customer request"
              />
            </div>
            {err && <p className="text-sm text-error">{err}</p>}
            <div className="flex gap-2">
              <PrimaryButton type="submit" disabled={saving}>
                {saving ? "Issuing…" : "Issue refund"}
              </PrimaryButton>
              <SecondaryButton type="button" onClick={onClose}>Cancel</SecondaryButton>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

function EcommerceOrdersPageInner() {
  const [orders, setOrders] = useState<OrderSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [selectedOrder, setSelectedOrder] = useState<OrderDetail | null>(null);
  const [refundOrder, setRefundOrder] = useState<OrderDetail | null>(null);
  const [statusFilter, setStatusFilter] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setLoadErr(null);
    try {
      const qs = statusFilter ? `?status=${statusFilter}` : "";
      const r = await fetch(`/api/ims/v1/admin/ecommerce-orders${qs}`);
      if (!r.ok) throw new Error(`Failed (${r.status})`);
      setOrders((await r.json()) as OrderSummary[]);
    } catch (e) {
      setLoadErr(e instanceof Error ? e.message : "Failed to load orders.");
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => { void load(); }, [load]);

  async function openDetail(orderId: string) {
    try {
      const r = await fetch(`/api/ims/v1/admin/ecommerce-orders/${orderId}`);
      if (r.ok) setSelectedOrder((await r.json()) as OrderDetail);
    } catch {
      // silently ignore
    }
  }

  async function handleDispatch(orderId: string) {
    try {
      const r = await fetch(`/api/ims/v1/admin/ecommerce-orders/${orderId}/dispatch`, { method: "POST" });
      if (r.ok) { setSelectedOrder(null); void load(); }
      else alert("Dispatch failed — check the order status and channel shipping configuration.");
    } catch { alert("Network error."); }
  }

  async function handleCancelShipment(orderId: string) {
    if (!confirm("Cancel this shipment? This only works before pickup.")) return;
    try {
      const r = await fetch(`/api/ims/v1/admin/ecommerce-orders/${orderId}/cancel-shipment`, { method: "POST" });
      if (r.ok) { setSelectedOrder(null); void load(); }
      else {
        const d = await r.json().catch(() => ({})) as { detail?: string };
        alert(d.detail ?? "Could not cancel shipment.");
      }
    } catch { alert("Network error."); }
  }

  const STATUS_OPTIONS = ["", "confirmed", "fulfilled", "partially_refunded", "refunded", "cancelled", "processing", "shipped", "out_for_delivery", "delivered", "failed"];

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="Commerce"
        title="E-commerce Orders"
        subtitle="Orders from all online channels — headless, Shopify, WooCommerce."
      />

      <div className="flex flex-wrap gap-3">
        {STATUS_OPTIONS.map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setStatusFilter(s)}
            className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${
              statusFilter === s
                ? "border-primary bg-primary/10 text-primary"
                : "border-outline-variant/30 text-on-surface-variant hover:border-primary/40"
            }`}
          >
            {s || "All"}
          </button>
        ))}
      </div>

      <Panel title="Orders" subtitle={`${orders.length} orders`} noPad>
        {loading ? (
          <p className="px-6 py-8 text-sm text-on-surface-variant">Loading…</p>
        ) : loadErr ? (
          <p className="px-6 py-8 text-center text-sm text-error">{loadErr}</p>
        ) : orders.length === 0 ? (
          <p className="px-6 py-8 text-center text-sm text-on-surface-variant">No orders yet.</p>
        ) : (
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-outline-variant/10">
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Order ID</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Customer</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Total</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Status</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Fulfillment</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Date</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {orders.map((order) => (
                <tr key={order.id} className="hover:bg-surface-container-low/50">
                  <td className="px-6 py-4 font-mono text-xs text-on-surface">#{order.id.slice(0, 8).toUpperCase()}</td>
                  <td className="px-6 py-4 text-on-surface-variant">{order.customer_email ?? "—"}</td>
                  <td className="px-6 py-4 font-medium tabular-nums text-on-surface">
                    {order.currency_code} {(order.total_cents / 100).toFixed(2)}
                  </td>
                  <td className="px-6 py-4">
                    <Badge tone={statusTone(order.status)}>{order.status}</Badge>
                  </td>
                  <td className="px-6 py-4">
                    <Badge tone={fulfillmentTone(order.fulfillment_status)}>{order.fulfillment_status}</Badge>
                  </td>
                  <td className="px-6 py-4 text-on-surface-variant text-xs">
                    {new Date(order.placed_at).toLocaleDateString()}
                  </td>
                  <td className="px-6 py-4">
                    <button
                      type="button"
                      onClick={() => void openDetail(order.id)}
                      className="inline-flex items-center gap-1 rounded-lg border border-outline-variant/40 px-3 py-1.5 text-xs font-semibold text-on-surface transition hover:bg-surface-container"
                    >
                      <span className="material-symbols-outlined text-sm">open_in_new</span>
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      {/* Order detail side panel */}
      {selectedOrder && (
        <div className="fixed inset-0 z-[100] flex justify-end bg-black/40">
          <div className="flex h-full w-full max-w-xl flex-col overflow-y-auto bg-surface-container-lowest shadow-2xl">
            <div className="flex items-center justify-between bg-gradient-to-r from-primary to-secondary px-6 py-4">
              <div>
                <p className="text-xs font-bold uppercase tracking-widest text-on-primary/70">Order detail</p>
                <p className="font-headline text-lg font-bold text-on-primary">
                  #{selectedOrder.id.slice(0, 8).toUpperCase()}
                </p>
              </div>
              <div className="flex items-center gap-2">
                {!["refunded", "cancelled"].includes(selectedOrder.status) && (
                  <button
                    type="button"
                    onClick={() => setRefundOrder(selectedOrder)}
                    className="rounded-lg bg-error/20 px-3 py-1.5 text-xs font-bold text-on-error hover:bg-error/30"
                  >
                    Refund
                  </button>
                )}
                <button type="button" onClick={() => setSelectedOrder(null)} className="text-on-primary/70 hover:text-on-primary">
                  <span className="material-symbols-outlined">close</span>
                </button>
              </div>
            </div>

            <div className="p-6 space-y-6">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <p className="text-xs text-on-surface-variant">Status</p>
                  <Badge tone={statusTone(selectedOrder.status)}>{selectedOrder.status}</Badge>
                </div>
                <div>
                  <p className="text-xs text-on-surface-variant">Customer</p>
                  <p className="font-medium">{selectedOrder.customer_email ?? "—"}</p>
                </div>
                <div>
                  <p className="text-xs text-on-surface-variant">Total</p>
                  <p className="font-medium tabular-nums">{selectedOrder.currency_code} {(selectedOrder.total_cents / 100).toFixed(2)}</p>
                </div>
                <div>
                  <p className="text-xs text-on-surface-variant">Date</p>
                  <p>{new Date(selectedOrder.placed_at).toLocaleDateString()}</p>
                </div>
              </div>

              <div>
                <p className="mb-2 text-xs font-bold uppercase tracking-widest text-on-surface-variant">Items</p>
                {selectedOrder.lines.map(line => (
                  <div key={line.id} className="flex justify-between py-2 text-sm border-b border-outline-variant/10 last:border-0">
                    <span>
                      {line.title} &times; {line.quantity}
                      {line.sku && <span className="ml-1 text-xs text-on-surface-variant">({line.sku})</span>}
                    </span>
                    <span className="tabular-nums">{selectedOrder.currency_code} {(line.line_total_cents / 100).toFixed(2)}</span>
                  </div>
                ))}
              </div>

              {(selectedOrder.awb_code || selectedOrder.fulfillment_status !== "pending") && (
                <div>
                  <p className="mb-2 text-xs font-bold uppercase tracking-widest text-on-surface-variant">
                    Shipment
                  </p>
                  <div className="rounded-xl border border-outline-variant/10 bg-surface-container-low p-4 space-y-2 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="text-on-surface-variant">Status</span>
                      <Badge tone={fulfillmentTone(selectedOrder.fulfillment_status)}>
                        {selectedOrder.fulfillment_status}
                      </Badge>
                    </div>
                    {selectedOrder.carrier_name && (
                      <div className="flex items-center justify-between">
                        <span className="text-on-surface-variant">Carrier</span>
                        <span className="font-medium">{selectedOrder.carrier_name}</span>
                      </div>
                    )}
                    {selectedOrder.awb_code && (
                      <div className="flex items-center justify-between">
                        <span className="text-on-surface-variant">AWB</span>
                        <span className="font-mono text-xs">{selectedOrder.awb_code}</span>
                      </div>
                    )}
                    {selectedOrder.tracking_url && (
                      <a href={selectedOrder.tracking_url} target="_blank" rel="noopener noreferrer"
                        className="block text-xs font-semibold text-primary hover:underline">
                        Track shipment →
                      </a>
                    )}
                    {selectedOrder.shipped_at && (
                      <div className="flex items-center justify-between text-xs text-on-surface-variant">
                        <span>Shipped</span>
                        <span>{new Date(selectedOrder.shipped_at).toLocaleDateString()}</span>
                      </div>
                    )}
                    {selectedOrder.delivered_at && (
                      <div className="flex items-center justify-between text-xs text-on-surface-variant">
                        <span>Delivered</span>
                        <span>{new Date(selectedOrder.delivered_at).toLocaleDateString()}</span>
                      </div>
                    )}
                  </div>
                  <div className="mt-2 flex gap-3">
                    {!["delivered", "cancelled", "returned", "pending"].includes(
                      selectedOrder.fulfillment_status
                    ) && (
                      <button type="button" onClick={() => void handleDispatch(selectedOrder.id)}
                        className="text-xs font-semibold text-primary hover:underline">
                        Re-dispatch
                      </button>
                    )}
                    {["processing", "shipped"].includes(selectedOrder.fulfillment_status) && (
                      <button type="button" onClick={() => void handleCancelShipment(selectedOrder.id)}
                        className="text-xs font-semibold text-error hover:underline">
                        Cancel pickup
                      </button>
                    )}
                  </div>
                </div>
              )}

              {selectedOrder.refunds.length > 0 && (
                <div>
                  <p className="mb-2 text-xs font-bold uppercase tracking-widest text-on-surface-variant">Refunds</p>
                  {selectedOrder.refunds.map(r => (
                    <div key={r.id} className="flex justify-between py-2 text-sm text-error">
                      <span>{r.reason ?? "Refund"}</span>
                      <span className="tabular-nums">−{selectedOrder.currency_code} {(r.amount_cents / 100).toFixed(2)}</span>
                    </div>
                  ))}
                </div>
              )}

              {selectedOrder.payments.map(p => (
                <div key={p.id} className="flex justify-between text-sm text-on-surface-variant">
                  <span>Paid via {p.provider} ({p.method})</span>
                  <Badge tone={p.status === "paid" ? "good" : "warn"}>{p.status}</Badge>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {refundOrder && (
        <RefundModal
          order={refundOrder}
          onClose={() => setRefundOrder(null)}
          onRefunded={() => {
            setRefundOrder(null);
            setSelectedOrder(null);
            void load();
          }}
        />
      )}
    </div>
  );
}

export default function EcommerceOrdersPage() {
  return (
    <RequiresBusinessType types={["online", "hybrid"]}>
      <EcommerceOrdersPageInner />
    </RequiresBusinessType>
  );
}
