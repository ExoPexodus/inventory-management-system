import { serverJsonGet } from "@/lib/api/server-json";
import { Badge, ErrorState, PageHeader, Panel, StatTile } from "@/components/ui/primitives";
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
    return <ErrorState detail={`Could not load dashboard (${res.status}). Try signing in again.`} />;
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
    <div className="space-y-7">
      <PageHeader
        kicker="Executive overview"
        title="Operations pulse"
        subtitle={`Tenant scope: ${d.tenant_count} tenant${d.tenant_count === 1 ? "" : "s"}`}
      />
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {tiles.map((t) => (
          <StatTile key={t.label} label={t.label} value={t.value} tone={t.label.includes("alerts") ? "warn" : "default"} />
        ))}
      </section>
      <Panel title="Recent activity" subtitle="Latest transaction and stock movement events">
        <ul className="divide-y divide-primary/5">
          {d.recent_activity.length === 0 ? (
            <li className="px-5 py-8 text-center text-sm text-primary/60">No events yet.</li>
          ) : (
            d.recent_activity.map((a) => (
              <li key={`${a.kind}:${a.ref_id}`} className="flex flex-wrap items-baseline gap-x-3 px-5 py-3 text-sm">
                <Badge>{a.kind}</Badge>
                <time className="text-primary/60">{a.created_at}</time>
                <span className="min-w-0 flex-1 font-mono text-xs text-primary/80">{a.detail}</span>
              </li>
            ))
          )}
        </ul>
      </Panel>
    </div>
  );
}
