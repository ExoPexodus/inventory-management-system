"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Badge,
  EmptyState,
  LoadingRow,
  PageHeader,
  Panel,
  PrimaryButton,
  SecondaryButton,
  SelectInput,
  TextInput,
} from "@/components/ui/primitives";
import { DateInput } from "@/components/ui/DateInput";
import { formatMoney } from "@/lib/format";
import { useCurrency } from "@/lib/currency-context";

type Shift = {
  id: string;
  shop_id: string;
  shop_name: string | null;
  opened_at: string;
  closed_at: string | null;
  status: "open" | "closed";
  expected_cash_cents: number;
  reported_cash_cents: number;
  discrepancy_cents: number;
  notes: string | null;
  transaction_count: number;
  gross_cents: number;
};

type ShiftPage = { items: Shift[] };

type Shop = { id: string; name: string };

function fmtDatetime(iso: string) {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function fmtDuration(openedAt: string, closedAt: string | null) {
  const start = new Date(openedAt).getTime();
  const end = closedAt ? new Date(closedAt).getTime() : Date.now();
  const ms = Math.max(0, end - start);
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

export default function ShiftsPage() {
  const currency = useCurrency();
  const [rows, setRows] = useState<Shift[]>([]);
  const [shops, setShops] = useState<Shop[]>([]);
  const [loading, setLoading] = useState(true);

  // Filters
  const [shopFilter, setShopFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");

  // Open shift dialog
  const [openDialogVisible, setOpenDialogVisible] = useState(false);
  const [openShopId, setOpenShopId] = useState("");
  const [openNotes, setOpenNotes] = useState("");
  const [openSaving, setOpenSaving] = useState(false);
  const [openErr, setOpenErr] = useState<string | null>(null);

  // Close shift dialog
  const [closeShift, setCloseShift] = useState<Shift | null>(null);
  const [cashCountStr, setCashCountStr] = useState("");
  const [closeNotes, setCloseNotes] = useState("");
  const [closeSaving, setCloseSaving] = useState(false);
  const [closeErr, setCloseErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const sp = new URLSearchParams();
    if (shopFilter) sp.set("shop_id", shopFilter);
    if (statusFilter) sp.set("status", statusFilter);
    if (fromDate) sp.set("from_date", fromDate);
    if (toDate) sp.set("to_date", toDate);
    try {
      const r = await fetch(`/api/ims/v1/admin/shifts?${sp.toString()}`);
      if (r.ok) setRows(((await r.json()) as ShiftPage).items ?? []);
      else setRows([]);
    } finally {
      setLoading(false);
    }
  }, [shopFilter, statusFilter, fromDate, toDate]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    fetch("/api/ims/v1/admin/shops")
      .then((r) => (r.ok ? r.json() : []))
      .then((d: Shop[]) => setShops(Array.isArray(d) ? d : []))
      .catch(() => setShops([]));
  }, []);

  // Stats
  const openNow = rows.filter((s) => s.status === "open").length;
  const startOfDay = new Date();
  startOfDay.setHours(0, 0, 0, 0);
  const closedToday = rows.filter(
    (s) =>
      s.status === "closed" &&
      s.closed_at &&
      new Date(s.closed_at).getTime() >= startOfDay.getTime()
  ).length;
  const grossToday = rows
    .filter(
      (s) =>
        s.status === "closed" &&
        s.closed_at &&
        new Date(s.closed_at).getTime() >= startOfDay.getTime()
    )
    .reduce((acc, s) => acc + s.gross_cents, 0);

  async function handleOpenShift(e: React.FormEvent) {
    e.preventDefault();
    if (!openShopId) { setOpenErr("Select a shop"); return; }
    setOpenSaving(true);
    setOpenErr(null);
    const r = await fetch("/api/ims/v1/admin/shifts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ shop_id: openShopId, notes: openNotes || null }),
    });
    if (r.ok) {
      setOpenDialogVisible(false);
      setOpenShopId("");
      setOpenNotes("");
      void load();
    } else {
      const body = await r.json().catch(() => ({})) as { detail?: string };
      setOpenErr(body.detail ?? `Failed (${r.status})`);
    }
    setOpenSaving(false);
  }

  function beginClose(shift: Shift) {
    setCloseShift(shift);
    setCashCountStr("");
    setCloseNotes("");
    setCloseErr(null);
  }

  async function handleCloseShift(e: React.FormEvent) {
    e.preventDefault();
    if (!closeShift) return;
    const dollars = parseFloat(cashCountStr);
    if (isNaN(dollars) || dollars < 0) { setCloseErr("Enter a valid cash amount"); return; }
    const cents = Math.round(dollars * Math.pow(10, currency.exponent));
    setCloseSaving(true);
    setCloseErr(null);
    const r = await fetch(`/api/ims/v1/admin/shifts/${closeShift.id}/close`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reported_cash_cents: cents, notes: closeNotes || null }),
    });
    if (r.ok) {
      setCloseShift(null);
      void load();
    } else {
      const body = await r.json().catch(() => ({})) as { detail?: string };
      setCloseErr(body.detail ?? `Failed (${r.status})`);
    }
    setCloseSaving(false);
  }

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="Operations"
        title="Shifts"
        subtitle="Track register sessions, staff coverage, and shift-level sales."
        action={
          <PrimaryButton type="button" onClick={() => { setOpenErr(null); setOpenDialogVisible(true); }}>
            <span className="material-symbols-outlined text-lg">schedule</span>
            Open shift
          </PrimaryButton>
        }
      />

      {/* Stat tiles */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Open now</p>
          <p className="mt-3 font-headline text-3xl font-extrabold text-primary">{openNow}</p>
        </div>
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Closed today</p>
          <p className="mt-3 font-headline text-3xl font-extrabold text-primary">{closedToday}</p>
        </div>
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Gross today</p>
          <p className="mt-3 font-headline text-3xl font-extrabold text-primary">{formatMoney(grossToday, currency)}</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-outline-variant/10 bg-surface-container-low p-4 shadow-sm">
        <SelectInput
          className="min-w-[12rem]"
          value={shopFilter}
          onChange={setShopFilter}
          placeholder="All shops"
          options={[
            { value: "", label: "All shops" },
            ...shops.map((s) => ({ value: s.id, label: s.name })),
          ]}
        />
        <SelectInput
          className="min-w-[10rem]"
          value={statusFilter}
          onChange={setStatusFilter}
          placeholder="All statuses"
          options={[
            { value: "", label: "All statuses" },
            { value: "open", label: "Open" },
            { value: "closed", label: "Closed" },
          ]}
        />
        <DateInput className="min-w-[10rem]" value={fromDate} onChange={setFromDate} placeholder="From date" />
        <DateInput className="min-w-[10rem]" value={toDate} onChange={setToDate} placeholder="To date" />
        {(shopFilter || statusFilter || fromDate || toDate) && (
          <SecondaryButton type="button" onClick={() => { setShopFilter(""); setStatusFilter(""); setFromDate(""); setToDate(""); }}>
            Clear
          </SecondaryButton>
        )}
      </div>

      {/* Table */}
      <Panel title="Shift log" subtitle={`${rows.length} shifts`} noPad>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-outline-variant/10">
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Shop</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Opened</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Closed</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Duration</th>
                <th className="px-6 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Transactions</th>
                <th className="px-6 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Gross</th>
                <th className="px-6 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Expected</th>
                <th className="px-6 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Counted</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Status</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {loading ? (
                <LoadingRow colSpan={10} label="Loading shifts…" />
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={10} className="p-0">
                    <EmptyState title="No shifts found" detail="Open a new shift to start tracking register sessions." />
                  </td>
                </tr>
              ) : (
                rows.map((s) => (
                  <tr key={s.id} className="group transition-colors hover:bg-surface-container-low/50">
                    <td className="px-6 py-4 font-medium text-on-surface">{s.shop_name ?? "—"}</td>
                    <td className="px-6 py-4 text-on-surface-variant">{fmtDatetime(s.opened_at)}</td>
                    <td className="px-6 py-4 text-on-surface-variant">{s.closed_at ? fmtDatetime(s.closed_at) : "—"}</td>
                    <td className="px-6 py-4 text-on-surface">{fmtDuration(s.opened_at, s.closed_at)}</td>
                    <td className="px-6 py-4 text-right tabular-nums text-on-surface">{s.transaction_count}</td>
                    <td className="px-6 py-4 text-right tabular-nums font-semibold text-on-surface">{formatMoney(s.gross_cents, currency)}</td>
                    <td className="px-6 py-4 text-right tabular-nums text-on-surface-variant">
                      {s.status === "closed" ? formatMoney(s.expected_cash_cents, currency) : "—"}
                    </td>
                    <td className="px-6 py-4 text-right tabular-nums text-on-surface-variant">
                      {s.status === "closed" ? formatMoney(s.reported_cash_cents, currency) : "—"}
                    </td>
                    <td className="px-6 py-4">
                      {s.status === "open" ? (
                        <Badge tone="good">open</Badge>
                      ) : s.discrepancy_cents !== 0 ? (
                        <Badge tone="warn">variance</Badge>
                      ) : (
                        <Badge tone="default">closed</Badge>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      {s.status === "open" && (
                        <button
                          type="button"
                          onClick={() => beginClose(s)}
                          className="inline-flex items-center gap-1 rounded-lg border border-outline-variant/30 bg-surface-container px-3 py-1.5 text-xs font-semibold text-on-surface transition hover:bg-surface-container-high"
                        >
                          <span className="material-symbols-outlined text-sm">lock</span>
                          Close
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      {/* Open shift dialog */}
      {openDialogVisible && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4" onClick={() => setOpenDialogVisible(false)}>
          <div className="w-full max-w-md rounded-2xl bg-surface shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="ink-gradient rounded-t-2xl px-6 py-5">
              <p className="text-xs font-bold uppercase tracking-widest text-on-primary/80">Start a new session</p>
              <p className="mt-1 font-headline text-xl font-extrabold text-on-primary">Open shift</p>
            </div>
            <form onSubmit={(e) => void handleOpenShift(e)} className="space-y-4 p-6">
              <div>
                <label className="block text-sm font-medium text-on-surface">
                  Shop
                  <SelectInput
                    className="mt-1"
                    value={openShopId}
                    onChange={setOpenShopId}
                    placeholder="Select shop…"
                    options={shops.map((s) => ({ value: s.id, label: s.name }))}
                  />
                </label>
              </div>
              <div>
                <label className="block text-sm font-medium text-on-surface">
                  Notes (optional)
                  <TextInput className="mt-1" value={openNotes} onChange={(e) => setOpenNotes(e.target.value)} placeholder="Opening notes…" />
                </label>
              </div>
              {openErr && <p className="text-sm text-error">{openErr}</p>}
              <div className="flex gap-2 pt-2">
                <PrimaryButton type="submit" disabled={openSaving}>{openSaving ? "Opening…" : "Open shift"}</PrimaryButton>
                <SecondaryButton type="button" onClick={() => setOpenDialogVisible(false)}>Cancel</SecondaryButton>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Close shift dialog */}
      {closeShift && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4" onClick={() => setCloseShift(null)}>
          <div className="w-full max-w-md rounded-2xl bg-surface shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="ink-gradient rounded-t-2xl px-6 py-5">
              <p className="text-xs font-bold uppercase tracking-widest text-on-primary/80">End-of-day</p>
              <p className="mt-1 font-headline text-xl font-extrabold text-on-primary">Close shift</p>
              <p className="mt-0.5 text-sm text-on-primary/70">{closeShift.shop_name ?? "Unknown shop"} — opened {fmtDatetime(closeShift.opened_at)}</p>
            </div>
            <form onSubmit={(e) => void handleCloseShift(e)} className="space-y-4 p-6">
              <div className="rounded-lg bg-surface-container-low p-4">
                <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Shift summary</p>
                <div className="mt-2 grid grid-cols-2 gap-2 text-sm">
                  <span className="text-on-surface-variant">Transactions</span>
                  <span className="text-right font-semibold text-on-surface">{closeShift.transaction_count}</span>
                  <span className="text-on-surface-variant">Gross sales</span>
                  <span className="text-right font-semibold text-on-surface">{formatMoney(closeShift.gross_cents, currency)}</span>
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-on-surface">
                  Cash counted ({currency.code})
                  <TextInput
                    type="number"
                    min="0"
                    step="0.01"
                    required
                    className="mt-1"
                    value={cashCountStr}
                    onChange={(e) => setCashCountStr(e.target.value)}
                    placeholder="e.g. 47.50"
                  />
                </label>
              </div>
              <div>
                <label className="block text-sm font-medium text-on-surface">
                  Closing notes (optional)
                  <TextInput className="mt-1" value={closeNotes} onChange={(e) => setCloseNotes(e.target.value)} placeholder="Any discrepancy explanation…" />
                </label>
              </div>
              {closeErr && <p className="text-sm text-error">{closeErr}</p>}
              <div className="flex gap-2 pt-2">
                <PrimaryButton type="submit" disabled={closeSaving}>{closeSaving ? "Closing…" : "Close shift"}</PrimaryButton>
                <SecondaryButton type="button" onClick={() => setCloseShift(null)}>Cancel</SecondaryButton>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
