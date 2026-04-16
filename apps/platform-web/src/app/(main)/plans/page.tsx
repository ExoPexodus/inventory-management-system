"use client";

import { useEffect, useState } from "react";

type Plan = { id: string; codename: string; display_name: string; description: string | null; base_price_cents: number; currency_code: string; yearly_discount_pct: number; max_shops: number; max_employees: number; storage_limit_mb: number; is_active: boolean };
type Addon = { id: string; codename: string; display_name: string; description: string | null; price_cents: number; currency_code: string; is_active: boolean };

function fmt(cents: number, code: string) { return `${code} ${(cents / 100).toLocaleString()}`; }

export default function PlansPage() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [addons, setAddons] = useState<Addon[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      const [pRes, aRes] = await Promise.all([
        fetch("/api/platform/v1/platform/plans"),
        fetch("/api/platform/v1/platform/addons"),
      ]);
      if (pRes.ok) setPlans(await pRes.json());
      if (aRes.ok) setAddons(await aRes.json());
      setLoading(false);
    }
    void load();
  }, []);

  if (loading) return <div className="flex justify-center py-16"><div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" /></div>;

  return (
    <div className="space-y-8">
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Pricing configuration</p>
        <h1 className="mt-1 font-headline text-3xl font-extrabold text-on-surface">Plans & Add-ons</h1>
      </div>

      <section>
        <h2 className="mb-4 text-xs font-bold uppercase tracking-widest text-on-surface-variant">Base plans</h2>
        <div className="grid gap-4 lg:grid-cols-3">
          {plans.map((p) => (
            <div key={p.id} className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
              <div className="flex items-center justify-between">
                <h3 className="font-headline text-xl font-extrabold text-on-surface">{p.display_name}</h3>
                {!p.is_active ? <span className="rounded bg-surface-container-highest px-2 py-0.5 text-[10px] font-bold uppercase text-on-surface-variant">Inactive</span> : null}
              </div>
              <p className="mt-1 text-sm text-on-surface-variant">{p.description}</p>
              <p className="mt-4 font-headline text-2xl font-extrabold text-primary">{fmt(p.base_price_cents, p.currency_code)}<span className="text-sm font-normal text-on-surface-variant">/mo</span></p>
              {p.yearly_discount_pct > 0 ? <p className="text-xs text-on-surface-variant">{p.yearly_discount_pct}% off yearly</p> : null}
              <div className="mt-4 space-y-1 text-sm text-on-surface-variant">
                <p>{p.max_shops} shop{p.max_shops !== 1 ? "s" : ""} &middot; {p.max_employees} employees &middot; {p.storage_limit_mb} MB</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-4 text-xs font-bold uppercase tracking-widest text-on-surface-variant">Add-ons</h2>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {addons.map((a) => (
            <div key={a.id} className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-5 shadow-sm">
              <h3 className="font-headline text-lg font-bold text-on-surface">{a.display_name}</h3>
              <p className="mt-1 text-xs text-on-surface-variant">{a.description}</p>
              <p className="mt-3 font-headline text-lg font-extrabold text-primary">{fmt(a.price_cents, a.currency_code)}<span className="text-xs font-normal text-on-surface-variant">/mo</span></p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
