import { NextResponse } from "next/server";
import { PLATFORM_JWT_COOKIE, PLATFORM_META_COOKIE } from "@/lib/auth/constants";

export async function POST() {
  const res = NextResponse.json({ ok: true });
  res.cookies.set(PLATFORM_JWT_COOKIE, "", { maxAge: 0, path: "/" });
  res.cookies.set(PLATFORM_META_COOKIE, "", { maxAge: 0, path: "/" });
  return res;
}
