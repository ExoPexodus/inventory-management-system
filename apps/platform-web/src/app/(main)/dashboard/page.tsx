"use client";

import { useEffect, useState } from "react";

type Stats = {
  total_tenants: number;
  active: number;
  trial: number;
  past_due: number;
  expired: number;
};

function StatCard({ label, value, icon, color }: { label: string; value: string | number; icon: string; color?: string }) {
  return (
    <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-5 shadow-sm">
      <div className="flex items-center gap-2 text-on-surface-variant">
        <span className="material-symbols-outlined text-lg">{icon}</span>
        <p className="text-xs font-bold uppercase tracking-widest">{label}</p>
      </div>
      <p className={`mt-3 font-headline text-3xl font-extrabold ${color ?? "text-on-surface"}`}>{value}</p>
    </div>
  );
}

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        // Fetch tenants and subscriptions to compute stats
        const [tRes, sRes] = await Promise.all([
          fetch("/api/platform/v1/platform/tenants?limit=200"),
          fetch("/api/platform/v1/platform/subscriptions?limit=200"),
        ]);
        const tenants = tRes.ok ? ((await tRes.json()) as { items: unknown[]; total: number }) : { items: [], total: 0 };
        const subs = sRes.ok ? ((await sRes.json()) as { status: string }[]) : [];

        const counts = { active: 0, trial: 0, past_due: 0, expired: 0 };
        for (const s of subs) {
          const st = s.status as keyof typeof counts;
          if (st in counts) counts[st]++;
        }

        setStats({
          total_tenants: tenants.total,
          ...counts,
        });
      } catch { /* ignore */ }
      setLoading(false);
    }
    void load();
  }, []);

  return (
    <div className="space-y-8">
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Platform overview</p>
        <h1 className="mt-1 font-headline text-3xl font-extrabold text-on-surface">Dashboard</h1>
        <p className="mt-1 text-sm text-on-surface-variant">SaaS health at a glance.</p>
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        </div>
      ) : stats ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard label="Total tenants" value={stats.total_tenants} icon="apartment" />
          <StatCard label="Active" value={stats.active} icon="check_circle" color="text-primary" />
          <StatCard label="On trial" value={stats.trial} icon="hourglass_top" color="text-secondary" />
          <StatCard label="Past due" value={stats.past_due} icon="warning" color="text-error" />
        </div>
      ) : (
        <p className="text-sm text-on-surface-variant">Failed to load stats.</p>
      )}
    </div>
  );
}
