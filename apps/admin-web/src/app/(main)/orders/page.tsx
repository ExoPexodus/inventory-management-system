"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Badge,
  EmptyState,
  ErrorState,
  LoadingRow,
  PageHeader,
  Panel,
  SecondaryButton,
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
    <div className="space-y-7">
      <PageHeader
        kicker="Order audit ledger"
        title="Synced transactions"
        subtitle="Filter by status or SKU/name to inspect posted, pending, and refunded activity."
      />
      <Panel
        title="Filters"
        subtitle="All filters apply server-side with keyset pagination."
      >
        <div className="flex flex-wrap gap-3">
          <TextInput
            placeholder="Search SKU / name…"
            className="min-w-[16rem]"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <SelectInput value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>
          <option value="posted">Posted</option>
          <option value="pending">Pending</option>
          <option value="refunded">Refunded</option>
          </SelectInput>
        </div>
      </Panel>
      {err ? <ErrorState detail={err} /> : null}
      <Panel
        title="Transactions"
        subtitle="Newest first. Includes tax-inclusive totals and line snapshots."
      >
        <div className="overflow-x-auto">
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
            {loading ? <LoadingRow colSpan={4} /> : null}
            {rows.map((t) => (
              <tr key={t.id}>
                <td className="px-4 py-3 font-mono text-xs text-primary/80">{t.created_at}</td>
                <td className="px-4 py-3">
                  <Badge tone={t.status === "posted" ? "good" : t.status === "refunded" ? "warn" : "default"}>
                    {t.status}
                  </Badge>
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
        </div>
        {rows.length === 0 && !loading ? <EmptyState title="No matching transactions" detail="Try clearing status/search filters." /> : null}
      </Panel>
      {nextCursor ? (
        <SecondaryButton
          type="button"
          disabled={loading}
          onClick={() => void fetchPage(nextCursor, true)}
        >
          {loading ? "Loading…" : "Load more"}
        </SecondaryButton>
      ) : null}
    </div>
  );
}
