"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/primitives";
import { formatMoneyUSD } from "@/lib/format";

type RecRow = {
  id: string;
  period: string;
  expected_cents: number;
  actual_cents: number;
  variance_cents: number;
  status: string;
};

type Page = { items: RecRow[] };

export default function ReconciliationPage() {
  const [rows, setRows] = useState<RecRow[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/ims/v1/admin/reconciliation");
      if (!r.ok) return;
      const data = (await r.json()) as Page;
      setRows(Array.isArray(data.items) ? data.items : []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const stats = useMemo(() => {
    const totalVariance = rows.reduce((acc, r) => acc + r.variance_cents, 0);
    const matched = rows.filter(
      (r) => r.status.toLowerCase() === "matched" || r.variance_cents === 0
    ).length;
    return { totalVariance, matched, periods: rows.length };
  }, [rows]);

  const varianceTone = stats.totalVariance !== 0;

  return (
    <div className="space-y-8">
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Finance</p>
        <h2 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">Reconciliation</h2>
      </div>

      <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Total periods</p>
          <h3 className="mt-3 font-headline text-3xl font-extrabold text-primary">{stats.periods}</h3>
        </div>
        <div
          className={`rounded-xl border p-6 shadow-sm ${
            varianceTone ? "border-error/20 bg-error-container/30" : "border-outline-variant/10 bg-surface-container-lowest"
          }`}
        >
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Total variance</p>
          <h3
            className={`mt-3 font-headline text-3xl font-extrabold ${varianceTone ? "text-error" : "text-primary"}`}
          >
            {formatMoneyUSD(stats.totalVariance)}
          </h3>
        </div>
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Matched count</p>
          <h3 className="mt-3 font-headline text-3xl font-extrabold text-primary">{stats.matched}</h3>
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm">
        <div className="border-b border-outline-variant/10 px-6 py-4">
          <h3 className="font-headline text-lg font-bold text-primary">Periods</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead>
              <tr className="border-b border-outline-variant/10">
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Period</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Expected</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Actual</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Variance</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {loading ? (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-on-surface-variant">
                    Loading…
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-on-surface-variant">
                    No reconciliation rows.
                  </td>
                </tr>
              ) : (
                rows.map((r) => {
                  const varBad = r.variance_cents !== 0;
                  return (
                    <tr key={r.id} className="transition-colors hover:bg-surface-container-low/50">
                      <td className="px-6 py-4 font-mono text-xs text-on-surface">{r.period}</td>
                      <td className="px-6 py-4 text-on-surface">{formatMoneyUSD(r.expected_cents)}</td>
                      <td className="px-6 py-4 text-on-surface">{formatMoneyUSD(r.actual_cents)}</td>
                      <td className={`px-6 py-4 font-semibold ${varBad ? "text-error" : "text-on-surface"}`}>
                        {formatMoneyUSD(r.variance_cents)}
                      </td>
                      <td className="px-6 py-4">
                        <Badge
                          tone={
                            r.status.toLowerCase() === "matched" && !varBad
                              ? "good"
                              : varBad
                                ? "danger"
                                : "default"
                          }
                        >
                          {r.status}
                        </Badge>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
