"use client";

import Link from "next/link";
import { ReactNode } from "react";
import { usePathname } from "next/navigation";
import { LogoutButton } from "@/components/dashboard/LogoutButton";

const NAV = [
  { href: "/overview", label: "Dashboard", icon: "dashboard" },
  { href: "/inventory", label: "Inventory", icon: "inventory_2" },
  { href: "/staff", label: "Staff", icon: "badge" },
  { href: "/orders", label: "Orders", icon: "receipt_long" },
  { href: "/analytics", label: "Analytics", icon: "analytics" },
  { href: "/suppliers", label: "Suppliers", icon: "local_shipping" },
  { href: "/products", label: "Products", icon: "category" },
  { href: "/purchase-orders", label: "Purchase Orders", icon: "shopping_bag" },
  { href: "/shifts", label: "Shifts", icon: "event_note" },
  { href: "/reconciliation", label: "Reconciliation", icon: "account_balance" },
  { href: "/audit", label: "Audit Log", icon: "policy" },
  { href: "/reports", label: "Reports", icon: "description" },
  { href: "/integrations", label: "Integrations", icon: "hub" },
  { href: "/settings", label: "Settings", icon: "settings" },
] as const;

export function AppShell({ children, current }: { children: ReactNode; current?: string }) {
  const pathname = usePathname();
  const activePath = current ?? pathname;

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="flex h-full w-60 shrink-0 flex-col border-r border-outline-variant/15 bg-surface-container font-headline tracking-tight">
        <div className="px-6 pb-6 pt-6">
          <h1 className="text-base font-bold leading-tight text-on-surface">The Tactile Archive</h1>
          <p className="mt-0.5 text-[9px] uppercase tracking-widest text-on-surface-variant opacity-60">Management Suite</p>
        </div>
        <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 pb-2">
          {NAV.map((item) => {
            const active = activePath === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 rounded-lg px-4 py-2.5 text-[13px] transition-colors duration-150 ${
                  active
                    ? "bg-primary/10 font-bold text-primary"
                    : "font-medium text-on-surface-variant hover:bg-surface-container-lowest/60 hover:text-on-surface"
                }`}
              >
                <span className={`material-symbols-outlined text-[20px] leading-none ${active ? "" : "opacity-70"}`} aria-hidden="true">
                  {item.icon}
                </span>
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="shrink-0 space-y-3 px-3 pb-4 pt-2">
          <Link
            href="/entries"
            className="ink-gradient flex w-full items-center justify-center gap-2 rounded-lg py-3 text-[13px] font-bold text-on-primary shadow-md transition-all hover:opacity-90 active:scale-[0.98]"
          >
            <span className="material-symbols-outlined text-lg leading-none" aria-hidden="true">add_circle</span>
            New Entry
          </Link>
          <div className="flex items-center gap-3 rounded-lg px-3 py-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-[10px] font-bold text-on-primary">
              A
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-bold text-on-surface">Admin</p>
              <p className="truncate text-[9px] uppercase tracking-wider text-on-surface-variant">Operator</p>
            </div>
          </div>
          <LogoutButton />
        </div>
      </aside>

      {/* Main content */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Top bar */}
        <header className="sticky top-0 z-40 flex h-20 items-center justify-between border-b border-outline-variant/20 bg-background/80 px-8 backdrop-blur-md">
          <div className="flex flex-1 items-center">
            <div className="relative w-full max-w-sm">
              <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-lg text-on-surface-variant" aria-hidden="true">search</span>
              <input
                className="w-full rounded-full border-none bg-surface-container-low py-2 pl-10 pr-4 text-sm text-on-surface outline-none placeholder:text-on-surface-variant focus:ring-1 focus:ring-primary"
                placeholder="Search archive..."
                type="text"
              />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button type="button" className="text-on-surface-variant transition-colors hover:text-primary" aria-label="Notifications">
              <span className="material-symbols-outlined text-[22px]" aria-hidden="true">notifications</span>
            </button>
            <button type="button" className="text-on-surface-variant transition-colors hover:text-primary" aria-label="Settings">
              <span className="material-symbols-outlined text-[22px]" aria-hidden="true">settings</span>
            </button>
            <button type="button" className="text-on-surface-variant transition-colors hover:text-primary" aria-label="Help">
              <span className="material-symbols-outlined text-[22px]" aria-hidden="true">help_outline</span>
            </button>
            <div className="mx-2 h-8 w-px bg-outline-variant/30" />
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-primary-container text-xs font-bold text-on-primary">
              A
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto p-8">{children}</main>
      </div>
    </div>
  );
}
