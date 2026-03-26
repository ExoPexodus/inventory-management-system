import { NextResponse } from "next/server";
import { OPERATOR_JWT_COOKIE } from "@/lib/auth/constants";
import { shouldUseSecureCookie } from "@/lib/auth/cookie-secure";
import { internalApiUrl } from "@/lib/api/internal-url";

export async function POST(req: Request) {
  let body: { email?: string; password?: string };
  try {
    body = (await req.json()) as { email?: string; password?: string };
  } catch {
    return NextResponse.json({ detail: "invalid_json" }, { status: 400 });
  }
  const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
  const password = typeof body.password === "string" ? body.password : "";
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
  let json: { access_token: string; expires_in?: number };
  try {
    json = JSON.parse(text) as { access_token: string; expires_in?: number };
  } catch {
    return NextResponse.json({ detail: "bad_upstream" }, { status: 502 });
  }
  const res = NextResponse.json({ ok: true });
  const maxAge = json.expires_in ?? 3600;
  res.cookies.set(OPERATOR_JWT_COOKIE, json.access_token, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge,
    secure: shouldUseSecureCookie(req),
  });
  return res;
}
