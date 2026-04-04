"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Badge,
  ErrorState,
  LoadingRow,
  PageHeader,
  Pagination,
  Panel,
  PrimaryButton,
  SecondaryButton,
  SelectInput,
  TextInput,
  Timeline,
} from "@/components/ui/primitives";
import { formatMoney } from "@/lib/format";
import { useCurrency } from "@/lib/currency-context";

type MovementRow = {
  id: string;
  shop_name: string | null;
  product_sku: string | null;
  product_name: string | null;
  quantity_delta: number;
  movement_type: string;
  created_at: string;
};

type MovementPage = { items: MovementRow[]; next_cursor: string | null };

type ShopRow = { id: string; tenant_id: string; name: string };

type StockRow = {
  product_id: string;
  sku: string;
  name: string;
  unit_price_cents: number;
  quantity: number;
  group_title?: string | null;
  variant_label?: string | null;
};

const MOV_PAGE = 12;

function qtyClass(q: number): string {
  if (q <= 5) return "font-bold text-error";
  if (q <= 10) return "font-semibold text-secondary";
  return "font-medium text-primary";
}

function stockBadge(q: number): "good" | "warn" | "danger" {
  if (q <= 5) return "danger";
  if (q <= 10) return "warn";
  return "good";
}

function movementIcon(t: string): string {
  const s = t.toLowerCase();
  if (s === "sale") return "point_of_sale";
  if (s === "adjustment") return "tune";
  if (s === "transfer") return "swap_horiz";
  return "inventory";
}

export default function InventoryPage() {
  return (
    <Suspense>
      <InventoryPageInner />
    </Suspense>
  );
}

function InventoryPageInner() {
  const currency = useCurrency();
  const searchParams = useSearchParams();
  const highlightCritical = searchParams.get("highlight") === "critical";
  const shopIdParam = searchParams.get("shopId");
  const firstCriticalRef = useRef<HTMLTableRowElement | null>(null);
  const [shops, setShops] = useState<ShopRow[]>([]);
  const [shopId, setShopId] = useState("");
  const [stockRows, setStockRows] = useState<StockRow[]>([]);
  const [stockLoading, setStockLoading] = useState(false);
  const [adjustOpen, setAdjustOpen] = useState(false);

  const [mtype, setMtype] = useState("");
  const [mPage, setMPage] = useState(1);
  const [mCache, setMCache] = useState<Record<number, MovementRow[]>>({});
  const [mNext, setMNext] = useState<Record<number, string | null>>({});
  const mNextRef = useRef(mNext);
  mNextRef.current = mNext;
  const [mLoading, setMLoading] = useState(true);
  const [mErr, setMErr] = useState<string | null>(null);
  const [recentMovements, setRecentMovements] = useState<MovementRow[]>([]);

  const fetchMovements = useCallback(
    async (targetPage: number) => {
      setMLoading(true);
      setMErr(null);
      try {
        const sp = new URLSearchParams({ limit: String(MOV_PAGE) });
        if (mtype) sp.set("movement_type", mtype);
        const cursor = targetPage <= 1 ? null : mNextRef.current[targetPage - 1] ?? null;
        if (targetPage > 1 && !cursor) {
          setMErr("Missing cursor for that page.");
          setMLoading(false);
          return;
        }
        if (cursor) sp.set("cursor", cursor);
        const r = await fetch(`/api/ims/v1/admin/inventory/movements?${sp}`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = (await r.json()) as MovementPage;
        setMCache((p) => ({ ...p, [targetPage]: data.items }));
        setMNext((p) => ({ ...p, [targetPage]: data.next_cursor }));

        // Silently prefetch next page so forward navigation is instant
        if (data.next_cursor) {
          const nextPage = targetPage + 1;
          setMCache((current) => {
            if (current[nextPage]) return current;
            const prefetchSp = new URLSearchParams({ limit: String(MOV_PAGE) });
            if (mtype) prefetchSp.set("movement_type", mtype);
            prefetchSp.set("cursor", data.next_cursor!);
            fetch(`/api/ims/v1/admin/inventory/movements?${prefetchSp}`)
              .then((res) => (res.ok ? res.json() : null))
              .then((prefetchData: MovementPage | null) => {
                if (!prefetchData) return;
                setMCache((p) => ({ ...p, [nextPage]: prefetchData.items }));
                setMNext((p) => ({ ...p, [nextPage]: prefetchData.next_cursor }));
              })
              .catch(() => { /* ignore prefetch errors */ });
            return current;
          });
        }
      } catch (e) {
        setMErr(e instanceof Error ? e.message : "Movements failed");
      } finally {
        setMLoading(false);
      }
    },
    [mtype],
  );

  useEffect(() => {
    setMPage(1);
    setMCache({});
    setMNext({});
  }, [mtype]);

  useEffect(() => {
    if (mCache[mPage]) {
      setMLoading(false);
      return;
    }
    void fetchMovements(mPage);
  }, [mPage, mCache, fetchMovements, mtype]);

  useEffect(() => {
    const sp = new URLSearchParams({ limit: "6" });
    if (mtype) sp.set("movement_type", mtype);
    fetch(`/api/ims/v1/admin/inventory/movements?${sp}`)
      .then((r) => (r.ok ? r.json() : { items: [] }))
      .then((data: MovementPage) => setRecentMovements(data.items ?? []))
      .catch(() => setRecentMovements([]));
  }, [mtype]);

  useEffect(() => {
    void (async () => {
      const r = await fetch("/api/ims/v1/admin/shops");
      if (r.ok) {
        const list = (await r.json()) as ShopRow[];
        setShops(list);
        setShopId((prev) => {
          if (prev && list.some((s) => s.id === prev)) return prev;
          if (shopIdParam && list.some((s) => s.id === shopIdParam)) return shopIdParam;
          return list[0]?.id ?? "";
        });
      }
    })();
  }, []);

  const fetchStock = useCallback(async (sid: string) => {
    if (!sid) { setStockRows([]); return; }
    setStockLoading(true);
    try {
      const r = await fetch(`/api/ims/v1/inventory/shop/${sid}/products`);
      if (r.ok) setStockRows((await r.json()) as StockRow[]);
      else setStockRows([]);
    } finally {
      setStockLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchStock(shopId);
  }, [shopId, fetchStock]);

  useEffect(() => {
    if (highlightCritical && firstCriticalRef.current) {
      firstCriticalRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [highlightCritical, stockRows]);

  const valuation = useMemo(() => {
    const totalValuation = stockRows.reduce((a, s) => a + s.quantity * s.unit_price_cents, 0);
    const critical = stockRows.filter((s) => s.quantity <= 5).length;
    return {
      totalValuation,
      critical,
      skus: stockRows.length,
    };
  }, [stockRows]);

  const movementRows = useMemo(() => mCache[mPage] ?? [], [mCache, mPage]);
  const mTotalPages = mNext[mPage] ? mPage + 1 : Math.max(mPage, 1);

  const timelineItems = useMemo(
    () =>
      recentMovements.map((r) => ({
        title: `${r.movement_type} · ${r.product_sku ?? "SKU"}`,
        detail: `${r.shop_name ?? "Shop"} · ${r.created_at}`,
        tone: r.quantity_delta < 0 ? ("warn" as const) : ("default" as const),
      })),
    [recentMovements],
  );

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="Inventory ledger"
        title="Holdings & movements"
        subtitle="Valuation is derived from on-hand × unit cost for the selected shop."
        action={
          <div className="flex flex-wrap gap-2">
            <Link
              href="/purchase-orders"
              className="inline-flex items-center gap-2 rounded-lg border border-outline-variant/40 px-6 py-2.5 text-sm font-semibold text-on-surface transition hover:bg-surface-container"
            >
              Transfer order
            </Link>
            <Link
              href="/purchase-orders"
              className="inline-flex items-center gap-2 rounded-lg border border-outline-variant/40 px-6 py-2.5 text-sm font-semibold text-on-surface transition hover:bg-surface-container"
            >
              Draft PO
            </Link>
          </div>
        }
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Total valuation</p>
          <p className="mt-4 font-headline text-3xl font-extrabold text-primary">{formatMoney(valuation.totalValuation, currency)}</p>
          <p className="mt-1 text-xs text-on-surface-variant">Shop scope: current selector</p>
        </div>
        <div className="rounded-xl border border-secondary/25 bg-secondary-container/20 p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Critical reorder</p>
          <p className="mt-4 font-headline text-3xl font-extrabold text-secondary">{valuation.critical}</p>
          <p className="mt-1 text-xs text-on-surface-variant">SKUs at ≤5 units</p>
        </div>
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Tracked SKUs</p>
          <p className="mt-4 font-headline text-3xl font-extrabold text-primary">{valuation.skus}</p>
        </div>
      </div>

      <Panel title="Holdings" subtitle="On-hand from the live inventory service" noPad>
        <div className="border-b border-outline-variant/10 px-6 py-4">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <label className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">
              Shop
              <SelectInput
                className="mt-1 min-w-[12rem]"
                value={shopId}
                onChange={setShopId}
                placeholder="Select shop"
                options={shops.map((s) => ({ value: s.id, label: s.name }))}
              />
            </label>
            <button
              type="button"
              disabled={!shopId || stockRows.length === 0}
              onClick={() => setAdjustOpen(true)}
              className="inline-flex items-center gap-2 rounded-lg border border-outline-variant/30 px-4 py-2 text-sm font-semibold text-on-surface transition hover:bg-surface-container disabled:opacity-40"
            >
              <span className="material-symbols-outlined text-base">tune</span>
              Adjust stock
            </button>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-outline-variant/10">
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">SKU</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Product</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Category</th>
                <th className="px-6 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">On hand</th>
                <th className="px-6 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Unit price</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {stockLoading ? (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-on-surface-variant">
                    Loading holdings…
                  </td>
                </tr>
              ) : stockRows.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-on-surface-variant">
                    No rows — pick a shop with catalog.
                  </td>
                </tr>
              ) : (
                stockRows.map((s, idx) => {
                  const badge = stockBadge(s.quantity);
                  const isHighlighted = highlightCritical && (badge === "danger" || badge === "warn");
                  const isFirst = isHighlighted && idx === stockRows.findIndex((r) => {
                    const b = stockBadge(r.quantity);
                    return b === "danger" || b === "warn";
                  });
                  return (
                  <tr
                    key={s.product_id}
                    ref={isFirst ? firstCriticalRef : null}
                    className={`hover:bg-surface-container-low/50 ${isHighlighted ? "ring-2 ring-inset ring-secondary/50 bg-secondary-container/10" : ""}`}
                  >
                    <td className="px-6 py-3 font-mono text-xs text-on-surface">{s.sku}</td>
                    <td className="px-6 py-3">
                      <span className="font-medium text-on-surface">{s.name}</span>
                      {s.variant_label ? (
                        <span className="mt-0.5 block text-xs text-on-surface-variant">{s.variant_label}</span>
                      ) : null}
                    </td>
                    <td className="px-6 py-3 text-on-surface-variant">{s.group_title ?? "—"}</td>
                    <td className={`px-6 py-3 text-right tabular-nums ${qtyClass(s.quantity)}`}>{s.quantity}</td>
                    <td className="px-6 py-3 text-right tabular-nums text-on-surface">{formatMoney(s.unit_price_cents, currency)}</td>
                    <td className="px-6 py-3">
                      <Badge tone={stockBadge(s.quantity)}>{s.quantity <= 5 ? "critical" : s.quantity <= 10 ? "low" : "ok"}</Badge>
                    </td>
                  </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="grid gap-6 lg:grid-cols-12">
        <section className="overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm lg:col-span-8">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-outline-variant/10 px-6 py-4">
            <div>
              <h3 className="font-headline text-lg font-bold text-on-surface">Movement journal</h3>
              <p className="text-sm text-on-surface-variant">Ledger deltas with type semantics</p>
            </div>
            <SelectInput
              className="max-w-[12rem]"
              value={mtype}
              onChange={setMtype}
              placeholder="All types"
              options={[
                { value: "", label: "All types" },
                { value: "adjustment", label: "adjustment" },
                { value: "sale", label: "sale" },
              ]}
            />
          </div>
          {mErr ? (
            <div className="px-6 py-3">
              <ErrorState detail={mErr} />
            </div>
          ) : null}
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b border-outline-variant/10">
                  <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Type</th>
                  <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">SKU</th>
                  <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Product</th>
                  <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Shop</th>
                  <th className="px-6 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Delta</th>
                  <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">When</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/10">
                {mLoading && movementRows.length === 0 ? <LoadingRow colSpan={6} /> : null}
                {movementRows.map((r) => (
                  <tr key={r.id} className="hover:bg-surface-container-low/40">
                    <td className="px-6 py-3">
                      <div className="flex items-center gap-2">
                        <span className="material-symbols-outlined text-lg text-on-surface-variant">{movementIcon(r.movement_type)}</span>
                        <Badge tone="default">{r.movement_type}</Badge>
                      </div>
                    </td>
                    <td className="px-6 py-3 font-mono text-xs text-on-surface">{r.product_sku}</td>
                    <td className="px-6 py-3 text-on-surface">{r.product_name}</td>
                    <td className="px-6 py-3 text-on-surface-variant">{r.shop_name}</td>
                    <td
                      className={`px-6 py-3 text-right tabular-nums font-bold ${
                        r.quantity_delta >= 0 ? "text-primary" : "text-error"
                      }`}
                    >
                      {r.quantity_delta > 0 ? `+${r.quantity_delta}` : r.quantity_delta}
                    </td>
                    <td className="px-6 py-3 font-mono text-xs text-on-surface-variant">{r.created_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={mPage} totalPages={mTotalPages} onChange={setMPage} />
        </section>

        <div className="space-y-6 lg:col-span-4">
          <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm lg:sticky lg:top-6">
            <h3 className="font-headline text-lg font-bold text-on-surface">Recent activity</h3>
            <p className="mt-1 text-sm text-on-surface-variant">Six most recent movements across all pages</p>
            <div className="mt-6">
              <Timeline items={timelineItems} />
            </div>
          </div>
          <div className="rounded-xl border border-outline-variant/10 bg-surface-container-low p-6 shadow-sm">
            <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Ready to restock?</p>
            <p className="mt-2 font-headline text-xl font-bold text-on-surface">Line up vendors & POs</p>
            <p className="mt-2 text-sm text-on-surface-variant">Draft purchase orders and notify suppliers in one pass.</p>
            <div className="mt-4 flex flex-col gap-2">
              <Link
                href="/purchase-orders"
                className="ink-gradient inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-center text-sm font-semibold text-on-primary"
              >
                Open purchase orders
              </Link>
              <Link
                href="/suppliers"
                className="inline-flex items-center justify-center rounded-lg border border-outline-variant/40 px-4 py-2.5 text-sm font-semibold text-on-surface transition hover:bg-surface-container"
              >
                Supplier hub
              </Link>
            </div>
          </div>
        </div>
      </div>

      {adjustOpen && shopId ? (
        <AdjustStockDialog
          shopId={shopId}
          stockRows={stockRows}
          onClose={() => setAdjustOpen(false)}
          onSaved={() => {
            setAdjustOpen(false);
            void fetchStock(shopId);
            setMPage(1);
            setMCache({});
            setMNext({});
          }}
        />
      ) : null}
    </div>
  );
}

function AdjustStockDialog({
  shopId,
  stockRows,
  onClose,
  onSaved,
}: {
  shopId: string;
  stockRows: StockRow[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [productId, setProductId] = useState(stockRows[0]?.product_id ?? "");
  const [delta, setDelta] = useState("");
  const [reason, setReason] = useState("correction");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const deltaNum = parseInt(delta, 10);
    if (isNaN(deltaNum) || deltaNum === 0) {
      setErr("Delta must be a non-zero integer");
      return;
    }
    setSaving(true);
    setErr(null);
    const r = await fetch("/api/ims/v1/admin/inventory/adjustments", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        shop_id: shopId,
        product_id: productId,
        quantity_delta: deltaNum,
        reason,
        notes: notes.trim() || null,
      }),
    });
    if (r.ok) {
      onSaved();
    } else {
      const body = await r.json().catch(() => ({})) as { detail?: string };
      setErr(body.detail ?? `Save failed (${r.status})`);
    }
    setSaving(false);
  }

  const selected = stockRows.find((s) => s.product_id === productId);

  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-2xl bg-surface shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="ink-gradient rounded-t-2xl px-6 py-5">
          <p className="text-xs font-bold uppercase tracking-widest text-on-primary/80">Stock adjustment</p>
          <p className="mt-1 font-headline text-xl font-extrabold text-on-primary">Adjust on-hand quantity</p>
          <p className="mt-1 text-xs text-on-primary/70">Creates an approved ledger entry immediately.</p>
        </div>
        <form onSubmit={onSubmit} className="space-y-4 p-6">
          <label className="block text-sm font-medium text-on-surface">
            Product
            <SelectInput
              className="mt-1"
              value={productId}
              onChange={setProductId}
              options={stockRows.map((s) => ({ value: s.product_id, label: `${s.sku} — ${s.name}` }))}
            />
            {selected ? (
              <p className="mt-1 text-xs text-on-surface-variant">Current on-hand: <span className="font-bold text-on-surface">{selected.quantity}</span></p>
            ) : null}
          </label>
          <label className="block text-sm font-medium text-on-surface">
            Quantity delta
            <TextInput
              required
              type="number"
              className="mt-1"
              value={delta}
              onChange={(e) => setDelta(e.target.value)}
              placeholder="e.g. +10 to add, -3 to remove"
            />
            <p className="mt-1 text-xs text-on-surface-variant">Positive = add stock · Negative = remove stock</p>
          </label>
          <label className="block text-sm font-medium text-on-surface">
            Reason
            <SelectInput
              className="mt-1"
              value={reason}
              onChange={setReason}
              options={[
                { value: "correction", label: "Correction" },
                { value: "damage", label: "Damage" },
                { value: "loss", label: "Loss / theft" },
                { value: "found", label: "Found / recovery" },
                { value: "other", label: "Other" },
              ]}
            />
          </label>
          <label className="block text-sm font-medium text-on-surface">
            Notes (optional)
            <TextInput
              className="mt-1"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Additional context…"
            />
          </label>
          {err ? <p className="text-sm text-error">{err}</p> : null}
          <div className="flex gap-2 pt-2">
            <PrimaryButton type="submit" disabled={saving}>{saving ? "Saving…" : "Apply adjustment"}</PrimaryButton>
            <SecondaryButton type="button" onClick={onClose}>Cancel</SecondaryButton>
          </div>
        </form>
      </div>
    </div>
  );
}
