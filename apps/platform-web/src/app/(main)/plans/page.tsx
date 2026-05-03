"use client";

import { useEffect, useState, FormEvent } from "react";

type Plan = {
  id: string;
  codename: string;
  display_name: string;
  description: string | null;
  base_price_cents: number;
  currency_code: string;
  yearly_discount_pct: number;
  max_shops: number;
  max_employees: number;
  storage_limit_mb: number;
  is_active: boolean;
  created_at: string;
};

type Addon = {
  id: string;
  codename: string;
  display_name: string;
  description: string | null;
  price_cents: number;
  currency_code: string;
  is_active: boolean;
  created_at: string;
};

function fmt(cents: number, code: string) {
  return `${code} ${(cents / 100).toLocaleString("en-IN", { minimumFractionDigits: 0 })}`;
}

function storageLabel(mb: number) {
  return mb >= 1024 ? `${mb / 1024} GB` : `${mb} MB`;
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function PlansPage() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [addons, setAddons] = useState<Addon[]>([]);
  const [loading, setLoading] = useState(true);

  const [editPlan, setEditPlan] = useState<Plan | null>(null);
  const [createPlan, setCreatePlan] = useState(false);
  const [editAddon, setEditAddon] = useState<Addon | null>(null);
  const [createAddon, setCreateAddon] = useState(false);

  async function load() {
    setLoading(true);
    const [pRes, aRes] = await Promise.all([
      fetch("/api/platform/v1/platform/plans"),
      fetch("/api/platform/v1/platform/addons"),
    ]);
    if (pRes.ok) setPlans(await pRes.json());
    if (aRes.ok) setAddons(await aRes.json());
    setLoading(false);
  }

  useEffect(() => { void load(); }, []);

  async function togglePlan(p: Plan) {
    await fetch(`/api/platform/v1/platform/plans/${p.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: !p.is_active }),
    });
    void load();
  }

  async function toggleAddon(a: Addon) {
    await fetch(`/api/platform/v1/platform/addons/${a.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: !a.is_active }),
    });
    void load();
  }

  if (loading) {
    return <div className="flex justify-center py-16"><div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" /></div>;
  }

  return (
    <div className="space-y-10">
      {/* Header */}
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Pricing configuration</p>
        <h1 className="mt-1 font-headline text-3xl font-extrabold text-on-surface">Plans & Add-ons</h1>
        <p className="mt-1 text-sm text-on-surface-variant">Manage subscription plans and optional add-on features available to tenants.</p>
      </div>

      {/* Plans section */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Base plans</h2>
          <button
            type="button"
            onClick={() => setCreatePlan(true)}
            className="ink-gradient inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold text-on-primary transition hover:opacity-90"
          >
            <span className="material-symbols-outlined text-base">add</span>
            New plan
          </button>
        </div>

        <div className="grid gap-4 lg:grid-cols-3">
          {plans.length === 0 ? (
            <div className="col-span-3 rounded-xl border border-dashed border-outline-variant/30 p-10 text-center text-sm text-on-surface-variant">
              No plans yet. Click &ldquo;New plan&rdquo; to create one.
            </div>
          ) : plans.map((p) => (
            <div key={p.id} className={`rounded-xl border bg-surface-container-lowest p-6 shadow-sm transition ${p.is_active ? "border-outline-variant/10" : "border-outline-variant/10 opacity-60"}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <h3 className="font-headline text-xl font-extrabold text-on-surface">{p.display_name}</h3>
                  <p className="font-mono text-[10px] text-on-surface-variant">{p.codename}</p>
                </div>
                {!p.is_active && (
                  <span className="shrink-0 rounded bg-surface-container-highest px-2 py-0.5 text-[10px] font-bold uppercase text-on-surface-variant">Inactive</span>
                )}
              </div>

              {p.description && <p className="mt-2 text-sm text-on-surface-variant">{p.description}</p>}

              <p className="mt-4 font-headline text-2xl font-extrabold text-primary">
                {fmt(p.base_price_cents, p.currency_code)}
                <span className="text-sm font-normal text-on-surface-variant">/mo</span>
              </p>
              {p.yearly_discount_pct > 0 && (
                <p className="text-xs text-tertiary">{p.yearly_discount_pct}% off billed yearly</p>
              )}

              <ul className="mt-4 space-y-1 text-sm text-on-surface-variant">
                <li className="flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-base text-primary">storefront</span>
                  {p.max_shops === -1 ? "Unlimited shops" : `${p.max_shops} shop${p.max_shops !== 1 ? "s" : ""}`}
                </li>
                <li className="flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-base text-primary">group</span>
                  {p.max_employees === -1 ? "Unlimited employees" : `${p.max_employees} employees`}
                </li>
                <li className="flex items-center gap-1.5">
                  <span className="material-symbols-outlined text-base text-primary">database</span>
                  {storageLabel(p.storage_limit_mb)} storage
                </li>
              </ul>

              <div className="mt-5 flex gap-2">
                <button
                  type="button"
                  onClick={() => setEditPlan(p)}
                  className="flex-1 rounded-lg border border-outline-variant/20 py-1.5 text-xs font-semibold text-on-surface transition hover:bg-surface-container-high"
                >
                  Edit
                </button>
                <button
                  type="button"
                  onClick={() => togglePlan(p)}
                  className="flex-1 rounded-lg border border-outline-variant/20 py-1.5 text-xs font-semibold text-on-surface transition hover:bg-surface-container-high"
                >
                  {p.is_active ? "Deactivate" : "Activate"}
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Add-ons section */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Add-ons</h2>
          <button
            type="button"
            onClick={() => setCreateAddon(true)}
            className="ink-gradient inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-semibold text-on-primary transition hover:opacity-90"
          >
            <span className="material-symbols-outlined text-base">add</span>
            New add-on
          </button>
        </div>

        <div className="overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm">
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-outline-variant/10">
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Name</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Codename</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Description</th>
                <th className="px-6 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Price/mo</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Status</th>
                <th className="px-6 py-3 text-center text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {addons.length === 0 ? (
                <tr><td colSpan={6} className="px-6 py-10 text-center text-sm text-on-surface-variant">No add-ons yet. Click &ldquo;New add-on&rdquo; to create one.</td></tr>
              ) : addons.map((a) => (
                <tr key={a.id} className={`hover:bg-surface-container-low/60 ${!a.is_active ? "opacity-50" : ""}`}>
                  <td className="px-6 py-3 font-semibold text-on-surface">{a.display_name}</td>
                  <td className="px-6 py-3 font-mono text-xs text-on-surface-variant">{a.codename}</td>
                  <td className="px-6 py-3 text-xs text-on-surface-variant">{a.description ?? "—"}</td>
                  <td className="px-6 py-3 text-right font-semibold tabular-nums text-on-surface">{fmt(a.price_cents, a.currency_code)}</td>
                  <td className="px-6 py-3">
                    <span className={`inline-flex rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase ${a.is_active ? "bg-tertiary-fixed text-on-tertiary-fixed-variant" : "bg-surface-container-highest text-on-surface"}`}>
                      {a.is_active ? "Active" : "Inactive"}
                    </span>
                  </td>
                  <td className="px-6 py-3">
                    <div className="flex justify-center gap-2">
                      <button
                        type="button"
                        onClick={() => setEditAddon(a)}
                        className="rounded-lg border border-outline-variant/20 px-3 py-1 text-xs font-semibold text-on-surface transition hover:bg-surface-container-high"
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => toggleAddon(a)}
                        className="rounded-lg border border-outline-variant/20 px-3 py-1 text-xs font-semibold text-on-surface transition hover:bg-surface-container-high"
                      >
                        {a.is_active ? "Deactivate" : "Activate"}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Modals */}
      {(createPlan || editPlan) && (
        <PlanModal
          plan={editPlan ?? undefined}
          onClose={() => { setCreatePlan(false); setEditPlan(null); }}
          onSaved={() => { setCreatePlan(false); setEditPlan(null); void load(); }}
        />
      )}
      {(createAddon || editAddon) && (
        <AddonModal
          addon={editAddon ?? undefined}
          onClose={() => { setCreateAddon(false); setEditAddon(null); }}
          onSaved={() => { setCreateAddon(false); setEditAddon(null); void load(); }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Plan modal (create + edit)
// ---------------------------------------------------------------------------

const CURRENCIES = ["INR", "USD", "EUR", "GBP", "AED", "SGD"];

function PlanModal({ plan, onClose, onSaved }: { plan?: Plan; onClose: () => void; onSaved: () => void }) {
  const isEdit = !!plan;

  const [codename, setCodename] = useState(plan?.codename ?? "");
  const [displayName, setDisplayName] = useState(plan?.display_name ?? "");
  const [description, setDescription] = useState(plan?.description ?? "");
  const [priceCents, setPriceCents] = useState(plan ? String(plan.base_price_cents / 100) : "");
  const [currency, setCurrency] = useState(plan?.currency_code ?? "INR");
  const [yearlyDiscount, setYearlyDiscount] = useState(plan ? String(plan.yearly_discount_pct) : "0");
  const [maxShops, setMaxShops] = useState(plan ? String(plan.max_shops) : "1");
  const [maxEmployees, setMaxEmployees] = useState(plan ? String(plan.max_employees) : "5");
  const [storageMb, setStorageMb] = useState(plan ? String(plan.storage_limit_mb) : "500");

  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setErr(null);
    const body = {
      codename: codename.trim(),
      display_name: displayName.trim(),
      description: description.trim() || null,
      base_price_cents: Math.round(parseFloat(priceCents) * 100),
      currency_code: currency,
      yearly_discount_pct: parseInt(yearlyDiscount) || 0,
      max_shops: parseInt(maxShops) || 1,
      max_employees: parseInt(maxEmployees) || 5,
      storage_limit_mb: parseInt(storageMb) || 500,
    };
    try {
      const r = await fetch(
        isEdit ? `/api/platform/v1/platform/plans/${plan!.id}` : "/api/platform/v1/platform/plans",
        { method: isEdit ? "PATCH" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
      );
      if (r.ok) { onSaved(); }
      else {
        const d = await r.json().catch(() => ({})) as { detail?: string };
        setErr(d.detail ?? `Failed (${r.status})`);
      }
    } catch { setErr("Network error."); }
    finally { setSaving(false); }
  }

  return (
    <Modal title={isEdit ? `Edit — ${plan!.display_name}` : "New plan"} onClose={onClose}>
      <form onSubmit={onSubmit} className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <Field label="Codename" required disabled={isEdit}>
            <input required disabled={isEdit} className={inputCls} value={codename}
              onChange={(e) => setCodename(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_"))}
              placeholder="e.g. starter" />
          </Field>
          <Field label="Display name" required>
            <input required className={inputCls} value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="e.g. Starter" />
          </Field>
        </div>

        <Field label="Description">
          <input className={inputCls} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Short tagline for this plan" />
        </Field>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Monthly price" required>
            <div className="relative">
              <select className="absolute left-0 top-0 h-full rounded-l-lg border border-r-0 border-outline-variant/30 bg-surface-container-low px-2 text-xs text-on-surface-variant outline-none" value={currency} onChange={(e) => setCurrency(e.target.value)}>
                {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
              </select>
              <input required type="number" min="0" step="0.01" className={`${inputCls} pl-[4.5rem]`} value={priceCents} onChange={(e) => setPriceCents(e.target.value)} placeholder="999" />
            </div>
          </Field>
          <Field label="Yearly discount %">
            <input type="number" min="0" max="100" className={inputCls} value={yearlyDiscount} onChange={(e) => setYearlyDiscount(e.target.value)} placeholder="0" />
          </Field>
        </div>

        <div className="grid grid-cols-3 gap-4">
          <Field label="Max shops">
            <input type="number" min="1" className={inputCls} value={maxShops} onChange={(e) => setMaxShops(e.target.value)} />
          </Field>
          <Field label="Max employees">
            <input type="number" min="1" className={inputCls} value={maxEmployees} onChange={(e) => setMaxEmployees(e.target.value)} />
          </Field>
          <Field label="Storage (MB)">
            <input type="number" min="1" className={inputCls} value={storageMb} onChange={(e) => setStorageMb(e.target.value)} />
          </Field>
        </div>

        {err && <p className="text-sm text-error">{err}</p>}
        <ModalActions saving={saving} label={isEdit ? "Save changes" : "Create plan"} onClose={onClose} />
      </form>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Add-on modal (create + edit)
// ---------------------------------------------------------------------------

function AddonModal({ addon, onClose, onSaved }: { addon?: Addon; onClose: () => void; onSaved: () => void }) {
  const isEdit = !!addon;

  const [codename, setCodename] = useState(addon?.codename ?? "");
  const [displayName, setDisplayName] = useState(addon?.display_name ?? "");
  const [description, setDescription] = useState(addon?.description ?? "");
  const [priceCents, setPriceCents] = useState(addon ? String(addon.price_cents / 100) : "");
  const [currency, setCurrency] = useState(addon?.currency_code ?? "INR");

  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setErr(null);
    const body = {
      codename: codename.trim(),
      display_name: displayName.trim(),
      description: description.trim() || null,
      price_cents: Math.round(parseFloat(priceCents) * 100),
      currency_code: currency,
    };
    try {
      const r = await fetch(
        isEdit ? `/api/platform/v1/platform/addons/${addon!.id}` : "/api/platform/v1/platform/addons",
        { method: isEdit ? "PATCH" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
      );
      if (r.ok) { onSaved(); }
      else {
        const d = await r.json().catch(() => ({})) as { detail?: string };
        setErr(d.detail ?? `Failed (${r.status})`);
      }
    } catch { setErr("Network error."); }
    finally { setSaving(false); }
  }

  return (
    <Modal title={isEdit ? `Edit — ${addon!.display_name}` : "New add-on"} onClose={onClose}>
      <form onSubmit={onSubmit} className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <Field label="Codename" required disabled={isEdit}>
            <input required disabled={isEdit} className={inputCls} value={codename}
              onChange={(e) => setCodename(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_"))}
              placeholder="e.g. extra_shop" />
          </Field>
          <Field label="Display name" required>
            <input required className={inputCls} value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="e.g. Extra Shop" />
          </Field>
        </div>

        <Field label="Description">
          <input className={inputCls} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What does this add-on unlock?" />
        </Field>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Monthly price" required>
            <div className="relative">
              <select className="absolute left-0 top-0 h-full rounded-l-lg border border-r-0 border-outline-variant/30 bg-surface-container-low px-2 text-xs text-on-surface-variant outline-none" value={currency} onChange={(e) => setCurrency(e.target.value)}>
                {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
              </select>
              <input required type="number" min="0" step="0.01" className={`${inputCls} pl-[4.5rem]`} value={priceCents} onChange={(e) => setPriceCents(e.target.value)} placeholder="499" />
            </div>
          </Field>
        </div>

        {err && <p className="text-sm text-error">{err}</p>}
        <ModalActions saving={saving} label={isEdit ? "Save changes" : "Create add-on"} onClose={onClose} />
      </form>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Shared primitives
// ---------------------------------------------------------------------------

const inputCls = "w-full rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-2 text-sm text-on-surface outline-none focus:border-primary disabled:opacity-50";

function Field({ label, required, disabled, children }: { label: string; required?: boolean; disabled?: boolean; children: React.ReactNode }) {
  return (
    <label className={`block text-sm font-medium text-on-surface ${disabled ? "opacity-50" : ""}`}>
      {label}{required && <span className="ml-0.5 text-error">*</span>}
      <div className="mt-1">{children}</div>
    </label>
  );
}

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="w-full max-w-lg rounded-2xl bg-surface shadow-xl max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="ink-gradient rounded-t-2xl px-6 py-5">
          <p className="font-headline text-xl font-extrabold text-on-primary">{title}</p>
        </div>
        <div className="p-6">{children}</div>
      </div>
    </div>
  );
}

function ModalActions({ saving, label, onClose }: { saving: boolean; label: string; onClose: () => void }) {
  return (
    <div className="flex gap-2 pt-2">
      <button type="submit" disabled={saving} className="ink-gradient rounded-lg px-6 py-2.5 text-sm font-semibold text-on-primary disabled:opacity-50">
        {saving ? "Saving…" : label}
      </button>
      <button type="button" onClick={onClose} className="rounded-lg border border-outline-variant/20 px-5 py-2.5 text-sm font-semibold text-on-surface-variant transition hover:bg-surface-container">
        Cancel
      </button>
    </div>
  );
}
