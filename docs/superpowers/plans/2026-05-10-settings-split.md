# Settings Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 805-line settings monolith with a Settings Index card grid + 7 focused sub-pages, each containing exactly one extracted section.

**Architecture:** The existing `settings/page.tsx` is rewritten as a pure index (card grid + danger zone). Seven new `page.tsx` files are created under `settings/` by extracting the relevant state, effects, handlers, and JSX from the current monolith unchanged. Each sub-page gains breadcrumb navigation. One link in the dashboard setup checklist is updated. No API calls, no backend changes.

**Tech Stack:** Next.js 15 App Router / TypeScript / Tailwind. Components: `Breadcrumbs`, `PageHeader`, `PrimaryButton`, `SecondaryButton`, `SelectInput`, `TextInput`, `Toggle` from `@/components/ui/primitives`. Hooks: `useBusinessType` from `@/lib/business-type-context`, `TIMEZONE_OPTIONS`/`MONTH_OPTIONS` from `@/lib/timezones`.

---

## Codebase context

### Pattern used by every sub-page
```tsx
"use client";
import { Breadcrumbs, PageHeader, ... } from "@/components/ui/primitives";

export default function Settings<Section>Page() {
  // ... state + effects + handlers from current monolith ...
  return (
    <div className="space-y-8">
      <Breadcrumbs items={[{ label: "Settings", href: "/settings" }, { label: "<Section>" }]} />
      <PageHeader kicker="Settings" title="<Section>" subtitle="<one-liner>" />
      {/* ... section content from monolith ... */}
    </div>
  );
}
```

### Deploy
```bash
docker compose up --build -d admin-web 2>&1 | grep -E "✓ Compiled|error TS|Error:|failed" | tail -5
```

---

## File map

| File | Status |
|---|---|
| `apps/admin-web/src/app/(main)/settings/page.tsx` | REWRITE — index grid + danger zone |
| `apps/admin-web/src/app/(main)/settings/email/page.tsx` | NEW |
| `apps/admin-web/src/app/(main)/settings/currency/page.tsx` | NEW |
| `apps/admin-web/src/app/(main)/settings/localisation/page.tsx` | NEW |
| `apps/admin-web/src/app/(main)/settings/devices/page.tsx` | NEW |
| `apps/admin-web/src/app/(main)/settings/reconciliation/page.tsx` | NEW |
| `apps/admin-web/src/app/(main)/settings/customer-groups/page.tsx` | NEW |
| `apps/admin-web/src/app/(main)/settings/business-type/page.tsx` | NEW |
| `apps/admin-web/src/app/(main)/overview/page.tsx` | MODIFY — email item href |

---

## Task 1: Settings Index page (rewrite settings/page.tsx)

**Files:**
- Modify: `apps/admin-web/src/app/(main)/settings/page.tsx`

- [ ] **Step 1: Replace settings/page.tsx with the index grid**

```tsx
"use client";

import Link from "next/link";

const SETTINGS_CARDS = [
  {
    href: "/settings/email",
    icon: "mail",
    title: "Email",
    description: "Configure SMTP or SendGrid for staff invites and notifications",
  },
  {
    href: "/settings/currency",
    icon: "payments",
    title: "Currency",
    description: "View your default currency and symbol",
  },
  {
    href: "/settings/localisation",
    icon: "language",
    title: "Localisation",
    description: "Set your timezone and financial year start month",
  },
  {
    href: "/settings/devices",
    icon: "devices",
    title: "Devices",
    description: "POS device security and employee session timeouts",
  },
  {
    href: "/settings/reconciliation",
    icon: "account_balance",
    title: "Reconciliation",
    description: "Auto-resolve thresholds for shift close variances",
  },
  {
    href: "/settings/customer-groups",
    icon: "groups",
    title: "Customer Groups",
    description: "Manage customer segment labels for reporting",
  },
  {
    href: "/settings/business-type",
    icon: "storefront",
    title: "Business Type",
    description: "Switch between online, retail, or hybrid mode",
  },
];

export default function SettingsIndexPage() {
  return (
    <div className="space-y-10">
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Platform</p>
        <h2 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">Settings</h2>
        <p className="mt-2 font-light text-on-surface-variant">Choose a section to configure.</p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {SETTINGS_CARDS.map((card) => (
          <Link
            key={card.href}
            href={card.href}
            className="flex items-start gap-4 rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-sm transition-all hover:border-primary/30 hover:bg-primary/5 hover:shadow-md"
          >
            <span className="material-symbols-outlined mt-0.5 text-2xl text-primary" aria-hidden="true">
              {card.icon}
            </span>
            <div className="flex-1">
              <p className="font-headline text-base font-bold text-on-surface">{card.title}</p>
              <p className="mt-0.5 text-sm text-on-surface-variant">{card.description}</p>
            </div>
            <span className="material-symbols-outlined shrink-0 text-xl text-on-surface-variant/40" aria-hidden="true">
              chevron_right
            </span>
          </Link>
        ))}
      </div>

      {/* Danger zone */}
      <section className="rounded-xl border border-error/20 bg-error-container/20 p-6 shadow-sm">
        <h3 className="font-headline text-lg font-bold text-error">Danger zone</h3>
        <p className="mt-2 text-sm text-on-error-container">
          Reset demo data and cached UI preferences for this tenant. This cannot be undone from the console alone.
        </p>
        <div className="mt-4">
          <button
            type="button"
            className="rounded-lg border border-error/40 px-4 py-2 text-sm font-semibold text-error hover:bg-error-container/30"
          >
            Reset tenant preferences
          </button>
        </div>
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

```bash
docker compose up --build -d admin-web 2>&1 | grep -E "✓ Compiled|error TS|Error:|failed" | tail -5
```

Expected: `✓ Compiled successfully`.

- [ ] **Step 3: Commit**

```bash
git add 'apps/admin-web/src/app/(main)/settings/page.tsx'
git commit -m "feat(admin-web): settings index page — card grid replaces monolith"
```

---

## Task 2: Email sub-page

**Files:**
- Create: `apps/admin-web/src/app/(main)/settings/email/page.tsx`

- [ ] **Step 1: Create the file**

```tsx
"use client";

import { useEffect, useState } from "react";
import {
  Breadcrumbs,
  PageHeader,
  PrimaryButton,
  SecondaryButton,
  SelectInput,
  TextInput,
  Toggle,
} from "@/components/ui/primitives";

export default function SettingsEmailPage() {
  const [saving, setSaving] = useState(false);
  const [emailProvider, setEmailProvider] = useState<"smtp" | "sendgrid">("smtp");
  const [smtpHost, setSmtpHost] = useState("");
  const [smtpPort, setSmtpPort] = useState("587");
  const [smtpUsername, setSmtpUsername] = useState("");
  const [smtpPassword, setSmtpPassword] = useState("");
  const [sendgridApiKey, setSendgridApiKey] = useState("");
  const [fromEmail, setFromEmail] = useState("");
  const [fromName, setFromName] = useState("");
  const [emailActive, setEmailActive] = useState(true);
  const [emailLoading, setEmailLoading] = useState(true);
  const [emailMessage, setEmailMessage] = useState<string | null>(null);
  const [emailError, setEmailError] = useState<string | null>(null);
  const [testEmail, setTestEmail] = useState("");
  const [testingEmail, setTestingEmail] = useState(false);

  useEffect(() => {
    async function load() {
      setEmailLoading(true);
      setEmailError(null);
      try {
        const res = await fetch("/api/ims/v1/admin/tenant-settings/email");
        if (res.ok) {
          const cfg = (await res.json()) as {
            provider: "smtp" | "sendgrid";
            smtp_host: string | null;
            smtp_port: number | null;
            smtp_username: string | null;
            from_email: string;
            from_name: string | null;
            is_active: boolean;
          };
          setEmailProvider(cfg.provider);
          setSmtpHost(cfg.smtp_host ?? "");
          setSmtpPort(cfg.smtp_port ? String(cfg.smtp_port) : "587");
          setSmtpUsername(cfg.smtp_username ?? "");
          setFromEmail(cfg.from_email ?? "");
          setFromName(cfg.from_name ?? "");
          setEmailActive(cfg.is_active);
          setTestEmail(cfg.from_email ?? "");
        } else if (res.status === 404) {
          setEmailMessage("Email provider is not configured yet.");
        } else {
          throw new Error(await res.text());
        }
      } catch (e) {
        setEmailError(e instanceof Error ? e.message : "Failed to load email settings");
      } finally {
        setEmailLoading(false);
      }
    }
    void load();
  }, []);

  async function saveEmailConfig() {
    setEmailError(null);
    setEmailMessage(null);
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {
        provider: emailProvider,
        from_email: fromEmail,
        from_name: fromName || null,
        is_active: emailActive,
      };
      if (emailProvider === "smtp") {
        payload.smtp_host = smtpHost;
        payload.smtp_port = Number(smtpPort);
        payload.smtp_username = smtpUsername || null;
        if (smtpPassword.trim()) payload.smtp_password = smtpPassword;
      } else {
        if (sendgridApiKey.trim()) payload.api_key = sendgridApiKey;
      }
      const res = await fetch("/api/ims/v1/admin/tenant-settings/email", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await res.text());
      setSmtpPassword("");
      setSendgridApiKey("");
      setEmailMessage("Email configuration saved.");
    } catch (e) {
      setEmailError(e instanceof Error ? e.message : "Failed to save email configuration");
    } finally {
      setSaving(false);
    }
  }

  async function sendTestEmail() {
    setTestingEmail(true);
    setEmailError(null);
    setEmailMessage(null);
    try {
      const res = await fetch("/api/ims/v1/admin/tenant-settings/email/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ to_email: testEmail }),
      });
      if (!res.ok) throw new Error(await res.text());
      setEmailMessage("Test email sent.");
    } catch (e) {
      setEmailError(e instanceof Error ? e.message : "Failed to send test email");
    } finally {
      setTestingEmail(false);
    }
  }

  return (
    <div className="space-y-8">
      <Breadcrumbs items={[{ label: "Settings", href: "/settings" }, { label: "Email" }]} />
      <PageHeader kicker="Settings" title="Email" subtitle="Configure SMTP or SendGrid for staff invites and notifications." />

      <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
        <h3 className="font-headline text-lg font-bold text-primary">Staff invite email provider</h3>
        <p className="mt-1 text-sm text-on-surface-variant">
          Configure SMTP or SendGrid. Staff invites and re-enrollment email depend on this.
        </p>

        {emailLoading ? <p className="mt-4 text-sm text-on-surface-variant">Loading email settings...</p> : (
          <div className="mt-5 space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">Provider</label>
                <SelectInput
                  value={emailProvider}
                  onChange={(value) => setEmailProvider(value as "smtp" | "sendgrid")}
                  options={[{ value: "smtp", label: "SMTP" }, { value: "sendgrid", label: "SendGrid" }]}
                />
              </div>
              <div className="flex items-end justify-between rounded-lg border border-outline-variant/20 bg-surface-container-low p-3">
                <div>
                  <p className="text-sm font-semibold text-on-surface">Enable email delivery</p>
                  <p className="text-xs text-on-surface-variant">When off, email invite actions are blocked.</p>
                </div>
                <Toggle checked={emailActive} onChange={setEmailActive} />
              </div>
            </div>

            {emailProvider === "smtp" ? (
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">SMTP host</label>
                  <TextInput value={smtpHost} onChange={(e) => setSmtpHost(e.target.value)} placeholder="smtp.example.com" />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">SMTP port</label>
                  <TextInput value={smtpPort} onChange={(e) => setSmtpPort(e.target.value)} placeholder="587" type="number" />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">SMTP username</label>
                  <TextInput value={smtpUsername} onChange={(e) => setSmtpUsername(e.target.value)} placeholder="username" />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">SMTP password</label>
                  <TextInput value={smtpPassword} onChange={(e) => setSmtpPassword(e.target.value)} placeholder="leave blank to keep current" type="password" />
                </div>
              </div>
            ) : (
              <div>
                <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">SendGrid API key</label>
                <TextInput value={sendgridApiKey} onChange={(e) => setSendgridApiKey(e.target.value)} placeholder="leave blank to keep current" type="password" />
              </div>
            )}

            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">From email</label>
                <TextInput value={fromEmail} onChange={(e) => setFromEmail(e.target.value)} placeholder="noreply@tenant.com" type="email" />
              </div>
              <div>
                <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">From name</label>
                <TextInput value={fromName} onChange={(e) => setFromName(e.target.value)} placeholder="Inventory Team" />
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <PrimaryButton type="button" disabled={saving || !fromEmail.trim()} onClick={() => void saveEmailConfig()}>
                {saving ? "Saving..." : "Save email provider"}
              </PrimaryButton>
              <TextInput value={testEmail} onChange={(e) => setTestEmail(e.target.value)} placeholder="test recipient" type="email" className="max-w-xs" />
              <SecondaryButton type="button" disabled={testingEmail || !testEmail.trim()} onClick={() => void sendTestEmail()}>
                {testingEmail ? "Sending..." : "Send test email"}
              </SecondaryButton>
            </div>

            {emailMessage && <p className="text-sm font-semibold text-primary">{emailMessage}</p>}
            {emailError && (
              <p className="rounded-lg border border-error/20 bg-error-container/20 px-3 py-2 text-sm text-on-error-container">{emailError}</p>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Build + commit**

```bash
docker compose up --build -d admin-web 2>&1 | grep -E "✓ Compiled|error TS|Error:|failed" | tail -5
git add 'apps/admin-web/src/app/(main)/settings/email/page.tsx'
git commit -m "feat(admin-web): settings/email sub-page"
```

---

## Task 3: Currency + Localisation + Devices sub-pages

**Files:**
- Create: `apps/admin-web/src/app/(main)/settings/currency/page.tsx`
- Create: `apps/admin-web/src/app/(main)/settings/localisation/page.tsx`
- Create: `apps/admin-web/src/app/(main)/settings/devices/page.tsx`

- [ ] **Step 1: Create currency/page.tsx**

```tsx
"use client";

import { useEffect, useState } from "react";
import { Breadcrumbs, PageHeader } from "@/components/ui/primitives";

type CurrencySettings = {
  currency_code: string;
  currency_symbol: string;
  currency_exponent: number;
  supported_currencies: Array<{ code: string; symbol: string; name: string; exponent: number }>;
};

export default function SettingsCurrencyPage() {
  const [currencySettings, setCurrencySettings] = useState<CurrencySettings | null>(null);
  const [currencyLoading, setCurrencyLoading] = useState(true);

  useEffect(() => {
    async function load() {
      setCurrencyLoading(true);
      try {
        const res = await fetch("/api/ims/v1/admin/tenant-settings/currency");
        if (res.ok) setCurrencySettings((await res.json()) as CurrencySettings);
      } finally {
        setCurrencyLoading(false);
      }
    }
    void load();
  }, []);

  return (
    <div className="space-y-8">
      <Breadcrumbs items={[{ label: "Settings", href: "/settings" }, { label: "Currency" }]} />
      <PageHeader kicker="Settings" title="Currency" subtitle="Your tenant's currency is managed by your platform administrator." />

      <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
        <h3 className="font-headline text-lg font-bold text-primary">Currency</h3>
        <p className="mt-1 text-sm text-on-surface-variant">
          Your tenant&rsquo;s currency is managed by your platform administrator. To request a change, contact support.
        </p>
        {currencyLoading ? (
          <p className="mt-4 text-sm text-on-surface-variant">Loading currency settings…</p>
        ) : currencySettings ? (
          <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
            <div>
              <dt className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Code</dt>
              <dd className="mt-1 text-sm font-semibold text-on-surface">{currencySettings.currency_code}</dd>
            </div>
            <div>
              <dt className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Symbol</dt>
              <dd className="mt-1 text-sm font-semibold text-on-surface">{currencySettings.currency_symbol}</dd>
            </div>
            <div>
              <dt className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Exponent</dt>
              <dd className="mt-1 text-sm font-semibold text-on-surface">{currencySettings.currency_exponent}</dd>
            </div>
          </dl>
        ) : null}
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Create localisation/page.tsx**

```tsx
"use client";

import { useEffect, useState } from "react";
import { Breadcrumbs, PageHeader, PrimaryButton, SelectInput } from "@/components/ui/primitives";
import { TIMEZONE_OPTIONS, MONTH_OPTIONS } from "@/lib/timezones";

export default function SettingsLocalisationPage() {
  const [localisationTimezone, setLocalisationTimezone] = useState("");
  const [localisationFyMonth, setLocalisationFyMonth] = useState("");
  const [localisationLoading, setLocalisationLoading] = useState(true);
  const [localisationMessage, setLocalisationMessage] = useState<string | null>(null);
  const [localisationError, setLocalisationError] = useState<string | null>(null);
  const [localisationSaving, setLocalisationSaving] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const r = await fetch("/api/ims/v1/admin/tenant-settings/localisation");
        if (!r.ok) { setLocalisationLoading(false); return; }
        const data = await r.json() as { timezone: string | null; financial_year_start_month: number | null };
        setLocalisationTimezone(data.timezone ?? "");
        setLocalisationFyMonth(data.financial_year_start_month ? String(data.financial_year_start_month) : "");
        setLocalisationLoading(false);
      } catch {
        setLocalisationLoading(false);
      }
    })();
  }, []);

  async function saveLocalisation() {
    setLocalisationMessage(null);
    setLocalisationError(null);
    setLocalisationSaving(true);
    try {
      const body: Record<string, string | number | null> = {
        timezone: localisationTimezone || null,
        financial_year_start_month: localisationFyMonth ? parseInt(localisationFyMonth, 10) : null,
      };
      const r = await fetch("/api/ims/v1/admin/tenant-settings/localisation", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (r.ok) {
        setLocalisationMessage("Localisation settings saved.");
      } else {
        const b = await r.json().catch(() => ({})) as { detail?: string };
        setLocalisationError(b.detail ?? `Save failed (${r.status})`);
      }
    } catch {
      setLocalisationError("Network error. Please try again.");
    } finally {
      setLocalisationSaving(false);
    }
  }

  return (
    <div className="space-y-8">
      <Breadcrumbs items={[{ label: "Settings", href: "/settings" }, { label: "Localisation" }]} />
      <PageHeader kicker="Settings" title="Localisation" subtitle="Set your timezone and financial year start month." />

      <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm space-y-4">
        <h3 className="font-headline text-lg font-bold text-primary">Localisation</h3>
        {localisationLoading ? (
          <p className="text-sm text-on-surface-variant">Loading localisation settings…</p>
        ) : (
          <>
            <label className="block text-sm font-medium text-on-surface">
              Timezone
              <SelectInput className="mt-1" value={localisationTimezone} onChange={setLocalisationTimezone} placeholder="Select timezone…"
                options={[{ value: "", label: "— Use UTC (default) —" }, ...TIMEZONE_OPTIONS.map((t) => ({ value: t.value, label: t.label }))]} />
            </label>
            <label className="block text-sm font-medium text-on-surface">
              Financial year start month
              <SelectInput className="mt-1" value={localisationFyMonth} onChange={setLocalisationFyMonth} placeholder="Select month…"
                options={[{ value: "", label: "— January (default) —" }, ...MONTH_OPTIONS.map((m) => ({ value: String(m.value), label: m.label }))]} />
            </label>
            {localisationMessage && <p className="text-sm text-primary">{localisationMessage}</p>}
            {localisationError && <p className="text-sm text-error">{localisationError}</p>}
            <PrimaryButton type="button" disabled={localisationSaving} onClick={() => void saveLocalisation()}>
              {localisationSaving ? "Saving…" : "Save localisation"}
            </PrimaryButton>
          </>
        )}
      </section>
    </div>
  );
}
```

- [ ] **Step 3: Create devices/page.tsx**

```tsx
"use client";

import { useEffect, useState } from "react";
import { Breadcrumbs, PageHeader, PrimaryButton, TextInput } from "@/components/ui/primitives";

export default function SettingsDevicesPage() {
  const [deviceSecurity, setDeviceSecurity] = useState<{ max_offline_minutes: number; employee_session_timeout_minutes: number } | null>(null);
  const [maxOfflineMinutes, setMaxOfflineMinutes] = useState("60");
  const [sessionTimeoutMinutes, setSessionTimeoutMinutes] = useState("30");
  const [deviceSecurityLoading, setDeviceSecurityLoading] = useState(true);
  const [deviceSecuritySaving, setDeviceSecuritySaving] = useState(false);
  const [deviceSecurityMessage, setDeviceSecurityMessage] = useState<string | null>(null);
  const [deviceSecurityError, setDeviceSecurityError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setDeviceSecurityLoading(true);
      try {
        const res = await fetch("/api/ims/v1/admin/tenant-settings/device-security");
        if (res.ok) {
          const cfg = (await res.json()) as { max_offline_minutes: number; employee_session_timeout_minutes: number };
          setDeviceSecurity(cfg);
          setMaxOfflineMinutes(String(cfg.max_offline_minutes));
          setSessionTimeoutMinutes(String(cfg.employee_session_timeout_minutes));
        }
      } finally {
        setDeviceSecurityLoading(false);
      }
    }
    void load();
  }, []);

  async function saveDeviceSecurity() {
    setDeviceSecuritySaving(true);
    setDeviceSecurityMessage(null);
    setDeviceSecurityError(null);
    try {
      const payload: Record<string, number> = {};
      const offline = parseInt(maxOfflineMinutes, 10);
      const timeout = parseInt(sessionTimeoutMinutes, 10);
      if (!isNaN(offline) && offline >= 1) payload.max_offline_minutes = offline;
      if (!isNaN(timeout) && timeout >= 1) payload.employee_session_timeout_minutes = timeout;
      const res = await fetch("/api/ims/v1/admin/tenant-settings/device-security", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await res.text());
      const updated = (await res.json()) as { max_offline_minutes: number; employee_session_timeout_minutes: number };
      setDeviceSecurity(updated);
      setDeviceSecurityMessage("Device security settings saved.");
    } catch (e) {
      setDeviceSecurityError(e instanceof Error ? e.message : "Failed to save device security settings");
    } finally {
      setDeviceSecuritySaving(false);
    }
  }

  return (
    <div className="space-y-8">
      <Breadcrumbs items={[{ label: "Settings", href: "/settings" }, { label: "Devices" }]} />
      <PageHeader kicker="Settings" title="Devices" subtitle="POS device security and employee session timeouts." />

      <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
        <h3 className="font-headline text-lg font-bold text-primary">Device security</h3>
        <p className="mt-1 text-sm text-on-surface-variant">
          Controls how long cashier devices can operate offline and how quickly employee sessions expire after inactivity.
        </p>
        {deviceSecurityLoading ? (
          <p className="mt-4 text-sm text-on-surface-variant">Loading device security settings…</p>
        ) : (
          <div className="mt-5 space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">Max offline minutes</label>
                <TextInput type="number" min="1" max="1440" value={maxOfflineMinutes} onChange={(e) => setMaxOfflineMinutes(e.target.value)} placeholder="60" />
                <p className="mt-1 text-xs text-on-surface-variant">Cashier app blocks usage after this many minutes without a server sync. Default: 60.</p>
              </div>
              <div>
                <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">Employee session timeout (minutes)</label>
                <TextInput type="number" min="1" max="1440" value={sessionTimeoutMinutes} onChange={(e) => setSessionTimeoutMinutes(e.target.value)} placeholder="30" />
                <p className="mt-1 text-xs text-on-surface-variant">Employee must re-enter PIN/password after this many minutes of inactivity. Default: 30.</p>
              </div>
            </div>
            {deviceSecurity && (
              <div className="rounded-lg border border-outline-variant/10 bg-surface-container-low p-3 text-sm text-on-surface-variant">
                Current: offline limit <strong className="text-on-surface">{deviceSecurity.max_offline_minutes} min</strong>
                {" · "}session timeout <strong className="text-on-surface">{deviceSecurity.employee_session_timeout_minutes} min</strong>
              </div>
            )}
            <PrimaryButton type="button" disabled={deviceSecuritySaving} onClick={() => void saveDeviceSecurity()}>
              {deviceSecuritySaving ? "Saving…" : "Save device security"}
            </PrimaryButton>
            {deviceSecurityMessage && <p className="text-sm font-semibold text-primary">{deviceSecurityMessage}</p>}
            {deviceSecurityError && (
              <p className="rounded-lg border border-error/20 bg-error-container/20 px-3 py-2 text-sm text-on-error-container">{deviceSecurityError}</p>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
```

- [ ] **Step 4: Build + commit**

```bash
docker compose up --build -d admin-web 2>&1 | grep -E "✓ Compiled|error TS|Error:|failed" | tail -5
git add 'apps/admin-web/src/app/(main)/settings/currency/page.tsx' \
        'apps/admin-web/src/app/(main)/settings/localisation/page.tsx' \
        'apps/admin-web/src/app/(main)/settings/devices/page.tsx'
git commit -m "feat(admin-web): settings/currency, /localisation, /devices sub-pages"
```

---

## Task 4: Reconciliation + Customer Groups + Business Type sub-pages

**Files:**
- Create: `apps/admin-web/src/app/(main)/settings/reconciliation/page.tsx`
- Create: `apps/admin-web/src/app/(main)/settings/customer-groups/page.tsx`
- Create: `apps/admin-web/src/app/(main)/settings/business-type/page.tsx`

- [ ] **Step 1: Create reconciliation/page.tsx**

```tsx
"use client";

import { useEffect, useState } from "react";
import { Breadcrumbs, PageHeader, PrimaryButton, TextInput } from "@/components/ui/primitives";

export default function SettingsReconciliationPage() {
  const [reconShortage, setReconShortage] = useState<string>("0");
  const [reconOverage, setReconOverage] = useState<string>("0");
  const [reconLoading, setReconLoading] = useState(true);
  const [reconSaving, setReconSaving] = useState(false);
  const [reconMessage, setReconMessage] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/ims/v1/admin/tenant-settings/reconciliation")
      .then((r) => { if (!r.ok) throw new Error("load failed"); return r.json(); })
      .then((data: { auto_resolve_shortage_cents: number; auto_resolve_overage_cents: number }) => {
        setReconShortage(String(data.auto_resolve_shortage_cents));
        setReconOverage(String(data.auto_resolve_overage_cents));
      })
      .catch(() => setReconMessage("Failed to load reconciliation settings"))
      .finally(() => setReconLoading(false));
  }, []);

  async function saveReconciliation() {
    setReconSaving(true);
    setReconMessage(null);
    const shortage = parseInt(reconShortage, 10);
    const overage = parseInt(reconOverage, 10);
    if (Number.isNaN(shortage) || shortage < 0 || Number.isNaN(overage) || overage < 0) {
      setReconMessage("Thresholds must be non-negative integers (in cents).");
      setReconSaving(false);
      return;
    }
    const resp = await fetch("/api/ims/v1/admin/tenant-settings/reconciliation", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ auto_resolve_shortage_cents: shortage, auto_resolve_overage_cents: overage }),
    });
    if (!resp.ok) {
      setReconMessage("Save failed.");
    } else {
      const data = (await resp.json()) as { auto_resolve_shortage_cents: number; auto_resolve_overage_cents: number };
      setReconShortage(String(data.auto_resolve_shortage_cents));
      setReconOverage(String(data.auto_resolve_overage_cents));
      setReconMessage("Saved.");
    }
    setReconSaving(false);
  }

  return (
    <div className="space-y-8">
      <Breadcrumbs items={[{ label: "Settings", href: "/settings" }, { label: "Reconciliation" }]} />
      <PageHeader kicker="Settings" title="Reconciliation" subtitle="Auto-resolve thresholds for shift close variances." />

      <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
        <h3 className="font-headline text-lg font-bold text-primary">Reconciliation auto-resolve</h3>
        <p className="mt-1 text-sm text-on-surface-variant">
          Variances within these thresholds are automatically marked resolved at shift close. Set to 0 to disable auto-resolve. Shops can override these values individually.
        </p>
        {reconLoading ? (
          <p className="mt-4 text-sm text-on-surface-variant">Loading reconciliation settings…</p>
        ) : (
          <div className="mt-5 space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">Shortage limit (cents)</label>
                <TextInput type="number" min="0" value={reconShortage} onChange={(e) => setReconShortage(e.target.value)} placeholder="0" />
                <p className="mt-1 text-xs text-on-surface-variant">Cashier counted less than expected. 0 disables.</p>
              </div>
              <div>
                <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">Overage limit (cents)</label>
                <TextInput type="number" min="0" value={reconOverage} onChange={(e) => setReconOverage(e.target.value)} placeholder="0" />
                <p className="mt-1 text-xs text-on-surface-variant">Cashier counted more than expected. 0 disables.</p>
              </div>
            </div>
            <PrimaryButton type="button" disabled={reconSaving} onClick={() => void saveReconciliation()}>
              {reconSaving ? "Saving…" : "Save reconciliation"}
            </PrimaryButton>
            {reconMessage && <p className="text-sm font-semibold text-primary">{reconMessage}</p>}
          </div>
        )}
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Create customer-groups/page.tsx**

```tsx
"use client";

import { useEffect, useState } from "react";
import { Breadcrumbs, PageHeader, PrimaryButton, TextInput } from "@/components/ui/primitives";

export default function SettingsCustomerGroupsPage() {
  const [customerGroups, setCustomerGroups] = useState<Array<{ id: string; name: string; colour: string | null }>>([]);
  const [newGroupName, setNewGroupName] = useState("");
  const [groupsLoading, setGroupsLoading] = useState(true);
  const [groupsError, setGroupsError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const r = await fetch("/api/ims/v1/admin/customer-groups");
        if (r.ok) setCustomerGroups(await r.json() as Array<{ id: string; name: string; colour: string | null }>);
      } catch {
        setGroupsError("Failed to load groups");
      } finally {
        setGroupsLoading(false);
      }
    })();
  }, []);

  async function createGroup() {
    if (!newGroupName.trim()) return;
    setGroupsError(null);
    try {
      const r = await fetch("/api/ims/v1/admin/customer-groups", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: newGroupName.trim() }),
      });
      if (r.ok) {
        const g = await r.json() as { id: string; name: string; colour: string | null };
        setCustomerGroups((prev) => [...prev, g].sort((a, b) => a.name.localeCompare(b.name)));
        setNewGroupName("");
      } else {
        const b = await r.json().catch(() => ({})) as { detail?: string };
        setGroupsError(b.detail === "group_name_conflict" ? "A group with this name already exists." : (b.detail ?? "Failed to create group"));
      }
    } catch {
      setGroupsError("Network error. Please try again.");
    }
  }

  async function deleteGroup(id: string) {
    try {
      const r = await fetch(`/api/ims/v1/admin/customer-groups/${id}`, { method: "DELETE" });
      if (r.ok) setCustomerGroups((prev) => prev.filter((g) => g.id !== id));
    } catch {
      setGroupsError("Failed to delete group.");
    }
  }

  return (
    <div className="space-y-8">
      <Breadcrumbs items={[{ label: "Settings", href: "/settings" }, { label: "Customer Groups" }]} />
      <PageHeader kicker="Settings" title="Customer Groups" subtitle="Manage customer segment labels for reporting and targeting." />

      <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm space-y-4">
        <h3 className="font-headline text-lg font-bold text-primary">Customer Groups</h3>
        {groupsLoading ? (
          <p className="text-sm text-on-surface-variant">Loading groups…</p>
        ) : (
          <>
            <div className="space-y-2">
              {customerGroups.map((g) => (
                <div key={g.id} className="flex items-center justify-between rounded-lg border border-outline-variant/10 px-4 py-2">
                  <span className="text-sm font-medium text-on-surface">{g.name}</span>
                  <button type="button" onClick={() => void deleteGroup(g.id)} className="text-xs text-error hover:underline">Delete</button>
                </div>
              ))}
              {customerGroups.length === 0 && <p className="text-sm text-on-surface-variant">No groups yet. Create one below.</p>}
            </div>
            {groupsError && <p className="text-sm text-error">{groupsError}</p>}
            <div className="flex gap-2">
              <TextInput className="flex-1" placeholder="Group name, e.g. VIP" value={newGroupName} onChange={(e) => setNewGroupName(e.target.value)} />
              <PrimaryButton type="button" disabled={!newGroupName.trim()} onClick={() => void createGroup()}>Add group</PrimaryButton>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
```

- [ ] **Step 3: Create business-type/page.tsx**

```tsx
"use client";

import { useEffect, useState } from "react";
import { Breadcrumbs, PageHeader, PrimaryButton } from "@/components/ui/primitives";
import { useBusinessType } from "@/lib/business-type-context";

export default function SettingsBusinessTypePage() {
  const { invalidate: invalidateBusinessType } = useBusinessType();
  const [businessType, setBusinessType] = useState<"online" | "retail" | "hybrid">("retail");
  const [btLoading, setBtLoading] = useState(true);
  const [btSaving, setBtSaving] = useState(false);
  const [btMsg, setBtMsg] = useState<string | null>(null);
  const [btErr, setBtErr] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const r = await fetch("/api/ims/v1/admin/tenant-settings/business-type");
        if (r.ok) {
          const d = (await r.json()) as { business_type: string };
          if (d.business_type === "online" || d.business_type === "retail" || d.business_type === "hybrid") {
            setBusinessType(d.business_type);
          }
        }
      } catch {
        // leave default
      } finally {
        setBtLoading(false);
      }
    })();
  }, []);

  async function handleSave() {
    setBtSaving(true);
    setBtMsg(null);
    setBtErr(null);
    try {
      const r = await fetch("/api/ims/v1/admin/tenant-settings/business-type", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ business_type: businessType }),
      });
      if (r.ok) {
        invalidateBusinessType();
        if (businessType === "hybrid") {
          setBtMsg("Hybrid mode active — both POS and ecommerce features are now available in the sidebar.");
        } else if (businessType === "online") {
          setBtMsg("Switched to online-only. Existing POS data is preserved; you can switch back anytime.");
        } else {
          setBtMsg("Switched to retail. Ecommerce sections are hidden; existing data is preserved and can be restored anytime.");
        }
      } else {
        const d = await r.json().catch(() => ({})) as { detail?: string };
        setBtErr(d.detail ?? "Failed to save.");
      }
    } catch {
      setBtErr("Network error. Please try again.");
    } finally {
      setBtSaving(false);
    }
  }

  return (
    <div className="space-y-8">
      <Breadcrumbs items={[{ label: "Settings", href: "/settings" }, { label: "Business Type" }]} />
      <PageHeader kicker="Settings" title="Business Type" subtitle="Switch between online, retail, or hybrid mode to control which features are available." />

      <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
        <h3 className="font-headline text-base font-bold text-on-surface">Business type</h3>
        <p className="mt-1 text-sm text-on-surface-variant">
          Controls which features are available. &ldquo;Online&rdquo; enables e-commerce channels and hosted checkout.
          &ldquo;Retail&rdquo; focuses on POS. &ldquo;Hybrid&rdquo; enables both.
        </p>
        {btLoading ? (
          <p className="mt-4 text-sm text-on-surface-variant">Loading…</p>
        ) : (
          <div className="mt-4 space-y-3">
            <div className="grid grid-cols-3 gap-3">
              {(["online", "retail", "hybrid"] as const).map((bt) => (
                <button
                  key={bt}
                  type="button"
                  onClick={() => setBusinessType(bt)}
                  className={`flex flex-col items-center rounded-xl border px-4 py-3 text-sm font-semibold transition ${
                    businessType === bt
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-outline-variant/30 text-on-surface-variant hover:border-primary/40 hover:text-on-surface"
                  }`}
                >
                  <span className="material-symbols-outlined text-xl mb-1">
                    {bt === "online" ? "language" : bt === "retail" ? "store" : "merge"}
                  </span>
                  {bt.charAt(0).toUpperCase() + bt.slice(1)}
                </button>
              ))}
            </div>
            {btMsg && <p className="text-sm font-semibold text-primary">{btMsg}</p>}
            {btErr && <p className="text-sm text-error">{btErr}</p>}
            <PrimaryButton type="button" onClick={() => void handleSave()} disabled={btSaving}>
              {btSaving ? "Saving…" : "Save business type"}
            </PrimaryButton>
          </div>
        )}
      </section>
    </div>
  );
}
```

- [ ] **Step 4: Build + commit**

```bash
docker compose up --build -d admin-web 2>&1 | grep -E "✓ Compiled|error TS|Error:|failed" | tail -5
git add 'apps/admin-web/src/app/(main)/settings/reconciliation/page.tsx' \
        'apps/admin-web/src/app/(main)/settings/customer-groups/page.tsx' \
        'apps/admin-web/src/app/(main)/settings/business-type/page.tsx'
git commit -m "feat(admin-web): settings/reconciliation, /customer-groups, /business-type sub-pages"
```

---

## Task 5: Update overview email href + full rebuild + push

**Files:**
- Modify: `apps/admin-web/src/app/(main)/overview/page.tsx`

- [ ] **Step 1: Update email item href in overview/page.tsx**

In `apps/admin-web/src/app/(main)/overview/page.tsx`, find the `allSetupItems` array inside `OverviewPage()`. Find the item with `key: "email"`. Change its `href` from `"/settings"` to `"/settings/email"`:

```tsx
// Before:
    href: "/settings",
// After (email item only):
    href: "/settings/email",
```

- [ ] **Step 2: Full rebuild**

```bash
docker compose down && docker compose up --build -d 2>&1 | grep -E "✓ Compiled|error TS|Error:|failed" | tail -5
sleep 12
docker compose ps --format "table {{.Name}}\t{{.Status}}"
```

Expected: all containers Up, admin-web `✓ Compiled successfully`.

- [ ] **Step 3: Smoke test**

1. Navigate to `/settings` — grid of 7 cards visible, Danger zone at bottom
2. Click each card — lands on the correct sub-page with a breadcrumb showing "Settings / <Section>"
3. Click "Settings" in the breadcrumb — returns to the index
4. Go to the dashboard setup checklist — click "Configure email → Start" — lands on `/settings/email` directly
5. On `/settings/business-type`, change the type and save — sidebar updates immediately

- [ ] **Step 4: Commit + push**

```bash
git add 'apps/admin-web/src/app/(main)/overview/page.tsx'
git commit -m "feat(admin-web): update setup checklist email href to /settings/email"
git push origin main
```

---

## Self-review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| 7-card index grid | Task 1 |
| Danger zone on index | Task 1 |
| `/settings/email` sub-page | Task 2 |
| `/settings/currency` sub-page | Task 3 |
| `/settings/localisation` sub-page | Task 3 |
| `/settings/devices` sub-page | Task 3 |
| `/settings/reconciliation` sub-page | Task 4 |
| `/settings/customer-groups` sub-page | Task 4 |
| `/settings/business-type` sub-page | Task 4 |
| Breadcrumbs on every sub-page linking back to `/settings` | Tasks 2–4 |
| Overview checklist email href → `/settings/email` | Task 5 |

**Placeholder scan:** None.

**Type consistency:**
- `CurrencySettings` type defined locally in currency page (not imported from monolith — it's just a local type, fine) ✅
- `useBusinessType()` imported from `@/lib/business-type-context` in business-type page ✅
- All save functions carry error state setters matching the `useState` declarations ✅
- API endpoint paths identical to the originals in settings/page.tsx ✅
