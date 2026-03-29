"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Badge,
  EmptyState,
  LoadingRow,
  PageHeader,
  Panel,
  SecondaryButton,
  SelectInput,
} from "@/components/ui/primitives";

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
    <div className="space-y-7">
      <PageHeader
        kicker="Inventory ledger"
        title="Stock movements"
        subtitle="Cross-shop journal and on-hand snapshots sourced from ledger totals."
      />
      <Panel
        title="Stock by shop"
        subtitle="On-hand quantity per SKU with group and variant context."
      >
        <div className="mt-3 flex flex-wrap gap-3">
          <label className="text-xs font-medium text-primary/60">
            Tenant
            <SelectInput
              className="mt-1 block"
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
            >
              {tenants.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </SelectInput>
          </label>
          <label className="text-xs font-medium text-primary/60">
            Shop
            <SelectInput
              className="mt-1 block min-w-[12rem]"
              value={shopId}
              onChange={(e) => setShopId(e.target.value)}
            >
              {shops.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </SelectInput>
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
              {stockLoading ? <LoadingRow colSpan={5} /> : null}
              {!stockLoading && stockRows.length > 0 ? (
                stockRows.map((s) => (
                  <tr key={s.product_id}>
                    <td className="px-3 py-2 text-primary/80">{s.group_title ?? "—"}</td>
                    <td className="px-3 py-2 text-primary/70">{s.variant_label ?? "—"}</td>
                    <td className="px-3 py-2 font-mono text-xs">{s.sku}</td>
                    <td className="px-3 py-2">{s.name}</td>
                    <td className="px-3 py-2 text-right tabular-nums font-medium">{s.quantity}</td>
                  </tr>
                ))
              ) : null}
            </tbody>
          </table>
        </div>
        {!stockLoading && stockRows.length === 0 ? <EmptyState title="No stock rows" detail="Select a tenant/shop with products." /> : null}
      </Panel>
      <Panel
        title="Movement journal"
        subtitle="Chronological ledger deltas with cursor pagination."
        right={
          <SelectInput value={mtype} onChange={(e) => setMtype(e.target.value)}>
            <option value="">All types</option>
            <option value="adjustment">adjustment</option>
            <option value="sale">sale</option>
            <option value="sale_out">sale_out</option>
            <option value="receipt">receipt</option>
            <option value="shrink">shrink</option>
          </SelectInput>
        }
      >
        <div className="overflow-x-auto">
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
            {loading ? <LoadingRow colSpan={5} /> : null}
            {rows.map((r) => (
              <tr key={r.id}>
                <td className="px-4 py-3 font-mono text-xs">{r.created_at}</td>
                <td className="px-4 py-3">{r.shop_name ?? "—"}</td>
                <td className="px-4 py-3 text-primary/80">{r.product_sku}</td>
                <td className="px-4 py-3 tabular-nums font-medium">{r.quantity_delta}</td>
                <td className="px-4 py-3">
                  <Badge>{r.movement_type}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
          </table>
        </div>
        {rows.length === 0 && !loading ? <EmptyState title="No movement rows" detail="Try changing movement type or refreshing demo data." /> : null}
      </Panel>
      {next ? (
        <SecondaryButton
          type="button"
          disabled={loading}
          onClick={() => void load(next, true)}
        >
          {loading ? "Loading…" : "Load more"}
        </SecondaryButton>
      ) : null}
    </div>
  );
}
