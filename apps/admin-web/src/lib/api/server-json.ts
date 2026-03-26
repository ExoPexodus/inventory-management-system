import { cookies } from "next/headers";
import { OPERATOR_JWT_COOKIE } from "@/lib/auth/constants";
import { internalApiUrl } from "@/lib/api/internal-url";

export async function serverJsonGet<T>(path: string): Promise<{ ok: true; data: T } | { ok: false; status: number }> {
  const jar = await cookies();
  const token = jar.get(OPERATOR_JWT_COOKIE)?.value;
  if (!token) return { ok: false, status: 401 };
  const base = internalApiUrl();
  const url = path.startsWith("http") ? path : `${base}${path.startsWith("/") ? path : `/${path}`}`;
  const r = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  });
  if (!r.ok) return { ok: false, status: r.status };
  return { ok: true, data: (await r.json()) as T };
}
