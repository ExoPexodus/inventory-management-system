import { NextResponse } from "next/server";
import { OPERATOR_JWT_COOKIE, OPERATOR_META_COOKIE, OPERATOR_TENANT_SLUG_COOKIE } from "@/lib/auth/constants";
import { shouldUseSecureCookie } from "@/lib/auth/cookie-secure";
import { internalApiUrl } from "@/lib/api/internal-url";

export async function POST(req: Request) {
  let body: { email?: string; password?: string; tenant_slug?: string };
  try {
    body = (await req.json()) as { email?: string; password?: string; tenant_slug?: string };
  } catch {
    return NextResponse.json({ detail: "invalid_json" }, { status: 400 });
  }
  const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
  const password = typeof body.password === "string" ? body.password : "";
  const expectedTenantSlug =
    typeof body.tenant_slug === "string" && body.tenant_slug.trim() ? body.tenant_slug.trim().toLowerCase() : "";
  const base = internalApiUrl();
  const r = await fetch(`${base}/v1/admin/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  const text = await r.text();
  if (!r.ok) {
    return new NextResponse(text, { status: r.status, headers: { "content-type": "application/json" } });
  }
  let json: { access_token: string; expires_in?: number; tenant_slug?: string; role?: string; permissions?: string[] };
  try {
    json = JSON.parse(text) as { access_token: string; expires_in?: number; tenant_slug?: string; role?: string; permissions?: string[] };
  } catch {
    return NextResponse.json({ detail: "bad_upstream" }, { status: 502 });
  }
  const tenantSlug = typeof json.tenant_slug === "string" ? json.tenant_slug.trim().toLowerCase() : "";
  if (expectedTenantSlug && tenantSlug && tenantSlug !== expectedTenantSlug) {
    return NextResponse.json(
      { detail: "Your account does not belong to this organization." },
      { status: 403 },
    );
  }
  if (!tenantSlug) {
    return NextResponse.json({ detail: "bad_upstream_tenant" }, { status: 502 });
  }
  const res = NextResponse.json({ ok: true });
  const maxAge = json.expires_in ?? 3600;
  const secure = shouldUseSecureCookie(req);
  res.cookies.set(OPERATOR_JWT_COOKIE, json.access_token, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge,
    secure,
  });
  res.cookies.set(OPERATOR_TENANT_SLUG_COOKIE, tenantSlug, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge,
    secure,
  });
  // Non-HttpOnly so client JS can read role + permissions for nav filtering.
  // The API enforces truth — this is informational only.
  const meta = JSON.stringify({ role: json.role ?? null, permissions: json.permissions ?? [] });
  res.cookies.set(OPERATOR_META_COOKIE, meta, {
    httpOnly: false,
    sameSite: "lax",
    path: "/",
    maxAge,
    secure,
  });
  return res;
}
