"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useBusinessType, typeAllows } from "@/lib/business-type-context";
import { useHasPermission } from "@/lib/auth/user-context";

// Type duplicated from AppShell to avoid circular import
type BizType = "online" | "retail" | "hybrid";

interface ActionItem {
  kind: "action";
  id: string;
  label: string;
  icon: string;
  href: string;
  allowedTypes: BizType[];
}

interface PageItem {
  kind: "page";
  id: string;
  label: string;
  group: string;
  icon: string;
  href: string;
  permission: string | null;
  allowedTypes: BizType[];
}

interface ProductItem {
  kind: "product";
  id: string;
  label: string;        // SKU + name
  href: string;
}

type ResultItem = ActionItem | PageItem | ProductItem;

const ALL: BizType[] = ["online", "retail", "hybrid"];

const ACTIONS: ActionItem[] = [
  { kind: "action", id: "act-product",  label: "Create Product",  icon: "inventory_2", href: "/entries",         allowedTypes: ALL },
  { kind: "action", id: "act-customer", label: "Create Customer", icon: "person_add",  href: "/customers?new=1", allowedTypes: ALL },
  { kind: "action", id: "act-shop",     label: "Create Shop",     icon: "store",       href: "/shops?new=1",     allowedTypes: ["retail", "hybrid"] },
  { kind: "action", id: "act-channel",  label: "Create Channel",  icon: "storefront",  href: "/channels/setup",  allowedTypes: ["online", "hybrid"] },
  { kind: "action", id: "act-discount", label: "Create Discount", icon: "local_offer", href: "/discounts?new=1", allowedTypes: ["online", "hybrid"] },
];

const PAGES: PageItem[] = [
  { kind: "page", id: "p-overview",        label: "Dashboard",        group: "Home",     icon: "dashboard",       href: "/overview",        permission: null,                     allowedTypes: ALL },
  // Sell
  { kind: "page", id: "p-orders",          label: "Orders",           group: "Sell",     icon: "receipt_long",    href: "/orders",          permission: "sales:read",             allowedTypes: ["retail", "hybrid"] },
  { kind: "page", id: "p-ecomm-orders",    label: "E-comm Orders",    group: "Sell",     icon: "orders",          href: "/ecommerce-orders", permission: "orders:manage",          allowedTypes: ["online", "hybrid"] },
  { kind: "page", id: "p-channels",        label: "Channels",         group: "Sell",     icon: "storefront",      href: "/channels",        permission: "channels:manage",         allowedTypes: ["online", "hybrid"] },
  { kind: "page", id: "p-discounts",       label: "Discounts",        group: "Sell",     icon: "local_offer",     href: "/discounts",       permission: "discounts:read",          allowedTypes: ALL },
  { kind: "page", id: "p-tax",             label: "Tax",              group: "Sell",     icon: "receipt",         href: "/tax",             permission: "tax:manage",              allowedTypes: ALL },
  // Catalog
  { kind: "page", id: "p-products",        label: "Products",         group: "Catalog",  icon: "category",        href: "/products",        permission: "catalog:read",            allowedTypes: ALL },
  { kind: "page", id: "p-purchase-orders", label: "Purchase Orders",  group: "Catalog",  icon: "shopping_bag",    href: "/purchase-orders", permission: "procurement:read",        allowedTypes: ALL },
  { kind: "page", id: "p-suppliers",       label: "Suppliers",        group: "Catalog",  icon: "local_shipping",  href: "/suppliers",       permission: "procurement:read",        allowedTypes: ALL },
  // Stock
  { kind: "page", id: "p-inventory",       label: "Inventory",        group: "Stock",    icon: "inventory_2",     href: "/inventory",       permission: "inventory:read",          allowedTypes: ALL },
  { kind: "page", id: "p-inv-pools",       label: "Inventory Pools",  group: "Stock",    icon: "layers",          href: "/inventory-pools", permission: "inventory_pools:manage", allowedTypes: ["online", "hybrid"] },
  { kind: "page", id: "p-reconciliation",  label: "Reconciliation",   group: "Stock",    icon: "account_balance", href: "/reconciliation",  permission: "operations:read",         allowedTypes: ["retail", "hybrid"] },
  // Insights
  { kind: "page", id: "p-insights",        label: "Insights",         group: "Insights", icon: "insights",        href: "/insights",        permission: "analytics:read",          allowedTypes: ALL },
  { kind: "page", id: "p-audit",           label: "Audit Log",        group: "Insights", icon: "policy",          href: "/audit",           permission: "audit:read",              allowedTypes: ALL },
  // People
  { kind: "page", id: "p-team",            label: "Team",             group: "People",   icon: "groups",          href: "/team",            permission: "staff:read",              allowedTypes: ALL },
  { kind: "page", id: "p-shifts",          label: "Shifts",           group: "People",   icon: "event_note",      href: "/shifts",          permission: "operations:read",         allowedTypes: ["retail", "hybrid"] },
  // Setup
  { kind: "page", id: "p-ecommerce",       label: "E-commerce",       group: "Setup",    icon: "shopping_cart",   href: "/ecommerce",       permission: "settings:read",           allowedTypes: ["online", "hybrid"] },
  { kind: "page", id: "p-integrations",    label: "Integrations",     group: "Setup",    icon: "hub",             href: "/integrations",    permission: "integrations:read",       allowedTypes: ALL },
  { kind: "page", id: "p-billing",         label: "Billing",          group: "Setup",    icon: "payments",        href: "/billing",         permission: "settings:read",           allowedTypes: ALL },
  { kind: "page", id: "p-apps",            label: "Get Apps",         group: "Setup",    icon: "install_mobile",  href: "/apps",            permission: "settings:read",           allowedTypes: ALL },
  { kind: "page", id: "p-settings",        label: "Settings",         group: "Setup",    icon: "settings",        href: "/settings",        permission: "settings:read",           allowedTypes: ALL },
  // Settings sub-pages
  { kind: "page", id: "p-set-email",       label: "Settings → Email",         group: "Settings", icon: "mail",            href: "/settings/email",          permission: "settings:read", allowedTypes: ALL },
  { kind: "page", id: "p-set-currency",    label: "Settings → Currency",      group: "Settings", icon: "payments",        href: "/settings/currency",       permission: "settings:read", allowedTypes: ALL },
  { kind: "page", id: "p-set-localisation",label: "Settings → Localisation",  group: "Settings", icon: "language",        href: "/settings/localisation",   permission: "settings:read", allowedTypes: ALL },
  { kind: "page", id: "p-set-devices",     label: "Settings → Devices",       group: "Settings", icon: "devices",         href: "/settings/devices",        permission: "settings:read", allowedTypes: ALL },
  { kind: "page", id: "p-set-recon",       label: "Settings → Reconciliation",group: "Settings", icon: "account_balance", href: "/settings/reconciliation", permission: "settings:read", allowedTypes: ALL },
  { kind: "page", id: "p-set-cust-groups", label: "Settings → Customer Groups", group: "Settings", icon: "groups",        href: "/settings/customer-groups", permission: "settings:read", allowedTypes: ALL },
  { kind: "page", id: "p-set-bt",          label: "Settings → Business Type", group: "Settings", icon: "storefront",      href: "/settings/business-type",  permission: "settings:read", allowedTypes: ALL },
];

interface Props {
  open: boolean;
  onClose: () => void;
}

export function CommandPalette({ open, onClose }: Props) {
  const router = useRouter();
  const { flags } = useBusinessType();
  const hasPermission = useHasPermission;
  const inputRef = useRef<HTMLInputElement>(null);

  const [query, setQuery] = useState("");
  const [highlightIndex, setHighlightIndex] = useState(0);
  const [productResults, setProductResults] = useState<ProductItem[]>([]);
  const [productLoading, setProductLoading] = useState(false);

  // Reset state when opened
  useEffect(() => {
    if (open) {
      setQuery("");
      setHighlightIndex(0);
      setProductResults([]);
      // Focus input
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  // Filter actions and pages by business type, permission, and query
  const matches = useCallback(
    (label: string) => {
      const q = query.trim().toLowerCase();
      if (!q) return true;
      return label.toLowerCase().includes(q);
    },
    [query],
  );

  const visibleActions = ACTIONS.filter(
    (a) => typeAllows(flags, a.allowedTypes) && matches(a.label),
  );
  const visiblePages = PAGES.filter((p) => {
    if (p.permission && !hasPermission(p.permission)) return false;
    if (!typeAllows(flags, p.allowedTypes)) return false;
    return matches(p.label) || matches(p.group);
  });

  // Live product search (debounced)
  useEffect(() => {
    if (!open) return;
    const q = query.trim();
    if (q.length < 2) {
      setProductResults([]);
      return;
    }
    const handle = window.setTimeout(async () => {
      setProductLoading(true);
      try {
        const r = await fetch(`/api/ims/v1/admin/products?q=${encodeURIComponent(q)}`);
        if (r.ok) {
          const data = (await r.json()) as Array<{ id: string; sku: string; name: string }>;
          setProductResults(
            data.slice(0, 8).map((p) => ({
              kind: "product" as const,
              id: `prod-${p.id}`,
              label: `${p.sku} — ${p.name}`,
              href: `/products?q=${encodeURIComponent(q)}`,
            })),
          );
        }
      } catch {
        // ignore
      } finally {
        setProductLoading(false);
      }
    }, 250);
    return () => window.clearTimeout(handle);
  }, [query, open]);

  // Build flat result list for keyboard navigation
  const flatResults: ResultItem[] = [...visibleActions, ...visiblePages, ...productResults];

  useEffect(() => {
    setHighlightIndex(0);
  }, [query]);

  function pickResult(item: ResultItem) {
    onClose();
    router.push(item.href);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightIndex((i) => Math.min(i + 1, flatResults.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const item = flatResults[highlightIndex];
      if (item) pickResult(item);
    } else if (e.key === "Escape") {
      onClose();
    }
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[300] flex items-start justify-center bg-black/50 p-4 pt-[10vh]"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl overflow-hidden rounded-2xl bg-surface shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search input */}
        <div className="flex items-center gap-3 border-b border-outline-variant/10 px-4 py-3">
          <span className="material-symbols-outlined text-xl text-on-surface-variant">search</span>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search actions, pages, products..."
            className="flex-1 bg-transparent text-sm text-on-surface outline-none placeholder:text-on-surface-variant"
          />
          <kbd className="hidden rounded border border-outline-variant/30 bg-surface-container-low px-2 py-0.5 text-[10px] font-bold text-on-surface-variant sm:inline-block">
            Esc
          </kbd>
        </div>

        {/* Results */}
        <div className="max-h-[60vh] overflow-y-auto">
          {flatResults.length === 0 && !productLoading && query && (
            <p className="p-6 text-center text-sm text-on-surface-variant">No results.</p>
          )}

          {!query && (
            <p className="p-6 text-center text-sm text-on-surface-variant">Type to search across actions, pages, and products.</p>
          )}

          {visibleActions.length > 0 && (
            <div className="border-b border-outline-variant/10 py-2">
              <p className="px-4 py-1 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant/60">Actions</p>
              {visibleActions.map((a, idxInSection) => {
                const flatIdx = idxInSection;
                return (
                  <button
                    key={a.id}
                    type="button"
                    onMouseDown={(e) => { e.preventDefault(); pickResult(a); }}
                    onMouseEnter={() => setHighlightIndex(flatIdx)}
                    className={`flex w-full items-center gap-3 px-4 py-2 text-left text-sm transition-colors ${
                      highlightIndex === flatIdx ? "bg-primary/10 text-on-surface" : "text-on-surface hover:bg-surface-container-low/60"
                    }`}
                  >
                    <span className="material-symbols-outlined text-[20px] text-primary">{a.icon}</span>
                    <span>{a.label}</span>
                  </button>
                );
              })}
            </div>
          )}

          {visiblePages.length > 0 && (
            <div className="border-b border-outline-variant/10 py-2">
              <p className="px-4 py-1 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant/60">Pages</p>
              {visiblePages.map((p, idxInSection) => {
                const flatIdx = visibleActions.length + idxInSection;
                return (
                  <button
                    key={p.id}
                    type="button"
                    onMouseDown={(e) => { e.preventDefault(); pickResult(p); }}
                    onMouseEnter={() => setHighlightIndex(flatIdx)}
                    className={`flex w-full items-center gap-3 px-4 py-2 text-left text-sm transition-colors ${
                      highlightIndex === flatIdx ? "bg-primary/10 text-on-surface" : "text-on-surface hover:bg-surface-container-low/60"
                    }`}
                  >
                    <span className="material-symbols-outlined text-[20px] text-on-surface-variant">{p.icon}</span>
                    <span className="flex-1">{p.label}</span>
                    <span className="text-[10px] text-on-surface-variant/60">{p.group}</span>
                  </button>
                );
              })}
            </div>
          )}

          {productResults.length > 0 && (
            <div className="py-2">
              <p className="px-4 py-1 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant/60">Products</p>
              {productResults.map((p, idxInSection) => {
                const flatIdx = visibleActions.length + visiblePages.length + idxInSection;
                return (
                  <button
                    key={p.id}
                    type="button"
                    onMouseDown={(e) => { e.preventDefault(); pickResult(p); }}
                    onMouseEnter={() => setHighlightIndex(flatIdx)}
                    className={`flex w-full items-center gap-3 px-4 py-2 text-left text-sm transition-colors ${
                      highlightIndex === flatIdx ? "bg-primary/10 text-on-surface" : "text-on-surface hover:bg-surface-container-low/60"
                    }`}
                  >
                    <span className="material-symbols-outlined text-[20px] text-on-surface-variant">category</span>
                    <span>{p.label}</span>
                  </button>
                );
              })}
            </div>
          )}

          {productLoading && (
            <p className="px-4 py-2 text-xs text-on-surface-variant">Searching products…</p>
          )}
        </div>

        {/* Footer hint */}
        <div className="border-t border-outline-variant/10 bg-surface-container-low px-4 py-2 text-[10px] text-on-surface-variant">
          <kbd className="rounded border border-outline-variant/30 bg-surface-container-lowest px-1.5 py-0.5 font-bold">↑</kbd>
          <kbd className="ml-1 rounded border border-outline-variant/30 bg-surface-container-lowest px-1.5 py-0.5 font-bold">↓</kbd>
          <span className="ml-2">to navigate</span>
          <kbd className="ml-3 rounded border border-outline-variant/30 bg-surface-container-lowest px-1.5 py-0.5 font-bold">↵</kbd>
          <span className="ml-2">to select</span>
          <kbd className="ml-3 rounded border border-outline-variant/30 bg-surface-container-lowest px-1.5 py-0.5 font-bold">esc</kbd>
          <span className="ml-2">to close</span>
        </div>
      </div>
    </div>
  );
}
