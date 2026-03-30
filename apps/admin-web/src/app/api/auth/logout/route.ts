import { NextResponse } from "next/server";
import { OPERATOR_JWT_COOKIE, OPERATOR_TENANT_SLUG_COOKIE } from "@/lib/auth/constants";

export async function POST() {
  const res = NextResponse.json({ ok: true });
  res.cookies.set(OPERATOR_JWT_COOKIE, "", { httpOnly: true, path: "/", maxAge: 0 });
  res.cookies.set(OPERATOR_TENANT_SLUG_COOKIE, "", { httpOnly: true, path: "/", maxAge: 0 });
  return res;
}
