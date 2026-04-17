"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  Badge,
  Breadcrumbs,
  DropZone,
  PageHeader,
  PrimaryButton,
  SecondaryButton,
  SelectInput,
  TextInput,
} from "@/components/ui/primitives";
import { formatMoney } from "@/lib/format";
import { useCurrency } from "@/lib/currency-context";

type ProductGroup = { id: string; title: string };

export default function EntriesPage() {
  const currency = useCurrency();
  const [sku, setSku] = useState("");
  const [pname, setPname] = useState("");
  const [price, setPrice] = useState("");
  const [category, setCategory] = useState("");
  const [productGroups, setProductGroups] = useState<ProductGroup[]>([]);
  const [productGroupId, setProductGroupId] = useState("");
  const [variantLabel, setVariantLabel] = useState("");
  const [newGroupTitle, setNewGroupTitle] = useState("");
  const [assetHint, setAssetHint] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      const r = await fetch("/api/ims/v1/admin/product-groups");
      if (r.ok) setProductGroups((await r.json()) as ProductGroup[]);
    })();
  }, []);

  const selectedGroupTitle = productGroups.find((g) => g.id === productGroupId)?.title ?? null;
  const previewPriceCents = Math.round(parseFloat(price) * 100);
  const priceOk = !Number.isNaN(previewPriceCents) && previewPriceCents > 0;

  async function createGroup() {
    setMsg(null);
    const title = newGroupTitle.trim();
    if (!title) {
      setMsg("Group title required");
      return;
    }
    const r = await fetch("/api/ims/v1/admin/product-groups", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    if (r.ok) {
      setNewGroupTitle("");
      const g = (await r.json()) as ProductGroup;
      setProductGroups((prev) => [...prev, g].sort((a, b) => a.title.localeCompare(b.title)));
      setProductGroupId(g.id);
      setMsg("Group created");
    } else {
      setMsg(`Group failed (${r.status})`);
    }
  }

  async function addProduct(e: FormEvent) {
    e.preventDefault();
    setMsg(null);
    const unit = Math.round(parseFloat(price) * 100);
    if (Number.isNaN(unit) || unit <= 0) {
      setMsg("Price must be a positive number");
      return;
    }
    const body: Record<string, unknown> = {
      sku,
      name: pname,
      unit_price_cents: unit,
      category: category || null,
    };
    if (productGroupId) body.product_group_id = productGroupId;
    const vl = variantLabel.trim();
    if (vl) body.variant_label = vl;

    const r = await fetch("/api/ims/v1/admin/products", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    setMsg(r.ok ? "Product created" : `Product failed (${r.status})`);
    if (r.ok) {
      setSku("");
      setPname("");
      setVariantLabel("");
    }
  }

  return (
    <div className="space-y-8">
      <Breadcrumbs
        items={[
          { label: "Catalog", href: "/products" },
          { label: "New entry hub" },
        ]}
      />
      <PageHeader
        kicker="New entry hub"
        title="Create Product"
        subtitle="Fill in the details below — see a live preview on the right."
      />

      <div className="grid grid-cols-12 gap-6">
        <form onSubmit={addProduct} className="col-span-12 space-y-6 lg:col-span-7">
          {msg ? (
            <Badge tone={msg === "Product created" || msg === "Group created" ? "good" : "danger"}>{msg}</Badge>
          ) : null}

          {/* Product Details */}
          <div className="space-y-4 rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
            <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Product details</p>
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block text-sm font-medium text-on-surface">
                SKU
                <TextInput required className="mt-1 font-mono" value={sku} onChange={(e) => setSku(e.target.value)} />
              </label>
              <label className="block text-sm font-medium text-on-surface">
                Category
                <TextInput className="mt-1" value={category} onChange={(e) => setCategory(e.target.value)} placeholder="e.g. Beverages" />
              </label>
            </div>
            <label className="block text-sm font-medium text-on-surface">
              Display name
              <TextInput required className="mt-1" value={pname} onChange={(e) => setPname(e.target.value)} />
            </label>
            <label className="block text-sm font-medium text-on-surface">
              Price ({currency.code})
              <TextInput required className="mt-1 tabular-nums" value={price} onChange={(e) => setPrice(e.target.value)} />
            </label>
          </div>

          {/* Product Image */}
          <div className="space-y-4 rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
            <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Product image</p>
            {/* Image file is queued for display only — upload endpoint not yet implemented */}
            <DropZone
              onChange={(e) => {
                const f = e.target.files?.[0];
                setAssetHint(f ? `Queued: ${f.name}` : null);
              }}
            />
            {assetHint ? <p className="text-xs text-on-surface-variant">{assetHint}</p> : null}
          </div>

          {/* Variants */}
          <div className="space-y-4 rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
            <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">
              Variants{" "}
              <span className="text-[10px] font-normal normal-case tracking-normal text-on-surface-variant/60">
                optional
              </span>
            </p>
            <SelectInput
              value={productGroupId}
              onChange={setProductGroupId}
              options={[
                { value: "", label: "None" },
                ...productGroups.map((g) => ({ value: g.id, label: g.title })),
              ]}
            />
            <label className="block text-sm font-medium text-on-surface">
              Variant label
              <TextInput
                className="mt-1"
                placeholder="e.g. 12oz · cold"
                value={variantLabel}
                onChange={(e) => setVariantLabel(e.target.value)}
              />
            </label>
            <div className="flex flex-wrap gap-2 border-t border-outline-variant/10 pt-4">
              <TextInput
                className="min-w-[12rem] flex-1"
                placeholder="New group title"
                value={newGroupTitle}
                onChange={(e) => setNewGroupTitle(e.target.value)}
              />
              <SecondaryButton type="button" onClick={() => void createGroup()}>
                Save group
              </SecondaryButton>
            </div>
          </div>

          <PrimaryButton type="submit">Commit product</PrimaryButton>
        </form>

        {/* Right panel */}
        <div className="col-span-12 lg:col-span-5">
          <div className="sticky top-6 space-y-4">
            {/* Live Preview */}
            <div className="overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm">
              <div className="ink-gradient px-6 py-4">
                <p className="text-xs font-bold uppercase tracking-widest text-on-primary/90">Live preview</p>
                <p className="mt-1 font-headline text-xl font-extrabold text-on-primary">{pname || "Product name"}</p>
              </div>
              <div className="space-y-3 p-6">
                <p className="font-headline text-3xl font-extrabold text-primary">
                  {priceOk ? formatMoney(previewPriceCents, currency) : "—"}
                </p>
                <div className="flex flex-wrap gap-2 text-sm">
                  <Badge tone="default">SKU {sku || "—"}</Badge>
                  <Badge tone="good">{category || "Category"}</Badge>
                  {variantLabel ? <Badge tone="warn">{variantLabel}</Badge> : null}
                </div>
                <p className="text-xs text-on-surface-variant">
                  Tenant scope is derived from your signed-in organization.
                </p>
              </div>
            </div>

            {/* Summary */}
            <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
              <p className="mb-4 text-xs font-bold uppercase tracking-widest text-on-surface-variant">Summary</p>
              <ul className="space-y-2 text-sm">
                <li className="flex justify-between">
                  <span className="text-on-surface-variant">SKU</span>
                  <span className="font-mono font-semibold">{sku || "—"}</span>
                </li>
                <li className="flex justify-between">
                  <span className="text-on-surface-variant">Category</span>
                  <span className={category ? "" : "italic text-on-surface-variant/60"}>
                    {category || "Uncategorized"}
                  </span>
                </li>
                <li className="flex justify-between">
                  <span className="text-on-surface-variant">Variant</span>
                  <span className={variantLabel ? "" : "italic text-on-surface-variant/60"}>
                    {variantLabel || "Standard"}
                  </span>
                </li>
                <li className="flex justify-between">
                  <span className="text-on-surface-variant">Group</span>
                  <span className={selectedGroupTitle ? "" : "italic text-on-surface-variant/60"}>
                    {selectedGroupTitle ?? "Ungrouped"}
                  </span>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
