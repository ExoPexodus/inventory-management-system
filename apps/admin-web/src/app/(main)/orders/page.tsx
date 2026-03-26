"use client";

import { useCallback, useEffect, useState } from "react";
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
  status: string;
  total_cents: number;
  tax_cents: number;
  created_at: string;
  lines: TxLine[];
};

type Page = { items: Tx[]; next_cursor: string | null };

export default function OrdersPage() {
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [rows, setRows] = useState<Tx[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const fetchPage = useCallback(async (cursor: string | null, append: boolean) => {
    setLoading(true);
    setErr(null);
    try {
      const sp = new URLSearchParams();
      sp.set("limit", "30");
      if (status) sp.set("status", status);
      if (q.trim()) sp.set("q", q.trim());
      if (cursor) sp.set("cursor", cursor);
      const r = await fetch(`/api/ims/v1/admin/transactions?${sp.toString()}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = (await r.json()) as Page;
      setRows((prev) => (append ? [...prev, ...data.items] : data.items));
      setNextCursor(data.next_cursor);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "failed");
    } finally {
      setLoading(false);
    }
  }, [status, q]);

  useEffect(() => {
    void fetchPage(null, false);
  }, [fetchPage]);

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-wider text-primary/50">Order audit ledger</p>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-primary">Synced transactions</h1>
      </header>
      <div className="flex flex-wrap gap-3">
        <input
          placeholder="Search SKU / name…"
          className="min-w-[12rem] rounded-lg border border-primary/15 px-3 py-2 text-sm"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select
          className="rounded-lg border border-primary/15 px-3 py-2 text-sm"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="">All statuses</option>
          <option value="posted">Posted</option>
          <option value="pending">Pending</option>
          <option value="refunded">Refunded</option>
        </select>
      </div>
      {err ? <p className="text-sm text-red-700">{err}</p> : null}
      <div className="overflow-x-auto rounded-xl border border-primary/10 bg-white/90 shadow-sm">
        <table className="min-w-full text-left text-sm">
          <thead>
            <tr className="border-b border-primary/10 text-xs uppercase tracking-wide text-primary/50">
              <th className="px-4 py-3">When</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3 text-right">Total</th>
              <th className="px-4 py-3">Lines</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-primary/5">
            {rows.map((t) => (
              <tr key={t.id}>
                <td className="px-4 py-3 font-mono text-xs text-primary/80">{t.created_at}</td>
                <td className="px-4 py-3">
                  <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium">{t.status}</span>
                </td>
                <td className="px-4 py-3 text-right tabular-nums font-medium">
                  {formatMoneyUSD(t.total_cents)}
                  <span className="ml-2 text-xs font-normal text-primary/60">tax {formatMoneyUSD(t.tax_cents)}</span>
                </td>
                <td className="px-4 py-3 text-xs text-primary/75">
                  {t.lines
                    .map((l) => `${l.product_sku ?? "?"} ×${l.quantity}`)
                    .join(" · ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {rows.length === 0 && !loading ? (
          <p className="p-6 text-center text-sm text-primary/60">No transactions match.</p>
        ) : null}
      </div>
      {nextCursor ? (
        <button
          type="button"
          className="rounded-lg border border-primary/20 px-4 py-2 text-sm font-medium text-primary hover:bg-primary/5"
          disabled={loading}
          onClick={() => void fetchPage(nextCursor, true)}
        >
          {loading ? "Loading…" : "Load more"}
        </button>
      ) : null}
    </div>
  );
}
