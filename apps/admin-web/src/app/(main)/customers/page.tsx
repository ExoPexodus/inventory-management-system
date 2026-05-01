"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  EmptyState,
  LoadingRow,
  PageHeader,
  Panel,
  PrimaryButton,
  SearchBar,
  SecondaryButton,
  SelectInput,
  TextInput,
} from "@/components/ui/primitives";

type CustomerGroup = { id: string; name: string; colour: string | null };
type Customer = {
  id: string;
  phone: string;
  name: string | null;
  email: string | null;
  city: string | null;
  group_id: string | null;
  group_name: string | null;
  created_at: string;
};

export default function CustomersPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [groups, setGroups] = useState<CustomerGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [groupFilter, setGroupFilter] = useState("");
  const [showCreate, setShowCreate] = useState(false);

  async function fetchData() {
    setLoading(true);
    const sp = new URLSearchParams();
    if (q.trim()) sp.set("q", q.trim());
    if (groupFilter) sp.set("group_id", groupFilter);
    const [custsRes, groupsRes] = await Promise.all([
      fetch(`/api/ims/v1/admin/customers?${sp}`),
      fetch("/api/ims/v1/admin/customer-groups"),
    ]);
    if (custsRes.ok) setCustomers(await custsRes.json() as Customer[]);
    if (groupsRes.ok) setGroups(await groupsRes.json() as CustomerGroup[]);
    setLoading(false);
  }

  useEffect(() => { void fetchData(); }, [q, groupFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="CRM"
        title="Customers"
        subtitle="Customer profiles, purchase history, and groups."
        action={
          <PrimaryButton onClick={() => setShowCreate(true)}>
            <span className="material-symbols-outlined text-lg">add</span>
            New customer
          </PrimaryButton>
        }
      />

      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-outline-variant/10 bg-surface-container-low p-4 shadow-sm">
        <SearchBar
          className="min-w-[14rem] flex-1"
          placeholder="Search name or phone"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <SelectInput
          className="min-w-[10rem]"
          value={groupFilter}
          onChange={setGroupFilter}
          placeholder="All groups"
          options={[
            { value: "", label: "All groups" },
            ...groups.map((g) => ({ value: g.id, label: g.name })),
          ]}
        />
      </div>

      <Panel title="Customers" subtitle={`${customers.length} results`} noPad>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-outline-variant/10">
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Name</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Phone</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Group</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">City</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Joined</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {loading ? (
                <LoadingRow colSpan={5} label="Loading customers…" />
              ) : customers.length === 0 ? (
                <tr>
                  <td colSpan={5} className="p-0">
                    <EmptyState title="No customers found" detail="Create a customer or adjust your search." />
                  </td>
                </tr>
              ) : (
                customers.map((c) => (
                  <tr key={c.id} className="group hover:bg-surface-container-low/50">
                    <td className="px-6 py-3">
                      <Link href={`/customers/${c.id}`} className="font-bold text-primary hover:underline">
                        {c.name ?? <span className="text-on-surface-variant italic">No name</span>}
                      </Link>
                    </td>
                    <td className="px-6 py-3 font-mono text-xs text-on-surface">{c.phone}</td>
                    <td className="px-6 py-3">
                      {c.group_name ? (
                        <span className="inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-xs font-semibold text-primary">
                          {c.group_name}
                        </span>
                      ) : (
                        <span className="text-on-surface-variant/40">—</span>
                      )}
                    </td>
                    <td className="px-6 py-3 text-on-surface-variant">{c.city ?? "—"}</td>
                    <td className="px-6 py-3 text-on-surface-variant text-xs">
                      {new Date(c.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      {showCreate && (
        <CreateCustomerModal
          groups={groups}
          onClose={() => setShowCreate(false)}
          onSaved={() => { setShowCreate(false); void fetchData(); }}
        />
      )}
    </div>
  );
}

function CreateCustomerModal({
  groups,
  onClose,
  onSaved,
}: {
  groups: CustomerGroup[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [city, setCity] = useState("");
  const [groupId, setGroupId] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!phone.trim()) { setErr("Phone number is required"); return; }
    setSaving(true);
    setErr(null);
    try {
      const r = await fetch("/api/ims/v1/admin/customers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          phone: phone.trim(),
          name: name.trim() || null,
          email: email.trim() || null,
          city: city.trim() || null,
          notes: notes.trim() || null,
          group_id: groupId || null,
        }),
      });
      if (r.ok) {
        onSaved();
      } else {
        const b = await r.json().catch(() => ({})) as { detail?: string };
        setErr(b.detail === "phone_conflict" ? "A customer with this phone already exists." : (b.detail ?? `Failed (${r.status})`));
      }
    } catch {
      setErr("Network error. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="w-full max-w-lg rounded-2xl bg-surface shadow-xl max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="ink-gradient rounded-t-2xl px-6 py-5">
          <p className="text-xs font-bold uppercase tracking-widest text-on-primary/80">New customer</p>
          <p className="mt-1 font-headline text-xl font-extrabold text-on-primary">Add customer profile</p>
        </div>
        <form onSubmit={onSubmit} className="space-y-4 p-6">
          <label className="block text-sm font-medium text-on-surface">
            Phone number <span className="text-error">*</span>
            <TextInput required className="mt-1" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="e.g. 9876543210" />
          </label>
          <label className="block text-sm font-medium text-on-surface">
            Name (optional)
            <TextInput className="mt-1" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Rajesh Kumar" />
          </label>
          <div className="grid grid-cols-2 gap-4">
            <label className="block text-sm font-medium text-on-surface">
              Email
              <TextInput type="email" className="mt-1" value={email} onChange={(e) => setEmail(e.target.value)} />
            </label>
            <label className="block text-sm font-medium text-on-surface">
              City
              <TextInput className="mt-1" value={city} onChange={(e) => setCity(e.target.value)} />
            </label>
          </div>
          <label className="block text-sm font-medium text-on-surface">
            Group
            <SelectInput
              className="mt-1"
              value={groupId}
              onChange={setGroupId}
              options={[{ value: "", label: "No group" }, ...groups.map((g) => ({ value: g.id, label: g.name }))]}
            />
          </label>
          <label className="block text-sm font-medium text-on-surface">
            Notes
            <TextInput className="mt-1" value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>
          {err && <p className="text-sm text-error">{err}</p>}
          <div className="flex gap-2 pt-2">
            <PrimaryButton type="submit" disabled={saving}>{saving ? "Saving…" : "Create customer"}</PrimaryButton>
            <SecondaryButton type="button" onClick={onClose}>Cancel</SecondaryButton>
          </div>
        </form>
      </div>
    </div>
  );
}
