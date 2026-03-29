"use client";

import { useEffect, useState } from "react";
import { EmptyState, ErrorState, PageHeader, Panel } from "@/components/ui/primitives";
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
    <div className="space-y-7">
      <PageHeader
        kicker="Analytics & insights"
        title="Sales trend"
        subtitle="Posted transactions, last 30 days."
      />
      {err ? <ErrorState detail={err} /> : null}
      <Panel title="Gross sales chart" subtitle="Daily bars, relative scale">
        <div className="flex h-56 items-end gap-1">
          {points.length === 0 ? (
            <EmptyState title="No data yet" detail="Seed demo transactions to populate analytics." />
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
      </Panel>
      <Panel title="Daily breakdown">
        <div className="overflow-x-auto">
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
      </Panel>
    </div>
  );
}
