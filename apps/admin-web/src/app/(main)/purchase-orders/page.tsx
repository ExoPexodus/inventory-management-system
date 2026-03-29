"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  Avatar,
  PageHeader,
  PrimaryButton,
  SecondaryButton,
  SelectInput,
  TextInput,
} from "@/components/ui/primitives";

type Supplier = { id: string; name: string; status: string };

type PO = {
  id: string;
  supplierId: string;
  supplierName: string;
  status: "draft" | "pending" | "received" | "cancelled";
  notes: string;
  createdAt: string;
};

function poStatusClass(s: PO["status"]): string {
  if (s === "draft") return "bg-surface-container-high text-on-surface-variant";
  if (s === "pending") return "bg-secondary-container text-on-secondary-container";
  if (s === "received") return "bg-tertiary-fixed text-on-tertiary-fixed-variant";
  return "bg-error-container text-on-error-container";
}

export default function PurchaseOrdersPage() {
  const [showForm, setShowForm] = useState(false);
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [supplierId, setSupplierId] = useState("");
  const [notes, setNotes] = useState("");
  const [pos, setPos] = useState<PO[]>([]);

  useEffect(() => {
    void (async () => {
      const r = await fetch("/api/ims/v1/admin/suppliers");
      if (r.ok) {
        const list = (await r.json()) as Supplier[];
        setSuppliers(list);
        setSupplierId((prev) => prev || list[0]?.id || "");
      }
    })();
  }, []);

  const stats = useMemo(() => {
    const draft = pos.filter((p) => p.status === "draft").length;
    const pending = pos.filter((p) => p.status === "pending").length;
    const received = pos.filter((p) => p.status === "received").length;
    return { draft, pending, received };
  }, [pos]);

  function onCreate(e: FormEvent) {
    e.preventDefault();
    const sup = suppliers.find((s) => s.id === supplierId);
    if (!sup) return;
    const id = `PO-${Date.now().toString(36).toUpperCase()}`;
    const row: PO = {
      id,
      supplierId: sup.id,
      supplierName: sup.name,
      status: "draft",
      notes: notes.trim(),
      createdAt: new Date().toISOString(),
    };
    setPos((p) => [row, ...p]);
    setNotes("");
    setShowForm(false);
  }

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="Procurement"
        title="Purchase orders"
        subtitle="Draft POs stay local until backend procurement endpoints are wired."
        action={
          <button
            type="button"
            onClick={() => setShowForm((v) => !v)}
            className="ink-gradient inline-flex items-center gap-2 rounded-lg px-6 py-2.5 text-sm font-semibold text-on-primary shadow-sm transition hover:opacity-90"
          >
            <span className="material-symbols-outlined text-lg">post_add</span>
            New draft PO
          </button>
        }
      />

      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Draft</p>
          <p className="mt-4 font-headline text-3xl font-extrabold text-primary">{stats.draft}</p>
        </div>
        <div className="rounded-xl border border-secondary/25 bg-secondary-container/25 p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Pending</p>
          <p className="mt-4 font-headline text-3xl font-extrabold text-secondary">{stats.pending}</p>
          <p className="mt-1 text-xs font-semibold text-secondary">Awaiting vendor confirmation</p>
        </div>
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Received</p>
          <p className="mt-4 font-headline text-3xl font-extrabold text-primary">{stats.received}</p>
        </div>
      </div>

      {showForm ? (
        <form
          onSubmit={onCreate}
          className="space-y-4 rounded-xl border border-outline-variant/10 bg-surface-container-low p-6 shadow-sm"
        >
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Create draft</p>
          <label className="block text-sm font-medium text-on-surface">
            Supplier
            <SelectInput className="mt-1" required value={supplierId} onChange={(e) => setSupplierId(e.target.value)}>
              {suppliers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </SelectInput>
          </label>
          <label className="block text-sm font-medium text-on-surface">
            Notes
            <TextInput className="mt-1" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Internal memo" />
          </label>
          <div className="flex gap-2">
            <PrimaryButton type="submit">Save draft</PrimaryButton>
            <SecondaryButton type="button" onClick={() => setShowForm(false)}>
              Cancel
            </SecondaryButton>
          </div>
        </form>
      ) : null}

      <section className="overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm">
        <div className="border-b border-outline-variant/10 px-6 py-4">
          <h3 className="font-headline text-lg font-bold text-on-surface">Open POs</h3>
          <p className="text-sm text-on-surface-variant">Statuses are local until API sync lands.</p>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-outline-variant/10">
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">PO ID</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Supplier</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Status</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Notes</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {pos.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center text-sm text-on-surface-variant">
                    No drafts yet — create one above.
                  </td>
                </tr>
              ) : (
                pos.map((p) => (
                  <tr key={p.id} className="hover:bg-surface-container-low/40">
                    <td className="px-6 py-3 font-mono text-xs text-on-surface">{p.id}</td>
                    <td className="px-6 py-3">
                      <div className="flex items-center gap-2">
                        <Avatar name={p.supplierName} className="h-9 w-9 text-[10px]" />
                        <span className="font-medium text-on-surface">{p.supplierName}</span>
                      </div>
                    </td>
                    <td className="px-6 py-3">
                      <span className={`inline-flex rounded-full px-2.5 py-1 text-[10px] font-bold uppercase ${poStatusClass(p.status)}`}>
                        {p.status}
                      </span>
                    </td>
                    <td className="max-w-xs truncate px-6 py-3 text-on-surface-variant">{p.notes || "—"}</td>
                    <td className="px-6 py-3 font-mono text-xs text-on-surface-variant">{p.createdAt.slice(0, 10)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
