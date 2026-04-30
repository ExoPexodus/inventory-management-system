"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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
import { formatMoney, fmtDatetime } from "@/lib/format";
import { useCurrency } from "@/lib/currency-context";
import { useTenantTimezone } from "@/lib/localisation-context";

type RecRow = {
  id: string;
  period: string;
  shop_id: string;
  shop_name: string | null;
  expected_cents: number;
  actual_cents: number;
  variance_cents: number;
  rec_status: string;
  auto_resolved: boolean;
  opened_at: string;
  closed_at: string | null;
  resolution_note: string | null;
  reviewed_by: string | null;
};

type RecPage = { items: RecRow[] };
type Shop = { id: string; name: string };

function recTone(status: string): "default" | "good" | "warn" | "danger" {
  if (status === "matched") return "good";
  if (status === "resolved") return "good";
  if (status === "variance") return "danger";
  if (status === "pending_review") return "warn";
  return "default";
}

export default function ReconciliationPage() {
  const currency = useCurrency();
  const timezone = useTenantTimezone();
  const [rows, setRows] = useState<RecRow[]>([]);
  const [shops, setShops] = useState<Shop[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);

  // Filters
  const [shopFilter, setShopFilter] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");

  // Resolve dialog
  const [resolveRow, setResolveRow] = useState<RecRow | null>(null);
  const [resolutionNotes, setResolutionNotes] = useState("");
  const [resolveSaving, setResolveSaving] = useState(false);
  const [resolveErr, setResolveErr] = useState<string | null>(null);

  // Approve
  const [approveSaving, setApproveSaving] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const sp = new URLSearchParams();
    if (shopFilter) sp.set("shop_id", shopFilter);
    if (fromDate) sp.set("from_date", fromDate);
    if (toDate) sp.set("to_date", toDate);
    try {
      const r = await fetch(`/api/ims/v1/admin/reconciliation?${sp.toString()}`);
      if (r.ok) setRows(((await r.json()) as RecPage).items ?? []);
      else setRows([]);
    } finally {
      setLoading(false);
    }
  }, [shopFilter, fromDate, toDate]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    fetch("/api/ims/v1/admin/shops")
      .then((r) => (r.ok ? r.json() : { items: [] }))
      .then((d) => setShops(Array.isArray(d.items) ? (d.items as Shop[]) : []))
      .catch(() => setShops([]));
  }, []);

  const stats = useMemo(() => {
    const totalVariance = rows.reduce((acc, r) => acc + r.variance_cents, 0);
    const matched = rows.filter((r) => r.rec_status === "matched" || r.rec_status === "resolved").length;
    const unresolved = rows.filter((r) => r.rec_status === "variance").length;
    return { totalVariance, matched, unresolved, periods: rows.length };
  }, [rows]);

  async function handleApprove(id: string) {
    setApproveSaving(id);
    await fetch(`/api/ims/v1/admin/reconciliation/${id}/approve`, { method: "PATCH" });
    setApproveSaving(null);
    void load();
  }

  async function handleResolve(e: React.FormEvent) {
    e.preventDefault();
    if (!resolveRow) return;
    if (!resolutionNotes.trim()) { setResolveErr("Enter a resolution note"); return; }
    setResolveSaving(true);
    setResolveErr(null);
    const r = await fetch(`/api/ims/v1/admin/reconciliation/${resolveRow.id}/resolve`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resolution_notes: resolutionNotes.trim() }),
    });
    if (r.ok) {
      setResolveRow(null);
      void load();
    } else {
      const body = await r.json().catch(() => ({})) as { detail?: string };
      setResolveErr(body.detail ?? `Failed (${r.status})`);
    }
    setResolveSaving(false);
  }

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="Finance"
        title="Reconciliation"
        subtitle="Compare expected vs. counted cash per shift. Resolve variances with notes."
      />

      {/* Stats */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-4">
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Periods</p>
          <p className="mt-3 font-headline text-3xl font-extrabold text-primary">{stats.periods}</p>
        </div>
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Matched</p>
          <p className="mt-3 font-headline text-3xl font-extrabold text-tertiary">{stats.matched}</p>
        </div>
        <div className="rounded-xl border border-error/20 bg-error-container/20 p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Unresolved</p>
          <p className="mt-3 font-headline text-3xl font-extrabold text-error">{stats.unresolved}</p>
        </div>
        <div
          className={`rounded-xl border p-6 shadow-sm ${
            stats.totalVariance !== 0
              ? "border-error/20 bg-error-container/20"
              : "border-outline-variant/10 bg-surface-container-lowest"
          }`}
        >
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Total variance</p>
          <p className={`mt-3 font-headline text-3xl font-extrabold ${stats.totalVariance !== 0 ? "text-error" : "text-primary"}`}>
            {formatMoney(stats.totalVariance, currency)}
          </p>
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
        <DateInput className="min-w-[10rem]" value={fromDate} onChange={setFromDate} placeholder="From date" />
        <DateInput className="min-w-[10rem]" value={toDate} onChange={setToDate} placeholder="To date" />
        {(shopFilter || fromDate || toDate) && (
          <SecondaryButton type="button" onClick={() => { setShopFilter(""); setFromDate(""); setToDate(""); }}>
            Clear
          </SecondaryButton>
        )}
      </div>

      {/* Table */}
      <Panel title="Periods" subtitle={`${rows.length} closed shifts`} noPad>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-outline-variant/10">
                <th className="w-8 px-4 py-3" />
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Period</th>
                <th className="px-6 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Expected</th>
                <th className="px-6 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Counted</th>
                <th className="px-6 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Variance</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Status</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {loading ? (
                <LoadingRow colSpan={7} label="Loading reconciliation…" />
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={7} className="p-0">
                    <EmptyState title="No closed shifts yet" detail="Close a shift from the Shifts page to see reconciliation data." />
                  </td>
                </tr>
              ) : (
                rows.map((r) => {
                  const isExpanded = expanded === r.id;
                  const hasVariance = r.variance_cents !== 0;
                  return (
                    <>
                      <tr
                        key={r.id}
                        className={`group cursor-pointer transition-colors hover:bg-surface-container-low/50 ${isExpanded ? "bg-surface-container-low/30" : ""}`}
                        onClick={() => setExpanded(isExpanded ? null : r.id)}
                      >
                        <td className="px-4 py-4">
                          <span className="material-symbols-outlined text-base text-on-surface-variant transition-transform"
                            style={{ display: "inline-block", transform: isExpanded ? "rotate(90deg)" : "rotate(0deg)" }}>
                            chevron_right
                          </span>
                        </td>
                        <td className="px-6 py-4 font-medium text-on-surface">{r.period}</td>
                        <td className="px-6 py-4 text-right tabular-nums text-on-surface">{formatMoney(r.expected_cents, currency)}</td>
                        <td className="px-6 py-4 text-right tabular-nums text-on-surface">{formatMoney(r.actual_cents, currency)}</td>
                        <td className={`px-6 py-4 text-right tabular-nums font-semibold ${hasVariance ? "text-error" : "text-on-surface"}`}>
                          {r.variance_cents >= 0 ? "+" : ""}{formatMoney(r.variance_cents, currency)}
                        </td>
                        <td className="px-6 py-4">
                          <div className="flex items-center gap-1.5">
                            <Badge tone={recTone(r.rec_status)}>{r.rec_status}</Badge>
                            {r.auto_resolved && (
                              <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600" title="Automatically resolved by the system">
                                Auto
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-6 py-4" onClick={(e) => e.stopPropagation()}>
                          <div className="flex gap-2">
                            {r.rec_status === "variance" && (
                              <button
                                type="button"
                                onClick={() => { setResolveRow(r); setResolutionNotes(""); setResolveErr(null); }}
                                className="inline-flex items-center gap-1 rounded-lg border border-outline-variant/30 bg-surface-container px-3 py-1.5 text-xs font-semibold text-on-surface transition hover:bg-surface-container-high"
                              >
                                <span className="material-symbols-outlined text-sm">check_circle</span>
                                Resolve
                              </button>
                            )}
                            {r.rec_status === "pending_review" && (
                              <button
                                type="button"
                                disabled={approveSaving === r.id}
                                onClick={() => void handleApprove(r.id)}
                                className="inline-flex items-center gap-1 rounded-lg border border-tertiary/30 bg-tertiary-fixed/10 px-3 py-1.5 text-xs font-semibold text-tertiary transition hover:bg-tertiary-fixed/20 disabled:opacity-50"
                              >
                                <span className="material-symbols-outlined text-sm">thumb_up</span>
                                {approveSaving === r.id ? "Approving…" : "Approve"}
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr key={`${r.id}-detail`} className="bg-surface-container-low/20">
                          <td />
                          <td colSpan={6} className="px-6 py-4">
                            <div className="rounded-lg border border-outline-variant/10 bg-surface-container-lowest p-4">
                              <div className="grid grid-cols-2 gap-x-8 gap-y-1 text-sm sm:grid-cols-4">
                                <span className="text-on-surface-variant">Opened</span>
                                <span className="font-medium text-on-surface">{fmtDatetime(r.opened_at, timezone)}</span>
                                <span className="text-on-surface-variant">Closed</span>
                                <span className="font-medium text-on-surface">{r.closed_at ? fmtDatetime(r.closed_at, timezone) : "—"}</span>
                                <span className="text-on-surface-variant">Shop</span>
                                <span className="font-medium text-on-surface">{r.shop_name ?? "—"}</span>
                                <span className="text-on-surface-variant">Discrepancy</span>
                                <span className={`font-semibold ${r.variance_cents !== 0 ? "text-error" : "text-tertiary"}`}>
                                  {r.variance_cents >= 0 ? "+" : ""}{formatMoney(r.variance_cents, currency)}
                                </span>
                              </div>
                              {r.resolution_note && (
                                <div className="mt-3 rounded-lg border-l-4 border-tertiary bg-tertiary-fixed/20 px-4 py-3">
                                  <p className="text-xs font-bold uppercase tracking-widest text-tertiary">Resolution</p>
                                  <p className="mt-1 text-sm text-on-surface">{r.resolution_note}</p>
                                </div>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      {/* Resolve dialog */}
      {resolveRow && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4" onClick={() => setResolveRow(null)}>
          <div className="w-full max-w-md rounded-2xl bg-surface shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="ink-gradient rounded-t-2xl px-6 py-5">
              <p className="text-xs font-bold uppercase tracking-widest text-on-primary/80">Cash variance</p>
              <p className="mt-1 font-headline text-xl font-extrabold text-on-primary">Resolve discrepancy</p>
              <p className="mt-0.5 text-sm text-on-primary/70">{resolveRow.period}</p>
            </div>
            <form onSubmit={(e) => void handleResolve(e)} className="space-y-4 p-6">
              <div className="rounded-lg bg-surface-container-low p-4">
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <span className="text-on-surface-variant">Expected</span>
                  <span className="text-right font-semibold">{formatMoney(resolveRow.expected_cents, currency)}</span>
                  <span className="text-on-surface-variant">Counted</span>
                  <span className="text-right font-semibold">{formatMoney(resolveRow.actual_cents, currency)}</span>
                  <span className="text-on-surface-variant font-bold">Variance</span>
                  <span className="text-right font-bold text-error">
                    {resolveRow.variance_cents >= 0 ? "+" : ""}{formatMoney(resolveRow.variance_cents, currency)}
                  </span>
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-on-surface">
                  Explain this variance *
                  <textarea
                    required
                    rows={4}
                    className="mt-1 w-full rounded-lg border border-outline-variant/20 bg-surface-container-lowest px-3 py-2 text-sm text-on-surface outline-none transition focus:border-primary"
                    value={resolutionNotes}
                    onChange={(e) => setResolutionNotes(e.target.value)}
                    placeholder="e.g. Cashier reported $5 in damaged bills that were removed from the till…"
                  />
                </label>
              </div>
              {resolveErr && <p className="text-sm text-error">{resolveErr}</p>}
              <div className="flex gap-2 pt-2">
                <PrimaryButton type="submit" disabled={resolveSaving}>{resolveSaving ? "Resolving…" : "Mark resolved"}</PrimaryButton>
                <SecondaryButton type="button" onClick={() => setResolveRow(null)}>Cancel</SecondaryButton>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
