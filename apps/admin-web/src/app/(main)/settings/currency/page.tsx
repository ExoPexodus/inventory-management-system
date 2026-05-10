"use client";

import { useEffect, useState } from "react";
import { Breadcrumbs, PageHeader } from "@/components/ui/primitives";

type CurrencySettings = {
  currency_code: string;
  currency_symbol: string;
  currency_exponent: number;
  supported_currencies: Array<{ code: string; symbol: string; name: string; exponent: number }>;
};

export default function SettingsCurrencyPage() {
  const [currencySettings, setCurrencySettings] = useState<CurrencySettings | null>(null);
  const [currencyLoading, setCurrencyLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setCurrencyLoading(true);
      try {
        const res = await fetch("/api/ims/v1/admin/tenant-settings/currency");
        if (res.ok) setCurrencySettings((await res.json()) as CurrencySettings);
      } finally {
        setCurrencyLoading(false);
      }
    }
    void load();
  }, []);

  return (
    <div className="space-y-8">
      <Breadcrumbs items={[{ label: "Settings", href: "/settings" }, { label: "Currency" }]} />
      <PageHeader kicker="Settings" title="Currency" subtitle="Your tenant's currency is managed by your platform administrator." />

      <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
        <h3 className="font-headline text-lg font-bold text-primary">Currency</h3>
        <p className="mt-1 text-sm text-on-surface-variant">
          Your tenant&rsquo;s currency is managed by your platform administrator. To request a change, contact support.
        </p>
        {currencyLoading ? (
          <p className="mt-4 text-sm text-on-surface-variant">Loading currency settings…</p>
        ) : currencySettings ? (
          <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
            <div>
              <dt className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Code</dt>
              <dd className="mt-1 text-sm font-semibold text-on-surface">{currencySettings.currency_code}</dd>
            </div>
            <div>
              <dt className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Symbol</dt>
              <dd className="mt-1 text-sm font-semibold text-on-surface">{currencySettings.currency_symbol}</dd>
            </div>
            <div>
              <dt className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Exponent</dt>
              <dd className="mt-1 text-sm font-semibold text-on-surface">{currencySettings.currency_exponent}</dd>
            </div>
          </dl>
        ) : null}
      </section>
    </div>
  );
}
