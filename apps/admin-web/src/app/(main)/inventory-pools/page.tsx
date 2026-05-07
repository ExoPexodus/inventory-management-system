"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Badge,
  PageHeader,
  Panel,
  PrimaryButton,
  SecondaryButton,
  SelectInput,
  TextInput,
} from "@/components/ui/primitives";

type Shop = { id: string; name: string };

type InventoryPool = {
  id: string;
  name: string;
  fulfillment_policy: string;
  shop_ids: string[];
  created_at: string;
};

const POLICY_OPTIONS = [
  { value: "fulfill_from_primary", label: "Fulfill from primary shop" },
  { value: "split_proportionally", label: "Split proportionally across shops" },
  { value: "manual_at_fulfillment", label: "Manual selection at fulfillment" },
];

function policyLabel(policy: string): string {
  return POLICY_OPTIONS.find((o) => o.value === policy)?.label ?? policy;
}

export default function InventoryPoolsPage() {
  const [pools, setPools] = useState<InventoryPool[]>([]);
  const [shops, setShops] = useState<Shop[]>([]);
  const [loading, setLoading] = useState(true);

  // Create form
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [policy, setPolicy] = useState("fulfill_from_primary");
  const [selectedShopIds, setSelectedShopIds] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Edit state
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editPolicy, setEditPolicy] = useState("fulfill_from_primary");
  const [editShopIds, setEditShopIds] = useState<string[]>([]);
  const [editSaving, setEditSaving] = useState(false);
  const [editErr, setEditErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [poolsRes, shopsRes] = await Promise.all([
        fetch("/api/ims/v1/admin/inventory-pools"),
        fetch("/api/ims/v1/admin/shops"),
      ]);
      if (poolsRes.ok) setPools((await poolsRes.json()) as InventoryPool[]);
      if (shopsRes.ok) setShops((await shopsRes.json()) as Shop[]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  function toggleShop(shopId: string, list: string[], setList: (v: string[]) => void) {
    setList(list.includes(shopId) ? list.filter((id) => id !== shopId) : [...list, shopId]);
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setErr(null);
    const r = await fetch("/api/ims/v1/admin/inventory-pools", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name.trim(), fulfillment_policy: policy, shop_ids: selectedShopIds }),
    });
    if (r.ok) {
      setShowForm(false);
      setName(""); setPolicy("fulfill_from_primary"); setSelectedShopIds([]);
      void load();
    } else {
      const d = await r.json().catch(() => ({})) as { detail?: string };
      setErr(d.detail ?? `Failed (${r.status})`);
    }
    setSaving(false);
  }

  function startEdit(pool: InventoryPool) {
    setEditingId(pool.id);
    setEditName(pool.name);
    setEditPolicy(pool.fulfillment_policy);
    setEditShopIds([...pool.shop_ids]);
    setEditErr(null);
  }

  async function handleEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!editingId) return;
    setEditSaving(true);
    setEditErr(null);
    const r = await fetch(`/api/ims/v1/admin/inventory-pools/${editingId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: editName.trim(), fulfillment_policy: editPolicy, shop_ids: editShopIds }),
    });
    if (r.ok) {
      setEditingId(null);
      void load();
    } else {
      const d = await r.json().catch(() => ({})) as { detail?: string };
      setEditErr(d.detail ?? `Failed (${r.status})`);
    }
    setEditSaving(false);
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this inventory pool? This cannot be undone.")) return;
    const r = await fetch(`/api/ims/v1/admin/inventory-pools/${id}`, { method: "DELETE" });
    if (r.ok) {
      void load();
    } else if (r.status === 409) {
      alert("This pool is used by one or more channels and cannot be deleted. Reassign those channels first.");
    } else {
      alert("Failed to delete pool.");
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="Commerce"
        title="Inventory Pools"
        subtitle="Group shops into pools to define which locations fulfil online orders."
        action={
          <PrimaryButton type="button" onClick={() => { setShowForm((p) => !p); setErr(null); }}>
            <span className="material-symbols-outlined text-lg">{showForm ? "close" : "add"}</span>
            {showForm ? "Cancel" : "New pool"}
          </PrimaryButton>
        }
      />

      {showForm && (
        <form
          onSubmit={(e) => void handleCreate(e)}
          className="rounded-xl border border-outline-variant/10 bg-surface-container-low p-5 space-y-4"
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-on-surface mb-1">Pool name</label>
              <TextInput
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Main warehouse"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-on-surface mb-1">Fulfillment policy</label>
              <SelectInput options={POLICY_OPTIONS} value={policy} onChange={setPolicy} placeholder="Select policy" />
            </div>
          </div>

          {shops.length > 0 && (
            <div>
              <p className="text-sm font-medium text-on-surface mb-2">Shops in this pool</p>
              <div className="flex flex-wrap gap-2">
                {shops.map((shop) => (
                  <button
                    key={shop.id}
                    type="button"
                    onClick={() => toggleShop(shop.id, selectedShopIds, setSelectedShopIds)}
                    className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${
                      selectedShopIds.includes(shop.id)
                        ? "border-primary bg-primary/10 text-primary"
                        : "border-outline-variant/30 text-on-surface-variant hover:border-primary/40"
                    }`}
                  >
                    {shop.name}
                  </button>
                ))}
              </div>
              {selectedShopIds.length === 0 && (
                <p className="mt-1 text-xs text-on-surface-variant">No shops selected — pool will be empty.</p>
              )}
            </div>
          )}

          {err && <p className="text-sm text-error">{err}</p>}
          <PrimaryButton type="submit" disabled={saving}>
            {saving ? "Creating…" : "Create pool"}
          </PrimaryButton>
        </form>
      )}

      <Panel title="Inventory pools" subtitle={`${pools.length} pool${pools.length === 1 ? "" : "s"}`} noPad>
        {loading ? (
          <p className="px-6 py-8 text-sm text-on-surface-variant">Loading…</p>
        ) : pools.length === 0 ? (
          <p className="px-6 py-8 text-center text-sm text-on-surface-variant">
            No pools yet. Create one above — channels require a pool before they can be created.
          </p>
        ) : (
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-outline-variant/10">
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Name</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Policy</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Shops</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {pools.map((pool) =>
                editingId === pool.id ? (
                  <tr key={pool.id} className="bg-surface-container-low/50">
                    <td colSpan={4} className="px-6 py-4">
                      <form onSubmit={(e) => void handleEdit(e)} className="space-y-3">
                        <div className="grid gap-3 sm:grid-cols-2">
                          <TextInput value={editName} onChange={(e) => setEditName(e.target.value)} required />
                          <SelectInput options={POLICY_OPTIONS} value={editPolicy} onChange={setEditPolicy} placeholder="Select policy" />
                        </div>
                        {shops.length > 0 && (
                          <div className="flex flex-wrap gap-2">
                            {shops.map((shop) => (
                              <button
                                key={shop.id}
                                type="button"
                                onClick={() => toggleShop(shop.id, editShopIds, setEditShopIds)}
                                className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${
                                  editShopIds.includes(shop.id)
                                    ? "border-primary bg-primary/10 text-primary"
                                    : "border-outline-variant/30 text-on-surface-variant hover:border-primary/40"
                                }`}
                              >
                                {shop.name}
                              </button>
                            ))}
                          </div>
                        )}
                        {editErr && <p className="text-xs text-error">{editErr}</p>}
                        <div className="flex gap-2">
                          <PrimaryButton type="submit" disabled={editSaving}>
                            {editSaving ? "Saving…" : "Save"}
                          </PrimaryButton>
                          <SecondaryButton type="button" onClick={() => setEditingId(null)}>
                            Cancel
                          </SecondaryButton>
                        </div>
                      </form>
                    </td>
                  </tr>
                ) : (
                  <tr key={pool.id} className="hover:bg-surface-container-low/50">
                    <td className="px-6 py-4 font-medium text-on-surface">{pool.name}</td>
                    <td className="px-6 py-4 text-on-surface-variant text-xs">{policyLabel(pool.fulfillment_policy)}</td>
                    <td className="px-6 py-4">
                      {pool.shop_ids.length === 0 ? (
                        <Badge tone="warn">No shops</Badge>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {pool.shop_ids.map((sid) => {
                            const shop = shops.find((s) => s.id === sid);
                            return (
                              <span
                                key={sid}
                                className="rounded-full bg-surface-container px-2 py-0.5 text-[10px] text-on-surface-variant"
                              >
                                {shop?.name ?? sid.slice(0, 8)}
                              </span>
                            );
                          })}
                        </div>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => startEdit(pool)}
                          className="inline-flex items-center gap-1 rounded-lg border border-outline-variant/40 px-3 py-1.5 text-xs font-semibold text-on-surface transition hover:bg-surface-container"
                        >
                          <span className="material-symbols-outlined text-sm">edit</span>
                          Edit
                        </button>
                        <button
                          type="button"
                          onClick={() => void handleDelete(pool.id)}
                          className="inline-flex items-center gap-1 rounded-lg border border-error/30 bg-error-container/10 px-3 py-1.5 text-xs font-semibold text-error transition hover:bg-error-container/30"
                        >
                          <span className="material-symbols-outlined text-sm">delete</span>
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              )}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}
