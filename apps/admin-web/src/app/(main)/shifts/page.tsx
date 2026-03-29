"use client";

import { useCallback, useEffect, useState } from "react";
import { Badge, PrimaryButton } from "@/components/ui/primitives";

type Shift = {
  id: string;
  staff_name?: string | null;
  shop_name?: string | null;
  started_at: string;
  ended_at?: string | null;
  status: "open" | "closed";
  transaction_count?: number | null;
  gross_cents?: number | null;
};

type Page = { items: Shift[] };

function formatDuration(startedAt: string, endedAt?: string | null): string {
  const start = new Date(startedAt).getTime();
  const end = endedAt ? new Date(endedAt).getTime() : Date.now();
  const ms = Math.max(0, end - start);
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

export default function ShiftsPage() {
  const [rows, setRows] = useState<Shift[]>([]);
  const [loading, setLoading] = useState(true);
  const [opening, setOpening] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/ims/v1/admin/shifts");
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

  const now = Date.now();
  const startOfDay = new Date();
  startOfDay.setHours(0, 0, 0, 0);
  const openNow = rows.filter((s) => s.status === "open").length;
  const closedToday = rows.filter(
    (s) => s.status === "closed" && s.ended_at && new Date(s.ended_at).getTime() >= startOfDay.getTime()
  ).length;

  const openShift = async () => {
    setOpening(true);
    try {
      const r = await fetch("/api/ims/v1/admin/shifts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "open" }),
      });
      if (r.ok) await load();
    } finally {
      setOpening(false);
    }
  };

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Operations</p>
          <h2 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">Shifts</h2>
          <p className="mt-2 font-light text-on-surface-variant">Track register sessions, staff coverage, and shift-level sales.</p>
        </div>
        <PrimaryButton type="button" disabled={opening} onClick={() => void openShift()}>
          <span className="material-symbols-outlined text-lg">schedule</span>
          Open shift
        </PrimaryButton>
      </div>

      <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Open now</p>
          <h3 className="mt-3 font-headline text-3xl font-extrabold text-primary">{openNow}</h3>
        </div>
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Closed today</p>
          <h3 className="mt-3 font-headline text-3xl font-extrabold text-primary">{closedToday}</h3>
        </div>
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Total shifts</p>
          <h3 className="mt-3 font-headline text-3xl font-extrabold text-primary">{rows.length}</h3>
        </div>
      </div>

      <div className="overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm">
        <div className="border-b border-outline-variant/10 px-6 py-4">
          <h3 className="font-headline text-lg font-bold text-primary">Shift log</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead>
              <tr className="border-b border-outline-variant/10">
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Staff</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Shop</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Started</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Duration</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {loading ? (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-on-surface-variant">
                    Loading shifts…
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-8 text-center text-on-surface-variant">
                    No shifts found.
                  </td>
                </tr>
              ) : (
                rows.map((s) => (
                  <tr key={s.id} className="transition-colors hover:bg-surface-container-low/50">
                    <td className="px-6 py-4 font-medium text-on-surface">{s.staff_name ?? "—"}</td>
                    <td className="px-6 py-4 text-on-surface-variant">{s.shop_name ?? "—"}</td>
                    <td className="px-6 py-4 text-on-surface-variant">{new Date(s.started_at).toLocaleString()}</td>
                    <td className="px-6 py-4 text-on-surface">{formatDuration(s.started_at, s.ended_at)}</td>
                    <td className="px-6 py-4">
                      <Badge tone={s.status === "open" ? "good" : "default"}>{s.status}</Badge>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
