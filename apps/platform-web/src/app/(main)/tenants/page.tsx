"use client";

import Link from "next/link";
import { useEffect, useState, FormEvent } from "react";

type Tenant = {
  id: string;
  name: string;
  slug: string;
  region: string;
  download_token: string;
  created_at: string;
};

const REGIONS = ["in", "us", "eu", "sg", "ae"];
const CURRENCIES = [
  { code: "INR", label: "INR — Indian Rupee", exponent: 2 },
  { code: "USD", label: "USD — US Dollar", exponent: 2 },
  { code: "EUR", label: "EUR — Euro", exponent: 2 },
  { code: "GBP", label: "GBP — British Pound", exponent: 2 },
  { code: "AED", label: "AED — UAE Dirham", exponent: 2 },
  { code: "SGD", label: "SGD — Singapore Dollar", exponent: 2 },
  { code: "IDR", label: "IDR — Indonesian Rupiah", exponent: 0 },
];

export default function TenantsPage() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [showCreate, setShowCreate] = useState(false);

  useEffect(() => {
    async function load() {
      setLoading(true);
      const sp = new URLSearchParams();
      if (q.trim()) sp.set("q", q.trim());
      const r = await fetch(`/api/platform/v1/platform/tenants?${sp}`);
      if (r.ok) {
        const d = await r.json();
        setTenants(d.items ?? []);
      }
      setLoading(false);
    }
    const t = setTimeout(load, 300);
    return () => clearTimeout(t);
  }, [q]);

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Tenant registry</p>
          <h1 className="mt-1 font-headline text-3xl font-extrabold text-on-surface">Tenants</h1>
        </div>
        <button
          type="button"
          onClick={() => setShowCreate(true)}
          className="ink-gradient inline-flex items-center gap-2 rounded-lg px-6 py-2.5 text-sm font-semibold text-on-primary shadow-sm transition hover:opacity-90"
        >
          <span className="material-symbols-outlined text-lg">add</span>
          New Tenant
        </button>
      </div>

      <input
        type="text"
        placeholder="Search tenants..."
        value={q}
        onChange={(e) => setQ(e.target.value)}
        className="w-full max-w-md rounded-lg border border-outline-variant/30 bg-surface-container-lowest px-4 py-2.5 text-sm text-on-surface outline-none focus:border-primary"
      />

      <div className="overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm">
        <table className="min-w-full text-left text-sm">
          <thead>
            <tr className="border-b border-outline-variant/10">
              <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Name</th>
              <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Slug</th>
              <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Region</th>
              <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Created</th>
              <th className="px-6 py-3 text-center text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-outline-variant/10">
            {loading ? (
              <tr><td colSpan={5} className="px-6 py-12 text-center text-sm text-on-surface-variant">Loading...</td></tr>
            ) : tenants.length === 0 ? (
              <tr><td colSpan={5} className="px-6 py-12 text-center text-sm text-on-surface-variant">No tenants found.</td></tr>
            ) : tenants.map((t) => (
              <tr key={t.id} className="hover:bg-surface-container-low/60">
                <td className="px-6 py-3 font-semibold text-on-surface">{t.name}</td>
                <td className="px-6 py-3 font-mono text-xs text-on-surface-variant">{t.slug}</td>
                <td className="px-6 py-3">
                  <span className="inline-flex rounded-full bg-primary/10 px-2.5 py-0.5 text-[10px] font-bold uppercase text-primary">
                    {t.region}
                  </span>
                </td>
                <td className="px-6 py-3 text-xs text-on-surface-variant">
                  {new Date(t.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}
                </td>
                <td className="px-6 py-3 text-center">
                  <Link
                    href={`/tenants/${t.id}`}
                    className="inline-flex items-center gap-1 rounded-lg border border-outline-variant/20 px-3 py-1.5 text-xs font-semibold text-on-surface transition hover:bg-surface-container-high"
                  >
                    <span className="material-symbols-outlined text-sm">open_in_new</span>
                    Detail
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {showCreate && (
        <CreateTenantModal
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false);
            setQ("");
          }}
        />
      )}
    </div>
  );
}

function CreateTenantModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [region, setRegion] = useState("in");
  const [apiBaseUrl, setApiBaseUrl] = useState("http://api:8000");
  const [currency, setCurrency] = useState("INR");
  const [currencyExponent, setCurrencyExponent] = useState(2);
  const [adminEmail, setAdminEmail] = useState("");
  const [adminPassword, setAdminPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  function handleNameChange(val: string) {
    setName(val);
    if (!slug) setSlug(val.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""));
  }

  function handleCurrencyChange(code: string) {
    setCurrency(code);
    const found = CURRENCIES.find((c) => c.code === code);
    if (found) setCurrencyExponent(found.exponent);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim() || !slug.trim() || !adminEmail.trim() || !adminPassword) {
      setErr("All required fields must be filled.");
      return;
    }
    setSaving(true);
    setErr(null);
    try {
      const r = await fetch("/api/platform/v1/platform/tenants", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          slug: slug.trim(),
          region,
          api_base_url: apiBaseUrl.trim(),
          default_currency_code: currency,
          currency_exponent: currencyExponent,
          initial_admin_email: adminEmail.trim(),
          initial_admin_password: adminPassword,
        }),
      });
      if (r.ok) {
        onCreated();
      } else {
        const d = await r.json().catch(() => ({})) as { detail?: string };
        setErr(d.detail ?? `Failed (${r.status})`);
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
          <p className="text-xs font-bold uppercase tracking-widest text-on-primary/80">Tenant registry</p>
          <p className="mt-1 font-headline text-xl font-extrabold text-on-primary">New Tenant</p>
        </div>

        <form onSubmit={onSubmit} className="space-y-4 p-6">
          {/* Tenant details */}
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Tenant details</p>

          <label className="block text-sm font-medium text-on-surface">
            Business name <span className="text-error">*</span>
            <input
              required
              className="mt-1 w-full rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-2 text-sm outline-none focus:border-primary"
              value={name}
              onChange={(e) => handleNameChange(e.target.value)}
              placeholder="e.g. Sunrise Mart"
            />
          </label>

          <label className="block text-sm font-medium text-on-surface">
            Slug <span className="text-error">*</span>
            <input
              required
              className="mt-1 w-full rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-2 font-mono text-sm outline-none focus:border-primary"
              value={slug}
              onChange={(e) => setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))}
              placeholder="e.g. sunrise-mart"
            />
          </label>

          <div className="grid grid-cols-2 gap-4">
            <label className="block text-sm font-medium text-on-surface">
              Region
              <select
                className="mt-1 w-full rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-2 text-sm outline-none focus:border-primary"
                value={region}
                onChange={(e) => setRegion(e.target.value)}
              >
                {REGIONS.map((r) => <option key={r} value={r}>{r.toUpperCase()}</option>)}
              </select>
            </label>

            <label className="block text-sm font-medium text-on-surface">
              Currency
              <select
                className="mt-1 w-full rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-2 text-sm outline-none focus:border-primary"
                value={currency}
                onChange={(e) => handleCurrencyChange(e.target.value)}
              >
                {CURRENCIES.map((c) => <option key={c.code} value={c.code}>{c.label}</option>)}
              </select>
            </label>
          </div>

          <label className="block text-sm font-medium text-on-surface">
            API base URL
            <input
              className="mt-1 w-full rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-2 font-mono text-sm outline-none focus:border-primary"
              value={apiBaseUrl}
              onChange={(e) => setApiBaseUrl(e.target.value)}
            />
          </label>

          {/* Initial admin */}
          <div className="border-t border-outline-variant/10 pt-4">
            <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Initial admin account</p>
            <p className="mt-1 text-xs text-on-surface-variant">This is the first operator who can log into the admin web dashboard.</p>
          </div>

          <label className="block text-sm font-medium text-on-surface">
            Email <span className="text-error">*</span>
            <input
              type="email"
              required
              className="mt-1 w-full rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-2 text-sm outline-none focus:border-primary"
              value={adminEmail}
              onChange={(e) => setAdminEmail(e.target.value)}
              placeholder="owner@example.com"
            />
          </label>

          <label className="block text-sm font-medium text-on-surface">
            Password <span className="text-error">*</span>
            <div className="relative mt-1">
              <input
                type={showPassword ? "text" : "password"}
                required
                minLength={8}
                className="w-full rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-2 pr-10 text-sm outline-none focus:border-primary"
                value={adminPassword}
                onChange={(e) => setAdminPassword(e.target.value)}
                placeholder="Min. 8 characters"
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-on-surface-variant"
              >
                <span className="material-symbols-outlined text-base">{showPassword ? "visibility_off" : "visibility"}</span>
              </button>
            </div>
          </label>

          {err && <p className="text-sm text-error">{err}</p>}

          <div className="flex gap-2 pt-2">
            <button
              type="submit"
              disabled={saving}
              className="ink-gradient inline-flex items-center gap-2 rounded-lg px-6 py-2.5 text-sm font-semibold text-on-primary disabled:opacity-50"
            >
              {saving ? "Creating…" : "Create tenant"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-outline-variant/20 px-5 py-2.5 text-sm font-semibold text-on-surface-variant transition hover:bg-surface-container"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
