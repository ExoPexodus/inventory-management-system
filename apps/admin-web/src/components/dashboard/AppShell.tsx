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
    <div className="flex min-h-screen">
      <aside className="flex w-60 flex-col border-r border-primary/10 bg-white/80 py-6 pr-4">
        <div className="px-4 pb-4 font-display text-lg font-semibold text-primary">IMS Admin</div>
        <nav className="flex flex-1 flex-col gap-1 px-2">
          {NAV.map((item) => {
            const active = current === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  active ? "bg-primary/10 text-primary" : "text-primary/75 hover:bg-primary/5"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-4 px-2">
          <LogoutButton />
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <main className="flex-1 overflow-auto p-8">{children}</main>
      </div>
    </div>
  );
}
