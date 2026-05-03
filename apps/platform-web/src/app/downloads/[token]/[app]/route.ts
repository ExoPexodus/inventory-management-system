import { NextRequest, NextResponse } from "next/server";
import { internalApiUrl } from "@/lib/api/internal-url";

export async function GET(
  _req: NextRequest,
  ctx: { params: Promise<{ token: string; app: string }> },
) {
  const { token, app } = await ctx.params;
  const upstream = `${internalApiUrl()}/downloads/${token}/${app}/latest`;

  let r: Response;
  try {
    r = await fetch(upstream, { cache: "no-store" });
  } catch {
    return NextResponse.json({ detail: "Download service unavailable" }, { status: 502 });
  }

  if (!r.ok) {
    const status = r.status === 404 ? 404 : 502;
    return NextResponse.json({ detail: "File not found" }, { status });
  }

  const headers = new Headers();
  const ct = r.headers.get("content-type");
  const cd = r.headers.get("content-disposition");
  const cl = r.headers.get("content-length");
  if (ct) headers.set("content-type", ct);
  if (cd) headers.set("content-disposition", cd);
  if (cl) headers.set("content-length", cl);

  return new NextResponse(r.body, { status: 200, headers });
}
