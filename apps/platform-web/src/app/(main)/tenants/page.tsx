"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

type Tenant = {
  id: string;
  name: string;
  slug: string;
  region: string;
  download_token: string;
  created_at: string;
};

export default function TenantsPage() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");

  useEffect(() => {
    async function load() {
      setLoading(true);
      const sp = new URLSearchParams();
      if (q.trim()) sp.set("q", q.trim());
      const r = await fetch(`/api/platform/v1/platform/tenants?${sp}`);
      if (r.ok) {
        const d = await r.json();
        setTenants(d.items ?? []);
      }
      setLoading(false);
    }
    const t = setTimeout(load, 300);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Tenant registry</p>
          <h1 className="mt-1 font-headline text-3xl font-extrabold text-on-surface">Tenants</h1>
        </div>
      </div>

      <input
        type="text"
        placeholder="Search tenants..."
        value={q}
        onChange={(e) => setQ(e.target.value)}
        className="w-full max-w-md rounded-lg border border-outline-variant/30 bg-surface-container-lowest px-4 py-2.5 text-sm text-on-surface outline-none focus:border-primary"
      />

      <div className="overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm">
        <table className="min-w-full text-left text-sm">
          <thead>
            <tr className="border-b border-outline-variant/10">
              <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Name</th>
              <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Slug</th>
              <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Region</th>
              <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Created</th>
              <th className="px-6 py-3 text-center text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-outline-variant/10">
            {loading ? (
              <tr><td colSpan={5} className="px-6 py-12 text-center text-sm text-on-surface-variant">Loading...</td></tr>
            ) : tenants.length === 0 ? (
              <tr><td colSpan={5} className="px-6 py-12 text-center text-sm text-on-surface-variant">No tenants found.</td></tr>
            ) : tenants.map((t) => (
              <tr key={t.id} className="hover:bg-surface-container-low/60">
                <td className="px-6 py-3 font-semibold text-on-surface">{t.name}</td>
                <td className="px-6 py-3 font-mono text-xs text-on-surface-variant">{t.slug}</td>
                <td className="px-6 py-3">
                  <span className="inline-flex rounded-full bg-primary/10 px-2.5 py-0.5 text-[10px] font-bold uppercase text-primary">
                    {t.region}
                  </span>
                </td>
                <td className="px-6 py-3 text-xs text-on-surface-variant">
                  {new Date(t.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
                </td>
                <td className="px-6 py-3 text-center">
                  <Link
                    href={`/tenants/${t.id}`}
                    className="inline-flex items-center gap-1 rounded-lg border border-outline-variant/20 px-3 py-1.5 text-xs font-semibold text-on-surface transition hover:bg-surface-container-high"
                  >
                    <span className="material-symbols-outlined text-sm">open_in_new</span>
                    Detail
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
