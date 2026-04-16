import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { OPERATOR_JWT_COOKIE, OPERATOR_META_COOKIE, OPERATOR_TENANT_SLUG_COOKIE } from "@/lib/auth/constants";

// Soft route-permission map: route segment → required permission codename.
// The API enforces truth — middleware redirects are informational UX only.
const ROUTE_PERMISSIONS: Record<string, string> = {
  inventory: "inventory:read",
  staff: "staff:read",
  orders: "sales:read",
  analytics: "analytics:read",
  suppliers: "procurement:read",
  products: "catalog:read",
  "purchase-orders": "procurement:read",
  shifts: "operations:read",
  reconciliation: "operations:read",
  audit: "audit:read",
  reports: "reports:read",
  integrations: "integrations:read",
  billing: "settings:read",
  settings: "settings:read",
};

function getPermissionsFromCookie(req: NextRequest): string[] {
  const raw = req.cookies.get(OPERATOR_META_COOKIE)?.value;
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as { permissions?: string[] };
    return Array.isArray(parsed.permissions) ? parsed.permissions : [];
  } catch {
    return [];
  }
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
  "billing",
  "settings",
  "entries",
  "login",
]);

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (pathname.startsWith("/api")) return NextResponse.next();
  if (pathname.startsWith("/login")) return NextResponse.next();
  if (pathname.startsWith("/_next")) return NextResponse.next();
  if (pathname === "/favicon.ico") return NextResponse.next();

  const token = req.cookies.get(OPERATOR_JWT_COOKIE)?.value;
  const tenantSlug = req.cookies.get(OPERATOR_TENANT_SLUG_COOKIE)?.value;
  const segments = pathname.split("/").filter(Boolean);
  const first = segments[0] ?? "";

  if (pathname === "/") {
    if (token && tenantSlug) {
      return NextResponse.redirect(new URL(`/${tenantSlug}/overview`, req.url));
    }
    return NextResponse.next();
  }

  if (ROOT_ROUTES.has(first)) {
    if (!token && first !== "login") {
      const login = new URL("/login", req.url);
      login.searchParams.set("from", pathname);
      return NextResponse.redirect(login);
    }
    if (token && tenantSlug && first !== "login") {
      const scoped = new URL(`/${tenantSlug}${pathname}`, req.url);
      scoped.search = req.nextUrl.search;
      return NextResponse.redirect(scoped);
    }
    return NextResponse.next();
  }

  const urlTenantSlug = first.toLowerCase();
  if (segments.length === 1) {
    return NextResponse.redirect(new URL(`/${urlTenantSlug}/login`, req.url));
  }

  if (segments[1] === "login") {
    const rewritten = new URL("/login", req.url);
    rewritten.search = req.nextUrl.search;
    rewritten.searchParams.set("tenant", urlTenantSlug);
    return NextResponse.rewrite(rewritten);
  }

  if (!token) {
    const login = new URL(`/${urlTenantSlug}/login`, req.url);
    login.searchParams.set("from", pathname);
    return NextResponse.redirect(login);
  }
  if (tenantSlug && tenantSlug !== urlTenantSlug) {
    const corrected = new URL(`/${tenantSlug}/${segments.slice(1).join("/")}`, req.url);
    corrected.search = req.nextUrl.search;
    return NextResponse.redirect(corrected);
  }

  // Soft permission guard — redirect to /overview if the user lacks the required permission.
  // segments[1] is the route segment (e.g. "staff", "settings") after the tenant slug.
  const routeSegment = segments[1] ?? "";
  const requiredPermission = ROUTE_PERMISSIONS[routeSegment];
  if (requiredPermission) {
    const permissions = getPermissionsFromCookie(req);
    if (permissions.length > 0 && !permissions.includes(requiredPermission)) {
      const overview = new URL(`/${urlTenantSlug}/overview`, req.url);
      return NextResponse.redirect(overview);
    }
  }

  const rewritten = new URL(`/${segments.slice(1).join("/")}`, req.url);
  rewritten.search = req.nextUrl.search;
  rewritten.searchParams.set("tenant", urlTenantSlug);
  return NextResponse.rewrite(rewritten);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
