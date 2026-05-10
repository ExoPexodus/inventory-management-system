"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { formatMoney } from "@/lib/format";
import { useCurrency } from "@/lib/currency-context";
import { Breadcrumbs, PageHeader, PrimaryButton } from "@/components/ui/primitives";

type RMALine = {
  id: string;
  product_name: string;
  product_sku: string | null;
  quantity_requested: number;
  quantity_approved: number;
  unit_price_cents: number;
  restock_on_approval: boolean;
  line_refund_cents: number;
};

type RMAEvent = {
  id: string;
  event_type: string;
  from_status: string | null;
  to_status: string | null;
  actor_user_id: string | null;
  actor_kind: string;
  event_metadata: Record<string, unknown> | null;
  created_at: string;
};

type RMADetail = {
  id: string;
  order_id: string | null;
  sale_transaction_id: string | null;
  customer_email: string | null;
  customer_name: string | null;
  refund_type: string;
  status: string;
  reason_code: string;
  reason_note: string | null;
  refund_shipping: boolean;
  return_shipping_required: boolean;
  return_shipping_awb: string | null;
  total_refund_cents: number;
  currency_code: string;
  provider_refund_ref: string | null;
  cash_returned: boolean;
  rejected_reason: string | null;
  auto_approved: boolean;
  created_at: string;
  approved_at: string | null;
  refunded_at: string | null;
  lines: RMALine[];
  events: RMAEvent[];
};

const STATUS_COLORS: Record<string, string> = {
  requested: "bg-amber-100 text-amber-800",
  approved: "bg-blue-100 text-blue-800",
  rejected: "bg-red-100 text-red-800",
  received: "bg-purple-100 text-purple-800",
  refunded: "bg-green-100 text-green-800",
  closed: "bg-gray-100 text-gray-600",
  cancelled: "bg-gray-100 text-gray-500",
};

export default function RMADetailPage() {
  const { id } = useParams<{ id: string }>();
  const currency = useCurrency();
  const [rma, setRma] = useState<RMADetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  // Approval state
  const [lineApprovals, setLineApprovals] = useState<Record<string, { qty: number; restock: boolean }>>({});
  const [refundShipping, setRefundShipping] = useState(false);

  // Reject state
  const [rejectReason, setRejectReason] = useState("");
  const [showRejectModal, setShowRejectModal] = useState(false);

  // Comment state
  const [comment, setComment] = useState("");

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`/api/ims/v1/admin/rma/${id}`);
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as RMADetail;
      setRma(data);
      // Initialize line approvals
      const approvals: Record<string, { qty: number; restock: boolean }> = {};
      for (const line of data.lines) {
        approvals[line.id] = { qty: line.quantity_requested, restock: line.restock_on_approval };
      }
      setLineApprovals(approvals);
      setRefundShipping(data.refund_shipping);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, [id]);

  async function doAction(endpoint: string, body?: Record<string, unknown>) {
    setActionLoading(true);
    setMessage(null);
    setError(null);
    try {
      const res = await fetch(`/api/ims/v1/admin/rma/${id}/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!res.ok) throw new Error(await res.text());
      await load();
      setMessage(`Action '${endpoint}' completed successfully.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setActionLoading(false);
    }
  }

  function handleApprove() {
    if (!rma) return;
    const lineApprovalsBody = rma.lines.map((line) => ({
      line_id: line.id,
      quantity_approved: lineApprovals[line.id]?.qty ?? line.quantity_requested,
      restock: lineApprovals[line.id]?.restock ?? true,
    }));
    void doAction("approve", { line_approvals: lineApprovalsBody, refund_shipping: refundShipping });
  }

  function handleReject() {
    if (!rejectReason.trim()) return;
    void doAction("reject", { reason: rejectReason });
    setShowRejectModal(false);
    setRejectReason("");
  }

  function handleAddComment() {
    if (!comment.trim()) return;
    void doAction("comment", { comment });
    setComment("");
  }

  if (loading) return <div className="p-8 text-sm text-on-surface-variant">Loading…</div>;
  if (!rma) return <div className="p-8 text-sm text-error">{error ?? "Refund request not found"}</div>;

  return (
    <div className="space-y-8">
      <Breadcrumbs items={[{ label: "Refunds", href: "/rma" }, { label: `#${rma.id.slice(0, 8).toUpperCase()}` }]} />
      <PageHeader
        kicker="Refund Request"
        title={`#${rma.id.slice(0, 8).toUpperCase()}`}
        subtitle={rma.customer_name ?? rma.customer_email ?? "No customer"}
      />

      {message && (
        <p className="rounded-lg border border-primary/20 bg-primary/5 px-4 py-2 text-sm font-semibold text-primary">
          {message}
        </p>
      )}
      {error && (
        <p className="rounded-lg border border-error/20 bg-error-container/20 px-4 py-2 text-sm text-on-error-container">
          {error}
        </p>
      )}

      {/* Header card */}
      <section className="grid grid-cols-2 gap-4 sm:grid-cols-4 rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
        <div>
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Status</p>
          <span className={`mt-1 inline-block rounded-full px-3 py-1 text-xs font-semibold capitalize ${STATUS_COLORS[rma.status] ?? "bg-gray-100 text-gray-700"}`}>
            {rma.status}
          </span>
        </div>
        <div>
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Type</p>
          <p className="mt-1 text-sm font-medium capitalize text-on-surface">{rma.refund_type.replace("_", " ")}</p>
        </div>
        <div>
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Total Refund</p>
          <p className="mt-1 text-sm font-bold text-on-surface">
            {formatMoney(rma.total_refund_cents, { code: rma.currency_code, exponent: currency.exponent })}
          </p>
        </div>
        <div>
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Reason</p>
          <p className="mt-1 text-sm capitalize text-on-surface">{rma.reason_code.replace("_", " ")}</p>
          {rma.reason_note && <p className="text-xs text-on-surface-variant">{rma.reason_note}</p>}
        </div>
        {rma.order_id && (
          <div className="col-span-2">
            <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Original Order</p>
            <Link href={`/ecommerce-orders/${rma.order_id}`} className="text-sm text-primary hover:underline">
              {rma.order_id.slice(0, 8).toUpperCase()}
            </Link>
          </div>
        )}
        {rma.rejected_reason && (
          <div className="col-span-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3">
            <p className="text-xs font-bold uppercase tracking-widest text-red-700">Rejection Reason</p>
            <p className="text-sm text-red-900">{rma.rejected_reason}</p>
          </div>
        )}
      </section>

      {/* Lines table */}
      <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm overflow-hidden">
        <div className="p-4 border-b border-outline-variant/10">
          <h3 className="font-headline text-base font-bold text-on-surface">Request Lines</h3>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-outline-variant/10 bg-surface-container">
              <th className="p-3 text-left text-xs font-bold uppercase tracking-widest text-on-surface-variant">Product</th>
              <th className="p-3 text-right text-xs font-bold uppercase tracking-widest text-on-surface-variant">Requested</th>
              <th className="p-3 text-right text-xs font-bold uppercase tracking-widest text-on-surface-variant">Approved Qty</th>
              <th className="p-3 text-center text-xs font-bold uppercase tracking-widest text-on-surface-variant">Restock</th>
              <th className="p-3 text-right text-xs font-bold uppercase tracking-widest text-on-surface-variant">Line Refund</th>
            </tr>
          </thead>
          <tbody>
            {rma.lines.map((line) => {
              const approval = lineApprovals[line.id];
              const computedRefund = (approval?.qty ?? line.quantity_approved) * line.unit_price_cents;
              return (
                <tr key={line.id} className="border-b border-outline-variant/5">
                  <td className="p-3">
                    <p className="font-medium text-on-surface">{line.product_name}</p>
                    {line.product_sku && <p className="text-xs text-on-surface-variant">{line.product_sku}</p>}
                  </td>
                  <td className="p-3 text-right text-on-surface">{line.quantity_requested}</td>
                  <td className="p-3 text-right">
                    {rma.status === "requested" ? (
                      <input
                        type="number"
                        min={0}
                        max={line.quantity_requested}
                        value={approval?.qty ?? line.quantity_requested}
                        onChange={(e) =>
                          setLineApprovals((prev) => ({
                            ...prev,
                            [line.id]: { ...prev[line.id], qty: parseInt(e.target.value) || 0 },
                          }))
                        }
                        className="w-16 rounded border border-outline-variant/30 px-2 py-1 text-right text-sm"
                      />
                    ) : (
                      <span className="text-on-surface">{line.quantity_approved}</span>
                    )}
                  </td>
                  <td className="p-3 text-center">
                    {rma.status === "requested" ? (
                      <input
                        type="checkbox"
                        checked={approval?.restock ?? line.restock_on_approval}
                        onChange={(e) =>
                          setLineApprovals((prev) => ({
                            ...prev,
                            [line.id]: { ...prev[line.id], restock: e.target.checked },
                          }))
                        }
                        className="h-4 w-4 rounded"
                      />
                    ) : (
                      <span className="text-xs text-on-surface-variant">{line.restock_on_approval ? "Yes" : "No"}</span>
                    )}
                  </td>
                  <td className="p-3 text-right font-medium text-on-surface">
                    {rma.status === "requested"
                      ? formatMoney(computedRefund, { code: rma.currency_code, exponent: currency.exponent })
                      : formatMoney(line.line_refund_cents, { code: rma.currency_code, exponent: currency.exponent })}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {/* Refund shipping toggle (only when editing) */}
        {rma.status === "requested" && (
          <div className="border-t border-outline-variant/10 p-4 flex items-center gap-3">
            <input
              type="checkbox"
              id="refund-shipping"
              checked={refundShipping}
              onChange={(e) => setRefundShipping(e.target.checked)}
              className="h-4 w-4 rounded"
            />
            <label htmlFor="refund-shipping" className="text-sm font-medium text-on-surface">
              Refund shipping cost
            </label>
          </div>
        )}
      </section>

      {/* Action buttons */}
      <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm space-y-4">
        <h3 className="font-headline text-base font-bold text-primary">Actions</h3>
        <div className="flex flex-wrap gap-3">
          {rma.status === "requested" && (
            <>
              <PrimaryButton type="button" disabled={actionLoading} onClick={handleApprove}>
                {actionLoading ? "Processing…" : "Approve"}
              </PrimaryButton>
              <button
                type="button"
                disabled={actionLoading}
                onClick={() => setShowRejectModal(true)}
                className="rounded-full border border-error px-5 py-2 text-sm font-semibold text-error hover:bg-error/5 disabled:opacity-40"
              >
                Reject
              </button>
              <button
                type="button"
                disabled={actionLoading}
                onClick={() => void doAction("reject", { reason: "Cancelled by merchant" })}
                className="rounded-full border border-outline-variant/30 px-5 py-2 text-sm font-semibold text-on-surface-variant hover:bg-surface-container disabled:opacity-40"
              >
                Cancel
              </button>
            </>
          )}
          {rma.status === "approved" && rma.refund_type === "return_refund" && (
            <>
              <PrimaryButton type="button" disabled={actionLoading} onClick={() => void doAction("mark-received")}>
                Mark Received
              </PrimaryButton>
              {rma.return_shipping_required && (
                <button
                  type="button"
                  disabled={actionLoading}
                  onClick={() => void doAction("issue-return-awb")}
                  className="rounded-full border border-primary px-5 py-2 text-sm font-semibold text-primary hover:bg-primary/5 disabled:opacity-40"
                >
                  Issue Return AWB
                </button>
              )}
            </>
          )}
          {rma.status === "approved" && rma.refund_type !== "return_refund" && !rma.cash_returned && (
            <button
              type="button"
              disabled={actionLoading}
              onClick={() => void doAction("mark-cash-returned")}
              className="rounded-full bg-green-600 px-5 py-2 text-sm font-semibold text-white hover:bg-green-700 disabled:opacity-40"
            >
              Mark Cash Returned
            </button>
          )}
          {rma.status === "refunded" && (
            <PrimaryButton type="button" disabled={actionLoading} onClick={() => void doAction("close")}>
              Close Request
            </PrimaryButton>
          )}
          {rma.status === "rejected" && (
            <PrimaryButton type="button" disabled={actionLoading} onClick={() => void doAction("close")}>
              Close Request
            </PrimaryButton>
          )}
        </div>

        {/* Comment */}
        <div className="border-t border-outline-variant/10 pt-4 space-y-2">
          <label className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Add Comment</label>
          <div className="flex gap-2">
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={2}
              placeholder="Write an internal note…"
              className="flex-1 rounded-lg border border-outline-variant/30 px-3 py-2 text-sm"
            />
            <button
              type="button"
              disabled={!comment.trim() || actionLoading}
              onClick={handleAddComment}
              className="self-end rounded-lg bg-surface-container px-4 py-2 text-sm font-semibold text-on-surface hover:bg-surface-container-high disabled:opacity-40"
            >
              Post
            </button>
          </div>
        </div>
      </section>

      {/* Timeline */}
      <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
        <h3 className="font-headline text-base font-bold text-on-surface mb-4">Timeline</h3>
        <ol className="space-y-4">
          {rma.events.map((evt) => (
            <li key={evt.id} className="flex gap-4">
              <div className="mt-1 h-2 w-2 shrink-0 rounded-full bg-primary/40"></div>
              <div className="flex-1">
                <p className="text-sm font-medium text-on-surface capitalize">
                  {evt.event_type.replace("_", " ")}
                  {evt.to_status && <span className="ml-2 text-xs text-on-surface-variant">→ {evt.to_status}</span>}
                </p>
                {evt.event_metadata?.comment != null && (
                  <p className="text-sm text-on-surface-variant italic">{String(evt.event_metadata.comment)}</p>
                )}
                {evt.event_metadata?.error != null && (
                  <p className="text-xs text-error">Error: {String(evt.event_metadata.error)}</p>
                )}
                <p className="text-xs text-on-surface-variant">
                  {evt.actor_kind} · {new Date(evt.created_at).toLocaleString()}
                </p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      {/* Reject modal */}
      {showRejectModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-md rounded-xl bg-surface p-6 shadow-xl space-y-4">
            <h3 className="font-headline text-lg font-bold text-on-surface">Reject Request</h3>
            <textarea
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              rows={4}
              placeholder="Reason for rejection (shown to customer)…"
              className="w-full rounded-lg border border-outline-variant/30 px-3 py-2 text-sm"
            />
            <div className="flex gap-3 justify-end">
              <button
                type="button"
                onClick={() => setShowRejectModal(false)}
                className="rounded-full border border-outline-variant/30 px-5 py-2 text-sm font-semibold text-on-surface-variant hover:bg-surface-container"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={!rejectReason.trim()}
                onClick={handleReject}
                className="rounded-full bg-error px-5 py-2 text-sm font-semibold text-on-error disabled:opacity-40"
              >
                Confirm Reject
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
