"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  Avatar,
  Badge,
  ErrorState,
  PageHeader,
  PrimaryButton,
  SearchBar,
  SecondaryButton,
  SelectInput,
  TextInput,
} from "@/components/ui/primitives";

type Supplier = {
  id: string;
  name: string;
  status: string;
  contact_email: string | null;
  contact_phone: string | null;
  notes: string | null;
  created_at: string;
};

function SupplierCard({ s, onEdit }: { s: Supplier; onEdit: (s: Supplier) => void }) {
  const active = s.status.toLowerCase() === "active";
  const created = s.created_at.slice(0, 10);
  return (
    <article className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-5 shadow-sm transition hover:border-outline-variant/20">
      <div className="flex items-start gap-3">
        <Avatar name={s.name} className="h-12 w-12 text-sm" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="font-headline text-base font-bold text-on-surface">{s.name}</h3>
              <Badge tone={active ? "good" : "warn"}>{s.status}</Badge>
            </div>
            <button
              type="button"
              aria-label={`Edit ${s.name}`}
              onClick={() => onEdit(s)}
              className="rounded p-1 transition hover:bg-primary/10 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
            >
              <span className="material-symbols-outlined text-xl text-on-surface-variant">edit</span>
            </button>
          </div>
          <p className="mt-1 truncate text-sm text-on-surface-variant">{s.contact_email ?? "No email on file"}</p>
          {s.contact_phone ? (
            <p className="text-sm text-on-surface-variant">{s.contact_phone}</p>
          ) : null}
          <dl className="mt-3 grid grid-cols-2 gap-2 text-xs text-on-surface-variant">
            <div>
              <dt className="font-bold uppercase tracking-wider text-on-surface-variant/80">Since</dt>
              <dd className="mt-0.5 font-mono text-on-surface">{created}</dd>
            </div>
            {s.notes ? (
              <div className="col-span-2">
                <dt className="font-bold uppercase tracking-wider text-on-surface-variant/80">Notes</dt>
                <dd className="mt-0.5 text-on-surface">{s.notes}</dd>
              </div>
            ) : null}
          </dl>
          <p className="mt-3 border-t border-outline-variant/10 pt-3 text-xs text-on-surface-variant">
            {active
              ? "Reliable fill rate — prioritize for seasonal buys."
              : "Paused relationship — review terms before next PO."}
          </p>
        </div>
      </div>
    </article>
  );
}

export default function SuppliersPage() {
  const [rows, setRows] = useState<Supplier[]>([]);
  const [q, setQ] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [editSupplier, setEditSupplier] = useState<Supplier | null>(null);

  async function refresh() {
    setLoading(true);
    setErr(null);
    const r = await fetch("/api/ims/v1/admin/suppliers");
    if (r.ok) setRows((await r.json()) as Supplier[]);
    else setErr(`Suppliers failed (${r.status})`);
    setLoading(false);
  }

  useEffect(() => {
    void refresh();
  }, []);

  const filtered = useMemo(() => {
    const n = q.trim().toLowerCase();
    if (!n) return rows;
    return rows.filter(
      (s) =>
        s.name.toLowerCase().includes(n) ||
        (s.contact_email ?? "").toLowerCase().includes(n),
    );
  }, [rows, q]);

  const activeList = filtered.filter((s) => s.status.toLowerCase() === "active");
  const inactiveList = filtered.filter((s) => s.status.toLowerCase() !== "active");
  const inactiveWarn = inactiveList.length > 0;
  const withContact = rows.filter((s) => s.contact_email).length;

  async function onAddSupplier(e: FormEvent) {
    e.preventDefault();
    setMsg(null);
    const r = await fetch("/api/ims/v1/admin/suppliers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: name.trim(),
        status: "active",
        contact_email: email.trim() || null,
        contact_phone: phone.trim() || null,
        notes: notes.trim() || null,
      }),
    });
    if (r.ok) {
      setName("");
      setEmail("");
      setPhone("");
      setNotes("");
      setShowForm(false);
      setMsg("Supplier added");
      await refresh();
    } else {
      setMsg(`Create failed (${r.status})`);
    }
  }

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="Supplier hub"
        title="Partners & lead times"
        subtitle="Active vendors power PO velocity — keep contact data fresh."
        action={
          <button
            type="button"
            onClick={() => setShowForm((v) => !v)}
            className="ink-gradient inline-flex items-center gap-2 rounded-lg px-6 py-2.5 text-sm font-semibold text-on-primary shadow-sm transition hover:opacity-90"
          >
            <span className="material-symbols-outlined text-lg">add</span>
            Add supplier
          </button>
        }
      />

      {showForm ? (
        <form
          onSubmit={onAddSupplier}
          className="rounded-xl border border-outline-variant/10 bg-surface-container-low p-6 shadow-sm"
        >
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">New supplier</p>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <label className="block text-sm font-medium text-on-surface">
              Name
              <TextInput required className="mt-1" value={name} onChange={(e) => setName(e.target.value)} placeholder="Vendor legal name" />
            </label>
            <label className="block text-sm font-medium text-on-surface">
              Email
              <TextInput type="email" className="mt-1" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="ap@supplier.com" />
            </label>
            <label className="block text-sm font-medium text-on-surface">
              Phone
              <TextInput className="mt-1" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+1 555 000 0000" />
            </label>
            <label className="block text-sm font-medium text-on-surface sm:col-span-2">
              Notes
              <TextInput className="mt-1" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Payment terms, special instructions…" />
            </label>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <PrimaryButton type="submit">Save supplier</PrimaryButton>
            <SecondaryButton type="button" onClick={() => setShowForm(false)}>
              Cancel
            </SecondaryButton>
          </div>
        </form>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Total suppliers</p>
          <p className="mt-4 font-headline text-3xl font-extrabold text-primary">{rows.length}</p>
        </div>
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Active partners</p>
          <p className="mt-4 font-headline text-3xl font-extrabold text-primary">{activeList.length}</p>
        </div>
        <div
          className={`rounded-xl border p-6 shadow-sm ${
            inactiveWarn ? "border-secondary/30 bg-secondary-container/25" : "border-outline-variant/10 bg-surface-container-lowest"
          }`}
        >
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Inactive</p>
          <p className={`mt-4 font-headline text-3xl font-extrabold ${inactiveWarn ? "text-secondary" : "text-primary"}`}>
            {inactiveList.length}
          </p>
          {inactiveWarn ? <p className="mt-1 text-xs font-semibold text-secondary">Review dormant vendors</p> : null}
        </div>
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">With contact info</p>
          <p className="mt-4 font-headline text-3xl font-extrabold text-primary">{withContact}</p>
          <p className="mt-1 text-xs text-on-surface-variant">have email on file</p>
        </div>
      </div>

      <SearchBar placeholder="Search suppliers…" value={q} onChange={(e) => setQ(e.target.value)} />

      {err ? <ErrorState detail={err} /> : null}
      {msg ? <p className="text-sm text-on-surface-variant">{msg}</p> : null}
      {loading ? <p className="text-sm text-on-surface-variant">Loading suppliers…</p> : null}

      <section className="space-y-4">
        <h2 className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Active partners</h2>
        {activeList.length === 0 ? (
          <p className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-8 text-center text-sm text-on-surface-variant shadow-sm">
            No active suppliers match.
          </p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {activeList.map((s) => (
              <SupplierCard key={s.id} s={s} onEdit={setEditSupplier} />
            ))}
          </div>
        )}
      </section>

      <section className="space-y-4">
        <h2 className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Inactive</h2>
        {inactiveList.length === 0 ? (
          <p className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-8 text-center text-sm text-on-surface-variant shadow-sm">
            No inactive suppliers — great coverage.
          </p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {inactiveList.map((s) => (
              <SupplierCard key={s.id} s={s} onEdit={setEditSupplier} />
            ))}
          </div>
        )}
      </section>

      {editSupplier ? (
        <EditSupplierDialog
          supplier={editSupplier}
          onClose={() => setEditSupplier(null)}
          onSaved={() => { setEditSupplier(null); void refresh(); }}
        />
      ) : null}
    </div>
  );
}

function EditSupplierDialog({
  supplier,
  onClose,
  onSaved,
}: {
  supplier: Supplier;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(supplier.name);
  const [status, setStatus] = useState(supplier.status);
  const [email, setEmail] = useState(supplier.contact_email ?? "");
  const [phone, setPhone] = useState(supplier.contact_phone ?? "");
  const [notes, setNotes] = useState(supplier.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setErr(null);
    const r = await fetch(`/api/ims/v1/admin/suppliers/${supplier.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: name.trim(),
        status,
        contact_email: email.trim() || null,
        contact_phone: phone.trim() || null,
        notes: notes.trim() || null,
      }),
    });
    if (r.ok) {
      onSaved();
    } else {
      setErr(`Save failed (${r.status})`);
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
          <p className="text-xs font-bold uppercase tracking-widest text-on-primary/80">Edit supplier</p>
          <p className="mt-1 font-headline text-xl font-extrabold text-on-primary">{supplier.name}</p>
        </div>
        <form onSubmit={onSubmit} className="space-y-4 p-6">
          <label className="block text-sm font-medium text-on-surface">
            Name
            <TextInput required className="mt-1" value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="block text-sm font-medium text-on-surface">
            Status
            <SelectInput
              className="mt-1"
              value={status}
              onChange={setStatus}
              options={[
                { value: "active", label: "Active" },
                { value: "inactive", label: "Inactive" },
              ]}
            />
          </label>
          <label className="block text-sm font-medium text-on-surface">
            Contact email
            <TextInput type="email" className="mt-1" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="ap@supplier.com" />
          </label>
          <label className="block text-sm font-medium text-on-surface">
            Contact phone
            <TextInput className="mt-1" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+1 555 000 0000" />
          </label>
          <label className="block text-sm font-medium text-on-surface">
            Notes
            <TextInput className="mt-1" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Payment terms, special instructions…" />
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
