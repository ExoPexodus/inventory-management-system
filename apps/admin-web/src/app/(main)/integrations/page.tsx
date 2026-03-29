import { headers } from "next/headers";
import { Badge } from "@/components/ui/primitives";

type IntegrationStatus = "active" | "available" | "coming_soon";

const INTEGRATIONS: Array<{
  id: string;
  icon: string;
  title: string;
  description: string;
  status: IntegrationStatus;
}> = [
  {
    id: "webhooks",
    icon: "webhook",
    title: "Webhooks",
    description: "Push signed events to your endpoints for near-real-time automation.",
    status: "active",
  },
  {
    id: "rest",
    icon: "api",
    title: "REST API",
    description: "Full CRUD over catalog, inventory, orders, and staff with OAuth-style tokens.",
    status: "active",
  },
  {
    id: "csv",
    icon: "table",
    title: "CSV import / export",
    description: "Bulk SKU, price, and on-hand updates with validation and dry-run.",
    status: "available",
  },
  {
    id: "pos",
    icon: "point_of_sale",
    title: "POS bridge",
    description: "Connect lane hardware and sync tenders, receipts, and voids.",
    status: "available",
  },
  {
    id: "accounting",
    icon: "account_balance",
    title: "Accounting",
    description: "Post journals to QuickBooks, Xero, or a neutral GL export.",
    status: "coming_soon",
  },
  {
    id: "barcode",
    icon: "barcode_scanner",
    title: "Barcode & labels",
    description: "Generate shelf labels and receive with handheld scanners.",
    status: "coming_soon",
  },
];

function statusTone(s: IntegrationStatus): "good" | "default" | "warn" {
  if (s === "active") return "good";
  if (s === "coming_soon") return "warn";
  return "default";
}

function statusLabel(s: IntegrationStatus): string {
  if (s === "active") return "Active";
  if (s === "coming_soon") return "Coming soon";
  return "Available";
}

export default async function IntegrationsPage() {
  const h = await headers();
  const host = h.get("x-forwarded-host") ?? h.get("host") ?? "localhost:3000";
  const proto = h.get("x-forwarded-proto") ?? (host.startsWith("localhost") ? "http" : "https");
  const baseUrl = `${proto}://${host}`;
  const apiBase = `${baseUrl}/api/ims/v1`;

  return (
    <div className="space-y-8">
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Platform</p>
        <h2 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">Integrations</h2>
        <p className="mt-2 font-light text-on-surface-variant">Connect external systems and automate data flow.</p>
      </div>

      <section className="overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm">
        <div className="ink-gradient px-6 py-4">
          <h3 className="font-headline text-lg font-bold text-on-primary">API credentials</h3>
          <p className="mt-1 text-sm text-on-primary/90">Use this base URL for server-to-server calls from your tenant backends.</p>
        </div>
        <div className="border-t border-outline-variant/10 px-6 py-5">
          <p className="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Base URL</p>
          <code className="mt-2 block break-all rounded-lg bg-surface-container-low px-4 py-3 font-mono text-sm text-primary">{apiBase}</code>
        </div>
      </section>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
        {INTEGRATIONS.map((item) => (
          <div
            key={item.id}
            className="flex flex-col rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm"
          >
            <div className="flex items-start justify-between gap-3">
              <span className="material-symbols-outlined rounded-lg bg-surface-container-low p-2 text-2xl text-primary">
                {item.icon}
              </span>
              <Badge tone={statusTone(item.status)}>{statusLabel(item.status)}</Badge>
            </div>
            <h3 className="mt-4 font-headline text-lg font-bold text-on-surface">{item.title}</h3>
            <p className="mt-2 flex-1 text-sm text-on-surface-variant">{item.description}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
