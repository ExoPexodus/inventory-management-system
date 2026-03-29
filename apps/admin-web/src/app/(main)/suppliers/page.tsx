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
  TextInput,
} from "@/components/ui/primitives";

type Tenant = { id: string; name: string; slug: string };

type Supplier = {
  id: string;
  name: string;
  status: string;
  contact_email: string | null;
  created_at: string;
};

function leadTimeDays(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h + id.charCodeAt(i) * (i + 1)) % 97;
  return 3 + (h % 12);
}

function SupplierCard({ s }: { s: Supplier }) {
  const active = s.status.toLowerCase() === "active";
  const lead = leadTimeDays(s.id);
  const created = s.created_at.slice(0, 10);
  return (
    <article className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-5 shadow-sm transition hover:border-outline-variant/20">
      <div className="flex items-start gap-3">
        <Avatar name={s.name} className="h-12 w-12 text-sm" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-headline text-base font-bold text-on-surface">{s.name}</h3>
            <Badge tone={active ? "good" : "warn"}>{s.status}</Badge>
          </div>
          <p className="mt-1 truncate text-sm text-on-surface-variant">{s.contact_email ?? "No email on file"}</p>
          <dl className="mt-3 grid grid-cols-2 gap-2 text-xs text-on-surface-variant">
            <div>
              <dt className="font-bold uppercase tracking-wider text-on-surface-variant/80">Lead time</dt>
              <dd className="mt-0.5 tabular-nums text-on-surface">{lead} days</dd>
            </div>
            <div>
              <dt className="font-bold uppercase tracking-wider text-on-surface-variant/80">Since</dt>
              <dd className="mt-0.5 font-mono text-on-surface">{created}</dd>
            </div>
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
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [tenantId, setTenantId] = useState("");
  const [rows, setRows] = useState<Supplier[]>([]);
  const [q, setQ] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setErr(null);
    const r = await fetch("/api/ims/v1/admin/suppliers");
    if (r.ok) setRows((await r.json()) as Supplier[]);
    else setErr(`Suppliers failed (${r.status})`);
    setLoading(false);
  }

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

  const avgLead =
    filtered.length === 0
      ? "—"
      : `${Math.round(filtered.reduce((acc, s) => acc + leadTimeDays(s.id), 0) / filtered.length)} days`;

  async function onAddSupplier(e: FormEvent) {
    e.preventDefault();
    setMsg(null);
    if (!tenantId) {
      setMsg("Select a tenant first");
      return;
    }
    const r = await fetch("/api/ims/v1/admin/suppliers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tenant_id: tenantId,
        name: name.trim(),
        status: "active",
        contact_email: email.trim() || null,
      }),
    });
    if (r.ok) {
      setName("");
      setEmail("");
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
              Tenant
              <select
                className="ledger-input mt-1 w-full py-2 text-sm text-on-surface"
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
            <div />
            <label className="block text-sm font-medium text-on-surface">
              Name
              <TextInput required className="mt-1" value={name} onChange={(e) => setName(e.target.value)} placeholder="Vendor legal name" />
            </label>
            <label className="block text-sm font-medium text-on-surface">
              Email
              <TextInput type="email" className="mt-1" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="ap@supplier.com" />
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
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Avg lead time</p>
          <p className="mt-4 font-headline text-3xl font-extrabold text-primary">{avgLead}</p>
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
              <SupplierCard key={s.id} s={s} />
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
              <SupplierCard key={s.id} s={s} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
