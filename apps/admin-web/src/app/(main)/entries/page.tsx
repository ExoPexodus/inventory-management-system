"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  Badge,
  PageHeader,
  Panel,
  PrimaryButton,
  SecondaryButton,
  SelectInput,
  TextInput,
} from "@/components/ui/primitives";

type Tenant = { id: string; name: string; slug: string };

type ProductGroup = { id: string; title: string };

export default function EntriesPage() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [tenantId, setTenantId] = useState("");
  const [shopName, setShopName] = useState("");
  const [sku, setSku] = useState("");
  const [pname, setPname] = useState("");
  const [price, setPrice] = useState("299");
  const [category, setCategory] = useState("");
  const [productGroups, setProductGroups] = useState<ProductGroup[]>([]);
  const [productGroupId, setProductGroupId] = useState("");
  const [variantLabel, setVariantLabel] = useState("");
  const [newGroupTitle, setNewGroupTitle] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

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
      const r = await fetch(`/api/ims/v1/admin/product-groups?tenant_id=${encodeURIComponent(tenantId)}`);
      if (r.ok) {
        const list = (await r.json()) as ProductGroup[];
        setProductGroups(list);
      }
    })();
  }, [tenantId]);

  async function addShop(e: FormEvent) {
    e.preventDefault();
    setMsg(null);
    const r = await fetch("/api/ims/v1/admin/shops", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tenant_id: tenantId, name: shopName }),
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
      body: JSON.stringify({ tenant_id: tenantId, title }),
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
      tenant_id: tenantId,
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
    <div className="space-y-7">
      <PageHeader
        kicker="New entry hub"
        title="Quick create"
        subtitle="Create shops, products, groups, and variants used by cashier and admin views."
      />
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="New shop">
          <form onSubmit={addShop}>
          <label className="mt-3 block text-xs font-medium text-primary/60">
            Tenant
            <SelectInput
              className="mt-1 w-full"
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
          <label className="mt-3 block text-xs font-medium text-primary/60">
            Shop name
            <TextInput
              required
              className="mt-1 w-full"
              value={shopName}
              onChange={(e) => setShopName(e.target.value)}
            />
          </label>
          <div className="mt-4">
            <PrimaryButton type="submit">Create shop</PrimaryButton>
          </div>
          </form>
        </Panel>
        <Panel title="New product">
          <form onSubmit={addProduct}>
          <label className="mt-3 block text-xs font-medium text-primary/60">
            Tenant
            <SelectInput
              className="mt-1 w-full"
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
          <label className="mt-3 block text-xs font-medium text-primary/60">
            SKU
            <TextInput
              required
              className="mt-1 w-full"
              value={sku}
              onChange={(e) => setSku(e.target.value)}
            />
          </label>
          <label className="mt-3 block text-xs font-medium text-primary/60">
            Name
            <TextInput
              required
              className="mt-1 w-full"
              value={pname}
              onChange={(e) => setPname(e.target.value)}
            />
          </label>
          <label className="mt-3 block text-xs font-medium text-primary/60">
            Price (USD)
            <TextInput
              required
              className="mt-1 w-full"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
            />
          </label>
          <label className="mt-3 block text-xs font-medium text-primary/60">
            Category
            <TextInput
              className="mt-1 w-full"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
            />
          </label>
          <details className="mt-4 rounded-lg border border-primary/15 bg-primary/[0.02] px-3 py-2">
            <summary className="cursor-pointer text-xs font-semibold text-primary/70">Variants (optional)</summary>
            <p className="mt-2 text-xs text-primary/55">
              Group related SKUs for clearer cashier lookup. Each row stays a separate product with its own stock.
            </p>
            <label className="mt-3 block text-xs font-medium text-primary/60">
              Product group
              <SelectInput
                className="mt-1 w-full"
                value={productGroupId}
                onChange={(e) => setProductGroupId(e.target.value)}
              >
                <option value="">None</option>
                {productGroups.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.title}
                  </option>
                ))}
              </SelectInput>
            </label>
            <label className="mt-2 block text-xs font-medium text-primary/60">
              Variant label (cashier subtitle)
              <TextInput
                className="mt-1 w-full"
                placeholder='e.g. A5 · recycled'
                value={variantLabel}
                onChange={(e) => setVariantLabel(e.target.value)}
              />
            </label>
            <div className="mt-3 flex flex-wrap items-end gap-2 border-t border-primary/10 pt-3">
              <label className="min-w-[12rem] flex-1 text-xs font-medium text-primary/60">
                New group title
                <TextInput
                  className="mt-1 w-full"
                  value={newGroupTitle}
                  onChange={(e) => setNewGroupTitle(e.target.value)}
                />
              </label>
              <SecondaryButton
                type="button"
                className="px-3 py-2"
                onClick={() => void createGroup()}
              >
                Save group
              </SecondaryButton>
            </div>
          </details>
          <div className="mt-4">
            <PrimaryButton type="submit">Create product</PrimaryButton>
          </div>
          </form>
        </Panel>
      </div>
      {msg ? <Badge tone="good">{msg}</Badge> : null}
    </div>
  );
}
