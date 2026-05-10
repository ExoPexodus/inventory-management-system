"use client";

import { useEffect, useState, FormEvent } from "react";

type Plan = { id: string; codename: string; display_name: string };
type CatalogEntry = { key: string; value_type: string; description: string; default: unknown };
type BulkResult = { count: number; affected_tenant_ids: string[] };

export default function BulkOverridesPage() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [catalog, setCatalog] = useState<CatalogEntry[]>([]);
  const [loading, setLoading] = useState(true);

  // Filter state
  const [planCodename, setPlanCodename] = useState("");
  const [region, setRegion] = useState("");

  // Override state
  const [featureKey, setFeatureKey] = useState("");
  const [featureValue, setFeatureValue] = useState<string>("");
  const [reason, setReason] = useState("");

  // Result state
  const [result, setResult] = useState<BulkResult | null>(null);
  const [applying, setApplying] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      const [pRes, cRes] = await Promise.all([
        fetch("/api/platform/v1/platform/plans"),
        fetch("/api/ims/v1/internal/platform/plan-features"),
      ]);
      if (pRes.ok) setPlans(await pRes.json());
      if (cRes.ok) {
        const cat = (await cRes.json()) as CatalogEntry[];
        setCatalog(cat);
        if (cat.length > 0) setFeatureKey(cat[0]?.key ?? "");
      }
      setLoading(false);
    })();
  }, []);

  const selectedDef = catalog.find((c) => c.key === featureKey);

  async function apply(e: FormEvent) {
    e.preventDefault();
    if (!featureKey) return;
    setApplying(true);
    setErr(null);
    setResult(null);

    let parsedValue: unknown = featureValue;
    if (selectedDef?.value_type === "bool") {
      parsedValue = featureValue === "true";
    } else if (selectedDef?.value_type === "numeric") {
      parsedValue = parseInt(featureValue) || 0;
    }

    const filter: Record<string, string | undefined> = {};
    if (planCodename) filter["plan_codename"] = planCodename;
    if (region) filter["region"] = region;

    try {
      const r = await fetch("/api/platform/v1/platform/overrides/bulk", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filter,
          feature_key: featureKey,
          value: parsedValue,
          reason: reason || null,
        }),
      });
      if (r.ok) {
        setResult(await r.json());
      } else {
        const d = await r.json().catch(() => ({})) as { detail?: string };
        setErr(d.detail ?? `Failed (${r.status})`);
      }
    } catch {
      setErr("Network error.");
    } finally {
      setApplying(false);
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center py-16">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-2xl">
      {/* Header */}
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Overrides</p>
        <h1 className="mt-1 font-headline text-3xl font-extrabold text-on-surface">Bulk Feature Override</h1>
        <p className="mt-1 text-sm text-on-surface-variant">
          Apply a feature override to all tenants matching a cohort filter. This sets per-tenant overrides
          that take precedence over plan-level values.
        </p>
      </div>

      <form onSubmit={apply} className="space-y-6">
        {/* Cohort filter */}
        <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm space-y-4">
          <h2 className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Cohort filter</h2>
          <p className="text-xs text-on-surface-variant">Leave blank to match all active subscribers.</p>

          <div className="grid grid-cols-2 gap-4">
            <label className="block">
              <span className="text-sm font-medium text-on-surface">Plan</span>
              <select
                value={planCodename}
                onChange={(e) => setPlanCodename(e.target.value)}
                className="mt-1 block w-full rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-2 text-sm text-on-surface outline-none focus:border-primary"
              >
                <option value="">Any plan</option>
                {plans.map((p) => (
                  <option key={p.codename} value={p.codename}>{p.display_name} ({p.codename})</option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="text-sm font-medium text-on-surface">Region</span>
              <input
                type="text"
                value={region}
                onChange={(e) => setRegion(e.target.value)}
                placeholder="e.g. in, us, eu"
                className="mt-1 block w-full rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-2 text-sm text-on-surface outline-none focus:border-primary"
              />
            </label>
          </div>
        </section>

        {/* Override settings */}
        <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm space-y-4">
          <h2 className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Override</h2>

          <label className="block">
            <span className="text-sm font-medium text-on-surface">Feature key</span>
            <select
              value={featureKey}
              onChange={(e) => { setFeatureKey(e.target.value); setFeatureValue(""); }}
              className="mt-1 block w-full rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-2 text-sm text-on-surface outline-none focus:border-primary"
            >
              {catalog.map((c) => (
                <option key={c.key} value={c.key}>{c.key} — {c.description}</option>
              ))}
            </select>
          </label>

          {selectedDef && (
            <label className="block">
              <span className="text-sm font-medium text-on-surface">
                Value
                <span className="ml-1 text-xs text-on-surface-variant">
                  ({selectedDef.value_type}, default: {String(selectedDef.default)})
                </span>
              </span>
              {selectedDef.value_type === "bool" ? (
                <select
                  value={featureValue}
                  onChange={(e) => setFeatureValue(e.target.value)}
                  className="mt-1 block w-full rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-2 text-sm text-on-surface outline-none focus:border-primary"
                >
                  <option value="true">true (enabled)</option>
                  <option value="false">false (disabled)</option>
                </select>
              ) : (
                <input
                  type="number"
                  value={featureValue}
                  onChange={(e) => setFeatureValue(e.target.value)}
                  className="mt-1 block w-full rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-2 text-sm text-on-surface outline-none focus:border-primary"
                  placeholder="Enter numeric value"
                />
              )}
            </label>
          )}

          <label className="block">
            <span className="text-sm font-medium text-on-surface">Reason (optional)</span>
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. promotional campaign Q3"
              className="mt-1 block w-full rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-2 text-sm text-on-surface outline-none focus:border-primary"
            />
          </label>
        </section>

        {err && (
          <div className="rounded-lg border border-error/20 bg-error-container/10 p-4 text-sm text-error">
            {err}
          </div>
        )}

        {result && (
          <div className="rounded-lg border border-tertiary/20 bg-tertiary-fixed/10 p-4 text-sm text-on-surface">
            <p className="font-semibold text-tertiary">Override applied to {result.count} tenant{result.count !== 1 ? "s" : ""}.</p>
            {result.affected_tenant_ids.length > 0 && (
              <details className="mt-2">
                <summary className="cursor-pointer text-xs text-on-surface-variant">Show tenant IDs</summary>
                <ul className="mt-1 space-y-0.5">
                  {result.affected_tenant_ids.map((id) => (
                    <li key={id} className="font-mono text-xs text-on-surface-variant">{id}</li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        )}

        <button
          type="submit"
          disabled={applying || !featureKey}
          className="ink-gradient rounded-lg px-6 py-3 text-sm font-semibold text-on-primary disabled:opacity-50"
        >
          {applying ? "Applying…" : "Apply override"}
        </button>
      </form>
    </div>
  );
}
