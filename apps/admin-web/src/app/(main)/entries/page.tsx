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
  Tabs,
  TextInput,
} from "@/components/ui/primitives";
import { formatMoney } from "@/lib/format";
import { useCurrency } from "@/lib/currency-context";

type ProductGroup = { id: string; title: string };

export default function EntriesPage() {
  const currency = useCurrency();
  const [tab, setTab] = useState("details");
  const [shopName, setShopName] = useState("");
  const [sku, setSku] = useState("");
  const [pname, setPname] = useState("");
  const [price, setPrice] = useState("29.99");
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
  const priceOk = !Number.isNaN(previewPriceCents);

  async function addShop(e: FormEvent) {
    e.preventDefault();
    setMsg(null);
    const r = await fetch("/api/ims/v1/admin/shops", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: shopName }),
    });
    setMsg(r.ok ? "Shop created" : `Shop failed (${r.status})`);
    if (r.ok) setShopName("");
  }

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
    if (Number.isNaN(unit)) {
      setMsg("Invalid price");
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
        title="Create shops & SKUs"
        subtitle="One surface for structural catalog changes — preview before you commit."
      />

      <Tabs
        tabs={[
          { id: "details", label: "Details" },
          { id: "provenance", label: "Provenance" },
          { id: "logistics", label: "Logistics" },
        ]}
        active={tab}
        onChange={setTab}
      />

      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-12 space-y-6 lg:col-span-7">
          {msg ? (
            <Badge tone={msg.includes("failed") ? "danger" : "good"}>{msg}</Badge>
          ) : null}

          {tab === "details" ? (
            <div className="space-y-6 rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
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
                Price (USD)
                <TextInput required className="mt-1 tabular-nums" value={price} onChange={(e) => setPrice(e.target.value)} />
              </label>
            </div>
          ) : null}

          {tab === "provenance" ? (
            <div className="space-y-6 rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
              <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Visual provenance</p>
              <DropZone
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  setAssetHint(f ? `Queued: ${f.name}` : null);
                }}
              />
              <div>
                <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Variant grouping</p>
                <SelectInput
                  className="mt-2"
                  value={productGroupId}
                  onChange={setProductGroupId}
                  placeholder="None"
                  options={[
                    { value: "", label: "None" },
                    ...productGroups.map((g) => ({ value: g.id, label: g.title })),
                  ]}
                />
                <label className="mt-3 block text-sm font-medium text-on-surface">
                  Variant label
                  <TextInput
                    className="mt-1"
                    placeholder="e.g. 12oz · cold"
                    value={variantLabel}
                    onChange={(e) => setVariantLabel(e.target.value)}
                  />
                </label>
                <div className="mt-4 flex flex-wrap gap-2 border-t border-outline-variant/10 pt-4">
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
              {assetHint ? <p className="text-xs text-on-surface-variant">{assetHint}</p> : null}
            </div>
          ) : null}

          {tab === "logistics" ? (
            <div className="space-y-4 rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
              <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Logistics confirmation</p>
              <ul className="space-y-2 text-sm text-on-surface">
                <li>
                  <span className="text-on-surface-variant">SKU · </span>
                  <span className="font-mono font-semibold">{sku || "—"}</span>
                </li>
                <li>
                  <span className="text-on-surface-variant">Category · </span>
                  <span>{category || "Uncategorized"}</span>
                </li>
                <li>
                  <span className="text-on-surface-variant">Variant · </span>
                  <span>{variantLabel || "Standard"}</span>
                </li>
                <li>
                  <span className="text-on-surface-variant">Group · </span>
                  <span>{selectedGroupTitle ?? "Ungrouped"}</span>
                </li>
              </ul>
              <PrimaryButton type="button" onClick={() => setTab("details")}>
                Back to edit
              </PrimaryButton>
            </div>
          ) : null}

          <form onSubmit={addShop} className="space-y-4 rounded-xl border border-outline-variant/10 bg-surface-container-low p-6 shadow-sm">
            <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Create shop</p>
            <label className="block text-sm font-medium text-on-surface">
              Shop name
              <TextInput required className="mt-1" value={shopName} onChange={(e) => setShopName(e.target.value)} />
            </label>
            <PrimaryButton type="submit">Create shop</PrimaryButton>
          </form>

          <form onSubmit={addProduct} className="space-y-4 rounded-xl border border-outline-variant/10 bg-surface-container-low p-6 shadow-sm">
            <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Create product</p>
            <PrimaryButton type="submit">Commit product</PrimaryButton>
          </form>
        </div>

        <div className="col-span-12 lg:col-span-5">
          <div className="sticky top-6 overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm">
            <div className="ink-gradient px-6 py-4">
              <p className="text-xs font-bold uppercase tracking-widest text-on-primary/90">Live preview</p>
              <p className="mt-1 font-headline text-xl font-extrabold text-on-primary">{pname || "Product name"}</p>
            </div>
            <div className="space-y-3 p-6">
              <p className="font-headline text-3xl font-extrabold text-primary">{priceOk ? formatMoney(previewPriceCents, currency) : "—"}</p>
              <div className="flex flex-wrap gap-2 text-sm">
                <Badge tone="default">SKU {sku || "—"}</Badge>
                <Badge tone="good">{category || "Category"}</Badge>
                {variantLabel ? <Badge tone="warn">{variantLabel}</Badge> : null}
              </div>
              <p className="text-xs text-on-surface-variant">Tenant scope is derived from your signed-in organization.</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
