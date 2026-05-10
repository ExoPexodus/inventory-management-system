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
