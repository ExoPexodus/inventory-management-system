"use client";

import { useEffect, useState } from "react";
import { PrimaryButton, SecondaryButton, SelectInput, TextInput, Toggle } from "@/components/ui/primitives";

type CurrencySettings = {
  currency_code: string;
  currency_symbol: string;
  currency_exponent: number;
  display_mode: "symbol" | "convert";
  conversion_rate: number | null;
  supported_currencies: Array<{ code: string; symbol: string; name: string; exponent: number }>;
};

export default function SettingsPage() {
  const [emailDigest, setEmailDigest] = useState(true);
  const [lowStockAlerts, setLowStockAlerts] = useState(true);
  const [pushNotify, setPushNotify] = useState(false);

  const [twoFactor, setTwoFactor] = useState(false);
  const [sessionNotify, setSessionNotify] = useState(true);
  const [apiKeyRotation, setApiKeyRotation] = useState(false);

  const [compactTables, setCompactTables] = useState(false);
  const [highContrast, setHighContrast] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);

  const [saved, setSaved] = useState(false);
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

  // Device security state
  const [deviceSecurity, setDeviceSecurity] = useState<{ max_offline_minutes: number; employee_session_timeout_minutes: number } | null>(null);
  const [maxOfflineMinutes, setMaxOfflineMinutes] = useState("60");
  const [sessionTimeoutMinutes, setSessionTimeoutMinutes] = useState("30");
  const [deviceSecurityLoading, setDeviceSecurityLoading] = useState(true);
  const [deviceSecuritySaving, setDeviceSecuritySaving] = useState(false);
  const [deviceSecurityMessage, setDeviceSecurityMessage] = useState<string | null>(null);
  const [deviceSecurityError, setDeviceSecurityError] = useState<string | null>(null);

  // Currency state
  const [currencySettings, setCurrencySettings] = useState<CurrencySettings | null>(null);
  const [currencyLoading, setCurrencyLoading] = useState(true);
  const [currencyCode, setCurrencyCode] = useState("USD");
  const [currencyDisplayMode, setCurrencyDisplayMode] = useState<"symbol" | "convert">("symbol");
  const [conversionRate, setConversionRate] = useState("");
  const [currencySaving, setCurrencySaving] = useState(false);
  const [currencyMessage, setCurrencyMessage] = useState<string | null>(null);
  const [currencyError, setCurrencyError] = useState<string | null>(null);

  useEffect(() => {
    async function loadEmailSettings() {
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
    void loadEmailSettings();
  }, []);

  useEffect(() => {
    async function loadDeviceSecurity() {
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
    void loadDeviceSecurity();
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

  useEffect(() => {
    async function loadCurrency() {
      setCurrencyLoading(true);
      try {
        const res = await fetch("/api/ims/v1/admin/tenant-settings/currency");
        if (res.ok) {
          const cfg = (await res.json()) as CurrencySettings;
          setCurrencySettings(cfg);
          setCurrencyCode(cfg.currency_code);
          setCurrencyDisplayMode(cfg.display_mode);
          setConversionRate(cfg.conversion_rate != null ? String(cfg.conversion_rate) : "");
        }
      } finally {
        setCurrencyLoading(false);
      }
    }
    void loadCurrency();
  }, []);

  async function saveCurrencySettings() {
    setCurrencySaving(true);
    setCurrencyMessage(null);
    setCurrencyError(null);
    try {
      const payload: Record<string, unknown> = {
        currency_code: currencyCode,
        display_mode: currencyDisplayMode,
      };
      if (currencyDisplayMode === "convert" && conversionRate.trim()) {
        payload.conversion_rate = parseFloat(conversionRate);
      }
      const res = await fetch("/api/ims/v1/admin/tenant-settings/currency", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await res.text());
      const updated = (await res.json()) as CurrencySettings;
      setCurrencySettings(updated);
      setCurrencyMessage("Currency settings saved.");
    } catch (e) {
      setCurrencyError(e instanceof Error ? e.message : "Failed to save currency settings");
    } finally {
      setCurrencySaving(false);
    }
  }

  const save = async () => {
    setSaving(true);
    setSaved(false);
    try {
      await new Promise((r) => setTimeout(r, 400));
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } finally {
      setSaving(false);
    }
  };

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
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Platform</p>
        <h2 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">Settings</h2>
        <p className="mt-2 font-light text-on-surface-variant">Tune notifications, security posture, and UI density.</p>
      </div>

      <div className="space-y-6">
        <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <h3 className="font-headline text-lg font-bold text-primary">Staff invite email provider</h3>
          <p className="mt-1 text-sm text-on-surface-variant">
            Configure SMTP or SendGrid. Staff invites and re-enrollment email depend on this.
          </p>

          {emailLoading ? <p className="mt-4 text-sm text-on-surface-variant">Loading email settings...</p> : null}
          {!emailLoading ? (
            <div className="mt-5 space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">Provider</label>
                  <SelectInput
                    value={emailProvider}
                    onChange={(value) => setEmailProvider(value as "smtp" | "sendgrid")}
                    options={[
                      { value: "smtp", label: "SMTP" },
                      { value: "sendgrid", label: "SendGrid" },
                    ]}
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
                  <TextInput
                    value={sendgridApiKey}
                    onChange={(e) => setSendgridApiKey(e.target.value)}
                    placeholder="leave blank to keep current"
                    type="password"
                  />
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
                <TextInput
                  value={testEmail}
                  onChange={(e) => setTestEmail(e.target.value)}
                  placeholder="test recipient"
                  type="email"
                  className="max-w-xs"
                />
                <SecondaryButton type="button" disabled={testingEmail || !testEmail.trim()} onClick={() => void sendTestEmail()}>
                  {testingEmail ? "Sending..." : "Send test email"}
                </SecondaryButton>
              </div>

              {emailMessage ? <p className="text-sm font-semibold text-primary">{emailMessage}</p> : null}
              {emailError ? (
                <p className="rounded-lg border border-error/20 bg-error-container/20 px-3 py-2 text-sm text-on-error-container">{emailError}</p>
              ) : null}
            </div>
          ) : null}
        </section>

        <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <h3 className="font-headline text-lg font-bold text-primary">Currency</h3>
          <p className="mt-1 text-sm text-on-surface-variant">
            Select your store currency. &ldquo;Symbol only&rdquo; displays amounts with the new symbol but keeps the underlying USD value. &ldquo;Convert&rdquo; multiplies all stored cent values by your rate.
          </p>
          {currencyLoading ? (
            <p className="mt-4 text-sm text-on-surface-variant">Loading currency settings…</p>
          ) : (
            <div className="mt-5 space-y-4">
              <div className="grid gap-4 md:grid-cols-3">
                <div>
                  <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">Currency</label>
                  <SelectInput
                    value={currencyCode}
                    onChange={setCurrencyCode}
                    options={(currencySettings?.supported_currencies ?? []).map((c) => ({
                      value: c.code,
                      label: `${c.code} — ${c.name} (${c.symbol})`,
                    }))}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">Display mode</label>
                  <SelectInput
                    value={currencyDisplayMode}
                    onChange={(v) => setCurrencyDisplayMode(v as "symbol" | "convert")}
                    options={[
                      { value: "symbol", label: "Symbol only (cosmetic)" },
                      { value: "convert", label: "Convert amounts" },
                    ]}
                  />
                </div>
                {currencyDisplayMode === "convert" && (
                  <div>
                    <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">
                      Rate (1 USD = ? {currencyCode})
                    </label>
                    <TextInput
                      type="number"
                      min="0"
                      step="0.01"
                      value={conversionRate}
                      onChange={(e) => setConversionRate(e.target.value)}
                      placeholder="e.g. 83.5"
                    />
                  </div>
                )}
              </div>
              {currencySettings && (
                <div className="rounded-lg border border-outline-variant/10 bg-surface-container-low p-3 text-sm text-on-surface-variant">
                  Current: <strong className="text-on-surface">{currencySettings.currency_symbol}</strong> {currencySettings.currency_code}{" "}
                  &bull; mode: <strong className="text-on-surface">{currencySettings.display_mode}</strong>
                  {currencySettings.conversion_rate != null && ` @ ${currencySettings.conversion_rate}×`}
                </div>
              )}
              <div className="flex flex-wrap items-center gap-3">
                <PrimaryButton type="button" disabled={currencySaving} onClick={() => void saveCurrencySettings()}>
                  {currencySaving ? "Saving…" : "Save currency"}
                </PrimaryButton>
              </div>
              {currencyMessage && <p className="text-sm font-semibold text-primary">{currencyMessage}</p>}
              {currencyError && (
                <p className="rounded-lg border border-error/20 bg-error-container/20 px-3 py-2 text-sm text-on-error-container">{currencyError}</p>
              )}
            </div>
          )}
        </section>

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
                  <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">
                    Max offline minutes
                  </label>
                  <TextInput
                    type="number"
                    min="1"
                    max="1440"
                    value={maxOfflineMinutes}
                    onChange={(e) => setMaxOfflineMinutes(e.target.value)}
                    placeholder="60"
                  />
                  <p className="mt-1 text-xs text-on-surface-variant">
                    Cashier app blocks usage after this many minutes without a server sync. Default: 60.
                  </p>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">
                    Employee session timeout (minutes)
                  </label>
                  <TextInput
                    type="number"
                    min="1"
                    max="1440"
                    value={sessionTimeoutMinutes}
                    onChange={(e) => setSessionTimeoutMinutes(e.target.value)}
                    placeholder="30"
                  />
                  <p className="mt-1 text-xs text-on-surface-variant">
                    Employee must re-enter PIN/password after this many minutes of inactivity. Default: 30.
                  </p>
                </div>
              </div>
              {deviceSecurity && (
                <div className="rounded-lg border border-outline-variant/10 bg-surface-container-low p-3 text-sm text-on-surface-variant">
                  Current: offline limit <strong className="text-on-surface">{deviceSecurity.max_offline_minutes} min</strong>
                  {" · "}session timeout <strong className="text-on-surface">{deviceSecurity.employee_session_timeout_minutes} min</strong>
                </div>
              )}
              <div className="flex flex-wrap items-center gap-3">
                <PrimaryButton type="button" disabled={deviceSecuritySaving} onClick={() => void saveDeviceSecurity()}>
                  {deviceSecuritySaving ? "Saving…" : "Save device security"}
                </PrimaryButton>
              </div>
              {deviceSecurityMessage && <p className="text-sm font-semibold text-primary">{deviceSecurityMessage}</p>}
              {deviceSecurityError && (
                <p className="rounded-lg border border-error/20 bg-error-container/20 px-3 py-2 text-sm text-on-error-container">{deviceSecurityError}</p>
              )}
            </div>
          )}
        </section>

        <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <h3 className="font-headline text-lg font-bold text-primary">Notifications</h3>
          <p className="mt-1 text-sm text-on-surface-variant">Choose how we reach you about inventory and orders.</p>
          <ul className="mt-6 divide-y divide-outline-variant/10">
            <li className="flex items-center justify-between gap-4 py-4 first:pt-0">
              <div>
                <p className="font-medium text-on-surface">Email digest</p>
                <p className="text-sm text-on-surface-variant">Daily summary of exceptions and low stock.</p>
              </div>
              <Toggle checked={emailDigest} onChange={setEmailDigest} />
            </li>
            <li className="flex items-center justify-between gap-4 py-4">
              <div>
                <p className="font-medium text-on-surface">Low-stock alerts</p>
                <p className="text-sm text-on-surface-variant">Immediate email when SKUs cross reorder points.</p>
              </div>
              <Toggle checked={lowStockAlerts} onChange={setLowStockAlerts} />
            </li>
            <li className="flex items-center justify-between gap-4 py-4 last:pb-0">
              <div>
                <p className="font-medium text-on-surface">Push (browser)</p>
                <p className="text-sm text-on-surface-variant">Requires permission; best for on-call managers.</p>
              </div>
              <Toggle checked={pushNotify} onChange={setPushNotify} />
            </li>
          </ul>
        </section>

        <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <h3 className="font-headline text-lg font-bold text-primary">Security</h3>
          <p className="mt-1 text-sm text-on-surface-variant">Harden access to the admin console and APIs.</p>
          <ul className="mt-6 divide-y divide-outline-variant/10">
            <li className="flex items-center justify-between gap-4 py-4 first:pt-0">
              <div>
                <p className="font-medium text-on-surface">Two-factor authentication</p>
                <p className="text-sm text-on-surface-variant">Require TOTP for all operator accounts.</p>
              </div>
              <Toggle checked={twoFactor} onChange={setTwoFactor} />
            </li>
            <li className="flex items-center justify-between gap-4 py-4">
              <div>
                <p className="font-medium text-on-surface">New session alerts</p>
                <p className="text-sm text-on-surface-variant">Email when a login occurs from a new device.</p>
              </div>
              <Toggle checked={sessionNotify} onChange={setSessionNotify} />
            </li>
            <li className="flex items-center justify-between gap-4 py-4 last:pb-0">
              <div>
                <p className="font-medium text-on-surface">API key rotation reminders</p>
                <p className="text-sm text-on-surface-variant">Nudge before long-lived keys expire.</p>
              </div>
              <Toggle checked={apiKeyRotation} onChange={setApiKeyRotation} />
            </li>
          </ul>
        </section>

        <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <h3 className="font-headline text-lg font-bold text-primary">Appearance</h3>
          <p className="mt-1 text-sm text-on-surface-variant">Adjust density and visual comfort.</p>
          <ul className="mt-6 divide-y divide-outline-variant/10">
            <li className="flex items-center justify-between gap-4 py-4 first:pt-0">
              <div>
                <p className="font-medium text-on-surface">Compact tables</p>
                <p className="text-sm text-on-surface-variant">Tighter row height for dense data review.</p>
              </div>
              <Toggle checked={compactTables} onChange={setCompactTables} />
            </li>
            <li className="flex items-center justify-between gap-4 py-4">
              <div>
                <p className="font-medium text-on-surface">High contrast</p>
                <p className="text-sm text-on-surface-variant">Stronger borders and focus rings.</p>
              </div>
              <Toggle checked={highContrast} onChange={setHighContrast} />
            </li>
            <li className="flex items-center justify-between gap-4 py-4 last:pb-0">
              <div>
                <p className="font-medium text-on-surface">Reduce motion</p>
                <p className="text-sm text-on-surface-variant">Minimize transitions and parallax.</p>
              </div>
              <Toggle checked={reducedMotion} onChange={setReducedMotion} />
            </li>
          </ul>
        </section>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <PrimaryButton type="button" disabled={saving} onClick={() => void save()}>
          {saving ? "Saving…" : "Save changes"}
        </PrimaryButton>
        {saved ? <span className="text-sm font-semibold text-primary">Settings saved.</span> : null}
      </div>

      <section className="rounded-xl border border-error/20 bg-error-container/20 p-6 shadow-sm">
        <h3 className="font-headline text-lg font-bold text-error">Danger zone</h3>
        <p className="mt-2 text-sm text-on-error-container">
          Reset demo data and cached UI preferences for this tenant. This cannot be undone from the console alone.
        </p>
        <div className="mt-4">
          <SecondaryButton type="button" className="border-error/40 text-error hover:bg-error-container/30">
            Reset tenant preferences
          </SecondaryButton>
        </div>
      </section>
    </div>
  );
}
