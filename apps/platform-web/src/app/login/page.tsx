"use client";

import { FormEvent, Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const from = params.get("from") ?? "/dashboard";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const r = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(d.detail ?? `Login failed (${r.status})`);
      }
      router.push(from);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-primary">
            <span className="material-symbols-outlined text-3xl text-on-primary">admin_panel_settings</span>
          </div>
          <h1 className="font-headline text-2xl font-extrabold text-on-surface">Platform Console</h1>
          <p className="mt-1 text-sm text-on-surface-variant">Internal SaaS management portal</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">Email</label>
            <input
              type="text"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-outline-variant/30 bg-surface-container-lowest px-4 py-2.5 text-sm text-on-surface outline-none transition focus:border-primary focus:ring-1 focus:ring-primary"
              placeholder="admin@platform.ims"
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-outline-variant/30 bg-surface-container-lowest px-4 py-2.5 text-sm text-on-surface outline-none transition focus:border-primary focus:ring-1 focus:ring-primary"
              placeholder="Enter password"
              required
            />
          </div>

          {error ? (
            <div className="rounded-lg bg-error-container/40 px-4 py-2.5 text-sm text-on-error-container">{error}</div>
          ) : null}

          <button
            type="submit"
            disabled={loading}
            className="ink-gradient w-full rounded-lg px-6 py-2.5 text-sm font-semibold text-on-primary shadow-sm transition hover:opacity-90 disabled:opacity-50"
          >
            {loading ? "Signing in..." : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}
