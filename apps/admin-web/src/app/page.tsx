"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

export default function HomePage() {
  const router = useRouter();
  const [slug, setSlug] = useState("");

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    const normalized = slug.trim().toLowerCase();
    if (!normalized) return;
    router.push(`/${encodeURIComponent(normalized)}/login`);
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-surface px-4">
      <div className="w-full max-w-md rounded-2xl border border-outline-variant/15 bg-surface-container-lowest p-8 shadow-sm">
        <h1 className="font-headline text-2xl font-extrabold text-on-surface">Find your organization</h1>
        <p className="mt-2 text-sm text-on-surface-variant">Enter your tenant slug to continue to sign in.</p>
        <form className="mt-6 space-y-4" onSubmit={onSubmit}>
          <label className="block text-[10px] font-bold uppercase tracking-widest text-on-surface-variant" htmlFor="tenant">
            Organization slug
          </label>
          <input
            id="tenant"
            className="ledger-input w-full py-2.5 font-headline text-base text-on-surface placeholder:text-outline-variant/50"
            placeholder="acme-corp"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
          />
          <button
            type="submit"
            className="ink-gradient w-full rounded-lg py-3 text-sm font-bold text-on-primary shadow-md transition-all hover:opacity-90"
          >
            Continue
          </button>
        </form>
      </div>
    </main>
  );
}
