"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Badge,
  EmptyState,
  ErrorState,
  LoadingRow,
  PageHeader,
  Panel,
  PrimaryButton,
  SecondaryButton,
  SelectInput,
  TextInput,
} from "@/components/ui/primitives";

type Discount = {
  id: string;
  name: string;
  code: string | null;
  discount_type: "percentage" | "fixed_amount" | "free_shipping";
  value_bps: number | null;
  value_cents: number | null;
  status: "active" | "archived";
  min_subtotal_cents: number | null;
  max_uses_total: number | null;
  max_uses_per_customer: number | null;
  times_used: number;
  starts_at: string | null;
  expires_at: string | null;
  created_at: string;
};

function displayValue(d: Discount): string {
  if (d.discount_type === "percentage") return `${((d.value_bps ?? 0) / 100).toFixed(0)}% off`;
  if (d.discount_type === "fixed_amount") return `${((d.value_cents ?? 0) / 100).toFixed(2)} off`;
  return "Free shipping";
}

function formatExpiry(expires_at: string | null): string {
  if (!expires_at) return "No expiry";
  return new Date(expires_at).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function typeLabel(type: Discount["discount_type"]): string {
  if (type === "percentage") return "% off";
  if (type === "fixed_amount") return "Fixed amount";
  return "Free shipping";
}

export default function DiscountsPage() {
  const newParams = useSearchParams();
  const [items, setItems] = useState<Discount[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    if (newParams.get("new") === "1") {
      setShowForm(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [newParams]);

  // form state
  const [fname, setFname] = useState("");
  const [fcode, setFcode] = useState("");
  const [ftype, setFtype] = useState<Discount["discount_type"]>("percentage");
  const [fvalue, setFvalue] = useState("");
  const [fminOrder, setFminOrder] = useState("");
  const [fmaxUses, setFmaxUses] = useState("");
  const [fperCustomer, setFperCustomer] = useState("");
  const [fstartsAt, setFstartsAt] = useState("");
  const [fexpiresAt, setFexpiresAt] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const r = await fetch("/api/ims/v1/admin/discounts");
      if (r.ok) {
        setItems((await r.json()) as Discount[]);
      } else {
        setErr(`Failed to load discounts (${r.status})`);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function resetForm() {
    setFname("");
    setFcode("");
    setFtype("percentage");
    setFvalue("");
    setFminOrder("");
    setFmaxUses("");
    setFperCustomer("");
    setFstartsAt("");
    setFexpiresAt("");
  }

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMsg(null);

    const valueBps =
      ftype === "percentage" ? Math.round(parseFloat(fvalue) * 100) : null;
    const valueCents =
      ftype === "fixed_amount" ? Math.round(parseFloat(fvalue)) : null;

    const body = {
      name: fname.trim(),
      code: fcode.trim() || null,
      discount_type: ftype,
      value_bps: valueBps,
      value_cents: valueCents,
      min_subtotal_cents: fminOrder.trim() ? parseInt(fminOrder.trim(), 10) : null,
      max_uses_total: fmaxUses.trim() ? parseInt(fmaxUses.trim(), 10) : null,
      max_uses_per_customer: fperCustomer.trim() ? parseInt(fperCustomer.trim(), 10) : null,
      starts_at: fstartsAt ? `${fstartsAt}T00:00:00Z` : null,
      expires_at: fexpiresAt ? `${fexpiresAt}T23:59:59Z` : null,
    };

    const r = await fetch("/api/ims/v1/admin/discounts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

    if (r.ok) {
      resetForm();
      setShowForm(false);
      setMsg("Discount created.");
      await load();
    } else {
      const payload = await r.json().catch(() => ({})) as { detail?: string };
      setMsg(payload.detail ?? `Create failed (${r.status})`);
    }
    setSaving(false);
  }

  async function toggleStatus(d: Discount) {
    const next = d.status === "active" ? "archived" : "active";
    const r = await fetch(`/api/ims/v1/admin/discounts/${d.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: next }),
    });
    if (r.ok) {
      const updated = (await r.json()) as Discount;
      setItems((prev) => prev.map((x) => (x.id === d.id ? updated : x)));
    } else {
      setErr(`Status update failed (${r.status})`);
    }
  }

  async function deleteDiscount(d: Discount) {
    if (!confirm(`Delete discount "${d.name}"? This cannot be undone.`)) return;
    const r = await fetch(`/api/ims/v1/admin/discounts/${d.id}`, {
      method: "DELETE",
    });
    if (r.ok || r.status === 204) {
      setItems((prev) => prev.filter((x) => x.id !== d.id));
      setMsg("Discount deleted.");
    } else {
      setErr(`Delete failed (${r.status})`);
    }
  }

  const activeCount = items.filter((d) => d.status === "active").length;
  const archivedCount = items.filter((d) => d.status === "archived").length;
  const withCodeCount = items.filter((d) => d.code !== null).length;
  const totalUses = items.reduce((acc, d) => acc + d.times_used, 0);

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="Commerce"
        title="Discounts"
        subtitle="Manage discount codes and automatic promotions."
        action={
          <PrimaryButton
            type="button"
            onClick={() => {
              setShowForm((v) => !v);
              if (!showForm) resetForm();
            }}
          >
            <span className="material-symbols-outlined text-lg">
              {showForm ? "close" : "add"}
            </span>
            {showForm ? "Cancel" : "New discount"}
          </PrimaryButton>
        }
      />

      {/* Stats row */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Active</p>
          <p className="mt-4 font-headline text-3xl font-extrabold text-primary">{activeCount}</p>
        </div>
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Archived</p>
          <p className="mt-4 font-headline text-3xl font-extrabold text-on-surface-variant">{archivedCount}</p>
        </div>
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">With code</p>
          <p className="mt-4 font-headline text-3xl font-extrabold text-primary">{withCodeCount}</p>
          <p className="mt-1 text-xs text-on-surface-variant">require code at checkout</p>
        </div>
        <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Total uses</p>
          <p className="mt-4 font-headline text-3xl font-extrabold text-primary">{totalUses}</p>
          <p className="mt-1 text-xs text-on-surface-variant">across all discounts</p>
        </div>
      </div>

      {/* Create form */}
      {showForm ? (
        <form
          onSubmit={onCreate}
          className="space-y-5 rounded-xl border border-outline-variant/10 bg-surface-container-low p-6 shadow-sm"
        >
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">
            New discount
          </p>

          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block text-sm font-medium text-on-surface">
              Name
              <TextInput
                required
                className="mt-1"
                value={fname}
                onChange={(e) => setFname(e.target.value)}
                placeholder="e.g. Summer sale 10%"
              />
            </label>

            <label className="block text-sm font-medium text-on-surface">
              Code
              <TextInput
                className="mt-1"
                value={fcode}
                onChange={(e) => setFcode(e.target.value.toUpperCase())}
                placeholder="Leave blank for automatic discount"
              />
            </label>

            <label className="block text-sm font-medium text-on-surface">
              Type
              <SelectInput
                className="mt-1"
                value={ftype}
                onChange={(v) => {
                  setFtype(v as Discount["discount_type"]);
                  setFvalue("");
                }}
                options={[
                  { value: "percentage", label: "% off" },
                  { value: "fixed_amount", label: "Fixed amount off" },
                  { value: "free_shipping", label: "Free shipping" },
                ]}
              />
            </label>

            {(ftype === "percentage" || ftype === "fixed_amount") ? (
              <label className="block text-sm font-medium text-on-surface">
                Value
                <TextInput
                  required
                  type="number"
                  min="0"
                  step={ftype === "percentage" ? "0.01" : "1"}
                  className="mt-1"
                  value={fvalue}
                  onChange={(e) => setFvalue(e.target.value)}
                  placeholder={
                    ftype === "percentage"
                      ? "e.g. 10 for 10% off"
                      : "e.g. 500 for ₹5.00 off"
                  }
                />
              </label>
            ) : (
              <div />
            )}

            <label className="block text-sm font-medium text-on-surface">
              Min. order
              <TextInput
                type="number"
                min="0"
                step="1"
                className="mt-1"
                value={fminOrder}
                onChange={(e) => setFminOrder(e.target.value)}
                placeholder="Minimum subtotal in cents (optional)"
              />
            </label>

            <label className="block text-sm font-medium text-on-surface">
              Max uses
              <TextInput
                type="number"
                min="1"
                step="1"
                className="mt-1"
                value={fmaxUses}
                onChange={(e) => setFmaxUses(e.target.value)}
                placeholder="Total usage limit (optional)"
              />
            </label>

            <label className="block text-sm font-medium text-on-surface">
              Per customer
              <TextInput
                type="number"
                min="1"
                step="1"
                className="mt-1"
                value={fperCustomer}
                onChange={(e) => setFperCustomer(e.target.value)}
                placeholder="Per customer limit (optional)"
              />
            </label>

            <label className="block text-sm font-medium text-on-surface">
              Starts at
              <TextInput
                type="date"
                className="mt-1"
                value={fstartsAt}
                onChange={(e) => setFstartsAt(e.target.value)}
              />
            </label>

            <label className="block text-sm font-medium text-on-surface">
              Expires at
              <TextInput
                type="date"
                className="mt-1"
                value={fexpiresAt}
                onChange={(e) => setFexpiresAt(e.target.value)}
              />
            </label>
          </div>

          <div className="flex flex-wrap gap-2 pt-1">
            <PrimaryButton type="submit" disabled={saving}>
              {saving ? "Creating…" : "Create discount"}
            </PrimaryButton>
            <SecondaryButton
              type="button"
              onClick={() => {
                setShowForm(false);
                resetForm();
              }}
            >
              Cancel
            </SecondaryButton>
          </div>
        </form>
      ) : null}

      {err ? <ErrorState detail={err} /> : null}
      {msg ? (
        <p className="text-sm text-on-surface-variant">{msg}</p>
      ) : null}

      {/* Table */}
      <Panel title="All discounts" subtitle="Click Archive or Delete to manage individual discounts." noPad>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-outline-variant/10">
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
                  Name
                </th>
                <th className="px-4 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
                  Code
                </th>
                <th className="px-4 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
                  Type
                </th>
                <th className="px-4 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
                  Value
                </th>
                <th className="px-4 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
                  Used
                </th>
                <th className="px-4 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
                  Expiry
                </th>
                <th className="px-4 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
                  Status
                </th>
                <th className="px-4 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {loading ? (
                <LoadingRow colSpan={8} label="Loading discounts…" />
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-6 py-10">
                    <EmptyState
                      title="No discounts yet"
                      detail="Create promo codes or automatic discounts to drive sales."
                      actionLabel="Create your first discount"
                      actionHref="?new=1"
                    />
                  </td>
                </tr>
              ) : (
                items.map((d) => (
                  <DiscountRow
                    key={d.id}
                    discount={d}
                    onToggle={toggleStatus}
                    onDelete={deleteDiscount}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}

function DiscountRow({
  discount: d,
  onToggle,
  onDelete,
}: {
  discount: Discount;
  onToggle: (d: Discount) => Promise<void>;
  onDelete: (d: Discount) => Promise<void>;
}) {
  const [toggling, setToggling] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function handleToggle() {
    setToggling(true);
    await onToggle(d);
    setToggling(false);
  }

  async function handleDelete() {
    setDeleting(true);
    await onDelete(d);
    setDeleting(false);
  }

  return (
    <tr className="hover:bg-surface-container-low/40">
      {/* Name */}
      <td className="px-6 py-4">
        <span className="font-medium text-on-surface">{d.name}</span>
      </td>

      {/* Code */}
      <td className="px-4 py-4">
        {d.code !== null ? (
          <code className="rounded bg-surface-container px-2 py-0.5 font-mono text-xs font-semibold text-on-surface">
            {d.code}
          </code>
        ) : (
          <Badge tone="default">Auto</Badge>
        )}
      </td>

      {/* Type */}
      <td className="px-4 py-4">
        <Badge tone={d.discount_type === "free_shipping" ? "good" : "default"}>
          {typeLabel(d.discount_type)}
        </Badge>
      </td>

      {/* Value */}
      <td className="px-4 py-4 tabular-nums text-on-surface">
        {displayValue(d)}
      </td>

      {/* Used */}
      <td className="px-4 py-4 tabular-nums text-on-surface-variant">
        {d.times_used}&nbsp;/&nbsp;{d.max_uses_total !== null ? d.max_uses_total : "∞"}
      </td>

      {/* Expiry */}
      <td className="px-4 py-4 text-on-surface-variant">
        {formatExpiry(d.expires_at)}
      </td>

      {/* Status */}
      <td className="px-4 py-4">
        <Badge tone={d.status === "active" ? "good" : "default"}>
          {d.status}
        </Badge>
      </td>

      {/* Actions */}
      <td className="px-4 py-4">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            disabled={toggling}
            onClick={handleToggle}
            className="inline-flex items-center gap-1 rounded-lg border border-outline-variant/40 px-3 py-1.5 text-xs font-semibold text-on-surface transition hover:bg-surface-container disabled:cursor-not-allowed disabled:opacity-60"
          >
            {toggling ? (
              "…"
            ) : d.status === "active" ? (
              <>
                <span className="material-symbols-outlined text-sm">archive</span>
                Archive
              </>
            ) : (
              <>
                <span className="material-symbols-outlined text-sm">unarchive</span>
                Activate
              </>
            )}
          </button>
          <button
            type="button"
            disabled={deleting}
            onClick={handleDelete}
            className="inline-flex items-center gap-1 rounded-lg border border-error/30 px-3 py-1.5 text-xs font-semibold text-error transition hover:bg-error-container/40 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {deleting ? (
              "…"
            ) : (
              <>
                <span className="material-symbols-outlined text-sm">delete</span>
                Delete
              </>
            )}
          </button>
        </div>
      </td>
    </tr>
  );
}
