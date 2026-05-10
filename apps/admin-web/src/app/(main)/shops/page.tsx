"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ErrorState, PageHeader, Panel, PrimaryButton, SecondaryButton, TextInput } from "@/components/ui/primitives";

type Shop = {
  id: string;
  tenant_id: string;
  name: string;
  created_at: string;
};

export default function ShopsPage() {
  const params = useSearchParams();
  const [shops, setShops] = useState<Shop[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  useEffect(() => {
    if (params.get("new") === "1") setShowCreate(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  async function loadShops() {
    setLoading(true);
    setErr(null);
    try {
      const r = await fetch("/api/ims/v1/admin/shops");
      if (r.ok) {
        setShops((await r.json()) as Shop[]);
      } else {
        setErr(`Failed to load shops (${r.status})`);
      }
    } catch {
      setErr("Network error loading shops.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadShops();
  }, []);

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-8">
      <div className="flex items-center justify-between">
        <PageHeader title="Shops" />
        <PrimaryButton onClick={() => setShowCreate(true)}>New Shop</PrimaryButton>
      </div>

      {err && <ErrorState detail={err} />}

      <Panel>
        {loading ? (
          <p className="px-6 py-8 text-sm text-on-surface-variant">Loading…</p>
        ) : shops.length === 0 ? (
          <div className="px-4 py-12 text-center">
            <p className="font-headline text-base font-bold text-on-surface">No shops yet</p>
            <p className="mt-1 text-sm text-on-surface-variant">Add a shop to start tracking inventory and sales.</p>
            <button
              type="button"
              onClick={() => setShowCreate(true)}
              className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-on-primary hover:opacity-90"
            >
              Add your first shop
            </button>
          </div>
        ) : (
          <ul className="divide-y divide-outline-variant/10">
            {shops.map((s) => (
              <li key={s.id} className="flex items-center justify-between px-6 py-4">
                <div>
                  <p className="font-headline text-sm font-bold text-on-surface">{s.name}</p>
                  <p className="text-xs text-on-surface-variant">
                    Created {new Date(s.created_at).toLocaleDateString()}
                  </p>
                </div>
                <Link
                  href={`/shops/${s.id}/edit`}
                  className="text-xs font-medium text-primary hover:underline"
                >
                  Edit
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      {showCreate && (
        <CreateShopModal
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false);
            void loadShops();
          }}
        />
      )}
    </div>
  );
}

function CreateShopModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setMsg(null);
    setSaving(true);
    try {
      const r = await fetch("/api/ims/v1/admin/shops", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim() }),
      });
      if (r.ok) {
        onCreated();
        return;
      }
      if (r.status === 409) {
        setMsg("A shop with this name already exists.");
      } else {
        setMsg(`Failed to create shop (${r.status})`);
      }
    } catch {
      setMsg("Network error. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl bg-surface shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="border-b border-outline-variant/10 px-6 py-4">
          <h2 className="font-headline text-lg font-bold text-on-surface">New Shop</h2>
          <p className="mt-0.5 text-sm text-on-surface-variant">Add a physical store or stock-holding location.</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4 p-6">
          <label className="block text-sm font-medium text-on-surface">
            Shop name
            <TextInput
              required
              autoFocus
              className="mt-1"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Downtown Store"
            />
          </label>
          {msg && <p className="text-sm text-error">{msg}</p>}
          <div className="flex justify-end gap-2 pt-2">
            <SecondaryButton type="button" onClick={onClose}>Cancel</SecondaryButton>
            <PrimaryButton type="submit" disabled={saving || !name.trim()}>
              {saving ? "Creating…" : "Create shop"}
            </PrimaryButton>
          </div>
        </form>
      </div>
    </div>
  );
}
