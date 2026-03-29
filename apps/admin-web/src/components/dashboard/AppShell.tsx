import Link from "next/link";
import { ReactNode } from "react";
import { LogoutButton } from "@/components/dashboard/LogoutButton";

const NAV = [
  { href: "/overview", label: "Executive Overview" },
  { href: "/orders", label: "Order Audit" },
  { href: "/suppliers", label: "Supplier Hub" },
  { href: "/analytics", label: "Analytics" },
  { href: "/entries", label: "New Entry" },
  { href: "/inventory", label: "Inventory Ledger" },
  { href: "/staff", label: "Staff & Permissions" },
] as const;

export function AppShell({ children, current }: { children: ReactNode; current: string }) {
  return (
    <div className="grid min-h-screen grid-cols-[272px_1fr] bg-[radial-gradient(circle_at_top_right,rgba(44,62,80,0.06),transparent_45%)]">
      <aside className="flex flex-col border-r border-primary/10 bg-white/90 px-4 py-6">
        <div className="pb-5">
          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-primary/45">Transaction History</p>
          <div className="mt-1 font-display text-xl font-semibold text-primary">IMS Admin Console</div>
        </div>
        <nav className="flex flex-1 flex-col gap-1 px-2">
          {NAV.map((item) => {
            const active = current === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-xl px-3 py-2.5 text-sm font-medium transition-colors ${
                  active ? "border border-primary/20 bg-primary/10 text-primary shadow-sm" : "text-primary/75 hover:bg-primary/5"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-4 rounded-xl border border-primary/10 bg-primary/[0.02] p-3">
          <p className="text-xs font-medium text-primary/60">Operator</p>
          <p className="text-sm font-semibold text-primary">Signed session</p>
        </div>
        <div className="mt-3 px-2">
          <LogoutButton />
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="border-b border-primary/10 bg-white/70 px-8 py-4 backdrop-blur">
          <p className="text-xs uppercase tracking-[0.18em] text-primary/45">Desktop Parity Pass</p>
        </div>
        <main className="flex-1 overflow-auto px-8 py-7">{children}</main>
      </div>
    </div>
  );
}
