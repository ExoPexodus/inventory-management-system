import { serverJsonGet } from "@/lib/api/server-json";
import { formatMoneyUSD } from "@/lib/format";

type DashboardSummary = {
  posted_transaction_count: number;
  gross_sales_cents: number;
  stock_alert_count: number;
  supplier_count: number;
  shop_count: number;
  product_count: number;
  tenant_count: number;
  recent_activity: Array<{ kind: string; ref_id: string; created_at: string; detail: string }>;
};

export default async function OverviewPage() {
  const res = await serverJsonGet<DashboardSummary>("/v1/admin/dashboard-summary");
  if (!res.ok) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50/80 p-4 text-sm text-red-900">
        Could not load dashboard ({res.status}). Try signing in again.
      </div>
    );
  }
  const d = res.data;
  const tiles = [
    { label: "Posted sales", value: formatMoneyUSD(d.gross_sales_cents) },
    { label: "Transactions", value: String(d.posted_transaction_count) },
    { label: "Stock alerts (≤5)", value: String(d.stock_alert_count) },
    { label: "Suppliers", value: String(d.supplier_count) },
    { label: "Shops", value: String(d.shop_count) },
    { label: "Products", value: String(d.product_count) },
  ];
  return (
    <div className="space-y-8">
      <header>
        <p className="text-xs font-semibold uppercase tracking-wider text-primary/50">Executive overview</p>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-primary">Operations pulse</h1>
        <p className="mt-1 text-sm text-primary/70">
          Tenant scope: <span className="font-medium">{d.tenant_count}</span> tenant
          {d.tenant_count === 1 ? "" : "s"}
        </p>
      </header>
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {tiles.map((t) => (
          <div
            key={t.label}
            className="rounded-xl border border-primary/10 bg-white/90 p-5 shadow-sm"
          >
            <p className="text-xs font-medium uppercase tracking-wide text-primary/50">{t.label}</p>
            <p className="mt-2 font-display text-2xl font-semibold tabular-nums text-primary">{t.value}</p>
          </div>
        ))}
      </section>
      <section className="rounded-xl border border-primary/10 bg-white/90 shadow-sm">
        <div className="border-b border-primary/10 px-5 py-3">
          <h2 className="font-display text-sm font-semibold text-primary">Recent activity</h2>
        </div>
        <ul className="divide-y divide-primary/5">
          {d.recent_activity.length === 0 ? (
            <li className="px-5 py-8 text-center text-sm text-primary/60">No events yet.</li>
          ) : (
            d.recent_activity.map((a) => (
              <li key={`${a.kind}:${a.ref_id}`} className="flex flex-wrap items-baseline gap-x-3 px-5 py-3 text-sm">
                <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary/80">
                  {a.kind}
                </span>
                <time className="text-primary/60">{a.created_at}</time>
                <span className="min-w-0 flex-1 font-mono text-xs text-primary/80">{a.detail}</span>
              </li>
            ))
          )}
        </ul>
      </section>
    </div>
  );
}
