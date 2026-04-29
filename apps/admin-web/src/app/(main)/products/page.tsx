"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  Avatar,
  Badge,
  EmptyState,
  LoadingRow,
  PageHeader,
  Panel,
  PrimaryButton,
  SearchBar,
  SecondaryButton,
  SelectInput,
  TextInput,
} from "@/components/ui/primitives";
import { formatMoney } from "@/lib/format";
import { useCurrency } from "@/lib/currency-context";

type Product = {
  id: string;
  sku: string;
  name: string;
  status: string;
  category: string | null;
  unit_price_cents: number;
  reorder_point: number;
  variant_label?: string | null;
  group_title?: string | null;
  barcode?: string | null;
  cost_price_cents?: number | null;
  mrp_cents?: number | null;
  hsn_code?: string | null;
  negative_inventory_allowed?: boolean;
};

function statusTone(s: string): "default" | "good" | "warn" | "danger" {
  const x = s.toLowerCase();
  if (x === "active") return "good";
  if (x === "draft") return "warn";
  if (x === "archived" || x === "discontinued") return "danger";
  return "default";
}

export default function ProductsPage() {
  const currency = useCurrency();
  const [rows, setRows] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");
  const [editProduct, setEditProduct] = useState<Product | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkReorderPt, setBulkReorderPt] = useState("");
  const [bulkSaving, setBulkSaving] = useState(false);

  async function fetchProducts() {
    setLoading(true);
    const sp = new URLSearchParams();
    if (q.trim()) sp.set("q", q.trim());
    if (status) sp.set("status", status);
    if (category.trim()) sp.set("category", category.trim());
    const r = await fetch(`/api/ims/v1/admin/products?${sp.toString()}`);
    if (r.ok) setRows((await r.json()) as Product[]);
    else setRows([]);
    setLoading(false);
  }

  useEffect(() => {
    void fetchProducts();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, status, category]);

  const categories = useMemo(() => {
    const s = new Set<string>();
    for (const r of rows) {
      if (r.category) s.add(r.category);
    }
    return [...s].sort();
  }, [rows]);

  function toggleSelect(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    if (selected.size === rows.length) setSelected(new Set());
    else setSelected(new Set(rows.map((r) => r.id)));
  }

  async function applyBulkReorder() {
    const rp = parseInt(bulkReorderPt, 10);
    if (isNaN(rp) || rp < 0) return;
    setBulkSaving(true);
    const r = await fetch("/api/ims/v1/admin/products/bulk-reorder-point", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ product_ids: [...selected], reorder_point: rp }),
    });
    setBulkSaving(false);
    if (r.ok) {
      setSelected(new Set());
      setBulkReorderPt("");
      void fetchProducts();
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="Catalog"
        title="Product library"
        subtitle="SKU truth with variant context — edit actions open the catalog tools."
        action={
          <Link
            href="/entries"
            className="ink-gradient inline-flex items-center gap-2 rounded-lg px-6 py-2.5 text-sm font-semibold text-on-primary shadow-sm transition hover:opacity-90"
          >
            <span className="material-symbols-outlined text-lg">add</span>
            New product
          </Link>
        }
      />

      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-outline-variant/10 bg-surface-container-low p-4 shadow-sm">
        <SearchBar className="min-w-[14rem] flex-1" placeholder="Search name or SKU" value={q} onChange={(e) => setQ(e.target.value)} />
        <SelectInput
          className="min-w-[9rem]"
          value={status}
          onChange={setStatus}
          placeholder="All statuses"
          options={[
            { value: "", label: "All statuses" },
            { value: "active", label: "active" },
            { value: "draft", label: "draft" },
            { value: "archived", label: "archived" },
            { value: "discontinued", label: "discontinued" },
          ]}
        />
        <SelectInput
          className="min-w-[11rem]"
          value={category}
          onChange={setCategory}
          placeholder="All categories"
          options={[
            { value: "", label: "All categories" },
            ...categories.map((c) => ({ value: c, label: c })),
          ]}
        />
      </div>

      <Panel title="Products" subtitle={`${rows.length} rows`} noPad>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-outline-variant/10">
                <th className="px-4 py-3">
                  <input
                    type="checkbox"
                    checked={rows.length > 0 && selected.size === rows.length}
                    onChange={toggleSelectAll}
                    className="rounded border-outline-variant/40 accent-primary"
                  />
                </th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Product</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">SKU</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Category</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Status</th>
                <th className="px-6 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Unit price</th>
                <th className="px-6 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">MRP</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Barcode</th>
                <th className="px-6 py-3 text-center text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Reorder Pt.</th>
                <th className="px-6 py-3 text-center text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {loading ? (
                <LoadingRow colSpan={10} label="Loading products…" />
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={10} className="p-0">
                    <EmptyState title="No products match filters" detail="Adjust filters or create a SKU from the entry hub." />
                  </td>
                </tr>
              ) : (
                rows.map((row) => (
                <tr key={row.id} className={`group hover:bg-surface-container-low/50 ${selected.has(row.id) ? "bg-primary/5" : ""}`}>
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      checked={selected.has(row.id)}
                      onChange={() => toggleSelect(row.id)}
                      className="rounded border-outline-variant/40 accent-primary"
                    />
                  </td>
                  <td className="px-6 py-3">
                    <div className="flex items-center gap-3">
                      <Avatar name={row.name} className="h-10 w-10 text-xs" />
                      <div>
                        <p className="font-headline font-bold text-on-surface">{row.name}</p>
                        <p className="text-xs text-on-surface-variant">
                          {row.variant_label || row.group_title || "Standard variant"}
                        </p>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-3 font-mono text-xs text-on-surface">{row.sku}</td>
                  <td className="px-6 py-3 text-on-surface-variant">{row.category ?? "—"}</td>
                  <td className="px-6 py-3">
                    <Badge tone={statusTone(row.status)}>{row.status}</Badge>
                  </td>
                  <td className="px-6 py-3 text-right tabular-nums font-semibold text-on-surface">{formatMoney(row.unit_price_cents, currency)}</td>
                  <td className="px-6 py-3 text-right tabular-nums text-on-surface-variant">
                    {row.mrp_cents != null
                      ? formatMoney(row.mrp_cents, currency)
                      : <span className="text-on-surface-variant/40">—</span>}
                  </td>
                  <td className="px-6 py-3 font-mono text-xs text-on-surface-variant">
                    {row.barcode ?? <span className="text-on-surface-variant/40">—</span>}
                  </td>
                  <td className="px-6 py-3 text-center">
                    {row.reorder_point > 0 ? (
                      <span className="inline-flex items-center rounded-full bg-secondary/10 px-2 py-0.5 text-xs font-bold text-secondary">{row.reorder_point}</span>
                    ) : (
                      <span className="text-xs text-on-surface-variant/40">—</span>
                    )}
                  </td>
                  <td className="px-6 py-3 text-center">
                    <button
                      type="button"
                      onClick={() => setEditProduct(row)}
                      className="inline-flex rounded-lg p-2 text-on-surface-variant opacity-0 transition group-hover:opacity-100 hover:bg-surface-container"
                      aria-label="Edit"
                    >
                      <span className="material-symbols-outlined text-xl">edit</span>
                    </button>
                  </td>
                </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      {/* Bulk reorder toolbar */}
      {selected.size > 0 && (
        <div className="fixed bottom-6 left-1/2 z-40 -translate-x-1/2">
          <div className="flex items-center gap-3 rounded-2xl border border-outline-variant/20 bg-surface-container-lowest px-5 py-3 shadow-2xl">
            <span className="text-sm font-medium text-on-surface">{selected.size} item{selected.size !== 1 ? "s" : ""} selected</span>
            <div className="h-5 w-px bg-outline-variant/30" />
            <span className="text-sm text-on-surface-variant">Set reorder point:</span>
            <input
              type="number"
              min="0"
              value={bulkReorderPt}
              onChange={(e) => setBulkReorderPt(e.target.value)}
              placeholder="e.g. 10"
              className="w-20 rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-1.5 text-sm text-on-surface outline-none focus:border-primary"
            />
            <PrimaryButton type="button" disabled={bulkSaving || !bulkReorderPt} onClick={() => void applyBulkReorder()}>
              {bulkSaving ? "Saving…" : "Apply"}
            </PrimaryButton>
            <SecondaryButton type="button" onClick={() => setSelected(new Set())}>Clear</SecondaryButton>
          </div>
        </div>
      )}

      <div className="rounded-xl border border-outline-variant/10 bg-surface-container-low p-6 shadow-sm">
        <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Need a new SKU?</p>
        <p className="mt-2 font-headline text-xl font-bold text-on-surface">Use the entry hub for structured creates</p>
        <p className="mt-2 text-sm text-on-surface-variant">Shops, groups, and variants stay consistent when you originate them together.</p>
        <Link
          href="/entries"
          className="mt-4 inline-flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-primary hover:underline"
        >
          Open entry hub
          <span className="material-symbols-outlined text-base">arrow_forward</span>
        </Link>
      </div>

      {editProduct ? (
        <EditProductDialog
          product={editProduct}
          onClose={() => setEditProduct(null)}
          onSaved={() => { setEditProduct(null); void fetchProducts(); }}
        />
      ) : null}
    </div>
  );
}

function EditProductDialog({
  product,
  onClose,
  onSaved,
}: {
  product: Product;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(product.name);
  const [cat, setCat] = useState(product.category ?? "");
  const [prodStatus, setProdStatus] = useState(product.status);
  const [priceUsd, setPriceUsd] = useState((product.unit_price_cents / 100).toFixed(2));
  const [reorderPt, setReorderPt] = useState(String(product.reorder_point ?? 0));
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [barcode, setBarcode] = useState(product.barcode ?? "");
  const [costPrice, setCostPrice] = useState(
    product.cost_price_cents != null ? (product.cost_price_cents / 100).toFixed(2) : ""
  );
  const [mrpPrice, setMrpPrice] = useState(
    product.mrp_cents != null ? (product.mrp_cents / 100).toFixed(2) : ""
  );
  const [hsnCode, setHsnCode] = useState(product.hsn_code ?? "");
  const [negativeInventory, setNegativeInventory] = useState(product.negative_inventory_allowed ?? false);

  const priceGuardWarning = (() => {
    const p = Math.round(parseFloat(priceUsd) * 100);
    const cost = costPrice.trim() ? Math.round(parseFloat(costPrice) * 100) : null;
    const mrp = mrpPrice.trim() ? Math.round(parseFloat(mrpPrice) * 100) : null;
    if (!isNaN(p)) {
      if (cost !== null && p < cost) return "Selling price is below cost price.";
      if (mrp !== null && p > mrp) return "Selling price exceeds MRP.";
    }
    return null;
  })();

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const priceCents = Math.round(parseFloat(priceUsd) * 100);
    if (isNaN(priceCents) || priceCents < 0) {
      setErr("Enter a valid price");
      return;
    }
    const rp = parseInt(reorderPt, 10);
    if (isNaN(rp) || rp < 0) {
      setErr("Reorder point must be 0 or greater");
      return;
    }
    const costCents = costPrice.trim() ? Math.round(parseFloat(costPrice) * 100) : null;
    const mrpCents = mrpPrice.trim() ? Math.round(parseFloat(mrpPrice) * 100) : null;
    setSaving(true);
    setErr(null);
    const r = await fetch(`/api/ims/v1/admin/products/${product.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: name.trim(),
        category: cat.trim() || null,
        status: prodStatus,
        unit_price_cents: priceCents,
        reorder_point: rp,
        barcode: barcode.trim() || null,
        cost_price_cents: costCents,
        mrp_cents: mrpCents,
        hsn_code: hsnCode.trim() || null,
        negative_inventory_allowed: negativeInventory,
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

  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-2xl bg-surface shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="ink-gradient rounded-t-2xl px-6 py-5">
          <p className="text-xs font-bold uppercase tracking-widest text-on-primary/80">Edit product</p>
          <p className="mt-1 font-headline text-xl font-extrabold text-on-primary">{product.name}</p>
          <p className="mt-0.5 font-mono text-xs text-on-primary/70">{product.sku}</p>
        </div>
        <form onSubmit={onSubmit} className="space-y-4 p-6">
          <label className="block text-sm font-medium text-on-surface">
            Name
            <TextInput required className="mt-1" value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <div className="grid grid-cols-2 gap-4">
            <label className="block text-sm font-medium text-on-surface">
              Category
              <TextInput className="mt-1" value={cat} onChange={(e) => setCat(e.target.value)} placeholder="e.g. Beverages" />
            </label>
            <label className="block text-sm font-medium text-on-surface">
              Unit price (USD)
              <TextInput
                type="number"
                min="0"
                step="0.01"
                className="mt-1"
                value={priceUsd}
                onChange={(e) => setPriceUsd(e.target.value)}
              />
            </label>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <label className="block text-sm font-medium text-on-surface">
              Status
              <SelectInput
                className="mt-1"
                value={prodStatus}
                onChange={setProdStatus}
                options={[
                  { value: "active", label: "Active" },
                  { value: "draft", label: "Draft" },
                  { value: "archived", label: "Archived" },
                  { value: "discontinued", label: "Discontinued" },
                ]}
              />
            </label>
            <label className="block text-sm font-medium text-on-surface">
              Reorder point
              <TextInput
                type="number"
                min="0"
                step="1"
                className="mt-1"
                value={reorderPt}
                onChange={(e) => setReorderPt(e.target.value)}
                placeholder="0"
              />
            </label>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <label className="block text-sm font-medium text-on-surface">
              Cost price
              <TextInput
                type="number"
                min="0"
                step="0.01"
                className="mt-1"
                value={costPrice}
                onChange={(e) => setCostPrice(e.target.value)}
                placeholder="e.g. 8.00"
              />
            </label>
            <label className="block text-sm font-medium text-on-surface">
              MRP
              <TextInput
                type="number"
                min="0"
                step="0.01"
                className="mt-1"
                value={mrpPrice}
                onChange={(e) => setMrpPrice(e.target.value)}
                placeholder="e.g. 25.00"
              />
            </label>
          </div>
          {priceGuardWarning ? (
            <p className="text-sm text-error">{priceGuardWarning}</p>
          ) : null}
          <label className="block text-sm font-medium text-on-surface">
            Barcode (UPC / EAN)
            <TextInput
              className="mt-1"
              value={barcode}
              onChange={(e) => setBarcode(e.target.value)}
              placeholder="e.g. 8901234567890"
            />
          </label>
          <label className="block text-sm font-medium text-on-surface">
            HSN code
            <TextInput
              className="mt-1"
              value={hsnCode}
              onChange={(e) => setHsnCode(e.target.value)}
              placeholder="e.g. 2101"
            />
          </label>
          <label className="flex items-center gap-3 text-sm font-medium text-on-surface">
            <input
              type="checkbox"
              checked={negativeInventory}
              onChange={(e) => setNegativeInventory(e.target.checked)}
              className="rounded border-outline-variant/40 accent-primary"
            />
            Allow sales when stock is zero
          </label>
          {err ? <p className="text-sm text-error">{err}</p> : null}
          <div className="flex gap-2 pt-2">
            <PrimaryButton type="submit" disabled={saving}>{saving ? "Saving…" : "Save changes"}</PrimaryButton>
            <SecondaryButton type="button" onClick={onClose}>Cancel</SecondaryButton>
          </div>
        </form>
      </div>
    </div>
  );
}
