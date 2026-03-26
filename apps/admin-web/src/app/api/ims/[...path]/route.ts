import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { OPERATOR_JWT_COOKIE } from "@/lib/auth/constants";
import { internalApiUrl } from "@/lib/api/internal-url";

async function proxy(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const jar = await cookies();
  const token = jar.get(OPERATOR_JWT_COOKIE)?.value;
  if (!token) return NextResponse.json({ detail: "unauthorized" }, { status: 401 });

  const base = internalApiUrl();
  const subpath = path.join("/");
  const target = `${base}/${subpath}${req.nextUrl.search}`;

  const headers = new Headers();
  headers.set("Authorization", `Bearer ${token}`);
  const ct = req.headers.get("content-type");
  if (ct) headers.set("content-type", ct);
  const accept = req.headers.get("accept");
  if (accept) headers.set("accept", accept);

  const init: RequestInit = { method: req.method, headers, redirect: "manual" };
  if (!["GET", "HEAD"].includes(req.method)) {
    const buf = await req.arrayBuffer();
    if (buf.byteLength) init.body = buf;
  }

  const r = await fetch(target, init);
  const body = await r.arrayBuffer();
  const res = new NextResponse(body, { status: r.status });
  const outCt = r.headers.get("content-type");
  if (outCt) res.headers.set("content-type", outCt);
  return res;
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const PUT = proxy;
export const DELETE = proxy;
