"use client";

import { FormEvent, useEffect, useState } from "react";

type Supplier = {
  id: string;
  tenant_id: string;
  name: string;
  status: string;
  contact_email: string | null;
  contact_phone: string | null;
};

type Tenant = { id: string; name: string; slug: string };

export default function SuppliersPage() {
  const [rows, setRows] = useState<Supplier[]>([]);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [tenantId, setTenantId] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  async function refresh() {
    const r = await fetch("/api/ims/v1/admin/suppliers");
    if (r.ok) setRows((await r.json()) as Supplier[]);
  }

  useEffect(() => {
    void (async () => {
      const o = await fetch("/api/ims/v1/admin/overview");
      if (o.ok) {
        const j = (await o.json()) as { tenants: Tenant[] };
        setTenants(j.tenants);
        if (j.tenants[0]) setTenantId(j.tenants[0].id);
      }
      await refresh();
    })();
  }, []);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setMsg(null);
    if (!tenantId) {
      setMsg("Select tenant");
      return;
    }
    const r = await fetch("/api/ims/v1/admin/suppliers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        tenant_id: tenantId,
        name,
        contact_email: email || null,
        status: "active",
      }),
    });
    if (!r.ok) setMsg(`Save failed (${r.status})`);
    else {
      setName("");
      setEmail("");
      setMsg("Supplier created");
      await refresh();
    }
  }

  return (
    <div className="space-y-8">
      <header>
        <p className="text-xs font-semibold uppercase tracking-wider text-primary/50">Supplier hub</p>
        <h1 className="font-display text-3xl font-semibold tracking-tight text-primary">Partners & vendors</h1>
      </header>
      <form onSubmit={onCreate} className="rounded-xl border border-primary/10 bg-white/90 p-5 shadow-sm">
        <h2 className="font-display text-sm font-semibold text-primary">Add supplier</h2>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <label className="block text-xs font-medium text-primary/60">
            Tenant
            <select
              className="mt-1 w-full rounded-lg border border-primary/15 px-3 py-2 text-sm"
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
            >
              {tenants.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({t.slug})
                </option>
              ))}
            </select>
          </label>
          <label className="block text-xs font-medium text-primary/60">
            Name
            <input
              required
              className="mt-1 w-full rounded-lg border border-primary/15 px-3 py-2 text-sm"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="block text-xs font-medium text-primary/60 sm:col-span-2">
            Contact email
            <input
              type="email"
              className="mt-1 w-full rounded-lg border border-primary/15 px-3 py-2 text-sm"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
        </div>
        {msg ? <p className="mt-3 text-sm text-primary/80">{msg}</p> : null}
        <button
          type="submit"
          className="mt-4 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary/90"
        >
          Save supplier
        </button>
      </form>
      <div className="overflow-x-auto rounded-xl border border-primary/10 bg-white/90 shadow-sm">
        <table className="min-w-full text-left text-sm">
          <thead>
            <tr className="border-b border-primary/10 text-xs uppercase tracking-wide text-primary/50">
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Email</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-primary/5">
            {rows.map((s) => (
              <tr key={s.id}>
                <td className="px-4 py-3 font-medium">{s.name}</td>
                <td className="px-4 py-3">
                  <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs capitalize text-emerald-800">
                    {s.status}
                  </span>
                </td>
                <td className="px-4 py-3 text-primary/75">{s.contact_email ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
