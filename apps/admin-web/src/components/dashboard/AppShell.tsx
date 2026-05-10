"use client";

import Link from "next/link";
import { ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { getSearchConfig } from "@/lib/search-context";
import { LogoutButton } from "@/components/dashboard/LogoutButton";
import { useHasPermission } from "@/lib/auth/user-context";
import { BusinessTypeProvider, useBusinessType, typeAllows } from "@/lib/business-type-context";
import type { BusinessType } from "@/lib/business-type-context";
import { NavGroup } from "@/components/dashboard/NavGroup";
import type { NavItem } from "@/components/dashboard/NavGroup";
import { CommandPalette } from "@/components/dashboard/CommandPalette";

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
  "team",
  "orders",
  "analytics",
  "suppliers",
  "products",
  "categories",
  "purchase-orders",
  "shifts",
  "reconciliation",
  "audit",
  "reports",
  "insights",
  "integrations",
  "settings",
  "billing",
  "apps",
  "entries",
  "shops",
  "login",
  "channels",
  "ecommerce-orders",
  "discounts",
  "ecommerce",
  "inventory-pools",
  "tax",
]);

type NavItemDef = NavItem & {
  permission: string | null;
  allowedTypes: BusinessType[];   // empty = all types
};

const ALL_TYPES: BusinessType[] = ["online", "retail", "hybrid"];

const HOME: NavItemDef = {
  href: "/overview", label: "Dashboard", icon: "dashboard", permission: null, allowedTypes: ALL_TYPES,
};

interface NavGroupDef {
  label: string;
  items: NavItemDef[];
}

const NAV_GROUPS: NavGroupDef[] = [
  {
    label: "Sell",
    items: [
      { href: "/orders",          label: "Orders",         icon: "receipt_long", permission: "sales:read",      allowedTypes: ["retail", "hybrid"] },
      { href: "/ecommerce-orders",label: "E-comm Orders",  icon: "orders",       permission: "orders:manage",   allowedTypes: ["online", "hybrid"] },
      { href: "/channels",        label: "Channels",       icon: "storefront",   permission: "channels:manage", allowedTypes: ["online", "hybrid"] },
      { href: "/discounts",       label: "Discounts",      icon: "local_offer",  permission: "discounts:read",  allowedTypes: ALL_TYPES },
      { href: "/tax",             label: "Tax",            icon: "receipt",      permission: "tax:manage",      allowedTypes: ALL_TYPES },
    ],
  },
  {
    label: "Catalog",
    items: [
      { href: "/products",        label: "Products",        icon: "category",       permission: "catalog:read",     allowedTypes: ALL_TYPES },
      { href: "/categories",      label: "Categories",      icon: "account_tree",   permission: "catalog:read",     allowedTypes: ALL_TYPES },
      { href: "/purchase-orders", label: "Purchase Orders", icon: "shopping_bag",   permission: "procurement:read", allowedTypes: ALL_TYPES },
      { href: "/suppliers",       label: "Suppliers",       icon: "local_shipping", permission: "procurement:read", allowedTypes: ALL_TYPES },
    ],
  },
  {
    label: "Stock",
    items: [
      { href: "/inventory",       label: "Inventory",       icon: "inventory_2",     permission: "inventory:read",         allowedTypes: ALL_TYPES },
      { href: "/inventory-pools", label: "Inventory Pools", icon: "layers",          permission: "inventory_pools:manage", allowedTypes: ["online", "hybrid"] },
      { href: "/reconciliation",  label: "Reconciliation",  icon: "account_balance", permission: "operations:read",        allowedTypes: ["retail", "hybrid"] },
    ],
  },
  {
    label: "Insights",
    items: [
      { href: "/insights", label: "Insights",  icon: "insights",    permission: "analytics:read", allowedTypes: ALL_TYPES },
      { href: "/audit",    label: "Audit Log", icon: "policy",      permission: "audit:read",     allowedTypes: ALL_TYPES },
    ],
  },
  {
    label: "People",
    items: [
      { href: "/team",   label: "Team",   icon: "groups",     permission: "staff:read",      allowedTypes: ALL_TYPES },
      { href: "/shifts", label: "Shifts", icon: "event_note", permission: "operations:read", allowedTypes: ["retail", "hybrid"] },
    ],
  },
  {
    label: "Setup",
    items: [
      { href: "/ecommerce",    label: "E-commerce",   icon: "shopping_cart",  permission: "settings:read",     allowedTypes: ["online", "hybrid"] },
      { href: "/integrations", label: "Integrations", icon: "hub",            permission: "integrations:read", allowedTypes: ALL_TYPES },
      { href: "/billing",      label: "Billing",      icon: "payments",       permission: "settings:read",     allowedTypes: ALL_TYPES },
      { href: "/apps",         label: "Get Apps",     icon: "install_mobile", permission: "settings:read",     allowedTypes: ALL_TYPES },
      { href: "/settings",     label: "Settings",     icon: "settings",       permission: "settings:read",     allowedTypes: ALL_TYPES },
    ],
  },
];

const EXPANDED_GROUPS_KEY = "nav-expanded-groups";

function readExpandedGroups(): Record<string, boolean> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(EXPANDED_GROUPS_KEY);
    if (!raw) return {};
    return JSON.parse(raw) as Record<string, boolean>;
  } catch {
    return {};
  }
}

function writeExpandedGroups(state: Record<string, boolean>): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(EXPANDED_GROUPS_KEY, JSON.stringify(state));
  } catch {
    // ignore
  }
}

type NewEntryItem = {
  href: string;
  label: string;
  icon: string;
  allowedTypes: BusinessType[];
};

const ALL_TYPES_NE: BusinessType[] = ["online", "retail", "hybrid"];

const NEW_ENTRY_ITEMS: NewEntryItem[] = [
  { href: "/entries",            label: "Create Product",  icon: "inventory_2", allowedTypes: ALL_TYPES_NE },
  { href: "/customers?new=1",    label: "Create Customer", icon: "person_add",  allowedTypes: ALL_TYPES_NE },
  { href: "/shops?new=1",        label: "Create Shop",     icon: "store",       allowedTypes: ["retail", "hybrid"] },
  { href: "/channels/setup",     label: "Create Channel",  icon: "storefront",  allowedTypes: ["online", "hybrid"] },
  { href: "/discounts?new=1",    label: "Create Discount", icon: "local_offer", allowedTypes: ["online", "hybrid"] },
];

function HeaderSearch() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const cfg = getSearchConfig(pathname);
  const [value, setValue] = useState(params.get(cfg?.paramName ?? "q") ?? "");

  // Sync local state from URL when navigating
  useEffect(() => {
    setValue(params.get(cfg?.paramName ?? "q") ?? "");
  }, [params, cfg?.paramName]);

  // Debounce push to URL
  useEffect(() => {
    if (!cfg) return;
    const handle = window.setTimeout(() => {
      const next = new URLSearchParams(params.toString());
      if (value.trim()) next.set(cfg.paramName, value.trim());
      else next.delete(cfg.paramName);
      const qs = next.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname);
    }, 300);
    return () => window.clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  if (!cfg) return null;

  return (
    <div className="relative w-full max-w-sm">
      <span
        className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-lg text-on-surface-variant"
        aria-hidden="true"
      >
        search
      </span>
      <input
        className="w-full rounded-full border-none bg-surface-container-low py-2 pl-10 pr-4 text-sm text-on-surface outline-none placeholder:text-on-surface-variant focus:ring-1 focus:ring-primary"
        placeholder={cfg.placeholder}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        type="text"
      />
    </div>
  );
}

export function AppShell({ children, current }: { children: ReactNode; current?: string }) {
  return (
    <BusinessTypeProvider>
      <AppShellInner current={current}>{children}</AppShellInner>
    </BusinessTypeProvider>
  );
}

function AppShellInner({ children, current }: { children: ReactNode; current?: string }) {
  const [notifOpen, setNotifOpen] = useState(false);
  const { items: notifItems, unread, loading: notifLoading, markAllRead, markRead } = useNotifications(notifOpen);
  const panelRef = useRef<HTMLDivElement>(null);
  const [entryMenuOpen, setEntryMenuOpen] = useState(false);
  const entryMenuRef = useRef<HTMLDivElement>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    if (!entryMenuOpen) return;
    function handleOutside(e: MouseEvent) {
      if (entryMenuRef.current && !entryMenuRef.current.contains(e.target as Node)) {
        setEntryMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, [entryMenuOpen]);

  useEffect(() => {
    function handleKeydown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setPaletteOpen((p) => !p);
      }
    }
    document.addEventListener("keydown", handleKeydown);
    return () => document.removeEventListener("keydown", handleKeydown);
  }, []);

  const pathname = usePathname();
  const activePathRaw = current ?? pathname;
  const segments = activePathRaw.split("/").filter(Boolean);
  const tenantPrefix = segments.length > 0 && !ROOT_ROUTES.has(segments[0]) ? `/${segments[0]}` : "";
  const activePath = tenantPrefix && activePathRaw.startsWith(tenantPrefix)
    ? activePathRaw.slice(tenantPrefix.length) || "/"
    : activePathRaw;

  const { flags, loading: btLoading } = useBusinessType();
  const visibleNewEntryItems = NEW_ENTRY_ITEMS.filter((item) =>
    typeAllows(flags, item.allowedTypes)
  );
  const hasPermission = useHasPermission;

  // Compute which group contains the active page (auto-expand)
  const activeGroupLabel = NAV_GROUPS.find((g) =>
    g.items.some((i) => i.href === activePath)
  )?.label ?? null;

  const filterItem = (item: NavItemDef): boolean => {
    if (item.permission && !hasPermission(item.permission)) return false;
    return typeAllows(flags, item.allowedTypes);
  };

  const homeVisible = filterItem(HOME);
  const visibleGroups = NAV_GROUPS
    .map((g) => ({ ...g, items: g.items.filter(filterItem) }))
    .filter((g) => g.items.length > 0);

  const expandedFromStorage = typeof window !== "undefined" ? readExpandedGroups() : {};
  const handleGroupToggle = (label: string, expanded: boolean) => {
    const next = { ...readExpandedGroups(), [label]: expanded };
    writeExpandedGroups(next);
  };
  const isExpanded = (label: string): boolean => {
    if (label === activeGroupLabel) return true;
    if (label in expandedFromStorage) return Boolean(expandedFromStorage[label]);
    return label === "Sell"; // default
  };

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="flex h-full w-60 shrink-0 flex-col border-r border-outline-variant/15 bg-surface-container font-headline tracking-tight">
        <div className="px-6 pb-6 pt-6">
          <h1 className="text-base font-bold leading-tight text-on-surface">The Tactile Archive</h1>
          <p className="mt-0.5 text-[9px] uppercase tracking-widest text-on-surface-variant opacity-60">Management Suite</p>
        </div>
        <nav className="flex-1 space-y-2 overflow-y-auto px-3 pb-2">
          {btLoading && !flags ? (
            <div className="space-y-1.5 px-1">
              {[0,1,2,3,4,5].map((i) => (
                <div key={i} className="h-9 animate-pulse rounded-lg bg-surface-container-lowest/60" />
              ))}
            </div>
          ) : (
            <>
              {homeVisible && (
                <div className="space-y-0.5">
                  <Link
                    href={`${tenantPrefix}${HOME.href}`}
                    className={`flex items-center gap-3 rounded-lg px-4 py-2.5 text-[13px] transition-colors duration-150 ${
                      activePath === HOME.href
                        ? "bg-primary/10 font-bold text-primary"
                        : "font-medium text-on-surface-variant hover:bg-surface-container-lowest/60 hover:text-on-surface"
                    }`}
                  >
                    <span className={`material-symbols-outlined text-[20px] leading-none ${activePath === HOME.href ? "" : "opacity-70"}`} aria-hidden="true">
                      {HOME.icon}
                    </span>
                    {HOME.label}
                  </Link>
                </div>
              )}
              {visibleGroups.map((g) => (
                <NavGroup
                  key={g.label}
                  label={g.label}
                  items={g.items}
                  activePath={activePath}
                  tenantPrefix={tenantPrefix}
                  initiallyExpanded={isExpanded(g.label)}
                  onToggle={(expanded) => handleGroupToggle(g.label, expanded)}
                />
              ))}
            </>
          )}
        </nav>
        <div className="shrink-0 space-y-3 px-3 pb-4 pt-2">
          <div ref={entryMenuRef} className="relative">
            <button
              type="button"
              onClick={() => setEntryMenuOpen((o) => !o)}
              className="ink-gradient flex w-full items-center justify-center gap-2 rounded-lg py-3 text-[13px] font-bold text-on-primary shadow-md transition-all hover:opacity-90 active:scale-[0.98]"
            >
              <span className="material-symbols-outlined text-lg leading-none" aria-hidden="true">add_circle</span>
              New Entry
            </button>
            {entryMenuOpen && (
              <div className="absolute bottom-full left-0 right-0 mb-1 overflow-hidden rounded-lg border border-outline-variant/10 bg-surface-container-lowest shadow-lg">
                {visibleNewEntryItems.map((item, idx) => (
                  <Link
                    key={item.href}
                    href={`${tenantPrefix}${item.href}`}
                    onClick={() => setEntryMenuOpen(false)}
                    className={`flex items-center gap-2 px-4 py-3 text-[13px] font-medium text-on-surface hover:bg-surface-container ${
                      idx > 0 ? "border-t border-outline-variant/10" : ""
                    }`}
                  >
                    <span className="material-symbols-outlined text-[18px]" aria-hidden="true">{item.icon}</span>
                    {item.label}
                  </Link>
                ))}
              </div>
            )}
          </div>
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
            <HeaderSearch />
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

      {/* Command palette */}
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />

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
