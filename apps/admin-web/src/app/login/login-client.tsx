"use client";

import { FormEvent, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

export function LoginClient({ tenantSlug }: { tenantSlug?: string }) {
  const router = useRouter();
  const qs = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const r = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, tenant_slug: tenantSlug ?? null }),
      });
      if (!r.ok) {
        let msg = `Login failed (${r.status})`;
        try {
          const j = (await r.json()) as { detail?: string };
          if (j.detail) msg = j.detail;
        } catch {
          /* ignore */
        }
        setError(msg);
        return;
      }
      const fallback = tenantSlug ? `/${tenantSlug}/overview` : "/overview";
      const dest = qs.get("from") || fallback;
      router.push(dest.startsWith("/") ? dest : fallback);
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-surface px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <h1 className="font-headline text-3xl font-extrabold tracking-tight text-on-surface">The Tactile Archive</h1>
          <p className="mt-1 text-[10px] uppercase tracking-widest text-on-surface-variant">Management Suite</p>
        </div>
        <div className="rounded-2xl border border-outline-variant/15 bg-surface-container-lowest p-8 shadow-sm">
          <h2 className="font-headline text-xl font-bold text-on-surface">Sign in</h2>
          <p className="mt-1 text-sm text-on-surface-variant">
            Enter your operator credentials to continue.
            {tenantSlug ? ` Organization: ${tenantSlug}` : ""}
          </p>
          <form onSubmit={onSubmit} className="mt-6 space-y-5">
            <div>
              <label className="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant" htmlFor="email">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="username"
                required
                className="ledger-input mt-2 w-full py-2.5 font-headline text-base text-on-surface placeholder:text-outline-variant/50"
                placeholder="operator@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div>
              <label className="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant" htmlFor="password">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                required
                className="ledger-input mt-2 w-full py-2.5 font-headline text-base text-on-surface placeholder:text-outline-variant/50"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            {error ? (
              <div className="rounded-lg border border-error/20 bg-error-container/30 px-3 py-2 text-sm text-on-error-container" role="alert">
                {error}
              </div>
            ) : null}
            <button
              type="submit"
              disabled={busy}
              className="ink-gradient w-full rounded-lg py-3 text-sm font-bold text-on-primary shadow-md transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </div>
      </div>
    </main>
  );
}
