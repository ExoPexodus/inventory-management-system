import Link from "next/link";
import { serverJsonGet } from "@/lib/api/server-json";
import { formatMoneyUSD } from "@/lib/format";

type DashboardSummary = {
  posted_transaction_count: number;
  gross_sales_cents: number;
  stock_alert_count: number;
  supplier_count: number;
  shop_count: number;
  product_count: number;
  pending_order_count?: number;
  avg_transaction_cents?: number;
  revenue_delta_pct?: number;
  recent_activity: Array<{ kind: string; ref_id: string; created_at: string; detail: string }>;
};

export default async function OverviewPage() {
  const res = await serverJsonGet<DashboardSummary>("/v1/admin/dashboard-summary");

  if (!res.ok) {
    return (
      <div className="rounded-xl border border-error/20 bg-error-container/30 p-4 text-sm text-on-error-container">
        Could not load dashboard ({res.status}). Try signing in again.
      </div>
    );
  }

  const d = res.data;
  const revDelta = d.revenue_delta_pct ?? 0;

  return (
    <div className="space-y-8">
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Executive overview</p>
        <h2 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">Operations Pulse</h2>
        <p className="mt-2 text-on-surface-variant">Live summary for your organization.</p>
      </div>

      {/* Bento stat cards */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
        <div className="flex flex-col justify-between rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <div className="flex items-start justify-between">
            <span className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Monthly Revenue</span>
            <span className="rounded-full bg-primary/10 px-2 py-1 text-xs font-bold text-primary">
              {revDelta >= 0 ? "+" : ""}{revDelta.toFixed(1)}%
            </span>
          </div>
          <div className="mt-4">
            <h3 className="font-headline text-4xl font-extrabold tracking-tighter text-primary">
              {formatMoneyUSD(d.gross_sales_cents)}
            </h3>
            <p className="mt-1 text-xs text-on-surface-variant/60">
              From {d.posted_transaction_count.toLocaleString()} transactions
            </p>
          </div>
        </div>
        <div className="flex flex-col justify-between rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <span className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Avg. Transaction</span>
          <div className="mt-4">
            <h3 className="font-headline text-4xl font-extrabold tracking-tighter text-primary">
              {formatMoneyUSD(d.avg_transaction_cents ?? 0)}
            </h3>
            <p className="mt-1 text-xs text-on-surface-variant/60">Per posted transaction</p>
          </div>
        </div>
        <div className="flex flex-col justify-between rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <div className="flex items-start justify-between">
            <span className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Pending Orders</span>
            <div className="h-2 w-2 animate-pulse rounded-full bg-secondary" />
          </div>
          <div className="mt-4">
            <h3 className="font-headline text-4xl font-extrabold tracking-tighter text-primary">
              {d.pending_order_count ?? 0}
            </h3>
            <p className="mt-1 text-xs text-on-surface-variant/60">Awaiting processing</p>
          </div>
        </div>
      </div>

      {/* Revenue Trends Chart */}
      <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-8 shadow-sm">
        <div className="mb-10 flex items-center justify-between">
          <div>
            <h3 className="font-headline text-xl font-bold text-primary">Revenue Trends</h3>
            <p className="text-sm text-on-surface-variant">A visualization of fiscal movement</p>
          </div>
        </div>
        <div className="relative h-64 w-full">
          <div className="absolute inset-0 flex items-end justify-between px-2 opacity-10">
            {Array.from({ length: 7 }).map((_, i) => (
              <div key={i} className="h-full w-px bg-outline" />
            ))}
          </div>
          <svg className="relative z-10 h-full w-full overflow-visible" viewBox="0 0 1000 200" preserveAspectRatio="none">
            <defs>
              <linearGradient id="lineGradient" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor="#06274d" stopOpacity="0.8" />
                <stop offset="100%" stopColor="#06274d" stopOpacity="0" />
              </linearGradient>
            </defs>
            <path d="M0,150 Q100,140 200,120 T400,100 T600,60 T800,80 T1000,40 V200 H0 Z" fill="url(#lineGradient)" />
            <path d="M0,150 Q100,140 200,120 T400,100 T600,60 T800,80 T1000,40" fill="none" stroke="#06274d" strokeLinecap="round" strokeWidth="3" />
            <circle cx="600" cy="60" r="6" fill="#06274d" />
            <circle cx="600" cy="60" r="10" fill="#06274d" fillOpacity="0.2" />
          </svg>
          <div className="mt-4 flex justify-between text-[10px] font-bold uppercase tracking-tighter text-on-surface-variant">
            <span>Mon</span><span>Tue</span><span>Wed</span><span>Thu</span><span>Fri</span><span>Sat</span><span>Sun</span>
          </div>
        </div>
      </div>

      {/* Two column: summary stats + recent activity */}
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-5">
        <div className="space-y-6 lg:col-span-2">
          <h3 className="flex items-center gap-2 font-headline text-lg font-bold text-primary">
            <span className="material-symbols-outlined text-xl">bar_chart</span>
            Archive Totals
          </h3>
          <div className="space-y-4">
            {[
              { label: "Products", value: d.product_count, icon: "category" },
              { label: "Suppliers", value: d.supplier_count, icon: "local_shipping" },
              { label: "Shops", value: d.shop_count, icon: "storefront" },
              { label: "Stock alerts", value: d.stock_alert_count, icon: "warning", warn: true },
            ].map((item) => (
              <div
                key={item.label}
                className={`flex items-center justify-between rounded-xl p-4 ${item.warn ? "bg-error-container/30" : "bg-surface-container-low"}`}
              >
                <div className="flex items-center gap-3">
                  <span className={`material-symbols-outlined text-xl ${item.warn ? "text-error" : "text-on-surface-variant"}`}>
                    {item.icon}
                  </span>
                  <span className="text-sm font-medium text-on-surface">{item.label}</span>
                </div>
                <span className={`font-headline text-2xl font-bold ${item.warn ? "text-error" : "text-primary"}`}>
                  {item.value}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-6 lg:col-span-3">
          <div className="flex items-center justify-between">
            <h3 className="flex items-center gap-2 font-headline text-lg font-bold text-primary">
              <span className="material-symbols-outlined text-xl">history</span>
              Recent Activity
            </h3>
            <Link href="/orders" className="rounded-full bg-secondary/10 px-3 py-1 text-xs font-bold text-on-secondary-container transition-colors hover:bg-secondary/20">
              View all orders
            </Link>
          </div>
          <div className="overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest">
            <table className="w-full text-left text-sm">
              <thead className="bg-surface-container-low text-[10px] uppercase tracking-widest text-on-surface-variant/60">
                <tr>
                  <th className="px-6 py-4 font-bold">Activity</th>
                  <th className="px-6 py-4 font-bold">Reference</th>
                  <th className="px-6 py-4 font-bold">Time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/10">
                {d.recent_activity.slice(0, 6).map((a, i) => (
                  <tr key={`${a.ref_id}-${i}`} className="transition-colors hover:bg-surface-container-low/50">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-surface-container-low">
                          <span className="material-symbols-outlined text-sm text-on-surface-variant">
                            {a.kind === "sale" ? "point_of_sale" : a.kind === "adjustment" ? "tune" : "inventory_2"}
                          </span>
                        </div>
                        <div>
                          <p className="font-bold capitalize text-on-surface">{a.kind}</p>
                          <p className="text-[10px] text-on-surface-variant">{a.detail}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span className="font-mono text-xs font-bold text-primary">#{a.ref_id.slice(0, 8)}</span>
                    </td>
                    <td className="px-6 py-4 text-xs text-on-surface-variant">
                      {new Date(a.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                    </td>
                  </tr>
                ))}
                {d.recent_activity.length === 0 && (
                  <tr>
                    <td colSpan={3} className="px-6 py-10 text-center text-sm text-on-surface-variant">
                      No recent activity. Seed demo data to populate.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
