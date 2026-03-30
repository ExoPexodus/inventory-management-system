import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { OPERATOR_JWT_COOKIE, OPERATOR_TENANT_SLUG_COOKIE } from "@/lib/auth/constants";

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

  const rewritten = new URL(`/${segments.slice(1).join("/")}`, req.url);
  rewritten.search = req.nextUrl.search;
  rewritten.searchParams.set("tenant", urlTenantSlug);
  return NextResponse.rewrite(rewritten);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
