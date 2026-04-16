import { NextResponse } from "next/server";
import { PLATFORM_JWT_COOKIE, PLATFORM_META_COOKIE } from "@/lib/auth/constants";
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
  const r = await fetch(`${base}/v1/platform/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });

  const text = await r.text();
  if (!r.ok) {
    return new NextResponse(text, { status: r.status, headers: { "content-type": "application/json" } });
  }

  let json: { access_token: string; expires_in?: number; display_name?: string; email?: string };
  try {
    json = JSON.parse(text);
  } catch {
    return NextResponse.json({ detail: "bad_upstream" }, { status: 502 });
  }

  const res = NextResponse.json({ ok: true });
  const maxAge = json.expires_in ?? 86400;
  const secure = process.env.COOKIE_SECURE === "true";

  res.cookies.set(PLATFORM_JWT_COOKIE, json.access_token, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    maxAge,
    secure,
  });
  res.cookies.set(PLATFORM_META_COOKIE, JSON.stringify({ display_name: json.display_name, email: json.email }), {
    httpOnly: false,
    sameSite: "lax",
    path: "/",
    maxAge,
    secure,
  });

  return res;
}
