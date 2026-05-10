"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Badge,
  Breadcrumbs,
  PageHeader,
  PrimaryButton,
  SecondaryButton,
  SelectInput,
  Tabs,
  TextInput,
  Toggle,
} from "@/components/ui/primitives";
import { useCurrency } from "@/lib/currency-context";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ProductGroup = { id: string; title: string };

interface StagedImage {
  file: File;
  previewUrl: string;
}

interface StagedVariant {
  sku: string;
  name: string;
  price: string;
  optionPairs: Array<{ key: string; value: string }>;
}

interface StagedPrice {
  currencyCode: string;
  amount: string;
}

// ---------------------------------------------------------------------------
// Details section
// ---------------------------------------------------------------------------

function DetailsSection({
  sku, setSku,
  pname, setPname,
  price, setPrice,
  category, setCategory,
  barcode, setBarcode,
  costPrice, setCostPrice,
  mrpPrice, setMrpPrice,
  hsnCode, setHsnCode,
  variantLabel, setVariantLabel,
  negativeInventory, setNegativeInventory,
  status, setStatus,
  productGroups, productGroupId, setProductGroupId,
  priceGuardWarning,
  currencyCode,
}: {
  sku: string; setSku: (v: string) => void;
  pname: string; setPname: (v: string) => void;
  price: string; setPrice: (v: string) => void;
  category: string; setCategory: (v: string) => void;
  barcode: string; setBarcode: (v: string) => void;
  costPrice: string; setCostPrice: (v: string) => void;
  mrpPrice: string; setMrpPrice: (v: string) => void;
  hsnCode: string; setHsnCode: (v: string) => void;
  variantLabel: string; setVariantLabel: (v: string) => void;
  negativeInventory: boolean; setNegativeInventory: (v: boolean) => void;
  status: string; setStatus: (v: string) => void;
  productGroups: ProductGroup[]; productGroupId: string; setProductGroupId: (v: string) => void;
  priceGuardWarning: string | null;
  currencyCode: string;
}) {
  return (
    <div className="space-y-6">
      <div className="space-y-4 rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
        <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Product details</p>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm font-medium text-on-surface">
            SKU *
            <TextInput required className="mt-1 font-mono" value={sku} onChange={(e) => setSku(e.target.value)} />
          </label>
          <label className="block text-sm font-medium text-on-surface">
            Category
            <TextInput className="mt-1" value={category} onChange={(e) => setCategory(e.target.value)} placeholder="e.g. Beverages" />
          </label>
        </div>
        <label className="block text-sm font-medium text-on-surface">
          Display name *
          <TextInput required className="mt-1" value={pname} onChange={(e) => setPname(e.target.value)} />
        </label>
        <label className="block text-sm font-medium text-on-surface">
          Price ({currencyCode}) *
          <TextInput required className="mt-1 tabular-nums" value={price} onChange={(e) => setPrice(e.target.value)} placeholder="0.00" />
        </label>
        {priceGuardWarning && <p className="text-sm text-error">{priceGuardWarning}</p>}
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm font-medium text-on-surface">
            Cost price
            <TextInput type="number" min="0" step="0.01" className="mt-1" value={costPrice} onChange={(e) => setCostPrice(e.target.value)} placeholder="e.g. 8.00" />
          </label>
          <label className="block text-sm font-medium text-on-surface">
            MRP
            <TextInput type="number" min="0" step="0.01" className="mt-1" value={mrpPrice} onChange={(e) => setMrpPrice(e.target.value)} placeholder="e.g. 25.00" />
          </label>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm font-medium text-on-surface">
            Barcode (UPC / EAN)
            <TextInput className="mt-1" value={barcode} onChange={(e) => setBarcode(e.target.value)} placeholder="e.g. 8901234567890" />
          </label>
          <label className="block text-sm font-medium text-on-surface">
            HSN code
            <TextInput className="mt-1" value={hsnCode} onChange={(e) => setHsnCode(e.target.value)} placeholder="e.g. 2101" />
          </label>
        </div>
        <label className="block text-sm font-medium text-on-surface">
          Variant label
          <TextInput className="mt-1" value={variantLabel} onChange={(e) => setVariantLabel(e.target.value)} placeholder="e.g. 12oz · cold" />
        </label>
        <label className="block text-sm font-medium text-on-surface">
          Product group
          <SelectInput
            value={productGroupId}
            onChange={setProductGroupId}
            options={[{ value: "", label: "None" }, ...productGroups.map((g) => ({ value: g.id, label: g.title }))]}
          />
        </label>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm font-medium text-on-surface">
            Status
            <SelectInput
              value={status}
              onChange={setStatus}
              options={[{ value: "active", label: "Active" }, { value: "draft", label: "Draft" }]}
            />
          </label>
        </div>
        <div className="flex items-center gap-3">
          <Toggle checked={negativeInventory} onChange={setNegativeInventory} />
          <span className="text-sm font-medium text-on-surface">Allow sales when stock reaches zero</span>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Images section
// ---------------------------------------------------------------------------

function ImagesSection({
  stagedImages,
  onAdd,
  onRemove,
}: {
  stagedImages: StagedImage[];
  onAdd: (files: File[]) => void;
  onRemove: (index: number) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const ALLOWED = new Set(["image/jpeg", "image/png", "image/webp", "image/gif", "image/avif"]);
  const MAX_MB = 10;

  function handleFiles(files: FileList | null) {
    if (!files) return;
    const valid = Array.from(files).filter((f) => {
      if (!ALLOWED.has(f.type)) return false;
      if (f.size > MAX_MB * 1024 * 1024) return false;
      return true;
    });
    const remaining = 10 - stagedImages.length;
    onAdd(valid.slice(0, remaining));
  }

  return (
    <div className="space-y-6">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); handleFiles(e.dataTransfer.files); }}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-12 text-center transition ${
          dragging ? "border-primary bg-primary/5" : "border-outline-variant/30 bg-surface-container-lowest/40 hover:bg-surface-container-lowest/80"
        }`}
        onClick={() => inputRef.current?.click()}
      >
        <span className="material-symbols-outlined mb-3 text-4xl text-on-surface-variant">add_a_photo</span>
        <p className="text-sm font-medium text-on-surface">Drop images here or click to browse</p>
        <p className="mt-1 text-xs text-on-surface-variant">JPEG, PNG, WebP, GIF, AVIF · max 10 MB each · up to 10 images</p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept="image/jpeg,image/png,image/webp,image/gif,image/avif"
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {stagedImages.length > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {stagedImages.map((img, i) => (
            <div key={i} className="group relative overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={img.previewUrl} alt={img.file.name} className="h-32 w-full object-cover" />
              <div className="p-2">
                <p className="truncate text-[10px] text-on-surface-variant">{img.file.name}</p>
                <p className="text-[10px] text-on-surface-variant/60">{(img.file.size / 1024 / 1024).toFixed(1)} MB</p>
              </div>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); onRemove(i); }}
                className="absolute right-1.5 top-1.5 flex h-6 w-6 items-center justify-center rounded-full bg-black/50 text-white opacity-0 transition-opacity group-hover:opacity-100"
              >
                <span className="material-symbols-outlined text-[14px]">close</span>
              </button>
            </div>
          ))}
        </div>
      )}

      {stagedImages.length === 0 && (
        <p className="text-center text-xs text-on-surface-variant">
          Images will be uploaded when you save the product.
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Variants section
// ---------------------------------------------------------------------------

function VariantsSection({
  stagedVariants,
  onAdd,
  onRemove,
  currencyCode,
}: {
  stagedVariants: StagedVariant[];
  onAdd: (v: StagedVariant) => void;
  onRemove: (index: number) => void;
  currencyCode: string;
}) {
  const [sku, setSku] = useState("");
  const [name, setName] = useState("");
  const [price, setPrice] = useState("");
  const [pairs, setPairs] = useState([{ key: "", value: "" }]);
  const [err, setErr] = useState<string | null>(null);

  function handleAdd() {
    if (!sku.trim() || !name.trim() || !price.trim()) {
      setErr("SKU, name, and price are required");
      return;
    }
    if (isNaN(parseFloat(price)) || parseFloat(price) <= 0) {
      setErr("Enter a valid price");
      return;
    }
    onAdd({ sku: sku.trim(), name: name.trim(), price, optionPairs: pairs });
    setSku(""); setName(""); setPrice(""); setPairs([{ key: "", value: "" }]); setErr(null);
  }

  return (
    <div className="space-y-6">
      <div className="space-y-4 rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
        <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Add variant</p>
        {err && <p className="text-sm text-error">{err}</p>}
        <div className="grid gap-4 sm:grid-cols-3">
          <label className="block text-sm font-medium text-on-surface">
            SKU *
            <TextInput className="mt-1 font-mono" value={sku} onChange={(e) => setSku(e.target.value)} placeholder="SKU-M" />
          </label>
          <label className="block text-sm font-medium text-on-surface">
            Name *
            <TextInput className="mt-1" value={name} onChange={(e) => setName(e.target.value)} placeholder="Medium" />
          </label>
          <label className="block text-sm font-medium text-on-surface">
            Price ({currencyCode}) *
            <TextInput className="mt-1 tabular-nums" value={price} onChange={(e) => setPrice(e.target.value)} placeholder="0.00" />
          </label>
        </div>
        <div className="space-y-2">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Options</p>
          {pairs.map((p, i) => (
            <div key={i} className="flex gap-2">
              <TextInput className="flex-1" value={p.key} onChange={(e) => setPairs(pairs.map((x, j) => j === i ? { ...x, key: e.target.value } : x))} placeholder="e.g. Size" />
              <TextInput className="flex-1" value={p.value} onChange={(e) => setPairs(pairs.map((x, j) => j === i ? { ...x, value: e.target.value } : x))} placeholder="e.g. M" />
              {pairs.length > 1 && (
                <button type="button" onClick={() => setPairs(pairs.filter((_, j) => j !== i))} className="text-on-surface-variant hover:text-error">
                  <span className="material-symbols-outlined text-lg">close</span>
                </button>
              )}
            </div>
          ))}
          <button type="button" onClick={() => setPairs([...pairs, { key: "", value: "" }])} className="text-xs font-semibold text-primary hover:underline">
            + Add option
          </button>
        </div>
        <SecondaryButton type="button" onClick={handleAdd}>Add variant</SecondaryButton>
      </div>

      {stagedVariants.length > 0 ? (
        <div className="overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest">
          <table className="min-w-full text-sm">
            <thead className="bg-surface-container-low text-[10px] uppercase tracking-widest text-on-surface-variant/60">
              <tr>
                <th className="px-4 py-3 text-left font-bold">Name</th>
                <th className="px-4 py-3 text-left font-bold">SKU</th>
                <th className="px-4 py-3 text-left font-bold">Price</th>
                <th className="px-4 py-3 text-left font-bold">Options</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {stagedVariants.map((v, i) => (
                <tr key={i}>
                  <td className="px-4 py-3 font-medium text-on-surface">{v.name}</td>
                  <td className="px-4 py-3 font-mono text-xs text-on-surface-variant">{v.sku}</td>
                  <td className="px-4 py-3 text-on-surface-variant">{v.price}</td>
                  <td className="px-4 py-3 text-xs text-on-surface-variant">
                    {v.optionPairs.filter(p => p.key).map(p => `${p.key}: ${p.value}`).join(", ") || "—"}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button type="button" onClick={() => onRemove(i)} className="text-on-surface-variant hover:text-error">
                      <span className="material-symbols-outlined text-lg">delete</span>
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-center text-sm text-on-surface-variant">No variants yet — add size, colour, or other options above.</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Prices section
// ---------------------------------------------------------------------------

function PricesSection({
  stagedPrices,
  onAdd,
  onRemove,
}: {
  stagedPrices: StagedPrice[];
  onAdd: (p: StagedPrice) => void;
  onRemove: (index: number) => void;
}) {
  const [currencyCode, setCurrencyCode] = useState("");
  const [amount, setAmount] = useState("");
  const [err, setErr] = useState<string | null>(null);

  function handleAdd() {
    const code = currencyCode.trim().toUpperCase();
    if (code.length !== 3) { setErr("Enter a valid 3-letter currency code"); return; }
    if (isNaN(parseFloat(amount)) || parseFloat(amount) <= 0) { setErr("Enter a valid amount"); return; }
    onAdd({ currencyCode: code, amount });
    setCurrencyCode(""); setAmount(""); setErr(null);
  }

  return (
    <div className="space-y-6">
      <div className="space-y-4 rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
        <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Add price</p>
        {err && <p className="text-sm text-error">{err}</p>}
        <div className="flex gap-3">
          <label className="block text-sm font-medium text-on-surface">
            Currency
            <TextInput className="mt-1 w-24 font-mono uppercase" value={currencyCode} onChange={(e) => setCurrencyCode(e.target.value)} placeholder="USD" maxLength={3} />
          </label>
          <label className="block flex-1 text-sm font-medium text-on-surface">
            Amount
            <TextInput type="number" min="0" step="0.01" className="mt-1 tabular-nums" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="0.00" />
          </label>
        </div>
        <SecondaryButton type="button" onClick={handleAdd}>Add price</SecondaryButton>
      </div>

      {stagedPrices.length > 0 ? (
        <div className="space-y-2">
          {stagedPrices.map((p, i) => (
            <div key={i} className="flex items-center justify-between rounded-xl border border-outline-variant/10 bg-surface-container-lowest px-4 py-3">
              <span className="font-semibold text-on-surface">{p.currencyCode}</span>
              <span className="tabular-nums text-on-surface-variant">{p.amount}</span>
              <button type="button" onClick={() => onRemove(i)} className="text-on-surface-variant hover:text-error">
                <span className="material-symbols-outlined text-lg">delete</span>
              </button>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-center text-sm text-on-surface-variant">No additional prices — your default price is set on the Details tab.</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function EntriesPage() {
  const router = useRouter();
  const currency = useCurrency();

  const [activeTab, setActiveTab] = useState("details");

  // Details state
  const [sku, setSku] = useState("");
  const [pname, setPname] = useState("");
  const [price, setPrice] = useState("");
  const [category, setCategory] = useState("");
  const [barcode, setBarcode] = useState("");
  const [costPrice, setCostPrice] = useState("");
  const [mrpPrice, setMrpPrice] = useState("");
  const [hsnCode, setHsnCode] = useState("");
  const [variantLabel, setVariantLabel] = useState("");
  const [negativeInventory, setNegativeInventory] = useState(false);
  const [status, setStatus] = useState("active");
  const [productGroups, setProductGroups] = useState<ProductGroup[]>([]);
  const [productGroupId, setProductGroupId] = useState("");

  // Staged collections
  const [stagedImages, setStagedImages] = useState<StagedImage[]>([]);
  const [stagedVariants, setStagedVariants] = useState<StagedVariant[]>([]);
  const [stagedPrices, setStagedPrices] = useState<StagedPrice[]>([]);

  // Save state
  const [savePhase, setSavePhase] = useState<"idle" | "saving">("idle");
  const [saveProgress, setSaveProgress] = useState("");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveWarnings, setSaveWarnings] = useState<string[]>([]);

  useEffect(() => {
    void fetch("/api/ims/v1/admin/product-groups")
      .then((r) => r.ok ? r.json() : [])
      .then((data) => setProductGroups(data as ProductGroup[]));
  }, []);

  // Revoke preview URLs on unmount
  useEffect(() => {
    return () => {
      for (const img of stagedImages) URL.revokeObjectURL(img.previewUrl);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const previewPriceCents = Math.round(parseFloat(price) * 100);
  const previewCostCents = costPrice.trim() ? Math.round(parseFloat(costPrice) * 100) : null;
  const previewMrpCents = mrpPrice.trim() ? Math.round(parseFloat(mrpPrice) * 100) : null;
  const priceGuardWarning = (() => {
    if (!price.trim() || isNaN(previewPriceCents)) return null;
    if (previewCostCents !== null && previewPriceCents < previewCostCents) return "Selling price is below cost price.";
    if (previewMrpCents !== null && previewPriceCents > previewMrpCents) return "Selling price exceeds MRP.";
    return null;
  })();

  function addImage(files: File[]) {
    const newImgs = files.map((f) => ({ file: f, previewUrl: URL.createObjectURL(f) }));
    setStagedImages((prev) => [...prev, ...newImgs]);
  }

  function removeImage(index: number) {
    setStagedImages((prev) => {
      URL.revokeObjectURL(prev[index]!.previewUrl);
      return prev.filter((_, i) => i !== index);
    });
  }

  async function handleSave() {
    if (!sku.trim() || !pname.trim()) { setSaveError("SKU and name are required"); return; }
    const unit = Math.round(parseFloat(price) * 100);
    if (isNaN(unit) || unit <= 0) { setSaveError("Enter a valid price"); return; }

    setSavePhase("saving");
    setSaveError(null);
    setSaveWarnings([]);
    const warnings: string[] = [];

    // 1. Create product
    setSaveProgress("Creating product…");
    const body: Record<string, unknown> = {
      sku: sku.trim(), name: pname.trim(), unit_price_cents: unit,
      category: category.trim() || null,
      barcode: barcode.trim() || null,
      cost_price_cents: previewCostCents,
      mrp_cents: previewMrpCents,
      hsn_code: hsnCode.trim() || null,
      negative_inventory_allowed: negativeInventory,
      status,
    };
    if (productGroupId) body.product_group_id = productGroupId;
    if (variantLabel.trim()) body.variant_label = variantLabel.trim();

    const productRes = await fetch("/api/ims/v1/admin/products", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!productRes.ok) {
      const d = await productRes.json().catch(() => ({})) as { detail?: string };
      setSaveError(d.detail ?? `Product creation failed (${productRes.status})`);
      setSavePhase("idle");
      return;
    }
    const product = (await productRes.json()) as { id: string };

    // 2. Upload images
    for (let i = 0; i < stagedImages.length; i++) {
      const img = stagedImages[i]!;
      setSaveProgress(`Uploading images (${i + 1} of ${stagedImages.length})…`);
      try {
        const presignRes = await fetch("/api/ims/v1/admin/media/presign-upload", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            folder: `products/${product.id}`,
            filename: img.file.name,
            content_type: img.file.type,
            file_size_bytes: img.file.size,
          }),
        });
        if (!presignRes.ok) {
          warnings.push(`Image "${img.file.name}" failed to upload — add it from the product page later.`);
          continue;
        }
        const { upload_url, public_url } = (await presignRes.json()) as { upload_url: string; public_url: string };
        const putRes = await fetch(upload_url, { method: "PUT", body: img.file, headers: { "Content-Type": img.file.type } });
        if (!putRes.ok) {
          warnings.push(`Image "${img.file.name}" upload failed — add it from the product page later.`);
          continue;
        }
        await fetch(`/api/ims/v1/admin/catalog/products/${product.id}/images`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url: public_url, sort_order: i, file_size_bytes: img.file.size }),
        });
      } catch {
        warnings.push(`Image "${img.file.name}" failed — add it from the product page later.`);
      }
    }

    // 3. Create variants
    if (stagedVariants.length > 0) {
      setSaveProgress("Adding variants…");
      for (const v of stagedVariants) {
        const options: Record<string, string> = {};
        for (const p of v.optionPairs) { if (p.key.trim()) options[p.key.trim()] = p.value.trim(); }
        const vRes = await fetch(`/api/ims/v1/admin/products/${product.id}/variants`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sku: v.sku, name: v.name, unit_price_cents: Math.round(parseFloat(v.price) * 100), options }),
        });
        if (!vRes.ok) warnings.push(`Variant "${v.name}" failed to save — add it from the product page later.`);
      }
    }

    // 4. Create prices
    if (stagedPrices.length > 0) {
      setSaveProgress("Adding prices…");
      for (const p of stagedPrices) {
        const pRes = await fetch(`/api/ims/v1/admin/products/${product.id}/prices`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ currency_code: p.currencyCode, amount_cents: Math.round(parseFloat(p.amount) * 100), channel_id: null }),
        });
        if (!pRes.ok) warnings.push(`Price (${p.currencyCode}) failed to save — add it from the product page later.`);
      }
    }

    setSaveWarnings(warnings);
    setSavePhase("idle");
    router.push("/products");
  }

  const tabs = [
    { id: "details",  label: "Details" },
    { id: "images",   label: `Images${stagedImages.length > 0 ? ` (${stagedImages.length})` : ""}` },
    { id: "variants", label: `Variants${stagedVariants.length > 0 ? ` (${stagedVariants.length})` : ""}` },
    { id: "prices",   label: `Prices${stagedPrices.length > 0 ? ` (${stagedPrices.length})` : ""}` },
  ];

  const saving = savePhase === "saving";

  return (
    <div className="space-y-8">
      <Breadcrumbs items={[{ label: "Catalog", href: "/products" }, { label: "Create product" }]} />
      <PageHeader kicker="New product" title="Create Product" subtitle="Fill in the details, then save — everything uploads in one go." />

      {saveError && (
        <div className="rounded-xl border border-error/20 bg-error-container/30 px-4 py-3 text-sm text-on-error-container">{saveError}</div>
      )}
      {saveWarnings.length > 0 && (
        <div className="rounded-xl border border-amber-400/30 bg-amber-50 px-4 py-3 space-y-1">
          {saveWarnings.map((w, i) => (
            <p key={i} className="text-sm text-amber-800">{w}</p>
          ))}
        </div>
      )}

      <Tabs tabs={tabs} active={activeTab} onChange={setActiveTab} />

      <div className="min-h-[20rem]">
        {activeTab === "details" && (
          <DetailsSection
            sku={sku} setSku={setSku}
            pname={pname} setPname={setPname}
            price={price} setPrice={setPrice}
            category={category} setCategory={setCategory}
            barcode={barcode} setBarcode={setBarcode}
            costPrice={costPrice} setCostPrice={setCostPrice}
            mrpPrice={mrpPrice} setMrpPrice={setMrpPrice}
            hsnCode={hsnCode} setHsnCode={setHsnCode}
            variantLabel={variantLabel} setVariantLabel={setVariantLabel}
            negativeInventory={negativeInventory} setNegativeInventory={setNegativeInventory}
            status={status} setStatus={setStatus}
            productGroups={productGroups} productGroupId={productGroupId} setProductGroupId={setProductGroupId}
            priceGuardWarning={priceGuardWarning}
            currencyCode={currency.code}
          />
        )}
        {activeTab === "images" && (
          <ImagesSection stagedImages={stagedImages} onAdd={addImage} onRemove={removeImage} />
        )}
        {activeTab === "variants" && (
          <VariantsSection
            stagedVariants={stagedVariants}
            onAdd={(v) => setStagedVariants((prev) => [...prev, v])}
            onRemove={(i) => setStagedVariants((prev) => prev.filter((_, j) => j !== i))}
            currencyCode={currency.code}
          />
        )}
        {activeTab === "prices" && (
          <PricesSection
            stagedPrices={stagedPrices}
            onAdd={(p) => setStagedPrices((prev) => [...prev, p])}
            onRemove={(i) => setStagedPrices((prev) => prev.filter((_, j) => j !== i))}
          />
        )}
      </div>

      <div className="sticky bottom-0 flex items-center justify-between border-t border-outline-variant/15 bg-background/90 py-4 backdrop-blur-md">
        <p className="text-sm text-on-surface-variant">
          {saving ? saveProgress : `${stagedImages.length} image${stagedImages.length !== 1 ? "s" : ""} · ${stagedVariants.length} variant${stagedVariants.length !== 1 ? "s" : ""} · ${stagedPrices.length} price${stagedPrices.length !== 1 ? "s" : ""} queued`}
        </p>
        <PrimaryButton type="button" onClick={() => void handleSave()} disabled={saving}>
          {saving ? "Saving…" : "Save product →"}
        </PrimaryButton>
      </div>
    </div>
  );
}
