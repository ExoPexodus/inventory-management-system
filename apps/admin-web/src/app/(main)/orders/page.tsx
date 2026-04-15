"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Avatar,
  ErrorState,
  LoadingRow,
  PageHeader,
  Pagination,
  SearchBar,
  SelectInput,
} from "@/components/ui/primitives";
import { DateInput } from "@/components/ui/DateInput";
import { formatMoney } from "@/lib/format";
import { useCurrency } from "@/lib/currency-context";

type TxLine = {
  product_id: string;
  product_sku: string | null;
  product_name: string | null;
  quantity: number;
  unit_price_cents: number;
};

type TxPayment = {
  tender_type: string;
  amount_cents: number;
};

type Tx = {
  id: string;
  shop_id: string;
  kind?: string;
  status: string;
  total_cents: number;
  tax_cents: number;
  created_at: string;
  lines: TxLine[];
  payments: TxPayment[];
  cashier_name?: string | null;
};

type Page = { items: Tx[]; next_cursor: string | null };

const PAGE_LIMIT = 20;

function statusBadgeClasses(status: string): string {
  const s = status.toLowerCase();
  if (s === "posted") return "bg-tertiary-fixed text-on-tertiary-fixed-variant";
  if (s === "pending") return "bg-secondary-container text-on-secondary-container";
  if (s === "refunded" || s === "voided") return "bg-surface-container-highest text-on-surface";
  if (s === "flagged") return "bg-error-container text-on-error-container";
  return "bg-surface-container-high text-on-surface-variant";
}

export default function OrdersPage() {
  const currency = useCurrency();
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);
  const [cache, setCache] = useState<Record<number, Tx[]>>({});
  const [nextAfter, setNextAfter] = useState<Record<number, string | null>>({});
  const nextAfterRef = useRef(nextAfter);
  nextAfterRef.current = nextAfter;
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [selectedTx, setSelectedTx] = useState<Tx | null>(null);
  const [showFlaggedModal, setShowFlaggedModal] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const rows = useMemo(() => cache[page] ?? [], [cache, page]);

  const fetchPage = useCallback(async (targetPage: number) => {
    setLoading(true);
    setErr(null);
    try {
      const sp = new URLSearchParams();
      sp.set("limit", String(PAGE_LIMIT));
      if (status) sp.set("status", status);
      if (q.trim()) sp.set("q", q.trim());
      if (dateFrom) sp.set("date_from", dateFrom);
      if (dateTo) sp.set("date_to", dateTo);
      const cursor = targetPage <= 1 ? null : nextAfterRef.current[targetPage - 1] ?? null;
      if (targetPage > 1 && !cursor) {
        setErr("Cannot load this page yet.");
        setLoading(false);
        return;
      }
      if (cursor) sp.set("cursor", cursor);
      const r = await fetch(`/api/ims/v1/admin/transactions?${sp.toString()}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = (await r.json()) as Page;
      setCache((prev) => ({ ...prev, [targetPage]: data.items }));
      setNextAfter((prev) => ({ ...prev, [targetPage]: data.next_cursor }));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [status, q, dateFrom, dateTo]);

  useEffect(() => {
    setPage(1);
    setCache({});
    setNextAfter({});
  }, [status, q, dateFrom, dateTo]);

  useEffect(() => {
    if (cache[page]) {
      setLoading(false);
      return;
    }
    void fetchPage(page);
  }, [page, cache, fetchPage, status, q, dateFrom, dateTo]);

  const shiftHealth = useMemo(() => {
    const count = rows.length;
    const volume = rows.reduce((acc, t) => acc + t.total_cents, 0);
    return { count, volume };
  }, [rows]);

  const flaggedPending = useMemo(
    () =>
      rows.filter((t) => {
        const s = t.status.toLowerCase();
        return s === "pending" || s === "flagged";
      }).length,
    [rows],
  );

  const totalPages = nextAfter[page] ? page + 1 : Math.max(page, 1);

  async function handleTxAction(txId: string, newStatus: "posted" | "voided") {
    setActionLoading(txId);
    try {
      await fetch(`/api/ims/v1/admin/transactions/${txId}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: newStatus }),
      });
    } finally {
      setActionLoading(null);
      setCache({});
      setNextAfter({});
      setPage(1);
    }
  }

  function exportAuditReport() {
    const header = ["order_id", "cashier", "timestamp", "status", "amount_cents", "tax_cents"];
    const lines = rows.map((t) =>
      [
        t.id,
        t.cashier_name ?? "",
        t.created_at,
        t.status,
        String(t.total_cents),
        String(t.tax_cents),
      ].join(","),
    );
    const csv = [header.join(","), ...lines].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `order-audit-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="Order audit ledger"
        title="Synced transactions"
        subtitle="Cursor-paginated register with shift health and exportable audit trail."
        action={
          <>
            <SearchBar
              className="min-w-[14rem]"
              placeholder="Search SKU / product…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
            <button
              type="button"
              onClick={exportAuditReport}
              className="ink-gradient inline-flex items-center gap-2 rounded-lg px-6 py-2.5 text-sm font-semibold text-on-primary shadow-sm transition hover:opacity-90"
            >
              <span className="material-symbols-outlined text-lg">download</span>
              Export audit report
            </button>
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Shift health</p>
          <p className="mt-4 font-headline text-3xl font-extrabold text-primary">{shiftHealth.count}</p>
          <p className="mt-1 text-sm text-on-surface-variant">Transactions on this page</p>
          <p className="mt-4 font-headline text-xl font-bold text-on-surface">{formatMoney(shiftHealth.volume, currency)}</p>
          <p className="text-xs text-on-surface-variant">Total volume (page)</p>
        </div>
        <button
          type="button"
          onClick={() => flaggedPending > 0 ? setShowFlaggedModal(true) : undefined}
          className={`rounded-xl border border-error/20 bg-error-container/30 p-6 shadow-sm text-left w-full transition ${flaggedPending > 0 ? "cursor-pointer hover:bg-error-container/45" : "cursor-default"}`}
        >
          <p className="text-xs font-bold uppercase tracking-widest text-on-error-container">Flagged / pending</p>
          <p className="mt-4 font-headline text-3xl font-extrabold text-error">{flaggedPending}</p>
          <p className="mt-1 text-sm text-on-error-container/90">
            {flaggedPending > 0 ? "Click to review and take action" : "No attention needed on this page"}
          </p>
        </button>
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-low p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Filters</p>
          <div className="mt-4 space-y-3">
            <label className="block text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Status</label>
            <SelectInput
              value={status}
              onChange={setStatus}
              placeholder="All statuses"
              options={[
                { value: "", label: "All statuses" },
                { value: "posted", label: "Posted" },
                { value: "pending", label: "Pending" },
                { value: "refunded", label: "Refunded" },
                { value: "voided", label: "Voided" },
                { value: "flagged", label: "Flagged" },
              ]}
            />
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">From</label>
                <DateInput value={dateFrom} onChange={setDateFrom} />
              </div>
              <div>
                <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">To</label>
                <DateInput value={dateTo} onChange={setDateTo} />
              </div>
            </div>
          </div>
        </div>
      </div>

      {err ? <ErrorState detail={err} /> : null}

      <section className="overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm">
        <div className="border-b border-outline-variant/10 px-6 py-4">
          <h3 className="font-headline text-lg font-bold text-on-surface">Transaction ledger</h3>
          <p className="mt-0.5 text-sm text-on-surface-variant">Immutable audit view — amounts in {currency.code}.</p>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-outline-variant/10">
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Order ID</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Cashier</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Timestamp</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Status</th>
                <th className="px-6 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Amount</th>
                <th className="px-6 py-3 text-center text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {loading && rows.length === 0 ? (
                <LoadingRow colSpan={6} />
              ) : null}
              {!loading && rows.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-10 text-center text-sm text-on-surface-variant">
                    No transactions for this page.
                  </td>
                </tr>
              ) : null}
              {rows.map((t) => {
                const cashier = t.cashier_name?.trim() || "Unassigned";
                return (
                  <tr key={t.id} className="group hover:bg-surface-container-low/60">
                    <td className="px-6 py-3 font-mono text-xs text-on-surface" title={t.id}>#{t.id.slice(0, 8)}</td>
                    <td className="px-6 py-3">
                      <div className="flex items-center gap-2">
                        <Avatar name={cashier} className="h-9 w-9 text-[11px]" />
                        <span className="font-medium text-on-surface">{cashier}</span>
                      </div>
                    </td>
                    <td className="px-6 py-3 text-xs text-on-surface-variant">
                      {new Date(t.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}{" "}
                      <span className="text-on-surface-variant/50">{new Date(t.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
                    </td>
                    <td className="px-6 py-3">
                      <span className={`inline-flex rounded-full px-2.5 py-1 text-[10px] font-bold uppercase ${statusBadgeClasses(t.status)}`}>
                        {t.status}
                      </span>
                    </td>
                    <td className="px-6 py-3 text-right tabular-nums font-semibold text-on-surface">{formatMoney(t.total_cents, currency)}</td>
                    <td className="px-6 py-3 text-center">
                      <button
                        type="button"
                        onClick={() => setSelectedTx(t)}
                        className="inline-flex rounded-lg p-2 text-on-surface-variant opacity-0 transition group-hover:opacity-100 hover:bg-surface-container"
                        aria-label="Receipt"
                      >
                        <span className="material-symbols-outlined text-xl">receipt_long</span>
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <Pagination
          page={page}
          totalPages={totalPages}
          onChange={(p) => setPage(p)}
        />
      </section>

      {selectedTx ? (
        <ReceiptDialog tx={selectedTx} onClose={() => setSelectedTx(null)} />
      ) : null}

      {showFlaggedModal ? (
        <FlaggedPendingModal
          txs={rows.filter((t) => {
            const s = t.status.toLowerCase();
            return s === "pending" || s === "flagged";
          })}
          onClose={() => setShowFlaggedModal(false)}
          onViewReceipt={(tx) => { setShowFlaggedModal(false); setSelectedTx(tx); }}
          onAction={(txId, newStatus) => void handleTxAction(txId, newStatus)}
          actionLoading={actionLoading}
        />
      ) : null}
    </div>
  );
}

function ReceiptDialog({ tx, onClose }: { tx: Tx; onClose: () => void }) {
  const currency = useCurrency();
  const subtotal = tx.lines.reduce((acc, l) => acc + l.quantity * l.unit_price_cents, 0);
  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-2xl bg-surface shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="ink-gradient rounded-t-2xl px-6 py-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-bold uppercase tracking-widest text-on-primary/80">Receipt</p>
              <p className="mt-1 font-mono text-sm text-on-primary/90">#{tx.id}</p>
            </div>
            <span className={`mt-1 rounded-full px-2.5 py-1 text-[10px] font-bold uppercase ${statusBadgeClasses(tx.status)}`}>
              {tx.status}
            </span>
          </div>
          <p className="mt-2 text-xs text-on-primary/70">
            {new Date(tx.created_at).toLocaleString(undefined, {
              dateStyle: "medium",
              timeStyle: "short",
            })}
            {tx.cashier_name ? ` · ${tx.cashier_name}` : ""}
          </p>
        </div>

        {/* Lines */}
        <div className="max-h-64 overflow-y-auto px-6 py-4">
          <p className="mb-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Items</p>
          {tx.lines.length === 0 ? (
            <p className="text-sm text-on-surface-variant">No line items.</p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-outline-variant/10 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
                  <th className="pb-2 text-left">Product</th>
                  <th className="pb-2 text-center">Qty</th>
                  <th className="pb-2 text-right">Total</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/10">
                {tx.lines.map((l, i) => (
                  <tr key={i}>
                    <td className="py-2">
                      <p className="font-medium text-on-surface">{l.product_name ?? "—"}</p>
                      {l.product_sku ? <p className="font-mono text-[11px] text-on-surface-variant">{l.product_sku}</p> : null}
                    </td>
                    <td className="py-2 text-center tabular-nums text-on-surface-variant">{l.quantity}</td>
                    <td className="py-2 text-right tabular-nums font-semibold text-on-surface">
                      {formatMoney(l.quantity * l.unit_price_cents, currency)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {/* Totals */}
        <div className="border-t border-outline-variant/10 px-6 py-4 space-y-1.5">
          <div className="flex justify-between text-sm text-on-surface-variant">
            <span>Subtotal</span><span className="tabular-nums">{formatMoney(subtotal, currency)}</span>
          </div>
          <div className="flex justify-between text-sm text-on-surface-variant">
            <span>Tax</span><span className="tabular-nums">{formatMoney(tx.tax_cents, currency)}</span>
          </div>
          <div className="flex justify-between font-bold text-base text-on-surface border-t border-outline-variant/10 pt-2">
            <span>Total</span><span className="tabular-nums">{formatMoney(tx.total_cents, currency)}</span>
          </div>
        </div>

        {/* Payments */}
        {tx.payments.length > 0 ? (
          <div className="border-t border-outline-variant/10 px-6 py-3 space-y-1">
            <p className="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant mb-2">Payments</p>
            {tx.payments.map((p, i) => (
              <div key={i} className="flex justify-between text-sm">
                <span className="capitalize text-on-surface-variant">{p.tender_type.replace(/_/g, " ")}</span>
                <span className="tabular-nums text-on-surface">{formatMoney(p.amount_cents, currency)}</span>
              </div>
            ))}
          </div>
        ) : null}

        {/* Close */}
        <div className="border-t border-outline-variant/10 px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="w-full rounded-lg border border-outline-variant/20 py-2 text-sm font-semibold text-on-surface-variant transition hover:bg-surface-container"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

function FlaggedPendingModal({
  txs,
  onClose,
  onViewReceipt,
  onAction,
  actionLoading,
}: {
  txs: Tx[];
  onClose: () => void;
  onViewReceipt: (tx: Tx) => void;
  onAction: (txId: string, newStatus: "posted" | "voided") => void;
  actionLoading: string | null;
}) {
  const currency = useCurrency();
  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl rounded-2xl bg-surface shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="rounded-t-2xl border-b border-error/20 bg-error-container/30 px-6 py-5">
          <p className="text-xs font-bold uppercase tracking-widest text-on-error-container">Attention required</p>
          <h3 className="mt-1 font-headline text-xl font-extrabold text-on-surface">
            Flagged &amp; pending transactions
          </h3>
          <p className="mt-0.5 text-sm text-on-surface-variant">
            {txs.length} transaction{txs.length !== 1 ? "s" : ""} need{txs.length === 1 ? "s" : ""} review on this page
          </p>
        </div>

        {/* List */}
        <div className="max-h-[60vh] overflow-y-auto">
          {txs.length === 0 ? (
            <p className="px-6 py-8 text-center text-sm text-on-surface-variant">No flagged or pending transactions on this page.</p>
          ) : (
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b border-outline-variant/10 bg-surface-container-low">
                  <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Order</th>
                  <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Cashier</th>
                  <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Status</th>
                  <th className="px-6 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Amount</th>
                  <th className="px-6 py-3 text-center text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/10">
                {txs.map((t) => {
                  const isActioning = actionLoading === t.id;
                  return (
                    <tr key={t.id} className="hover:bg-surface-container-low/40">
                      <td className="px-6 py-4">
                        <p className="font-mono text-xs font-bold text-on-surface">#{t.id.slice(0, 8)}</p>
                        <p className="mt-0.5 text-[10px] text-on-surface-variant">
                          {new Date(t.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                          {" "}
                          {new Date(t.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                        </p>
                      </td>
                      <td className="px-6 py-4 text-on-surface">{t.cashier_name?.trim() || "Unassigned"}</td>
                      <td className="px-6 py-4">
                        <span className={`inline-flex rounded-full px-2.5 py-1 text-[10px] font-bold uppercase ${statusBadgeClasses(t.status)}`}>
                          {t.status}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-right tabular-nums font-semibold text-on-surface">
                        {formatMoney(t.total_cents, currency)}
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center justify-center gap-1.5">
                          <button
                            type="button"
                            disabled={isActioning}
                            onClick={() => onAction(t.id, "posted")}
                            className="inline-flex items-center gap-1 rounded-lg bg-tertiary-fixed px-2.5 py-1.5 text-xs font-semibold text-on-tertiary-fixed-variant transition hover:opacity-90 disabled:opacity-50"
                          >
                            <span className="material-symbols-outlined text-sm">check_circle</span>
                            {isActioning ? "…" : "Approve"}
                          </button>
                          <button
                            type="button"
                            disabled={isActioning}
                            onClick={() => onAction(t.id, "voided")}
                            className="inline-flex items-center gap-1 rounded-lg border border-outline-variant/30 bg-surface-container px-2.5 py-1.5 text-xs font-semibold text-on-surface transition hover:bg-surface-container-high disabled:opacity-50"
                          >
                            <span className="material-symbols-outlined text-sm">cancel</span>
                            {isActioning ? "…" : "Void"}
                          </button>
                          <button
                            type="button"
                            disabled={isActioning}
                            onClick={() => onViewReceipt(t)}
                            className="inline-flex items-center gap-1 rounded-lg border border-outline-variant/20 px-2.5 py-1.5 text-xs font-semibold text-on-surface-variant transition hover:bg-surface-container disabled:opacity-50"
                          >
                            <span className="material-symbols-outlined text-sm">receipt_long</span>
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Footer */}
        <div className="border-t border-outline-variant/10 px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="w-full rounded-lg border border-outline-variant/20 py-2 text-sm font-semibold text-on-surface-variant transition hover:bg-surface-container"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
