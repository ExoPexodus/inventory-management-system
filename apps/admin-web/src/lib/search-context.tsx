"use client";

export interface PageSearchConfig {
  placeholder: string;
  paramName: string;
}

const PAGE_SEARCH_CONFIG: Record<string, PageSearchConfig> = {
  "/products":         { placeholder: "Search products...",      paramName: "q" },
  "/inventory":        { placeholder: "Search inventory...",     paramName: "q" },
  "/orders":           { placeholder: "Search transactions...",  paramName: "q" },
  "/ecommerce-orders": { placeholder: "Search online orders...", paramName: "q" },
  "/customers":        { placeholder: "Search customers...",     paramName: "q" },
  "/audit":            { placeholder: "Search audit events...",  paramName: "q" },
};

const ROOT_ROUTES = new Set([
  "overview", "inventory", "staff", "team", "orders", "analytics",
  "suppliers", "products", "purchase-orders", "shifts", "reconciliation",
  "audit", "reports", "integrations", "settings", "billing", "apps",
  "entries", "shops", "login", "channels", "ecommerce-orders", "discounts",
  "ecommerce", "inventory-pools", "tax", "customers",
]);

/** Strip a tenant prefix segment (e.g. "/some-tenant/products" -> "/products"). */
function stripTenantPrefix(pathname: string): string {
  const segs = pathname.split("/").filter(Boolean);
  if (segs.length === 0) return pathname;
  if (!ROOT_ROUTES.has(segs[0])) {
    return "/" + segs.slice(1).join("/");
  }
  return pathname;
}

export function getSearchConfig(pathname: string): PageSearchConfig | null {
  const stripped = stripTenantPrefix(pathname);
  for (const [route, cfg] of Object.entries(PAGE_SEARCH_CONFIG)) {
    if (stripped === route || stripped.startsWith(route + "/")) {
      return cfg;
    }
  }
  return null;
}
