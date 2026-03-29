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
  TextInput,
} from "@/components/ui/primitives";
import { formatMoneyUSD } from "@/lib/format";

type TxLine = {
  product_id: string;
  product_sku: string | null;
  product_name: string | null;
  quantity: number;
  unit_price_cents: number;
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
          <p className="mt-4 font-headline text-xl font-bold text-on-surface">{formatMoneyUSD(shiftHealth.volume)}</p>
          <p className="text-xs text-on-surface-variant">Total volume (page)</p>
        </div>
        <div className="rounded-xl border border-error/20 bg-error-container/30 p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-error-container">Flagged / pending</p>
          <p className="mt-4 font-headline text-3xl font-extrabold text-error">{flaggedPending}</p>
          <p className="mt-1 text-sm text-on-error-container/90">Needs attention on current page</p>
        </div>
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-low p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Filters</p>
          <div className="mt-4 space-y-3">
            <label className="block text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Status</label>
            <SelectInput value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All statuses</option>
              <option value="posted">Posted</option>
              <option value="pending">Pending</option>
              <option value="refunded">Refunded</option>
              <option value="voided">Voided</option>
              <option value="flagged">Flagged</option>
            </SelectInput>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">From</label>
                <TextInput type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
              </div>
              <div>
                <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">To</label>
                <TextInput type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
              </div>
            </div>
          </div>
        </div>
      </div>

      {err ? <ErrorState detail={err} /> : null}

      <section className="overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm">
        <div className="border-b border-outline-variant/10 px-6 py-4">
          <h3 className="font-headline text-lg font-bold text-on-surface">Transaction ledger</h3>
          <p className="mt-0.5 text-sm text-on-surface-variant">Immutable audit view — amounts in USD.</p>
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
                    <td className="px-6 py-3 text-right tabular-nums font-semibold text-on-surface">{formatMoneyUSD(t.total_cents)}</td>
                    <td className="px-6 py-3 text-center">
                      <button
                        type="button"
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
    </div>
  );
}
