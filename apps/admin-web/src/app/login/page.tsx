import { Suspense } from "react";
import { notFound } from "next/navigation";
import { LoginClient } from "./login-client";
import { internalApiUrl } from "@/lib/api/internal-url";

type SearchParams = { from?: string; tenant?: string };

export default async function LoginPage({
  searchParams,
}: {
  searchParams?: Promise<SearchParams>;
}) {
  const resolved = (await searchParams) ?? {};
  const tenantSlug = typeof resolved.tenant === "string" ? resolved.tenant.trim().toLowerCase() : "";
  if (tenantSlug) {
    const base = internalApiUrl();
    const r = await fetch(`${base}/v1/tenants/by-slug/${encodeURIComponent(tenantSlug)}`, {
      cache: "no-store",
    });
    if (!r.ok) notFound();
  }
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center text-sm text-primary/60">Loading…</main>
      }
    >
      <LoginClient tenantSlug={tenantSlug || undefined} />
    </Suspense>
  );
}
