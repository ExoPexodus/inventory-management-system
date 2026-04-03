"use client";

import Link from "next/link";
import { ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { LogoutButton } from "@/components/dashboard/LogoutButton";

type NotifItem = {
  id: string;
  type: string;
  title: string;
  body: string | null;
  read_at: string | null;
  created_at: string;
};

function useNotifications(open: boolean) {
  const [items, setItems] = useState<NotifItem[]>([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(false);

  const fetchNotifs = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/ims/v1/admin/notifications");
      if (!r.ok) return;
      const d = (await r.json()) as { items: NotifItem[]; unread_count: number };
      setItems(d.items ?? []);
      setUnread(d.unread_count ?? 0);
    } finally {
      setLoading(false);
    }
  }, []);

  // Poll unread count every 60s
  useEffect(() => {
    void fetchNotifs();
    const t = setInterval(() => void fetchNotifs(), 60_000);
    return () => clearInterval(t);
  }, [fetchNotifs]);

  // Refresh when panel opens
  useEffect(() => {
    if (open) void fetchNotifs();
  }, [open, fetchNotifs]);

  const markAllRead = async () => {
    await fetch("/api/ims/v1/admin/notifications/read-all", { method: "POST" });
    void fetchNotifs();
  };

  const markRead = async (id: string) => {
    await fetch(`/api/ims/v1/admin/notifications/${id}/read`, { method: "PATCH" });
    setItems((prev) => prev.map((n) => (n.id === id ? { ...n, read_at: new Date().toISOString() } : n)));
    setUnread((u) => Math.max(0, u - 1));
  };

  return { items, unread, loading, markAllRead, markRead };
}

const ROOT_ROUTES = new Set([
  "overview",
  "inventory",
  "staff",
  "orders",
  "analytics",
  "suppliers",
  "products",
  "purchase-orders",
  "shifts",
  "reconciliation",
  "audit",
  "reports",
  "integrations",
  "settings",
  "entries",
  "login",
]);

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
  const [notifOpen, setNotifOpen] = useState(false);
  const { items: notifItems, unread, loading: notifLoading, markAllRead, markRead } = useNotifications(notifOpen);
  const panelRef = useRef<HTMLDivElement>(null);
  const pathname = usePathname();
  const activePathRaw = current ?? pathname;
  const segments = activePathRaw.split("/").filter(Boolean);
  const tenantPrefix = segments.length > 0 && !ROOT_ROUTES.has(segments[0]) ? `/${segments[0]}` : "";
  const activePath = tenantPrefix && activePathRaw.startsWith(tenantPrefix)
    ? activePathRaw.slice(tenantPrefix.length) || "/"
    : activePathRaw;

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
                href={`${tenantPrefix}${item.href}`}
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
            href={`${tenantPrefix}/entries`}
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
            <button
              type="button"
              onClick={() => setNotifOpen((p) => !p)}
              className="relative text-on-surface-variant transition-colors hover:text-primary"
              aria-label="Notifications"
            >
              <span className="material-symbols-outlined text-[22px]" aria-hidden="true">notifications</span>
              {unread > 0 && (
                <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-error text-[9px] font-bold text-on-error">
                  {unread > 9 ? "9+" : unread}
                </span>
              )}
            </button>
            <Link
              href={`${tenantPrefix}/settings`}
              className="text-on-surface-variant transition-colors hover:text-primary"
              aria-label="Settings"
            >
              <span className="material-symbols-outlined text-[22px]" aria-hidden="true">settings</span>
            </Link>
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

      {/* Notification slide-over */}
      {notifOpen && (
        <>
          <div className="fixed inset-0 z-40 bg-black/30" onClick={() => setNotifOpen(false)} />
          <div
            ref={panelRef}
            className="fixed right-0 top-0 z-50 flex h-full w-[22rem] flex-col border-l border-outline-variant/20 bg-surface shadow-2xl"
          >
            <div className="flex items-center justify-between border-b border-outline-variant/10 px-5 py-4">
              <div>
                <p className="font-headline text-base font-bold text-on-surface">Notifications</p>
                {unread > 0 && (
                  <p className="text-xs text-on-surface-variant">{unread} unread</p>
                )}
              </div>
              <div className="flex items-center gap-2">
                {unread > 0 && (
                  <button
                    type="button"
                    onClick={() => void markAllRead()}
                    className="text-xs font-semibold text-primary transition-opacity hover:opacity-70"
                  >
                    Mark all read
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setNotifOpen(false)}
                  className="ml-2 text-on-surface-variant transition-colors hover:text-on-surface"
                  aria-label="Close"
                >
                  <span className="material-symbols-outlined text-xl">close</span>
                </button>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto">
              {notifLoading && notifItems.length === 0 ? (
                <p className="px-5 py-8 text-sm text-on-surface-variant">Loading…</p>
              ) : notifItems.length === 0 ? (
                <div className="flex flex-col items-center gap-2 px-5 py-12 text-center">
                  <span className="material-symbols-outlined text-4xl text-on-surface-variant/40">notifications_none</span>
                  <p className="text-sm text-on-surface-variant">You&apos;re all caught up</p>
                </div>
              ) : (
                notifItems.map((n) => (
                  <button
                    key={n.id}
                    type="button"
                    onClick={() => { if (!n.read_at) void markRead(n.id); }}
                    className={`w-full border-b border-outline-variant/10 px-5 py-4 text-left transition-colors hover:bg-surface-container-low/60 ${
                      n.read_at ? "opacity-60" : ""
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <span className={`mt-0.5 flex h-2 w-2 shrink-0 rounded-full ${n.read_at ? "bg-transparent" : "bg-primary"}`} />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-semibold text-on-surface">{n.title}</p>
                        {n.body && <p className="mt-0.5 text-xs text-on-surface-variant">{n.body}</p>}
                        <p className="mt-1 text-[10px] text-on-surface-variant/60">
                          {new Date(n.created_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
                        </p>
                      </div>
                    </div>
                  </button>
                ))
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
