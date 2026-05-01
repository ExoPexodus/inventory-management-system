"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  PageHeader,
  Panel,
  PrimaryButton,
  SecondaryButton,
  SelectInput,
  TextInput,
} from "@/components/ui/primitives";
import { formatMoney } from "@/lib/format";
import { useCurrency } from "@/lib/currency-context";
import { useTenantTimezone } from "@/lib/localisation-context";
import { fmtDatetime } from "@/lib/format";

type CustomerGroup = { id: string; name: string; colour: string | null };
type TxSummary = {
  id: string;
  created_at: string;
  shop_name: string | null;
  total_cents: number;
  status: string;
};
type CustomerDetail = {
  id: string;
  tenant_id: string;
  group_id: string | null;
  group_name: string | null;
  phone: string;
  name: string | null;
  email: string | null;
  address_line1: string | null;
  city: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  transactions: TxSummary[];
};

export default function CustomerProfilePage() {
  const params = useParams<{ id: string }>();
  const currency = useCurrency();
  const timezone = useTenantTimezone();
  const [customer, setCustomer] = useState<CustomerDetail | null>(null);
  const [groups, setGroups] = useState<CustomerGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    try {
      const [cRes, gRes] = await Promise.all([
        fetch(`/api/ims/v1/admin/customers/${params.id}`),
        fetch("/api/ims/v1/admin/customer-groups"),
      ]);
      if (!cRes.ok) { setErr("Customer not found"); setLoading(false); return; }
      setCustomer(await cRes.json() as CustomerDetail);
      if (gRes.ok) setGroups(await gRes.json() as CustomerGroup[]);
    } catch {
      setErr("Network error loading customer.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) return <div className="p-8 text-sm text-on-surface-variant">Loading…</div>;
  if (err || !customer) return <div className="p-8 text-sm text-error">{err ?? "Not found"}</div>;

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="CRM"
        title={customer.name ?? customer.phone}
        subtitle={`Customer since ${new Date(customer.created_at).toLocaleDateString()}`}
        action={<PrimaryButton onClick={() => setEditing(true)}>Edit</PrimaryButton>}
      />

      <Panel title="Details">
        <dl className="grid grid-cols-2 gap-4 text-sm">
          <div><dt className="text-on-surface-variant">Phone</dt><dd className="font-mono font-bold">{customer.phone}</dd></div>
          <div><dt className="text-on-surface-variant">Email</dt><dd>{customer.email ?? "—"}</dd></div>
          <div><dt className="text-on-surface-variant">City</dt><dd>{customer.city ?? "—"}</dd></div>
          <div>
            <dt className="text-on-surface-variant">Group</dt>
            <dd>
              {customer.group_name
                ? <span className="inline-flex items-center rounded-full bg-primary/10 px-2 py-0.5 text-xs font-semibold text-primary">{customer.group_name}</span>
                : "—"}
            </dd>
          </div>
          {customer.address_line1 && (
            <div className="col-span-2"><dt className="text-on-surface-variant">Address</dt><dd>{customer.address_line1}</dd></div>
          )}
          {customer.notes && (
            <div className="col-span-2"><dt className="text-on-surface-variant">Notes</dt><dd className="whitespace-pre-wrap">{customer.notes}</dd></div>
          )}
        </dl>
      </Panel>

      <Panel title="Purchase history" subtitle={`Last ${customer.transactions.length} transactions`} noPad>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-outline-variant/10">
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Date</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Shop</th>
                <th className="px-6 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Total</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {customer.transactions.length === 0 ? (
                <tr><td colSpan={4} className="px-6 py-4 text-sm text-on-surface-variant">No transactions yet.</td></tr>
              ) : (
                customer.transactions.map((tx) => (
                  <tr key={tx.id} className="hover:bg-surface-container-low/50">
                    <td className="px-6 py-3 text-xs text-on-surface-variant">{fmtDatetime(tx.created_at, timezone)}</td>
                    <td className="px-6 py-3 text-on-surface">{tx.shop_name ?? "—"}</td>
                    <td className="px-6 py-3 text-right tabular-nums font-semibold">{formatMoney(tx.total_cents, currency)}</td>
                    <td className="px-6 py-3 text-xs capitalize text-on-surface-variant">{tx.status}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      {editing && customer && (
        <EditCustomerModal
          customer={customer}
          groups={groups}
          onClose={() => setEditing(false)}
          onSaved={() => { setEditing(false); void load(); }}
        />
      )}
    </div>
  );
}

function EditCustomerModal({
  customer,
  groups,
  onClose,
  onSaved,
}: {
  customer: CustomerDetail;
  groups: CustomerGroup[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(customer.name ?? "");
  const [email, setEmail] = useState(customer.email ?? "");
  const [city, setCity] = useState(customer.city ?? "");
  const [addressLine1, setAddressLine1] = useState(customer.address_line1 ?? "");
  const [notes, setNotes] = useState(customer.notes ?? "");
  const [groupId, setGroupId] = useState(customer.group_id ?? "");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setErr(null);
    try {
      const r = await fetch(`/api/ims/v1/admin/customers/${customer.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim() || null,
          email: email.trim() || null,
          city: city.trim() || null,
          address_line1: addressLine1.trim() || null,
          notes: notes.trim() || null,
          group_id: groupId || null,
        }),
      });
      if (r.ok) { onSaved(); }
      else {
        const b = await r.json().catch(() => ({})) as { detail?: string };
        setErr(b.detail ?? `Save failed (${r.status})`);
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
          <p className="text-xs font-bold uppercase tracking-widest text-on-primary/80">Edit customer</p>
          <p className="mt-1 font-headline text-xl font-extrabold text-on-primary">{customer.name ?? customer.phone}</p>
        </div>
        <form onSubmit={onSubmit} className="space-y-4 p-6">
          <label className="block text-sm font-medium text-on-surface">
            Name
            <TextInput className="mt-1" value={name} onChange={(e) => setName(e.target.value)} />
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
            Address
            <TextInput className="mt-1" value={addressLine1} onChange={(e) => setAddressLine1(e.target.value)} />
          </label>
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
            <PrimaryButton type="submit" disabled={saving}>{saving ? "Saving…" : "Save changes"}</PrimaryButton>
            <SecondaryButton type="button" onClick={onClose}>Cancel</SecondaryButton>
          </div>
        </form>
      </div>
    </div>
  );
}
