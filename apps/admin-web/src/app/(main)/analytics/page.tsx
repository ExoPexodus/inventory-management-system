"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AreaChart,
  PageHeader,
  Panel,
  ProgressBar,
  SegmentedControl,
} from "@/components/ui/primitives";
import { formatMoneyUSD } from "@/lib/format";

type SalesPoint = { day: string; gross_cents: number; transaction_count: number };

type SalesSeries = { points: SalesPoint[] };

type DashboardSummary = {
  posted_transaction_count: number;
  gross_sales_cents: number;
  stock_alert_count: number;
  product_count: number;
  shop_count: number;
};

const PERIODS = [
  { days: 7, label: "7d" },
  { days: 30, label: "30d" },
  { days: 90, label: "90d" },
] as const;

function aggregateSeries(points: SalesPoint[], mode: "daily" | "weekly" | "monthly"): number[] {
  if (mode === "daily") return points.map((p) => p.gross_cents);
  if (mode === "weekly") {
    const out: number[] = [];
    for (let i = 0; i < points.length; i += 7) {
      const slice = points.slice(i, i + 7);
      out.push(slice.reduce((a, p) => a + p.gross_cents, 0));
    }
    return out.length ? out : [0];
  }
  const out: number[] = [];
  let bucket = 0;
  let count = 0;
  for (const p of points) {
    bucket += p.gross_cents;
    count += 1;
    if (count >= 30) {
      out.push(bucket);
      bucket = 0;
      count = 0;
    }
  }
  if (bucket > 0) out.push(bucket);
  return out.length ? out : [0];
}

export default function AnalyticsPage() {
  const [periodIdx, setPeriodIdx] = useState(1);
  const [granularity, setGranularity] = useState<"daily" | "weekly" | "monthly">("daily");
  const [series, setSeries] = useState<SalesPoint[]>([]);
  const [dash, setDash] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const days = PERIODS[periodIdx].days;

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [sRes, dRes] = await Promise.all([
        fetch(`/api/ims/v1/admin/analytics/sales-series?days=${days}`),
        fetch("/api/ims/v1/admin/dashboard-summary"),
      ]);
      if (!sRes.ok) throw new Error(`Series ${sRes.status}`);
      if (!dRes.ok) throw new Error(`Dashboard ${dRes.status}`);
      const sJson = (await sRes.json()) as SalesSeries;
      const dJson = (await dRes.json()) as DashboardSummary;
      setSeries(sJson.points);
      setDash(dJson);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Load failed");
      setSeries([]);
      setDash(null);
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => {
    void load();
  }, [load]);

  const chartValues = useMemo(() => aggregateSeries(series, granularity), [series, granularity]);

  const tableRows = useMemo(() => {
    return [...series].sort((a, b) => b.day.localeCompare(a.day)).slice(0, 14);
  }, [series]);

  const totalRevenue = series.reduce((a, p) => a + p.gross_cents, 0);
  const totalTx = series.reduce((a, p) => a + p.transaction_count, 0);
  const avgTicket = totalTx > 0 ? Math.round(totalRevenue / totalTx) : 0;
  const conversionProxy =
    dash && dash.product_count > 0
      ? `${Math.min(99.9, (dash.posted_transaction_count / Math.max(dash.product_count, 1)) * 12).toFixed(1)}%`
      : "—";

  function exportSnapshot() {
    const lines = [
      "day,gross_cents,transactions",
      ...series.map((p) => `${p.day},${p.gross_cents},${p.transaction_count}`),
    ];
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `analytics-${days}d.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const categorySplit = useMemo(
    () => [
      { label: "Retail floor", value: 42 },
      { label: "Wholesale", value: 28 },
      { label: "Digital / prepay", value: 18 },
      { label: "Other", value: 12 },
    ],
    [],
  );

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="Analytics"
        title="Revenue intelligence"
        subtitle="Sales series from posted transactions — aligned with dashboard KPIs."
        action={
          <div className="flex flex-wrap items-center gap-3">
            <div className="inline-flex rounded-lg bg-surface-container p-1">
              {PERIODS.map((p, i) => (
                <button
                  key={p.days}
                  type="button"
                  onClick={() => setPeriodIdx(i)}
                  className={`rounded-md px-3 py-1.5 text-xs font-bold uppercase tracking-wider ${
                    periodIdx === i ? "bg-surface-container-lowest text-on-surface shadow-sm" : "text-on-surface-variant"
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={exportSnapshot}
              className="ink-gradient inline-flex items-center gap-2 rounded-lg px-6 py-2.5 text-sm font-semibold text-on-primary shadow-sm transition hover:opacity-90"
            >
              <span className="material-symbols-outlined text-lg">ios_share</span>
              Export
            </button>
          </div>
        }
      />

      {err ? (
        <div className="rounded-xl border border-error/20 bg-error-container/30 px-4 py-3 text-sm text-on-error-container">{err}</div>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "Total revenue", value: formatMoneyUSD(totalRevenue) },
          { label: "Avg transaction", value: formatMoneyUSD(avgTicket) },
          { label: "Transactions", value: String(totalTx) },
          { label: "Conversion proxy", value: conversionProxy },
        ].map((k) => (
          <div key={k.label} className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
            <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">{k.label}</p>
            <p className="mt-4 font-headline text-3xl font-extrabold text-primary">{loading ? "…" : k.value}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 lg:col-span-8">
          <Panel
            title="Gross revenue"
            subtitle={`Last ${days} days · normalized for chart`}
            right={
              <SegmentedControl
                value={granularity}
                onChange={(v) => setGranularity(v as "daily" | "weekly" | "monthly")}
                options={[
                  { value: "daily", label: "Daily" },
                  { value: "weekly", label: "Weekly" },
                  { value: "monthly", label: "Monthly" },
                ]}
              />
            }
          >
            <AreaChart values={chartValues.map((v) => v / 100)} />
          </Panel>
        </div>
        <div className="col-span-12 space-y-6 rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm lg:col-span-4">
          <div>
            <h3 className="font-headline text-lg font-bold text-on-surface">Categories</h3>
            <p className="mt-0.5 text-sm text-on-surface-variant">Share of gross (illustrative split)</p>
          </div>
          <div className="space-y-5">
            {categorySplit.map((c) => (
              <ProgressBar key={c.label} label={c.label} value={c.value} max={100} />
            ))}
          </div>
        </div>
      </div>

      <Panel title="Daily breakdown" subtitle="Newest days first">
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-outline-variant/10">
                <th className="px-4 py-2 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Day</th>
                <th className="px-4 py-2 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Gross</th>
                <th className="px-4 py-2 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Tx</th>
                <th className="px-4 py-2 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Avg ticket</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {tableRows.map((row) => (
                <tr key={row.day}>
                  <td className="px-4 py-2 font-mono text-xs text-on-surface">{row.day}</td>
                  <td className="px-4 py-2 text-right tabular-nums font-semibold text-on-surface">{formatMoneyUSD(row.gross_cents)}</td>
                  <td className="px-4 py-2 text-right tabular-nums text-on-surface-variant">{row.transaction_count}</td>
                  <td className="px-4 py-2 text-right tabular-nums text-on-surface">
                    {row.transaction_count > 0 ? formatMoneyUSD(Math.round(row.gross_cents / row.transaction_count)) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <Link
        href="/inventory"
        className="flex items-center justify-between gap-4 rounded-xl border border-outline-variant/10 bg-surface-container-low p-6 shadow-sm transition hover:bg-surface-container"
      >
        <div>
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Inventory health</p>
          <p className="mt-2 font-headline text-lg font-bold text-on-surface">
            {dash ? `${dash.stock_alert_count} SKUs need attention` : "Open the inventory ledger"}
          </p>
          <p className="mt-1 text-sm text-on-surface-variant">Reconcile on-hand before the next buying cycle.</p>
        </div>
        <span className="material-symbols-outlined text-3xl text-primary">inventory_2</span>
      </Link>
    </div>
  );
}
