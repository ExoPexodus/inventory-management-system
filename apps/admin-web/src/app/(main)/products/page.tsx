"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Avatar,
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
import { formatMoney } from "@/lib/format";
import { useCurrency } from "@/lib/currency-context";
import { BulkActionsBar } from "@/components/ui/BulkActionsBar";

type ProductPrice = {
  id: string;
  currency_code: string;
  amount_cents: number;
  channel_id: string | null;
};

type Variant = {
  id: string;
  product_id: string;
  sku: string;
  name: string;
  options: Record<string, string>;
  unit_price_cents: number;
  status: string;
  barcode: string | null;
  sort_order: number;
  created_at: string;
};

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
  const params = useSearchParams();
  const q = params.get("q") ?? "";
  const [rows, setRows] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState("");
  const [category, setCategory] = useState("");
  const [editProduct, setEditProduct] = useState<Product | null>(null);
  const [pricesProduct, setPricesProduct] = useState<{ id: string; name: string } | null>(null);
  const [variantsProduct, setVariantsProduct] = useState<{ id: string; name: string } | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [bulkReorderPt, setBulkReorderPt] = useState("");
  const [bulkSaving, setBulkSaving] = useState(false);
  const [archiving, setArchiving] = useState(false);
  const PER_PAGE = 50;
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

  async function fetchProducts() {
    setLoading(true);
    const sp = new URLSearchParams();
    if (q.trim()) sp.set("q", q.trim());
    if (status) sp.set("status", status);
    if (category.trim()) sp.set("category", category.trim());
    sp.set("page", String(page));
    sp.set("per_page", String(PER_PAGE));
    const r = await fetch(`/api/ims/v1/admin/products?${sp.toString()}`);
    if (r.ok) {
      const data = await r.json() as { items: Product[]; total: number; page: number; per_page: number };
      setRows(data.items);
      setTotal(data.total);
    } else {
      setRows([]);
      setTotal(0);
    }
    setLoading(false);
  }

  // Reset to page 1 whenever a filter changes
  useEffect(() => {
    setPage(1);
  }, [q, status, category]);

  useEffect(() => {
    void fetchProducts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, status, category, page]);

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

  async function applyBulkArchive() {
    if (selected.size === 0) return;
    if (!confirm(`Archive ${selected.size} product${selected.size === 1 ? "" : "s"}? They can be unarchived later from each product's edit dialog.`)) return;
    setArchiving(true);
    try {
      const r = await fetch("/api/ims/v1/admin/products/bulk-archive", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ product_ids: Array.from(selected) }),
      });
      if (r.ok) {
        setSelected(new Set());
        void fetchProducts();
      } else {
        alert("Archive failed.");
      }
    } finally {
      setArchiving(false);
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

      <BulkActionsBar
        selectedCount={selected.size}
        onClear={() => setSelected(new Set())}
      >
        <div className="flex items-center gap-2">
          <input
            type="number"
            min="0"
            value={bulkReorderPt}
            onChange={(e) => setBulkReorderPt(e.target.value)}
            placeholder="Reorder pt"
            className="w-28 rounded-lg border border-outline-variant/30 bg-surface-container-low px-2 py-1.5 text-sm text-on-surface outline-none focus:border-primary focus:ring-1 focus:ring-primary"
          />
          <button
            type="button"
            onClick={() => void applyBulkReorder()}
            disabled={bulkSaving || !bulkReorderPt.trim()}
            className="rounded-lg border border-outline-variant/30 px-3 py-1.5 text-xs font-semibold text-on-surface hover:bg-surface-container-low disabled:opacity-50"
          >
            {bulkSaving ? "Applying…" : "Set reorder point"}
          </button>
        </div>
        <button
          type="button"
          onClick={() => void applyBulkArchive()}
          disabled={archiving}
          className="rounded-lg border border-error/30 bg-error/5 px-3 py-1.5 text-xs font-semibold text-error hover:bg-error/10 disabled:opacity-50"
        >
          {archiving ? "Archiving…" : "Archive"}
        </button>
      </BulkActionsBar>

      <Panel title="Products" subtitle={`${total > 0 ? total.toLocaleString() : rows.length} rows`} noPad>
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
                    <div className="flex items-center justify-center gap-1 opacity-0 transition group-hover:opacity-100">
                      <button
                        type="button"
                        onClick={() => setPricesProduct({ id: row.id, name: row.name })}
                        className="inline-flex rounded-lg p-2 text-on-surface-variant hover:bg-surface-container"
                        aria-label="Manage prices"
                        title="Multi-currency prices"
                      >
                        <span className="material-symbols-outlined text-xl">currency_exchange</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => setVariantsProduct({ id: row.id, name: row.name })}
                        className="inline-flex rounded-lg p-2 text-on-surface-variant hover:bg-surface-container"
                        aria-label="Manage variants"
                        title="Variants"
                      >
                        <span className="material-symbols-outlined text-xl">tune</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => setEditProduct(row)}
                        className="inline-flex rounded-lg p-2 text-on-surface-variant hover:bg-surface-container"
                        aria-label="Edit"
                      >
                        <span className="material-symbols-outlined text-xl">edit</span>
                      </button>
                    </div>
                  </td>
                </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {total > 0 && (
          <div className="flex items-center justify-between border-t border-outline-variant/10 px-6 py-4">
            <p className="text-xs text-on-surface-variant">
              Page {page} of {Math.max(1, Math.ceil(total / PER_PAGE))} · {total.toLocaleString()} products
            </p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1 || loading}
                className="rounded-lg border border-outline-variant/30 px-3 py-1.5 text-xs font-semibold text-on-surface hover:bg-surface-container-low disabled:opacity-40"
              >
                ← Prev
              </button>
              <button
                type="button"
                onClick={() => setPage((p) => p + 1)}
                disabled={page >= Math.ceil(total / PER_PAGE) || loading}
                className="rounded-lg border border-outline-variant/30 px-3 py-1.5 text-xs font-semibold text-on-surface hover:bg-surface-container-low disabled:opacity-40"
              >
                Next →
              </button>
            </div>
          </div>
        )}
      </Panel>

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
      {pricesProduct && (
        <PricesModal
          productId={pricesProduct.id}
          productName={pricesProduct.name}
          onClose={() => setPricesProduct(null)}
        />
      )}
      {variantsProduct && (
        <VariantsModal
          productId={variantsProduct.id}
          productName={variantsProduct.name}
          onClose={() => setVariantsProduct(null)}
        />
      )}
    </div>
  );
}

function ImageUploadSection({ productId }: { productId: string }) {
  const [images, setImages] = useState<{ id: string; url: string; alt_text: string | null }[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadErr, setUploadErr] = useState<string | null>(null);

  const loadImages = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`/api/ims/v1/admin/catalog/products/${productId}/images`);
      if (r.ok) setImages((await r.json()) as { id: string; url: string; alt_text: string | null }[]);
    } finally {
      setLoading(false);
    }
  }, [productId]);

  useEffect(() => { void loadImages(); }, [loadImages]);

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!["image/jpeg", "image/png", "image/webp", "image/gif", "image/avif"].includes(file.type)) {
      setUploadErr("Only JPEG, PNG, WebP, GIF, and AVIF images are accepted.");
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setUploadErr("Image must be under 10 MB.");
      return;
    }

    setUploading(true);
    setUploadErr(null);
    try {
      // 1. Get presigned URL
      const presignResp = await fetch("/api/ims/v1/admin/media/presign-upload", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          folder: `products/${productId}`,
          filename: file.name,
          content_type: file.type,
          file_size_bytes: file.size,
        }),
      });
      if (!presignResp.ok) {
        const d = await presignResp.json().catch(() => ({})) as { detail?: string };
        throw new Error(d.detail ?? `Presign failed (${presignResp.status})`);
      }
      const { upload_url, public_url, storage_warning } = (await presignResp.json()) as {
        upload_url: string;
        public_url: string;
        key: string;
        storage_warning: { used_pct: number; used_mb: number; limit_mb: number } | null;
      };

      // 2. PUT directly to R2 from browser
      const putResp = await fetch(upload_url, {
        method: "PUT",
        headers: { "Content-Type": file.type },
        body: file,
      });
      if (!putResp.ok) throw new Error(`Storage upload failed (${putResp.status})`);

      // 3. Save URL to product gallery
      const saveResp = await fetch(
        `/api/ims/v1/admin/catalog/products/${productId}/images`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: public_url, sort_order: images.length, file_size_bytes: file.size }),
        }
      );
      if (!saveResp.ok) throw new Error("Failed to save image URL");

      void loadImages();
      if (storage_warning) {
        setUploadErr(
          `Storage ${storage_warning.used_pct}% used (${storage_warning.used_mb} MB of ${storage_warning.limit_mb} MB). Consider upgrading your plan.`
        );
      }
    } catch (err) {
      setUploadErr(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  async function handleDelete(imageId: string) {
    if (!confirm("Remove this image?")) return;
    try {
      await fetch(`/api/ims/v1/admin/catalog/products/${productId}/images/${imageId}`, {
        method: "DELETE",
      });
      void loadImages();
    } catch { /* silently ignore */ }
  }

  return (
    <div className="space-y-3">
      <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">
        Product images
      </p>

      {loading ? (
        <p className="text-xs text-on-surface-variant">Loading…</p>
      ) : images.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {images.map((img) => (
            <div key={img.id} className="group relative">
              <img
                src={img.url}
                alt={img.alt_text ?? ""}
                className="h-20 w-20 rounded-lg object-cover border border-outline-variant/20"
              />
              <button
                type="button"
                onClick={() => void handleDelete(img.id)}
                className="absolute -right-1.5 -top-1.5 hidden h-5 w-5 items-center justify-center rounded-full bg-error text-[10px] text-white group-hover:flex"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      ) : null}

      <label className={`flex cursor-pointer items-center gap-2 rounded-lg border-2 border-dashed border-outline-variant/40 px-4 py-3 text-sm text-on-surface-variant transition hover:border-primary/50 hover:text-primary ${uploading ? "opacity-50 cursor-not-allowed" : ""}`}>
        <span className="material-symbols-outlined text-lg">add_photo_alternate</span>
        {uploading ? "Uploading…" : "Add image"}
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp,image/gif,image/avif"
          className="sr-only"
          disabled={uploading}
          onChange={(e) => void handleFileChange(e)}
        />
      </label>

      {uploadErr && <p className="text-xs text-error">{uploadErr}</p>}
      <p className="text-[11px] text-on-surface-variant">JPEG, PNG, WebP, GIF or AVIF · max 10 MB</p>
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
        className="w-full max-w-lg rounded-2xl bg-surface shadow-xl max-h-[90vh] overflow-y-auto"
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
            Allow sales when stock reaches zero (permit negative stock)
          </label>
          {err ? <p className="text-sm text-error">{err}</p> : null}
          <ImageUploadSection productId={product.id} />
          <div className="flex gap-2 pt-2">
            <PrimaryButton type="submit" disabled={saving}>{saving ? "Saving…" : "Save changes"}</PrimaryButton>
            <SecondaryButton type="button" onClick={onClose}>Cancel</SecondaryButton>
          </div>
        </form>
      </div>
    </div>
  );
}

/** Returns the number of fractional digits (exponent) for a currency code using the browser Intl API. */
function currencyExponent(code: string): number {
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency: code })
      .resolvedOptions().minimumFractionDigits ?? 2;
  } catch {
    return 2; // safe default for unknown codes
  }
}

/** Formats stored minor-unit cents to a display string using the currency's correct exponent. */
function formatCurrencyAmount(amountCents: number, currencyCode: string): string {
  const exp = currencyExponent(currencyCode);
  const major = amountCents / 10 ** exp;
  try {
    return major.toLocaleString(undefined, {
      style: "currency",
      currency: currencyCode,
      minimumFractionDigits: exp,
      maximumFractionDigits: exp,
    });
  } catch {
    return `${major.toFixed(exp)} ${currencyCode}`;
  }
}

function PricesModal({
  productId,
  productName,
  onClose,
}: {
  productId: string;
  productName: string;
  onClose: () => void;
}) {
  const [prices, setPrices] = useState<ProductPrice[]>([]);
  const [loading, setLoading] = useState(true);
  const [currency, setCurrency] = useState("");
  const [amount, setAmount] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const r = await fetch(`/api/ims/v1/admin/products/${productId}/prices`);
      if (r.ok) {
        setPrices((await r.json()) as ProductPrice[]);
      } else {
        setErr(`Failed to load prices (${r.status})`);
      }
    } catch {
      setErr("Network error. Could not load prices.");
    } finally {
      setLoading(false);
    }
  }, [productId]);

  useEffect(() => { void load(); }, [load]);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!currency.trim() || !amount.trim()) return;
    setSaving(true);
    setErr(null);
    try {
      const r = await fetch(`/api/ims/v1/admin/products/${productId}/prices`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          currency_code: currency.trim().toUpperCase(),
          amount_cents: Math.round(parseFloat(amount) * 10 ** currencyExponent(currency.trim().toUpperCase())),
          channel_id: null,
        }),
      });
      if (r.ok) {
        setCurrency(""); setAmount("");
        void load();
      } else {
        const d = await r.json().catch(() => ({})) as { detail?: string };
        setErr(d.detail ?? `Failed (${r.status})`);
      }
    } catch {
      setErr("Network error. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(priceId: string) {
    try {
      const r = await fetch(`/api/ims/v1/admin/products/${productId}/prices/${priceId}`, {
        method: "DELETE",
      });
      if (r.ok) void load();
    } catch {
      // silently ignore delete errors — user can retry
    }
  }

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-lg rounded-2xl bg-surface-container-lowest shadow-2xl">
        <div className="flex items-center justify-between rounded-t-2xl bg-gradient-to-r from-primary to-secondary px-6 py-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-widest text-on-primary/70">
              Multi-currency prices
            </p>
            <p className="mt-0.5 font-headline text-lg font-bold text-on-primary">{productName}</p>
          </div>
          <button type="button" onClick={onClose} className="text-on-primary/70 hover:text-on-primary">
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        <div className="p-6 space-y-4">
          <form onSubmit={(e) => void handleAdd(e)} className="flex gap-2">
            <TextInput
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
              placeholder="USD"
              maxLength={3}
              className="w-24"
              required
            />
            <TextInput
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder="9.99"
              step="0.01"
              min="0"
              className="flex-1"
              required
            />
            <PrimaryButton type="submit" disabled={saving}>
              {saving ? "…" : "Add"}
            </PrimaryButton>
          </form>
          <p className="text-[11px] text-on-surface-variant">
            Enter the amount in the currency&apos;s major unit (e.g. 9.99 for $9.99 → 999 cents stored).
          </p>
          {err && <p className="text-sm text-error">{err}</p>}

          {loading ? (
            <p className="text-sm text-on-surface-variant">Loading…</p>
          ) : prices.length === 0 ? (
            <p className="text-sm text-on-surface-variant">No override prices set. Add one above.</p>
          ) : (
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b border-outline-variant/10">
                  <th className="py-2 pr-4 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
                    Currency
                  </th>
                  <th className="py-2 pr-4 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
                    Amount
                  </th>
                  <th className="py-2 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/10">
                {prices.map((p) => (
                  <tr key={p.id}>
                    <td className="py-2 pr-4 font-mono text-on-surface">{p.currency_code}</td>
                    <td className="py-2 pr-4 text-on-surface tabular-nums">
                      {formatCurrencyAmount(p.amount_cents, p.currency_code)}
                    </td>
                    <td className="py-2">
                      <button
                        type="button"
                        onClick={() => void handleDelete(p.id)}
                        className="text-xs text-error hover:underline"
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

function VariantsModal({
  productId,
  productName,
  onClose,
}: {
  productId: string;
  productName: string;
  onClose: () => void;
}) {
  const [variants, setVariants] = useState<Variant[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  // Create form state
  const [sku, setSku] = useState("");
  const [name, setName] = useState("");
  const [price, setPrice] = useState("");
  const [optionPairs, setOptionPairs] = useState<{ key: string; value: string }[]>([
    { key: "", value: "" },
  ]);
  const [saving, setSaving] = useState(false);
  const [saveErr, setSaveErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const r = await fetch(`/api/ims/v1/admin/products/${productId}/variants`);
      if (!r.ok) throw new Error(`Failed (${r.status})`);
      setVariants((await r.json()) as Variant[]);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load variants.");
    } finally {
      setLoading(false);
    }
  }, [productId]);

  useEffect(() => { void load(); }, [load]);

  function addOptionRow() {
    setOptionPairs((prev) => [...prev, { key: "", value: "" }]);
  }

  function updateOption(index: number, field: "key" | "value", val: string) {
    setOptionPairs((prev) =>
      prev.map((p, i) => (i === index ? { ...p, [field]: val } : p))
    );
  }

  function removeOption(index: number) {
    setOptionPairs((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setSaveErr(null);
    const options: Record<string, string> = {};
    optionPairs
      .filter((p) => p.key.trim())
      .forEach((p) => { options[p.key.trim()] = p.value.trim(); });
    try {
      const r = await fetch(`/api/ims/v1/admin/products/${productId}/variants`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sku: sku.trim(),
          name: name.trim(),
          options,
          unit_price_cents: Math.round(parseFloat(price) * 100),
        }),
      });
      if (r.ok) {
        setSku(""); setName(""); setPrice("");
        setOptionPairs([{ key: "", value: "" }]);
        void load();
      } else {
        const d = await r.json().catch(() => ({})) as { detail?: string };
        setSaveErr(d.detail ?? `Failed (${r.status})`);
      }
    } catch {
      setSaveErr("Network error. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(variantId: string) {
    if (!confirm("Delete this variant?")) return;
    try {
      const r = await fetch(
        `/api/ims/v1/admin/products/${productId}/variants/${variantId}`,
        { method: "DELETE" }
      );
      if (r.ok) void load();
    } catch { /* silently ignore */ }
  }

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4">
      <div className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-2xl bg-surface-container-lowest shadow-2xl">
        <div className="flex items-center justify-between rounded-t-2xl bg-gradient-to-r from-primary to-secondary px-6 py-4">
          <div>
            <p className="text-xs font-bold uppercase tracking-widest text-on-primary/70">
              Variants
            </p>
            <p className="mt-0.5 font-headline text-lg font-bold text-on-primary">
              {productName}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-on-primary/70 hover:text-on-primary"
          >
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* Create form */}
          <form
            onSubmit={(e) => void handleCreate(e)}
            className="rounded-xl border border-outline-variant/10 bg-surface-container-low p-4 space-y-3"
          >
            <p className="text-sm font-semibold text-on-surface">Add variant</p>
            <div className="grid gap-3 sm:grid-cols-3">
              <div>
                <label className="block text-xs font-medium text-on-surface mb-1">SKU</label>
                <TextInput
                  value={sku}
                  onChange={(e) => setSku(e.target.value)}
                  placeholder="SHIRT-M-BLK"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-on-surface mb-1">Name</label>
                <TextInput
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="T-Shirt M Black"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-on-surface mb-1">
                  Price (major unit)
                </label>
                <TextInput
                  type="number"
                  value={price}
                  onChange={(e) => setPrice(e.target.value)}
                  placeholder="19.99"
                  step="0.01"
                  min="0"
                  required
                />
              </div>
            </div>

            <div>
              <p className="text-xs font-medium text-on-surface mb-2">
                Options (e.g. size, colour)
              </p>
              {optionPairs.map((pair, idx) => (
                <div key={idx} className="mb-2 flex gap-2">
                  <TextInput
                    value={pair.key}
                    onChange={(e) => updateOption(idx, "key", e.target.value)}
                    placeholder="size"
                    className="flex-1"
                  />
                  <TextInput
                    value={pair.value}
                    onChange={(e) => updateOption(idx, "value", e.target.value)}
                    placeholder="M"
                    className="flex-1"
                  />
                  {optionPairs.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removeOption(idx)}
                      className="px-1 text-xs text-error hover:underline"
                    >
                      ✕
                    </button>
                  )}
                </div>
              ))}
              <button
                type="button"
                onClick={addOptionRow}
                className="text-xs font-semibold text-primary hover:underline"
              >
                + Add option
              </button>
            </div>

            {saveErr && <p className="text-sm text-error">{saveErr}</p>}
            <PrimaryButton type="submit" disabled={saving}>
              {saving ? "Creating…" : "Add variant"}
            </PrimaryButton>
          </form>

          {/* Variants list */}
          {loading ? (
            <p className="text-sm text-on-surface-variant">Loading…</p>
          ) : err ? (
            <p className="text-sm text-error">{err}</p>
          ) : variants.length === 0 ? (
            <p className="text-sm text-on-surface-variant">
              No variants yet. Add one above.
            </p>
          ) : (
            <table className="min-w-full text-left text-sm">
              <thead>
                <tr className="border-b border-outline-variant/10">
                  <th className="py-2 pr-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
                    SKU
                  </th>
                  <th className="py-2 pr-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
                    Name
                  </th>
                  <th className="py-2 pr-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
                    Options
                  </th>
                  <th className="py-2 pr-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
                    Price
                  </th>
                  <th className="py-2 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant/10">
                {variants.map((v) => (
                  <tr key={v.id}>
                    <td className="py-2 pr-3 font-mono text-xs text-on-surface">{v.sku}</td>
                    <td className="py-2 pr-3 text-on-surface">{v.name}</td>
                    <td className="py-2 pr-3">
                      <div className="flex flex-wrap gap-1">
                        {Object.entries(v.options).map(([k, val]) => (
                          <span
                            key={k}
                            className="rounded-full bg-surface-container px-2 py-0.5 text-[10px] text-on-surface-variant"
                          >
                            {k}: {val}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="py-2 pr-3 tabular-nums text-on-surface">
                      {(v.unit_price_cents / 100).toFixed(2)}
                    </td>
                    <td className="py-2">
                      <button
                        type="button"
                        onClick={() => void handleDelete(v.id)}
                        className="text-xs text-error hover:underline"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
