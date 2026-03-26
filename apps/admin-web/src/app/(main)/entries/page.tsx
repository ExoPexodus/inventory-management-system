"use client";

import { FormEvent, useEffect, useState } from "react";

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
    <div className="space-y-8">
      <header>
        <p className="text-xs font-semibold uppercase tracking-wider text-primary/50">New entry hub</p>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-primary">Quick create</h1>
      </header>
      <div className="grid gap-6 lg:grid-cols-2">
        <form onSubmit={addShop} className="rounded-xl border border-primary/10 bg-white/90 p-5 shadow-sm">
          <h2 className="font-display text-sm font-semibold text-primary">New shop</h2>
          <label className="mt-3 block text-xs font-medium text-primary/60">
            Tenant
            <select
              className="mt-1 w-full rounded-lg border border-primary/15 px-3 py-2 text-sm"
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
          <label className="mt-3 block text-xs font-medium text-primary/60">
            Shop name
            <input
              required
              className="mt-1 w-full rounded-lg border border-primary/15 px-3 py-2 text-sm"
              value={shopName}
              onChange={(e) => setShopName(e.target.value)}
            />
          </label>
          <button
            type="submit"
            className="mt-4 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90"
          >
            Create shop
          </button>
        </form>
        <form onSubmit={addProduct} className="rounded-xl border border-primary/10 bg-white/90 p-5 shadow-sm">
          <h2 className="font-display text-sm font-semibold text-primary">New product</h2>
          <label className="mt-3 block text-xs font-medium text-primary/60">
            Tenant
            <select
              className="mt-1 w-full rounded-lg border border-primary/15 px-3 py-2 text-sm"
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
          <label className="mt-3 block text-xs font-medium text-primary/60">
            SKU
            <input
              required
              className="mt-1 w-full rounded-lg border border-primary/15 px-3 py-2 text-sm"
              value={sku}
              onChange={(e) => setSku(e.target.value)}
            />
          </label>
          <label className="mt-3 block text-xs font-medium text-primary/60">
            Name
            <input
              required
              className="mt-1 w-full rounded-lg border border-primary/15 px-3 py-2 text-sm"
              value={pname}
              onChange={(e) => setPname(e.target.value)}
            />
          </label>
          <label className="mt-3 block text-xs font-medium text-primary/60">
            Price (USD)
            <input
              required
              className="mt-1 w-full rounded-lg border border-primary/15 px-3 py-2 text-sm"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
            />
          </label>
          <label className="mt-3 block text-xs font-medium text-primary/60">
            Category
            <input
              className="mt-1 w-full rounded-lg border border-primary/15 px-3 py-2 text-sm"
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
              <select
                className="mt-1 w-full rounded-lg border border-primary/15 bg-white px-3 py-2 text-sm"
                value={productGroupId}
                onChange={(e) => setProductGroupId(e.target.value)}
              >
                <option value="">None</option>
                {productGroups.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.title}
                  </option>
                ))}
              </select>
            </label>
            <label className="mt-2 block text-xs font-medium text-primary/60">
              Variant label (cashier subtitle)
              <input
                className="mt-1 w-full rounded-lg border border-primary/15 bg-white px-3 py-2 text-sm"
                placeholder='e.g. A5 · recycled'
                value={variantLabel}
                onChange={(e) => setVariantLabel(e.target.value)}
              />
            </label>
            <div className="mt-3 flex flex-wrap items-end gap-2 border-t border-primary/10 pt-3">
              <label className="min-w-[12rem] flex-1 text-xs font-medium text-primary/60">
                New group title
                <input
                  className="mt-1 w-full rounded-lg border border-primary/15 bg-white px-3 py-2 text-sm"
                  value={newGroupTitle}
                  onChange={(e) => setNewGroupTitle(e.target.value)}
                />
              </label>
              <button
                type="button"
                className="rounded-lg border border-primary/25 px-3 py-2 text-sm font-medium text-primary hover:bg-primary/5"
                onClick={() => void createGroup()}
              >
                Save group
              </button>
            </div>
          </details>
          <button
            type="submit"
            className="mt-4 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90"
          >
            Create product
          </button>
        </form>
      </div>
      {msg ? <p className="text-sm text-primary/80">{msg}</p> : null}
    </div>
  );
}
