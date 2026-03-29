"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Badge,
  ErrorState,
  LoadingRow,
  PageHeader,
  Pagination,
  Panel,
  SelectInput,
  Timeline,
} from "@/components/ui/primitives";
import { formatMoneyUSD } from "@/lib/format";

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

type Tenant = { id: string; name: string };

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
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [tenantId, setTenantId] = useState("");
  const [shops, setShops] = useState<ShopRow[]>([]);
  const [shopId, setShopId] = useState("");
  const [stockRows, setStockRows] = useState<StockRow[]>([]);
  const [stockLoading, setStockLoading] = useState(false);

  const [mtype, setMtype] = useState("");
  const [mPage, setMPage] = useState(1);
  const [mCache, setMCache] = useState<Record<number, MovementRow[]>>({});
  const [mNext, setMNext] = useState<Record<number, string | null>>({});
  const mNextRef = useRef(mNext);
  mNextRef.current = mNext;
  const [mLoading, setMLoading] = useState(true);
  const [mErr, setMErr] = useState<string | null>(null);

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
    void (async () => {
      const o = await fetch("/api/ims/v1/admin/overview");
      if (o.ok) {
        const j = (await o.json()) as { tenants: Tenant[] };
        setTenants(j.tenants);
        if (j.tenants[0]) setTenantId(j.tenants[0].id);
      }
    })();
  }, []);

  useEffect(() => {
    if (!tenantId) return;
    void (async () => {
      const r = await fetch(`/api/ims/v1/admin/shops?tenant_id=${encodeURIComponent(tenantId)}`);
      if (r.ok) {
        const list = (await r.json()) as ShopRow[];
        setShops(list);
        setShopId((prev) => {
          if (prev && list.some((s) => s.id === prev)) return prev;
          return list[0]?.id ?? "";
        });
      }
    })();
  }, [tenantId]);

  useEffect(() => {
    if (!shopId) {
      setStockRows([]);
      return;
    }
    void (async () => {
      setStockLoading(true);
      try {
        const r = await fetch(`/api/ims/v1/inventory/shop/${shopId}/products`);
        if (r.ok) setStockRows((await r.json()) as StockRow[]);
        else setStockRows([]);
      } finally {
        setStockLoading(false);
      }
    })();
  }, [shopId]);

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
      movementRows.slice(0, 6).map((r) => ({
        title: `${r.movement_type} · ${r.product_sku ?? "SKU"}`,
        detail: `${r.shop_name ?? "Shop"} · ${r.created_at}`,
        tone: r.quantity_delta < 0 ? ("warn" as const) : ("default" as const),
      })),
    [movementRows],
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
          <p className="mt-4 font-headline text-3xl font-extrabold text-primary">{formatMoneyUSD(valuation.totalValuation)}</p>
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
          <div className="flex flex-wrap gap-4">
            <label className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">
              Tenant
              <SelectInput className="mt-1 min-w-[10rem]" value={tenantId} onChange={(e) => setTenantId(e.target.value)}>
                {tenants.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </SelectInput>
            </label>
            <label className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">
              Shop
              <SelectInput className="mt-1 min-w-[12rem]" value={shopId} onChange={(e) => setShopId(e.target.value)}>
                {shops.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </SelectInput>
            </label>
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
                stockRows.map((s) => (
                  <tr key={s.product_id} className="hover:bg-surface-container-low/50">
                    <td className="px-6 py-3 font-mono text-xs text-on-surface">{s.sku}</td>
                    <td className="px-6 py-3">
                      <span className="font-medium text-on-surface">{s.name}</span>
                      {s.variant_label ? (
                        <span className="mt-0.5 block text-xs text-on-surface-variant">{s.variant_label}</span>
                      ) : null}
                    </td>
                    <td className="px-6 py-3 text-on-surface-variant">{s.group_title ?? "—"}</td>
                    <td className={`px-6 py-3 text-right tabular-nums ${qtyClass(s.quantity)}`}>{s.quantity}</td>
                    <td className="px-6 py-3 text-right tabular-nums text-on-surface">{formatMoneyUSD(s.unit_price_cents)}</td>
                    <td className="px-6 py-3">
                      <Badge tone={stockBadge(s.quantity)}>{s.quantity <= 5 ? "critical" : s.quantity <= 10 ? "low" : "ok"}</Badge>
                    </td>
                  </tr>
                ))
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
            <SelectInput className="max-w-[12rem]" value={mtype} onChange={(e) => setMtype(e.target.value)}>
              <option value="">All types</option>
              <option value="adjustment">adjustment</option>
              <option value="sale">sale</option>
            </SelectInput>
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
            <p className="mt-1 text-sm text-on-surface-variant">Last six movements on this journal page</p>
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
    </div>
  );
}
