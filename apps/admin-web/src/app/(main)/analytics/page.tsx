"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  PageHeader,
  Panel,
  ProgressBar,
  SegmentedControl,
} from "@/components/ui/primitives";
import { InteractiveAreaChart, HourlyHeatmap } from "@/components/ui/charts";
import { formatMoney } from "@/lib/format";
import { useCurrency } from "@/lib/currency-context";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type SalesPoint = { day: string; gross_cents: number; transaction_count: number };
type SalesSeries = { points: SalesPoint[] };

type DashboardSummary = {
  posted_transaction_count: number;
  gross_sales_cents: number;
  stock_alert_count: number;
  product_count: number;
  shop_count: number;
  revenue_delta_pct: number;
};

type CategoryItem = {
  category: string;
  gross_cents: number;
  transaction_count: number;
  pct: number;
};

type TopProductItem = {
  product_id: string;
  product_name: string;
  sku: string;
  category: string | null;
  qty_sold: number;
  gross_cents: number;
};

type HourBucket = {
  hour: number;
  avg_gross_cents: number;
  avg_tx_count: number;
};

type PaymentMethodItem = {
  tender_type: string;
  gross_cents: number;
  transaction_count: number;
  pct: number;
};

type ShopRevenueItem = {
  shop_id: string;
  shop_name: string;
  gross_cents: number;
  transaction_count: number;
  pct: number;
  stock_alert_count: number;
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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
      out.push(points.slice(i, i + 7).reduce((a, p) => a + p.gross_cents, 0));
    }
    return out.length ? out : [0];
  }
  const out: number[] = [];
  let bucket = 0;
  let count = 0;
  for (const p of points) {
    bucket += p.gross_cents;
    if (++count >= 30) { out.push(bucket); bucket = 0; count = 0; }
  }
  if (bucket > 0) out.push(bucket);
  return out.length ? out : [0];
}

function tenderLabel(t: string): string {
  const map: Record<string, string> = { cash: "Cash", card: "Card", gift_card: "Gift card", other: "Other" };
  return map[t.toLowerCase()] ?? t;
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AnalyticsPage() {
  const currency = useCurrency();
  const [periodIdx, setPeriodIdx] = useState(1);
  const [granularity, setGranularity] = useState<"daily" | "weekly" | "monthly">("daily");
  const [series, setSeries] = useState<SalesPoint[]>([]);
  const [dash, setDash] = useState<DashboardSummary | null>(null);
  const [categories, setCategories] = useState<CategoryItem[]>([]);
  const [topProducts, setTopProducts] = useState<TopProductItem[]>([]);
  const [hourly, setHourly] = useState<HourBucket[]>([]);
  const [payments, setPayments] = useState<PaymentMethodItem[]>([]);
  const [shopRevenue, setShopRevenue] = useState<ShopRevenueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const days = PERIODS[periodIdx].days;

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const [sRes, dRes, catRes, topRes, hourRes, payRes, shopRes] = await Promise.all([
        fetch(`/api/ims/v1/admin/analytics/sales-series?days=${days}`),
        fetch("/api/ims/v1/admin/dashboard-summary"),
        fetch(`/api/ims/v1/admin/analytics/category-revenue?days=${days}`),
        fetch(`/api/ims/v1/admin/analytics/top-products?days=${days}&limit=8`),
        fetch(`/api/ims/v1/admin/analytics/hourly-heatmap?days=${Math.min(days, 14)}`),
        fetch(`/api/ims/v1/admin/analytics/payment-methods?days=${days}`),
        fetch(`/api/ims/v1/admin/analytics/shop-revenue?days=${days}`),
      ]);

      if (!sRes.ok) throw new Error(`Series ${sRes.status}`);
      if (!dRes.ok) throw new Error(`Dashboard ${dRes.status}`);

      const sJson = (await sRes.json()) as SalesSeries;
      const dJson = (await dRes.json()) as DashboardSummary;
      setSeries(sJson.points);
      setDash(dJson);

      if (catRes.ok) setCategories(((await catRes.json()) as { items: CategoryItem[] }).items);
      if (topRes.ok) setTopProducts(((await topRes.json()) as { items: TopProductItem[] }).items);
      if (hourRes.ok) setHourly(((await hourRes.json()) as { buckets: HourBucket[] }).buckets);
      if (payRes.ok) setPayments(((await payRes.json()) as { items: PaymentMethodItem[] }).items);
      if (shopRes.ok) setShopRevenue(((await shopRes.json()) as { items: ShopRevenueItem[] }).items);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Load failed");
      setSeries([]);
      setDash(null);
    } finally {
      setLoading(false);
    }
  }, [days]);

  useEffect(() => { void load(); }, [load]);

  const chartValues = useMemo(() => aggregateSeries(series, granularity), [series, granularity]);
  const tableRows = useMemo(() => [...series].sort((a, b) => b.day.localeCompare(a.day)).slice(0, 14), [series]);

  const totalRevenue = series.reduce((a, p) => a + p.gross_cents, 0);
  const totalTx = series.reduce((a, p) => a + p.transaction_count, 0);
  const avgTicket = totalTx > 0 ? Math.round(totalRevenue / totalTx) : 0;
  const revDelta = dash?.revenue_delta_pct ?? 0;


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

  return (
    <div className="space-y-8">
      {/* ------------------------------------------------------------------ Header */}
      <PageHeader
        kicker="Analytics"
        title="Revenue intelligence"
        subtitle="Sales data from posted transactions — filter by period to compare."
        action={
          <div className="flex flex-wrap items-center gap-3">
            <div className="inline-flex rounded-lg bg-surface-container p-1">
              {PERIODS.map((p, i) => (
                <button
                  key={p.days}
                  type="button"
                  onClick={() => setPeriodIdx(i)}
                  className={`rounded-md px-3 py-1.5 text-xs font-bold uppercase tracking-wider ${
                    periodIdx === i
                      ? "bg-surface-container-lowest text-on-surface shadow-sm"
                      : "text-on-surface-variant"
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
        <div className="rounded-xl border border-error/20 bg-error-container/30 px-4 py-3 text-sm text-on-error-container">
          {err}
        </div>
      ) : null}

      {/* ------------------------------------------------------------------ Inventory health callout */}
      {dash && dash.stock_alert_count > 0 ? (
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-low p-6 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Inventory health</p>
              <p className="mt-2 font-headline text-lg font-bold text-on-surface">
                {dash.stock_alert_count} SKU{dash.stock_alert_count !== 1 ? "s" : ""} need attention
              </p>
              <p className="mt-1 text-sm text-on-surface-variant">
                Reconcile on-hand quantities before the next buying cycle.
              </p>
            </div>
            <span className="material-symbols-outlined text-3xl text-primary">inventory_2</span>
          </div>
          {/* Multi-shop: only show links for shops that actually have alerts */}
          {(() => {
            const alertShops = shopRevenue.filter((s) => s.stock_alert_count > 0);
            return alertShops.length > 1 ? (
              <div className="mt-4 flex flex-wrap gap-2">
                {alertShops.map((s) => (
                  <Link
                    key={s.shop_id}
                    href={`/inventory?highlight=critical&shopId=${s.shop_id}`}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-outline-variant/20 bg-surface px-3 py-2 text-xs font-semibold text-on-surface transition hover:bg-surface-container"
                  >
                    <span className="material-symbols-outlined text-sm text-on-surface-variant">storefront</span>
                    {s.shop_name}
                  </Link>
                ))}
              </div>
            ) : alertShops.length === 1 ? (
              <Link
                href={`/inventory?highlight=critical&shopId=${alertShops[0].shop_id}`}
                className="mt-4 inline-flex items-center gap-1.5 rounded-lg border border-outline-variant/20 bg-surface px-3 py-2 text-xs font-semibold text-on-surface transition hover:bg-surface-container"
              >
                <span className="material-symbols-outlined text-sm text-on-surface-variant">open_in_new</span>
                View inventory
              </Link>
            ) : (
              <Link
                href="/inventory?highlight=critical"
                className="mt-4 inline-flex items-center gap-1.5 rounded-lg border border-outline-variant/20 bg-surface px-3 py-2 text-xs font-semibold text-on-surface transition hover:bg-surface-container"
              >
                <span className="material-symbols-outlined text-sm text-on-surface-variant">open_in_new</span>
                View inventory
              </Link>
            );
          })()}
        </div>
      ) : null}

      {/* ------------------------------------------------------------------ KPI cards */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "Total revenue", value: formatMoney(totalRevenue, currency), icon: "payments" },
          { label: "Avg transaction", value: formatMoney(avgTicket, currency), icon: "receipt_long" },
          { label: "Transactions", value: String(totalTx), icon: "point_of_sale" },
          {
            label: "vs prev period",
            value: `${revDelta >= 0 ? "+" : ""}${revDelta.toFixed(1)}%`,
            icon: revDelta >= 0 ? "trending_up" : "trending_down",
            highlight: revDelta !== 0,
          },
        ].map((k) => (
          <div
            key={k.label}
            className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm"
          >
            <div className="flex items-center justify-between">
              <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">{k.label}</p>
              <span className={`material-symbols-outlined text-xl ${k.highlight ? (revDelta >= 0 ? "text-primary" : "text-error") : "text-on-surface-variant/40"}`}>
                {k.icon}
              </span>
            </div>
            <p className="mt-4 font-headline text-3xl font-extrabold text-primary">{loading ? "…" : k.value}</p>
          </div>
        ))}
      </div>

      {/* ------------------------------------------------------------------ Revenue chart + Categories */}
      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 lg:col-span-8">
          <Panel
            title="Gross revenue"
            subtitle={`Last ${days} days`}
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
            <InteractiveAreaChart
              values={chartValues.map((v) => v / 100)}
              labels={granularity === "daily" ? series.map((p) => p.day) : undefined}
              formatValue={(v) => formatMoney(Math.round(v * 100), currency)}
            />
          </Panel>
        </div>
        <div className="col-span-12 space-y-6 rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm lg:col-span-4">
          <div>
            <h3 className="font-headline text-lg font-bold text-on-surface">Revenue by category</h3>
            <p className="mt-0.5 text-sm text-on-surface-variant">Share of gross revenue · last {days} days</p>
          </div>
          <div className="space-y-4">
            {loading ? (
              <p className="text-sm text-on-surface-variant">Loading…</p>
            ) : categories.length === 0 ? (
              <p className="text-sm text-on-surface-variant">No sales data yet.</p>
            ) : (
              categories.map((c) => (
                <ProgressBar
                  key={c.category}
                  label={`${c.category} · ${formatMoney(c.gross_cents, currency)}`}
                  value={c.pct}
                  max={100}
                />
              ))
            )}
          </div>
        </div>
      </div>

      {/* ------------------------------------------------------------------ Payment methods + Peak hours */}
      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 space-y-6 rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm lg:col-span-5">
          <div>
            <h3 className="font-headline text-lg font-bold text-on-surface">Payment methods</h3>
            <p className="mt-0.5 text-sm text-on-surface-variant">How customers pay — last {days} days</p>
          </div>
          <div className="space-y-4">
            {loading ? (
              <p className="text-sm text-on-surface-variant">Loading…</p>
            ) : payments.length === 0 ? (
              <p className="text-sm text-on-surface-variant">No payment data yet.</p>
            ) : (
              payments.map((p) => (
                <div key={p.tender_type}>
                  <ProgressBar
                    label={`${tenderLabel(p.tender_type)} · ${formatMoney(p.gross_cents, currency)}`}
                    value={p.pct}
                    max={100}
                  />
                  <p className="mt-0.5 pl-0 text-xs text-on-surface-variant">
                    {p.transaction_count} transaction{p.transaction_count !== 1 ? "s" : ""}
                  </p>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="col-span-12 space-y-4 rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm lg:col-span-7">
          <div>
            <h3 className="font-headline text-lg font-bold text-on-surface">Peak trading hours</h3>
            <p className="mt-0.5 text-sm text-on-surface-variant">
              Avg revenue per hour of day · last {Math.min(days, 14)} days
            </p>
          </div>
          {loading ? (
            <p className="text-sm text-on-surface-variant">Loading…</p>
          ) : (
            <HourlyHeatmap buckets={hourly} formatValue={(c) => formatMoney(c, currency)} />
          )}
        </div>
      </div>

      {/* ------------------------------------------------------------------ Top products */}
      <Panel title="Top products" subtitle={`By revenue · last ${days} days`} noPad>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-outline-variant/10">
                <th className="px-4 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">#</th>
                <th className="px-4 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Product</th>
                <th className="px-4 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Category</th>
                <th className="px-4 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Units sold</th>
                <th className="px-4 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Revenue</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {loading ? (
                <tr>
                  <td colSpan={5} className="px-4 py-4 text-center text-sm text-on-surface-variant">Loading…</td>
                </tr>
              ) : topProducts.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-sm text-on-surface-variant">
                    No sales recorded in this period.
                  </td>
                </tr>
              ) : (
                topProducts.map((p, i) => (
                  <tr key={p.product_id} className="hover:bg-surface-container-low/50">
                    <td className="px-4 py-3 text-xs font-bold text-on-surface-variant">{i + 1}</td>
                    <td className="px-4 py-3">
                      <p className="font-semibold text-on-surface">{p.product_name}</p>
                      <p className="font-mono text-xs text-on-surface-variant">{p.sku}</p>
                    </td>
                    <td className="px-4 py-3 text-sm text-on-surface-variant">{p.category ?? "—"}</td>
                    <td className="px-4 py-3 text-right tabular-nums text-on-surface">{p.qty_sold}</td>
                    <td className="px-4 py-3 text-right tabular-nums font-semibold text-on-surface">
                      {formatMoney(p.gross_cents, currency)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      {/* ------------------------------------------------------------------ Per-shop revenue (multi-shop only) */}
      {shopRevenue.length > 1 ? (
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm space-y-4">
          <div>
            <h3 className="font-headline text-lg font-bold text-on-surface">Revenue by location</h3>
            <p className="mt-0.5 text-sm text-on-surface-variant">Per-store contribution · last {days} days</p>
          </div>
          <div className="space-y-4">
            {shopRevenue.map((s) => (
              <ProgressBar
                key={s.shop_id}
                label={`${s.shop_name} · ${formatMoney(s.gross_cents, currency)} · ${s.transaction_count} tx`}
                value={s.pct}
                max={100}
              />
            ))}
          </div>
        </div>
      ) : null}

      {/* ------------------------------------------------------------------ Daily breakdown table */}
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
                  <td className="px-4 py-2 text-right tabular-nums font-semibold text-on-surface">
                    {formatMoney(row.gross_cents, currency)}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums text-on-surface-variant">
                    {row.transaction_count}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums text-on-surface">
                    {row.transaction_count > 0
                      ? formatMoney(Math.round(row.gross_cents / row.transaction_count), currency)
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

    </div>
  );
}
