import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";
import { PLATFORM_JWT_COOKIE } from "@/lib/auth/constants";

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Skip API routes, static assets, login page, and public download pages
  if (pathname.startsWith("/api")) return NextResponse.next();
  if (pathname.startsWith("/login")) return NextResponse.next();
  if (pathname.startsWith("/_next")) return NextResponse.next();
  if (pathname.startsWith("/downloads")) return NextResponse.next();
  if (pathname === "/favicon.ico") return NextResponse.next();

  const token = req.cookies.get(PLATFORM_JWT_COOKIE)?.value;
  if (!token) {
    const login = new URL("/login", req.url);
    login.searchParams.set("from", pathname);
    return NextResponse.redirect(login);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
