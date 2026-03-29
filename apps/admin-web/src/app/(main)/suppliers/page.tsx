"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  Badge,
  EmptyState,
  ErrorState,
  PageHeader,
  Panel,
  PrimaryButton,
  SelectInput,
  TextInput,
} from "@/components/ui/primitives";

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
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const sp = new URLSearchParams();
    if (tenantId) sp.set("tenant_id", tenantId);
    if (status) sp.set("status", status);
    if (search.trim()) sp.set("q", search.trim());
    const r = await fetch(`/api/ims/v1/admin/suppliers?${sp.toString()}`);
    if (r.ok) {
      setRows((await r.json()) as Supplier[]);
      setErr(null);
    } else {
      setErr(`Failed to load suppliers (${r.status})`);
    }
  }, [tenantId, status, search]);

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
  }, [refresh]);

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
    <div className="space-y-7">
      <PageHeader
        kicker="Supplier hub"
        title="Partners & vendors"
        subtitle="Maintain contact and status metadata for purchasing and fulfillment."
      />
      <Panel title="Add supplier">
        <form onSubmit={onCreate}>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <label className="block text-xs font-medium text-primary/60">
            Tenant
            <SelectInput
              className="mt-1 w-full"
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
            >
              {tenants.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name} ({t.slug})
                </option>
              ))}
            </SelectInput>
          </label>
          <label className="block text-xs font-medium text-primary/60">
            Name
            <TextInput
              required
              className="mt-1 w-full"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="block text-xs font-medium text-primary/60 sm:col-span-2">
            Contact email
            <TextInput
              type="email"
              className="mt-1 w-full"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
        </div>
          {msg ? <div className="mt-3"><Badge tone="good">{msg}</Badge></div> : null}
          <div className="mt-4">
            <PrimaryButton type="submit">Save supplier</PrimaryButton>
          </div>
        </form>
      </Panel>
      {err ? <ErrorState detail={err} /> : null}
      <Panel title="Supplier list" subtitle="Status, name, and contact details">
        <div className="mb-4 flex flex-wrap gap-3">
          <TextInput
            placeholder="Search name or contact…"
            className="min-w-[16rem]"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <SelectInput value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All statuses</option>
            <option value="active">active</option>
            <option value="inactive">inactive</option>
          </SelectInput>
        </div>
        <div className="overflow-x-auto">
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
                  <Badge tone={s.status === "active" ? "good" : "warn"}>{s.status}</Badge>
                </td>
                <td className="px-4 py-3 text-primary/75">{s.contact_email ?? "—"}</td>
              </tr>
            ))}
          </tbody>
          </table>
        </div>
        {rows.length === 0 ? <EmptyState title="No suppliers yet" detail="Create your first supplier using the form above." /> : null}
      </Panel>
    </div>
  );
}
