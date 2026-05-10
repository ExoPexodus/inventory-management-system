"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  Badge,
  Breadcrumbs,
  EmptyState,
  Panel,
  PrimaryButton,
  SecondaryButton,
  TextInput,
  Timeline,
  Tooltip,
} from "@/components/ui/primitives";
import { Typeahead } from "@/components/ui/Typeahead";
import { formatMoney } from "@/lib/format";
import { useCurrency } from "@/lib/currency-context";
import { useHasPermission } from "@/lib/auth/user-context";

type ProductOption = { id: string; sku: string; name: string };

type LineInput = { product_id: string; quantity_requested: number; line_notes: string };

type LineOut = {
  id: string;
  product_id: string;
  product_sku: string | null;
  product_name: string | null;
  quantity_requested: number;
  quantity_shipped: number;
  quantity_received: number;
  unit_cost_at_transfer_cents: number | null;
  line_notes: string | null;
};

type TransferOut = {
  id: string;
  tenant_id: string;
  from_shop_id: string;
  from_shop_name: string | null;
  to_shop_id: string;
  to_shop_name: string | null;
  status: string;
  created_by_user_id: string | null;
  approved_by_user_id: string | null;
  approved_at: string | null;
  rejected_at: string | null;
  rejection_reason: string | null;
  shipped_at: string | null;
  received_at: string | null;
  cancelled_at: string | null;
  notes: string | null;
  lines: LineOut[];
  created_at: string;
};

function statusTone(s: string): "default" | "good" | "warn" | "danger" {
  switch (s) {
    case "completed": return "good";
    case "approved": return "good";
    case "in_transit": return "warn";
    case "pending_approval": return "warn";
    case "rejected": return "danger";
    case "cancelled": return "danger";
    default: return "default";
  }
}

function statusLabel(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// ── Edit Modal ─────────────────────────────────────────────────────────────

function EditTransferModal({
  transfer,
  products,
  onClose,
  onSaved,
}: {
  transfer: TransferOut;
  products: ProductOption[];
  onClose: () => void;
  onSaved: (t: TransferOut) => void;
}) {
  const [notes, setNotes] = useState(transfer.notes ?? "");
  const [lines, setLines] = useState<LineInput[]>(
    transfer.lines.map((l) => ({
      product_id: l.product_id,
      quantity_requested: l.quantity_requested,
      line_notes: l.line_notes ?? "",
    }))
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const productOptions = products.map((p) => ({ value: p.id, label: `${p.sku} — ${p.name}` }));

  const addLine = () => setLines((prev) => [...prev, { product_id: "", quantity_requested: 1, line_notes: "" }]);
  const updateLine = (idx: number, field: keyof LineInput, value: string | number) =>
    setLines((prev) => prev.map((l, i) => (i === idx ? { ...l, [field]: value } : l)));
  const removeLine = (idx: number) => setLines((prev) => prev.filter((_, i) => i !== idx));

  const handleSave = async () => {
    setError(null);
    setSaving(true);
    try {
      const body = {
        notes: notes || null,
        lines: lines.map((l) => ({
          product_id: l.product_id,
          quantity_requested: Number(l.quantity_requested),
          line_notes: l.line_notes || null,
        })),
      };
      const res = await fetch(`/api/ims/v1/admin/transfer-orders/${transfer.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const d = (await res.json()) as { detail?: string };
        throw new Error(d.detail ?? res.statusText);
      }
      onSaved((await res.json()) as TransferOut);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl bg-surface p-6 shadow-xl">
        <h2 className="font-headline text-xl font-bold text-on-surface">Edit Transfer</h2>
        <p className="mt-1 text-sm text-on-surface-variant">Update lines and notes while still in draft.</p>

        <div className="mt-4">
          <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">Notes</label>
          <TextInput value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Optional notes" />
        </div>

        <div className="mt-5 space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold text-on-surface">Lines</p>
            <button onClick={addLine} type="button" className="text-xs font-semibold text-primary hover:underline">
              + Add line
            </button>
          </div>
          {lines.map((line, idx) => (
            <div key={idx} className="grid grid-cols-12 gap-2 rounded-lg border border-outline-variant/20 bg-surface-container-low p-3">
              <div className="col-span-6">
                <label className="mb-0.5 block text-xs text-on-surface-variant">Product</label>
                <Typeahead
                  value={line.product_id}
                  onChange={(v) => updateLine(idx, "product_id", v)}
                  options={productOptions}
                  placeholder="Search products…"
                />
              </div>
              <div className="col-span-2">
                <label className="mb-0.5 block text-xs text-on-surface-variant">Qty</label>
                <TextInput
                  type="number"
                  min="1"
                  value={String(line.quantity_requested)}
                  onChange={(e) => updateLine(idx, "quantity_requested", parseInt(e.target.value, 10) || 1)}
                />
              </div>
              <div className="col-span-3">
                <label className="mb-0.5 block text-xs text-on-surface-variant">Notes</label>
                <TextInput
                  value={line.line_notes}
                  onChange={(e) => updateLine(idx, "line_notes", e.target.value)}
                  placeholder=""
                />
              </div>
              <div className="col-span-1 flex items-end pb-1">
                {lines.length > 1 && (
                  <button
                    type="button"
                    onClick={() => removeLine(idx)}
                    className="text-error hover:text-error/70"
                    title="Remove"
                  >
                    <span className="material-symbols-outlined text-lg">delete</span>
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>

        {error && (
          <p className="mt-3 rounded-lg border border-error/20 bg-error-container/20 px-3 py-2 text-sm text-on-error-container">
            {error}
          </p>
        )}

        <div className="mt-6 flex justify-end gap-3">
          <SecondaryButton type="button" onClick={onClose} disabled={saving}>Cancel</SecondaryButton>
          <PrimaryButton type="button" onClick={() => void handleSave()} disabled={saving}>
            {saving ? "Saving…" : "Save changes"}
          </PrimaryButton>
        </div>
      </div>
    </div>
  );
}

// ── Reject Modal ───────────────────────────────────────────────────────────

function RejectModal({
  onConfirm,
  onClose,
  saving,
}: {
  onConfirm: (reason: string) => void;
  onClose: () => void;
  saving: boolean;
}) {
  const [reason, setReason] = useState("");
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-2xl bg-surface p-6 shadow-xl">
        <h2 className="font-headline text-xl font-bold text-on-surface">Reject Transfer</h2>
        <p className="mt-1 text-sm text-on-surface-variant">Provide a reason for rejection.</p>
        <div className="mt-4">
          <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">Reason</label>
          <TextInput
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Explain why this transfer is rejected…"
          />
        </div>
        <div className="mt-5 flex justify-end gap-3">
          <SecondaryButton type="button" onClick={onClose} disabled={saving}>Cancel</SecondaryButton>
          <PrimaryButton
            type="button"
            onClick={() => onConfirm(reason)}
            disabled={saving || !reason.trim()}
            className="bg-error text-on-error hover:bg-error/90"
          >
            {saving ? "Rejecting…" : "Confirm reject"}
          </PrimaryButton>
        </div>
      </div>
    </div>
  );
}

// ── Ship Modal ─────────────────────────────────────────────────────────────

function ShipModal({
  lines,
  onConfirm,
  onClose,
  saving,
}: {
  lines: LineOut[];
  onConfirm: (quantities: Record<string, number>) => void;
  onClose: () => void;
  saving: boolean;
}) {
  const [qtys, setQtys] = useState<Record<string, number>>(
    Object.fromEntries(lines.map((l) => [l.id, l.quantity_requested]))
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-xl rounded-2xl bg-surface p-6 shadow-xl">
        <h2 className="font-headline text-xl font-bold text-on-surface">Mark as Shipped</h2>
        <p className="mt-1 text-sm text-on-surface-variant">Enter the quantity shipped per line.</p>
        <div className="mt-4 space-y-3">
          {lines.map((line) => (
            <div key={line.id} className="flex items-center gap-4 rounded-lg border border-outline-variant/20 bg-surface-container-low p-3">
              <div className="flex-1">
                <p className="text-sm font-semibold text-on-surface">{line.product_name ?? line.product_sku ?? line.product_id.slice(0, 8)}</p>
                <p className="text-xs text-on-surface-variant">Requested: {line.quantity_requested}</p>
              </div>
              <div className="w-24">
                <TextInput
                  type="number"
                  min="0"
                  max={String(line.quantity_requested)}
                  value={String(qtys[line.id] ?? 0)}
                  onChange={(e) => setQtys((prev) => ({ ...prev, [line.id]: parseInt(e.target.value, 10) || 0 }))}
                />
              </div>
            </div>
          ))}
        </div>
        <div className="mt-5 flex justify-end gap-3">
          <SecondaryButton type="button" onClick={onClose} disabled={saving}>Cancel</SecondaryButton>
          <PrimaryButton type="button" onClick={() => onConfirm(qtys)} disabled={saving}>
            {saving ? "Shipping…" : "Confirm ship"}
          </PrimaryButton>
        </div>
      </div>
    </div>
  );
}

// ── Receive Modal ──────────────────────────────────────────────────────────

function ReceiveModal({
  lines,
  onConfirm,
  onClose,
  saving,
}: {
  lines: LineOut[];
  onConfirm: (quantities: Record<string, number>) => void;
  onClose: () => void;
  saving: boolean;
}) {
  const [qtys, setQtys] = useState<Record<string, number>>(
    Object.fromEntries(lines.map((l) => [l.id, l.quantity_shipped]))
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-xl rounded-2xl bg-surface p-6 shadow-xl">
        <h2 className="font-headline text-xl font-bold text-on-surface">Confirm Receipt</h2>
        <p className="mt-1 text-sm text-on-surface-variant">Enter the quantity received per line.</p>
        <div className="mt-4 space-y-3">
          {lines.map((line) => (
            <div key={line.id} className="flex items-center gap-4 rounded-lg border border-outline-variant/20 bg-surface-container-low p-3">
              <div className="flex-1">
                <p className="text-sm font-semibold text-on-surface">{line.product_name ?? line.product_sku ?? line.product_id.slice(0, 8)}</p>
                <p className="text-xs text-on-surface-variant">Shipped: {line.quantity_shipped}</p>
                {line.quantity_shipped < line.quantity_requested && (
                  <p className="text-xs text-secondary">
                    Note: {line.quantity_requested - line.quantity_shipped} unit(s) not shipped
                  </p>
                )}
              </div>
              <div className="w-24">
                <TextInput
                  type="number"
                  min="0"
                  max={String(line.quantity_shipped)}
                  value={String(qtys[line.id] ?? 0)}
                  onChange={(e) => setQtys((prev) => ({ ...prev, [line.id]: parseInt(e.target.value, 10) || 0 }))}
                />
              </div>
            </div>
          ))}
        </div>
        <div className="mt-5 flex justify-end gap-3">
          <SecondaryButton type="button" onClick={onClose} disabled={saving}>Cancel</SecondaryButton>
          <PrimaryButton type="button" onClick={() => onConfirm(qtys)} disabled={saving}>
            {saving ? "Confirming…" : "Confirm receipt"}
          </PrimaryButton>
        </div>
      </div>
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────

export default function TransferDetailPage() {
  const params = useParams<{ id: string }>();
  const currency = useCurrency();
  const canWrite = useHasPermission("operations:write");
  const canApprove = useHasPermission("transfers:approve");

  const [transfer, setTransfer] = useState<TransferOut | null>(null);
  const [products, setProducts] = useState<ProductOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSaving, setActionSaving] = useState(false);

  const [showEdit, setShowEdit] = useState(false);
  const [showReject, setShowReject] = useState(false);
  const [showShip, setShowShip] = useState(false);
  const [showReceive, setShowReceive] = useState(false);

  const fetchTransfer = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`/api/ims/v1/admin/transfer-orders/${params.id}`);
      if (r.ok) setTransfer((await r.json()) as TransferOut);
    } finally {
      setLoading(false);
    }
  }, [params.id]);

  useEffect(() => {
    void fetchTransfer();
    // Load products for edit modal
    void (async () => {
      const r = await fetch("/api/ims/v1/admin/products");
      if (r.ok) setProducts((await r.json()) as ProductOption[]);
    })();
  }, [fetchTransfer]);

  const doAction = async (path: string, body?: unknown) => {
    setActionError(null);
    setActionSaving(true);
    try {
      const r = await fetch(`/api/ims/v1/admin/transfer-orders/${params.id}/${path}`, {
        method: "POST",
        headers: body ? { "Content-Type": "application/json" } : {},
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!r.ok) {
        const d = (await r.json()) as { detail?: string };
        throw new Error(d.detail ?? r.statusText);
      }
      setTransfer((await r.json()) as TransferOut);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setActionSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <Breadcrumbs items={[{ label: "Transfer Orders", href: "/transfer-orders" }, { label: "Loading…" }]} />
        <div className="rounded-xl bg-surface-container-lowest p-8 text-center text-on-surface-variant">Loading…</div>
      </div>
    );
  }

  if (!transfer) {
    return (
      <div className="space-y-6">
        <Breadcrumbs items={[{ label: "Transfer Orders", href: "/transfer-orders" }, { label: "Not found" }]} />
        <EmptyState title="Transfer not found" detail="This transfer order does not exist or you don't have access." />
      </div>
    );
  }

  // Status timeline items
  const timelineItems: Array<{ title: string; detail?: string; tone?: "default" | "warn" | "danger" }> = [
    { title: "Created", detail: new Date(transfer.created_at).toLocaleString(), tone: "default" },
  ];
  if (transfer.approved_at) {
    timelineItems.push({
      title: transfer.approved_by_user_id ? "Approved" : "Auto-approved",
      detail: new Date(transfer.approved_at).toLocaleString(),
      tone: "default",
    });
  }
  if (transfer.rejected_at) {
    timelineItems.push({
      title: "Rejected",
      detail: `${new Date(transfer.rejected_at).toLocaleString()} — ${transfer.rejection_reason ?? ""}`,
      tone: "danger",
    });
  }
  if (transfer.shipped_at) {
    timelineItems.push({
      title: "Shipped",
      detail: new Date(transfer.shipped_at).toLocaleString(),
      tone: "default",
    });
  }
  if (transfer.received_at) {
    timelineItems.push({
      title: "Received",
      detail: new Date(transfer.received_at).toLocaleString(),
      tone: "default",
    });
  }
  if (transfer.cancelled_at) {
    timelineItems.push({
      title: "Cancelled",
      detail: new Date(transfer.cancelled_at).toLocaleString(),
      tone: "danger",
    });
  }

  const totalCostValue = transfer.lines.reduce((sum, l) => {
    if (l.unit_cost_at_transfer_cents != null) {
      return sum + l.unit_cost_at_transfer_cents * l.quantity_requested;
    }
    return sum;
  }, 0);

  return (
    <div className="space-y-6">
      <Breadcrumbs
        items={[
          { label: "Transfer Orders", href: "/transfer-orders" },
          { label: transfer.id.slice(0, 8) + "…" },
        ]}
      />

      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="font-headline text-3xl font-extrabold text-on-surface">
              {transfer.from_shop_name ?? "—"}
              <span className="mx-2 text-on-surface-variant">→</span>
              {transfer.to_shop_name ?? "—"}
            </h1>
            <Badge tone={statusTone(transfer.status)}>{statusLabel(transfer.status)}</Badge>
          </div>
          <p className="mt-1 font-mono text-xs text-on-surface-variant">{transfer.id}</p>
          {transfer.notes && (
            <p className="mt-2 text-sm text-on-surface-variant">{transfer.notes}</p>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex flex-wrap gap-2">
          {transfer.status === "draft" && canWrite && (
            <>
              <SecondaryButton type="button" onClick={() => setShowEdit(true)}>
                Edit
              </SecondaryButton>
              <PrimaryButton
                type="button"
                disabled={actionSaving}
                onClick={() => void doAction("submit")}
              >
                Submit
              </PrimaryButton>
              <SecondaryButton
                type="button"
                disabled={actionSaving}
                onClick={() => void doAction("cancel")}
                className="border-error/40 text-error hover:bg-error-container/30"
              >
                Cancel
              </SecondaryButton>
            </>
          )}

          {transfer.status === "pending_approval" && (
            <>
              {canApprove ? (
                <>
                  <PrimaryButton type="button" disabled={actionSaving} onClick={() => void doAction("approve")}>
                    {actionSaving ? "Approving…" : "Approve"}
                  </PrimaryButton>
                  <SecondaryButton
                    type="button"
                    disabled={actionSaving}
                    onClick={() => setShowReject(true)}
                    className="border-error/40 text-error hover:bg-error-container/30"
                  >
                    Reject
                  </SecondaryButton>
                </>
              ) : (
                <Tooltip label="You need the 'transfers:approve' permission">
                  <span className="inline-flex cursor-not-allowed items-center gap-2 rounded-lg border border-outline-variant/40 px-4 py-2 text-sm font-semibold text-on-surface-variant opacity-60">
                    <span className="material-symbols-outlined text-base">lock</span>
                    Approve (permission required)
                  </span>
                </Tooltip>
              )}
              {canWrite && (
                <SecondaryButton
                  type="button"
                  disabled={actionSaving}
                  onClick={() => void doAction("cancel")}
                  className="border-error/40 text-error hover:bg-error-container/30"
                >
                  Cancel
                </SecondaryButton>
              )}
            </>
          )}

          {transfer.status === "approved" && canWrite && (
            <>
              <PrimaryButton type="button" disabled={actionSaving} onClick={() => setShowShip(true)}>
                Ship
              </PrimaryButton>
              <SecondaryButton
                type="button"
                disabled={actionSaving}
                onClick={() => void doAction("cancel")}
                className="border-error/40 text-error hover:bg-error-container/30"
              >
                Cancel
              </SecondaryButton>
            </>
          )}

          {transfer.status === "in_transit" && canWrite && (
            <PrimaryButton type="button" disabled={actionSaving} onClick={() => setShowReceive(true)}>
              Receive
            </PrimaryButton>
          )}
        </div>
      </div>

      {actionError && (
        <p className="rounded-lg border border-error/20 bg-error-container/20 px-4 py-3 text-sm text-on-error-container">
          {actionError}
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Lines table */}
        <div className="lg:col-span-2">
          <Panel title="Line Items" noPad>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-outline-variant/20 text-left text-xs font-bold uppercase tracking-widest text-on-surface-variant">
                    <th className="px-4 py-3">Product</th>
                    <th className="px-4 py-3 text-right">Requested</th>
                    <th className="px-4 py-3 text-right">Shipped</th>
                    <th className="px-4 py-3 text-right">Received</th>
                    <th className="px-4 py-3 text-right">Unit Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {transfer.lines.length === 0 ? (
                    <tr><td colSpan={5}><EmptyState title="No lines" /></td></tr>
                  ) : (
                    transfer.lines.map((line) => (
                      <tr key={line.id} className="border-b border-outline-variant/10 hover:bg-surface-container-low">
                        <td className="px-4 py-3">
                          <p className="font-medium text-on-surface">{line.product_name ?? line.product_sku ?? "—"}</p>
                          {line.product_sku && line.product_name && (
                            <p className="text-xs text-on-surface-variant">{line.product_sku}</p>
                          )}
                          {line.line_notes && (
                            <p className="mt-0.5 text-xs italic text-on-surface-variant">{line.line_notes}</p>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right">{line.quantity_requested}</td>
                        <td className="px-4 py-3 text-right">
                          {line.quantity_shipped > 0 ? (
                            <span className={line.quantity_shipped < line.quantity_requested ? "text-secondary" : ""}>
                              {line.quantity_shipped}
                            </span>
                          ) : (
                            <span className="text-on-surface-variant">—</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right">
                          {line.quantity_received > 0 ? (
                            <span className={line.quantity_received < line.quantity_shipped ? "text-secondary" : ""}>
                              {line.quantity_received}
                              {line.quantity_received < line.quantity_shipped && (
                                <Tooltip label={`${line.quantity_shipped - line.quantity_received} unit(s) unaccounted — create a manual adjustment`}>
                                  <span className="material-symbols-outlined ml-1 align-middle text-sm text-secondary">warning</span>
                                </Tooltip>
                              )}
                            </span>
                          ) : (
                            <span className="text-on-surface-variant">—</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-right text-on-surface-variant">
                          {line.unit_cost_at_transfer_cents != null
                            ? formatMoney(line.unit_cost_at_transfer_cents, currency)
                            : "—"}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
                {transfer.lines.length > 0 && totalCostValue > 0 && (
                  <tfoot>
                    <tr className="border-t border-outline-variant/20 bg-surface-container-low">
                      <td colSpan={4} className="px-4 py-3 text-right text-xs font-bold uppercase tracking-widest text-on-surface-variant">
                        Total transfer value
                      </td>
                      <td className="px-4 py-3 text-right font-bold text-on-surface">
                        {formatMoney(totalCostValue, currency)}
                      </td>
                    </tr>
                  </tfoot>
                )}
              </table>
            </div>
          </Panel>
        </div>

        {/* Status timeline */}
        <div>
          <Panel title="Timeline">
            <Timeline items={timelineItems} />
          </Panel>
        </div>
      </div>

      {/* Modals */}
      {showEdit && transfer && (
        <EditTransferModal
          transfer={transfer}
          products={products}
          onClose={() => setShowEdit(false)}
          onSaved={(updated) => {
            setTransfer(updated);
            setShowEdit(false);
          }}
        />
      )}

      {showReject && (
        <RejectModal
          saving={actionSaving}
          onClose={() => setShowReject(false)}
          onConfirm={(reason) => {
            void doAction("reject", { reason }).then(() => setShowReject(false));
          }}
        />
      )}

      {showShip && transfer && (
        <ShipModal
          lines={transfer.lines}
          saving={actionSaving}
          onClose={() => setShowShip(false)}
          onConfirm={(quantities) => {
            const lines = Object.entries(quantities).map(([line_id, quantity]) => ({ line_id, quantity }));
            void doAction("ship", { lines }).then(() => setShowShip(false));
          }}
        />
      )}

      {showReceive && transfer && (
        <ReceiveModal
          lines={transfer.lines}
          saving={actionSaving}
          onClose={() => setShowReceive(false)}
          onConfirm={(quantities) => {
            const lines = Object.entries(quantities).map(([line_id, quantity]) => ({ line_id, quantity }));
            void doAction("receive", { lines }).then(() => setShowReceive(false));
          }}
        />
      )}
    </div>
  );
}
