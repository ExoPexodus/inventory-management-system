"use client";

import { useCallback, useEffect, useState } from "react";

type Row = {
  id: string;
  shop_name: string | null;
  product_sku: string | null;
  product_name: string | null;
  quantity_delta: number;
  movement_type: string;
  created_at: string;
};

type Page = { items: Row[]; next_cursor: string | null };

type Tenant = { id: string; name: string };

type ShopRow = { id: string; tenant_id: string; name: string };

type StockRow = {
  product_id: string;
  sku: string;
  name: string;
  unit_price_cents: number;
  quantity: number;
  product_group_id?: string | null;
  group_title?: string | null;
  variant_label?: string | null;
};

export default function InventoryPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [mtype, setMtype] = useState("");
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [tenantId, setTenantId] = useState("");
  const [shops, setShops] = useState<ShopRow[]>([]);
  const [shopId, setShopId] = useState("");
  const [stockRows, setStockRows] = useState<StockRow[]>([]);
  const [stockLoading, setStockLoading] = useState(false);

  const load = useCallback(
    async (cursor: string | null, append: boolean) => {
      setLoading(true);
      try {
        const sp = new URLSearchParams({ limit: "40" });
        if (mtype) sp.set("movement_type", mtype);
        if (cursor) sp.set("cursor", cursor);
        const r = await fetch(`/api/ims/v1/admin/inventory/movements?${sp}`);
        if (!r.ok) return;
        const data = (await r.json()) as Page;
        setRows((p) => (append ? [...p, ...data.items] : data.items));
        setNext(data.next_cursor);
      } finally {
        setLoading(false);
      }
    },
    [mtype],
  );

  useEffect(() => {
    void load(null, false);
  }, [load]);

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

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-wider text-primary/50">Inventory ledger</p>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-primary">Stock movements</h1>
      </header>
      <section className="rounded-xl border border-primary/10 bg-white/90 p-5 shadow-sm">
        <h2 className="font-display text-sm font-semibold text-primary">Stock by shop</h2>
        <p className="mt-1 text-xs text-primary/55">
          Current on-hand from the ledger, with product group for restocking related SKUs together.
        </p>
        <div className="mt-3 flex flex-wrap gap-3">
          <label className="text-xs font-medium text-primary/60">
            Tenant
            <select
              className="mt-1 block rounded-lg border border-primary/15 px-3 py-2 text-sm"
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
            >
              {tenants.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs font-medium text-primary/60">
            Shop
            <select
              className="mt-1 block min-w-[12rem] rounded-lg border border-primary/15 px-3 py-2 text-sm"
              value={shopId}
              onChange={(e) => setShopId(e.target.value)}
            >
              {shops.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="mt-4 overflow-x-auto rounded-lg border border-primary/10">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-primary/10 text-xs uppercase tracking-wide text-primary/50">
                <th className="px-3 py-2">Group</th>
                <th className="px-3 py-2">Variant</th>
                <th className="px-3 py-2">SKU</th>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2 text-right">Qty</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-primary/5">
              {stockLoading ? (
                <tr>
                  <td colSpan={5} className="px-3 py-4 text-primary/60">
                    Loading…
                  </td>
                </tr>
              ) : stockRows.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-3 py-4 text-primary/60">
                    No products or select a shop.
                  </td>
                </tr>
              ) : (
                stockRows.map((s) => (
                  <tr key={s.product_id}>
                    <td className="px-3 py-2 text-primary/80">{s.group_title ?? "—"}</td>
                    <td className="px-3 py-2 text-primary/70">{s.variant_label ?? "—"}</td>
                    <td className="px-3 py-2 font-mono text-xs">{s.sku}</td>
                    <td className="px-3 py-2">{s.name}</td>
                    <td className="px-3 py-2 text-right tabular-nums font-medium">{s.quantity}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
      <select
        className="rounded-lg border border-primary/15 px-3 py-2 text-sm"
        value={mtype}
        onChange={(e) => setMtype(e.target.value)}
      >
        <option value="">All types</option>
        <option value="adjustment">adjustment</option>
        <option value="sale">sale</option>
      </select>
      <div className="overflow-x-auto rounded-xl border border-primary/10 bg-white/90 shadow-sm">
        <table className="min-w-full text-left text-sm">
          <thead>
            <tr className="border-b border-primary/10 text-xs uppercase tracking-wide text-primary/50">
              <th className="px-4 py-3">When</th>
              <th className="px-4 py-3">Shop</th>
              <th className="px-4 py-3">SKU</th>
              <th className="px-4 py-3">Δ</th>
              <th className="px-4 py-3">Type</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-primary/5">
            {rows.map((r) => (
              <tr key={r.id}>
                <td className="px-4 py-3 font-mono text-xs">{r.created_at}</td>
                <td className="px-4 py-3">{r.shop_name ?? "—"}</td>
                <td className="px-4 py-3 text-primary/80">{r.product_sku}</td>
                <td className="px-4 py-3 tabular-nums font-medium">{r.quantity_delta}</td>
                <td className="px-4 py-3">
                  <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs">{r.movement_type}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {next ? (
        <button
          type="button"
          disabled={loading}
          className="rounded-lg border border-primary/20 px-4 py-2 text-sm font-medium text-primary"
          onClick={() => void load(next, true)}
        >
          {loading ? "Loading…" : "Load more"}
        </button>
      ) : null}
    </div>
  );
}
