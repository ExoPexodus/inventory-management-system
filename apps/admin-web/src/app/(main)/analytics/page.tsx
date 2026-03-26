"use client";

import { useEffect, useState } from "react";
import { formatMoneyUSD } from "@/lib/format";

type Point = { day: string; gross_cents: number; transaction_count: number };

export default function AnalyticsPage() {
  const [points, setPoints] = useState<Point[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const max = Math.max(...points.map((p) => p.gross_cents), 1);

  useEffect(() => {
    void (async () => {
      const r = await fetch("/api/ims/v1/admin/analytics/sales-series?days=30");
      if (!r.ok) setErr(`HTTP ${r.status}`);
      else {
        const j = (await r.json()) as { points: Point[] };
        setPoints(j.points);
      }
    })();
  }, []);

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-wider text-primary/50">Analytics & insights</p>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-primary">Sales trend</h1>
        <p className="mt-1 text-sm text-primary/70">Posted transactions, last 30 days · all tenants</p>
      </header>
      {err ? <p className="text-sm text-red-700">{err}</p> : null}
      <div className="rounded-xl border border-primary/10 bg-white/90 p-6 shadow-sm">
        <div className="flex h-56 items-end gap-1">
          {points.length === 0 ? (
            <p className="w-full text-center text-sm text-primary/60">No data yet.</p>
          ) : (
            points.map((p) => (
              <div key={p.day} className="flex flex-1 flex-col items-center justify-end gap-1">
                <div
                  className="w-full max-w-[20px] rounded-t bg-primary/70"
                  style={{ height: `${(p.gross_cents / max) * 100}%`, minHeight: p.gross_cents ? 4 : 0 }}
                  title={`${p.day}: ${formatMoneyUSD(p.gross_cents)} (${p.transaction_count} tx)`}
                />
                <span className="origin-bottom rotate-45 text-[10px] text-primary/50">{p.day.slice(5)}</span>
              </div>
            ))
          )}
        </div>
      </div>
      <div className="overflow-x-auto rounded-xl border border-primary/10 bg-white/90 shadow-sm">
        <table className="min-w-full text-left text-sm">
          <thead>
            <tr className="border-b border-primary/10 text-xs uppercase tracking-wide text-primary/50">
              <th className="px-4 py-3">Day</th>
              <th className="px-4 py-3 text-right">Gross</th>
              <th className="px-4 py-3 text-right">Txns</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-primary/5">
            {points.map((p) => (
              <tr key={p.day}>
                <td className="px-4 py-3 font-mono text-xs">{p.day}</td>
                <td className="px-4 py-3 text-right tabular-nums">{formatMoneyUSD(p.gross_cents)}</td>
                <td className="px-4 py-3 text-right tabular-nums">{p.transaction_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
