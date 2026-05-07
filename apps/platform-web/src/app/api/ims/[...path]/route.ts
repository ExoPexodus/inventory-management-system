import { NextRequest, NextResponse } from "next/server";

const IMS_URL = process.env.IMS_API_URL ?? "http://api:8000";

async function proxy(req: NextRequest, path: string[], method: string, body?: string) {
  const url = `${IMS_URL}/${path.join("/")}${req.nextUrl.search}`;
  const headers: Record<string, string> = {};
  const ct = req.headers.get("content-type");
  if (ct) headers["content-type"] = ct;
  const adminToken = process.env.IMS_ADMIN_TOKEN ?? process.env.ADMIN_API_TOKEN;
  if (adminToken) headers["x-admin-token"] = adminToken;
  try {
    const upstream = await fetch(url, { method, headers, body });
    const text = await upstream.text();
    return new NextResponse(text, {
      status: upstream.status,
      headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json({ detail: "IMS API unreachable" }, { status: 502 });
  }
}

export async function GET(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(req, (await params).path, "GET");
}
export async function POST(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(req, (await params).path, "POST", await req.text());
}
export async function PATCH(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(req, (await params).path, "PATCH", await req.text());
}
export async function DELETE(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(req, (await params).path, "DELETE");
}
