"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Badge,
  PageHeader,
  Panel,
  PrimaryButton,
  SecondaryButton,
  Tabs,
  TextInput,
  SelectInput,
} from "@/components/ui/primitives";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type EmailConfig = {
  configured: boolean;
  provider: string | null;
  from_email: string | null;
  from_name: string | null;
};

type WebhookEndpoint = {
  id: string;
  url: string;
  events: string[];
  status: string;
  description: string | null;
  created_at: string;
};

type DeliveryLog = {
  id: string;
  endpoint_id: string;
  event_type: string;
  status: string;
  response_status: number | null;
  attempt_count: number;
  delivered_at: string | null;
  created_at: string;
};

type FxRate = {
  id: string;
  from_currency: string;
  to_currency: string;
  rate: string;
  source: string;
  effective_at: string;
};

type ShippingZone = {
  id: string;
  channel_id: string;
  name: string;
  countries: string[] | null;
  is_catch_all: boolean;
  created_at: string;
};

type ShippingRate = {
  id: string;
  zone_id: string;
  name: string;
  base_price_cents: number;
  currency_code: string;
  free_above_cents: number | null;
  condition_type: string;
  created_at: string;
};

type Channel = {
  id: string;
  name: string;
  currency_code: string;
};

// ---------------------------------------------------------------------------
// Tab 1: Email
// ---------------------------------------------------------------------------

function EmailTab() {
  const [config, setConfig] = useState<EmailConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [provider, setProvider] = useState<"smtp" | "resend">("smtp");

  // SMTP fields
  const [smtpHost, setSmtpHost] = useState("");
  const [smtpPort, setSmtpPort] = useState("587");
  const [smtpUsername, setSmtpUsername] = useState("");
  const [smtpPassword, setSmtpPassword] = useState("");

  // Resend fields
  const [resendApiKey, setResendApiKey] = useState("");

  // Shared
  const [fromEmail, setFromEmail] = useState("");
  const [fromName, setFromName] = useState("");

  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  const [saveErr, setSaveErr] = useState<string | null>(null);

  // Test send
  const [testTo, setTestTo] = useState("");
  const [testing, setTesting] = useState(false);
  const [testMsg, setTestMsg] = useState<string | null>(null);
  const [testErr, setTestErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/ims/v1/admin/email/config");
      if (r.ok) {
        const data = (await r.json()) as EmailConfig;
        setConfig(data);
        if (data.provider === "resend" || data.provider === "smtp") {
          setProvider(data.provider);
        }
        setFromEmail(data.from_email ?? "");
        setFromName(data.from_name ?? "");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setSaveMsg(null);
    setSaveErr(null);
    try {
      let r: Response;
      if (provider === "smtp") {
        r = await fetch("/api/ims/v1/admin/email/configure/smtp", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            provider: "smtp",
            smtp_host: smtpHost,
            smtp_port: parseInt(smtpPort, 10),
            smtp_username: smtpUsername,
            smtp_password: smtpPassword,
            from_email: fromEmail,
            from_name: fromName,
          }),
        });
      } else {
        r = await fetch("/api/ims/v1/admin/email/configure/resend", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            provider: "resend",
            resend_api_key: resendApiKey,
            from_email: fromEmail,
            from_name: fromName,
          }),
        });
      }
      if (!r.ok) {
        const body = await r.json().catch(() => ({})) as { detail?: string };
        setSaveErr(body.detail ?? `Failed (${r.status})`);
      } else {
        setSaveMsg("Email configuration saved.");
        setSmtpPassword("");
        setResendApiKey("");
        void load();
      }
    } catch {
      setSaveErr("Network error. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  async function handleTestSend(e: React.FormEvent) {
    e.preventDefault();
    if (!testTo.trim()) return;
    setTesting(true);
    setTestMsg(null);
    setTestErr(null);
    try {
      const r = await fetch("/api/ims/v1/admin/email/test-send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ to_email: testTo.trim() }),
      });
      const data = (await r.json()) as { sent: boolean; message: string };
      if (data.sent) {
        setTestMsg(data.message || "Test email sent.");
      } else {
        setTestErr(data.message || "Test send failed.");
      }
    } catch {
      setTestErr("Network error. Please try again.");
    } finally {
      setTesting(false);
    }
  }

  if (loading) {
    return <p className="text-sm text-on-surface-variant">Loading email configuration…</p>;
  }

  return (
    <div className="space-y-6">
      {/* Status */}
      <div className="flex items-center gap-3">
        <Badge tone={config?.configured ? "good" : "warn"}>
          {config?.configured ? "Configured" : "Not configured"}
        </Badge>
        {config?.configured && config.provider && (
          <span className="text-xs text-on-surface-variant">Provider: {config.provider}</span>
        )}
      </div>

      {/* Provider segmented control */}
      <div>
        <p className="mb-2 text-xs font-bold uppercase tracking-widest text-on-surface-variant">Provider</p>
        <div className="inline-flex rounded-lg bg-surface-container p-1">
          {(["smtp", "resend"] as const).map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setProvider(p)}
              className={`rounded-md px-4 py-1.5 text-xs font-semibold transition ${
                provider === p
                  ? "bg-surface-container-lowest text-on-surface shadow-sm"
                  : "text-on-surface-variant hover:text-on-surface"
              }`}
            >
              {p === "smtp" ? "SMTP" : "Resend"}
            </button>
          ))}
        </div>
      </div>

      {/* Config form */}
      <form onSubmit={(e) => void handleSave(e)} className="space-y-5">
        <Panel title={provider === "smtp" ? "SMTP Configuration" : "Resend Configuration"}>
          <div className="space-y-4">
            {provider === "smtp" ? (
              <>
                <p className="text-xs text-on-surface-variant">
                  Hostinger: <span className="font-mono">smtp.hostinger.com</span> · port 587 (TLS) or 465 (SSL)
                </p>
                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">
                      SMTP Host
                    </label>
                    <TextInput
                      value={smtpHost}
                      onChange={(e) => setSmtpHost(e.target.value)}
                      placeholder="smtp.hostinger.com"
                      required
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">
                      SMTP Port
                    </label>
                    <TextInput
                      type="number"
                      value={smtpPort}
                      onChange={(e) => setSmtpPort(e.target.value)}
                      placeholder="587"
                      required
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">
                      SMTP Username
                    </label>
                    <TextInput
                      value={smtpUsername}
                      onChange={(e) => setSmtpUsername(e.target.value)}
                      placeholder="username@yourdomain.com"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">
                      SMTP Password
                    </label>
                    <TextInput
                      type="password"
                      value={smtpPassword}
                      onChange={(e) => setSmtpPassword(e.target.value)}
                      placeholder="leave blank to keep current"
                    />
                  </div>
                </div>
              </>
            ) : (
              <div>
                <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">
                  Resend API Key
                </label>
                <TextInput
                  type="password"
                  value={resendApiKey}
                  onChange={(e) => setResendApiKey(e.target.value)}
                  placeholder="re_xxxxxxxxxxxxxxxx"
                />
              </div>
            )}

            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">
                  From Email
                </label>
                <TextInput
                  type="email"
                  value={fromEmail}
                  onChange={(e) => setFromEmail(e.target.value)}
                  placeholder="noreply@yourdomain.com"
                  required
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">
                  From Name
                </label>
                <TextInput
                  value={fromName}
                  onChange={(e) => setFromName(e.target.value)}
                  placeholder="Your Store"
                />
              </div>
            </div>

            {saveErr && (
              <p className="rounded-lg border border-error/20 bg-error-container/20 px-3 py-2 text-sm text-on-error-container">
                {saveErr}
              </p>
            )}
            {saveMsg && <p className="text-sm font-semibold text-primary">{saveMsg}</p>}

            <PrimaryButton type="submit" disabled={saving || !fromEmail.trim()}>
              {saving ? "Saving…" : "Save configuration"}
            </PrimaryButton>
          </div>
        </Panel>
      </form>

      {/* Test send */}
      <Panel title="Send test email" subtitle="Verify your configuration by sending a test message.">
        <form onSubmit={(e) => void handleTestSend(e)} className="space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <div className="flex-1 min-w-48">
              <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">
                Recipient
              </label>
              <TextInput
                type="email"
                value={testTo}
                onChange={(e) => setTestTo(e.target.value)}
                placeholder="you@example.com"
                required
              />
            </div>
            <PrimaryButton type="submit" disabled={testing || !testTo.trim()}>
              {testing ? "Sending…" : "Send test email"}
            </PrimaryButton>
          </div>
          {testMsg && <p className="text-sm font-semibold text-primary">{testMsg}</p>}
          {testErr && (
            <p className="rounded-lg border border-error/20 bg-error-container/20 px-3 py-2 text-sm text-on-error-container">
              {testErr}
            </p>
          )}
        </form>
      </Panel>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab 2: Webhooks
// ---------------------------------------------------------------------------

function WebhooksTab() {
  const [endpoints, setEndpoints] = useState<WebhookEndpoint[]>([]);
  const [deliveries, setDeliveries] = useState<DeliveryLog[]>([]);
  const [supportedEvents, setSupportedEvents] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [deliveriesLoading, setDeliveriesLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [newUrl, setNewUrl] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [newEvents, setNewEvents] = useState<string[]>([]);
  const [creating, setCreating] = useState(false);
  const [createErr, setCreateErr] = useState<string | null>(null);
  const [newSecret, setNewSecret] = useState<string | null>(null);

  const loadEndpoints = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/ims/v1/admin/webhooks/endpoints");
      if (r.ok) setEndpoints((await r.json()) as WebhookEndpoint[]);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDeliveries = useCallback(async () => {
    setDeliveriesLoading(true);
    try {
      const r = await fetch("/api/ims/v1/admin/webhooks/deliveries?limit=20");
      if (r.ok) setDeliveries((await r.json()) as DeliveryLog[]);
    } finally {
      setDeliveriesLoading(false);
    }
  }, []);

  useEffect(() => {
    void (async () => {
      const r = await fetch("/api/ims/v1/admin/webhooks/supported-events");
      if (r.ok) setSupportedEvents((await r.json()) as string[]);
    })();
    void loadEndpoints();
    void loadDeliveries();
  }, [loadEndpoints, loadDeliveries]);

  const toggleEvent = (ev: string) =>
    setNewEvents((prev) => (prev.includes(ev) ? prev.filter((e) => e !== ev) : [...prev, ev]));

  async function createEndpoint(e: React.FormEvent) {
    e.preventDefault();
    if (!newUrl.trim() || newEvents.length === 0) {
      setCreateErr("URL and at least one event are required.");
      return;
    }
    setCreating(true);
    setCreateErr(null);
    const r = await fetch("/api/ims/v1/admin/webhooks/endpoints", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: newUrl.trim(),
        events: newEvents,
        description: newDescription.trim() || undefined,
      }),
    });
    if (r.ok) {
      const data = (await r.json()) as { secret?: string };
      if (data.secret) setNewSecret(data.secret);
      setShowForm(false);
      setNewUrl("");
      setNewDescription("");
      setNewEvents([]);
      void loadEndpoints();
    } else {
      const body = await r.json().catch(() => ({})) as { detail?: string };
      setCreateErr(body.detail ?? `Failed (${r.status})`);
    }
    setCreating(false);
  }

  async function toggleStatus(ep: WebhookEndpoint) {
    const nextStatus = ep.status === "active" ? "disabled" : "active";
    await fetch(`/api/ims/v1/admin/webhooks/endpoints/${ep.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: nextStatus }),
    });
    void loadEndpoints();
  }

  async function rotateSecret(id: string) {
    const r = await fetch(`/api/ims/v1/admin/webhooks/endpoints/${id}/rotate-secret`, {
      method: "POST",
    });
    if (r.ok) {
      const data = (await r.json()) as { secret: string };
      setNewSecret(data.secret);
    }
  }

  async function deleteEndpoint(id: string) {
    if (!confirm("Delete this webhook endpoint?")) return;
    await fetch(`/api/ims/v1/admin/webhooks/endpoints/${id}`, { method: "DELETE" });
    void loadEndpoints();
    void loadDeliveries();
  }

  function deliveryBadgeTone(status: string): "good" | "danger" | "warn" {
    if (status === "delivered") return "good";
    if (status === "failed") return "danger";
    return "warn";
  }

  return (
    <div className="space-y-6">
      {/* One-time secret banner */}
      {newSecret && (
        <div className="rounded-xl border border-tertiary/20 bg-tertiary-fixed/20 p-4">
          <p className="text-sm font-bold text-on-surface">
            Copy your signing secret — it won&apos;t be shown again.
          </p>
          <code className="mt-2 block break-all rounded-lg bg-surface-container-lowest px-4 py-3 font-mono text-sm text-primary">
            {newSecret}
          </code>
          <button
            type="button"
            className="mt-2 text-xs font-semibold text-primary underline"
            onClick={() => setNewSecret(null)}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* New endpoint button + form */}
      <div className="flex justify-end">
        <PrimaryButton
          type="button"
          onClick={() => { setShowForm((p) => !p); setCreateErr(null); }}
        >
          <span className="material-symbols-outlined text-lg">{showForm ? "close" : "add"}</span>
          {showForm ? "Cancel" : "New endpoint"}
        </PrimaryButton>
      </div>

      {showForm && (
        <form
          onSubmit={(e) => void createEndpoint(e)}
          className="rounded-xl border border-outline-variant/10 bg-surface-container-low p-5 space-y-4"
        >
          <div>
            <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">
              Endpoint URL
            </label>
            <TextInput
              value={newUrl}
              onChange={(e) => setNewUrl(e.target.value)}
              placeholder="https://yourapp.com/webhooks"
              required
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">
              Description (optional)
            </label>
            <TextInput
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
              placeholder="e.g. Order notifications to CRM"
            />
          </div>
          <div>
            <p className="mb-2 text-xs font-bold uppercase tracking-widest text-on-surface-variant">
              Events
            </p>
            <div className="flex flex-wrap gap-2">
              {supportedEvents.map((ev) => (
                <button
                  key={ev}
                  type="button"
                  onClick={() => toggleEvent(ev)}
                  className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${
                    newEvents.includes(ev)
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-outline-variant/30 text-on-surface-variant hover:border-primary/40"
                  }`}
                >
                  {ev}
                </button>
              ))}
            </div>
          </div>
          {createErr && <p className="text-sm text-error">{createErr}</p>}
          <PrimaryButton type="submit" disabled={creating}>
            {creating ? "Creating…" : "Create endpoint"}
          </PrimaryButton>
        </form>
      )}

      {/* Endpoints table */}
      <Panel title="Endpoints" subtitle={`${endpoints.length} registered`} noPad>
        {loading ? (
          <p className="px-6 py-8 text-sm text-on-surface-variant">Loading…</p>
        ) : endpoints.length === 0 ? (
          <p className="px-6 py-8 text-center text-sm text-on-surface-variant">No webhook endpoints configured.</p>
        ) : (
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-outline-variant/10">
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">URL</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Events</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Status</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {endpoints.map((ep) => (
                <tr key={ep.id} className="hover:bg-surface-container-low/50">
                  <td className="px-6 py-4">
                    <p className="font-mono text-xs text-on-surface">{ep.url}</p>
                    {ep.description && (
                      <p className="mt-0.5 text-xs text-on-surface-variant">{ep.description}</p>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex flex-wrap gap-1">
                      {ep.events.map((ev) => (
                        <span key={ev} className="rounded-full bg-surface-container px-2 py-0.5 text-[10px] text-on-surface-variant">
                          {ev}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <Badge tone={ep.status === "active" ? "good" : "warn"}>{ep.status}</Badge>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => void toggleStatus(ep)}
                        className="inline-flex items-center gap-1 rounded-lg border border-outline-variant/30 px-3 py-1.5 text-xs font-semibold text-on-surface transition hover:bg-surface-container"
                      >
                        {ep.status === "active" ? "Disable" : "Enable"}
                      </button>
                      <button
                        type="button"
                        onClick={() => void rotateSecret(ep.id)}
                        className="inline-flex items-center gap-1 rounded-lg border border-outline-variant/30 px-3 py-1.5 text-xs font-semibold text-on-surface transition hover:bg-surface-container"
                      >
                        <span className="material-symbols-outlined text-sm">refresh</span>
                        Rotate secret
                      </button>
                      <button
                        type="button"
                        onClick={() => void deleteEndpoint(ep.id)}
                        className="inline-flex items-center gap-1 rounded-lg border border-error/30 bg-error-container/10 px-3 py-1.5 text-xs font-semibold text-error transition hover:bg-error-container/30"
                      >
                        <span className="material-symbols-outlined text-sm">delete</span>
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      {/* Delivery log */}
      <Panel title="Delivery log" subtitle="Last 20 deliveries" noPad>
        {deliveriesLoading ? (
          <p className="px-6 py-8 text-sm text-on-surface-variant">Loading…</p>
        ) : deliveries.length === 0 ? (
          <p className="px-6 py-8 text-center text-sm text-on-surface-variant">No deliveries yet.</p>
        ) : (
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-outline-variant/10">
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Event</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Status</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Response</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Attempts</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Delivered at</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {deliveries.map((d) => (
                <tr key={d.id} className="hover:bg-surface-container-low/50">
                  <td className="px-6 py-4 font-mono text-xs text-on-surface">{d.event_type}</td>
                  <td className="px-6 py-4">
                    <Badge tone={deliveryBadgeTone(d.status)}>{d.status}</Badge>
                  </td>
                  <td className="px-6 py-4 text-xs text-on-surface-variant">
                    {d.response_status ?? "—"}
                  </td>
                  <td className="px-6 py-4 text-xs text-on-surface-variant">{d.attempt_count}</td>
                  <td className="px-6 py-4 text-xs text-on-surface-variant">
                    {d.delivered_at ? new Date(d.delivered_at).toLocaleString() : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab 3: FX Rates
// ---------------------------------------------------------------------------

function FxRatesTab() {
  const [rates, setRates] = useState<FxRate[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncBase, setSyncBase] = useState("INR");
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);
  const [syncErr, setSyncErr] = useState<string | null>(null);
  const [showManual, setShowManual] = useState(false);
  const [manualFrom, setManualFrom] = useState("");
  const [manualTo, setManualTo] = useState("");
  const [manualRate, setManualRate] = useState("");
  const [manualSaving, setManualSaving] = useState(false);
  const [manualErr, setManualErr] = useState<string | null>(null);

  const loadRates = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/ims/v1/admin/fx-rates");
      if (r.ok) {
        const data = (await r.json()) as FxRate[];
        setRates(data.slice().sort((a, b) => a.from_currency.localeCompare(b.from_currency)));
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void loadRates(); }, [loadRates]);

  async function handleSync(e: React.FormEvent) {
    e.preventDefault();
    setSyncing(true);
    setSyncMsg(null);
    setSyncErr(null);
    try {
      const r = await fetch("/api/ims/v1/admin/fx-rates/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ base: syncBase.trim().toUpperCase(), targets: [] }),
      });
      if (r.ok) {
        const data = (await r.json()) as { rates_synced: number; rates: Record<string, string>; base: string };
        setSyncMsg(`Synced ${data.rates_synced} rates as of today`);
        void loadRates();
      } else {
        const body = await r.json().catch(() => ({})) as { detail?: string };
        setSyncErr(body.detail ?? `Sync failed (${r.status})`);
      }
    } catch {
      setSyncErr("Network error. Please try again.");
    } finally {
      setSyncing(false);
    }
  }

  async function handleManualSave(e: React.FormEvent) {
    e.preventDefault();
    if (!manualFrom.trim() || !manualTo.trim() || !manualRate.trim()) {
      setManualErr("All fields are required.");
      return;
    }
    setManualSaving(true);
    setManualErr(null);
    try {
      const r = await fetch("/api/ims/v1/admin/fx-rates", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          from_currency: manualFrom.trim().toUpperCase(),
          to_currency: manualTo.trim().toUpperCase(),
          rate: manualRate.trim(),
        }),
      });
      if (r.ok) {
        setManualFrom("");
        setManualTo("");
        setManualRate("");
        setShowManual(false);
        void loadRates();
      } else {
        const body = await r.json().catch(() => ({})) as { detail?: string };
        setManualErr(body.detail ?? `Failed (${r.status})`);
      }
    } catch {
      setManualErr("Network error. Please try again.");
    } finally {
      setManualSaving(false);
    }
  }

  async function deleteRate(id: string) {
    if (!confirm("Delete this rate?")) return;
    await fetch(`/api/ims/v1/admin/fx-rates/${id}`, { method: "DELETE" });
    void loadRates();
  }

  return (
    <div className="space-y-6">
      {/* Sync section */}
      <Panel title="Sync from Frankfurter" subtitle="Fetch live rates for all currencies.">
        <form onSubmit={(e) => void handleSync(e)} className="space-y-4">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">
                Base currency
              </label>
              <TextInput
                value={syncBase}
                onChange={(e) => setSyncBase(e.target.value)}
                placeholder="INR"
                className="w-28"
              />
            </div>
            <PrimaryButton type="submit" disabled={syncing || !syncBase.trim()}>
              {syncing ? "Syncing…" : "Sync all rates"}
            </PrimaryButton>
          </div>
          {syncMsg && <p className="text-sm font-semibold text-primary">{syncMsg}</p>}
          {syncErr && (
            <p className="rounded-lg border border-error/20 bg-error-container/20 px-3 py-2 text-sm text-on-error-container">
              {syncErr}
            </p>
          )}
        </form>
      </Panel>

      {/* Manual rate section */}
      <div>
        <button
          type="button"
          onClick={() => { setShowManual((p) => !p); setManualErr(null); }}
          className="inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline"
        >
          <span className="material-symbols-outlined text-base">
            {showManual ? "expand_less" : "expand_more"}
          </span>
          {showManual ? "Hide manual rate" : "Add manual rate"}
        </button>
        {showManual && (
          <form
            onSubmit={(e) => void handleManualSave(e)}
            className="mt-3 rounded-xl border border-outline-variant/10 bg-surface-container-low p-5 space-y-4"
          >
            <div className="grid gap-4 md:grid-cols-3">
              <div>
                <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">
                  From
                </label>
                <TextInput
                  value={manualFrom}
                  onChange={(e) => setManualFrom(e.target.value)}
                  placeholder="USD"
                  required
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">
                  To
                </label>
                <TextInput
                  value={manualTo}
                  onChange={(e) => setManualTo(e.target.value)}
                  placeholder="INR"
                  required
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">
                  Rate
                </label>
                <TextInput
                  value={manualRate}
                  onChange={(e) => setManualRate(e.target.value)}
                  placeholder="83.25"
                  required
                />
              </div>
            </div>
            {manualErr && <p className="text-sm text-error">{manualErr}</p>}
            <div className="flex gap-2">
              <PrimaryButton type="submit" disabled={manualSaving}>
                {manualSaving ? "Saving…" : "Save rate"}
              </PrimaryButton>
              <SecondaryButton type="button" onClick={() => setShowManual(false)}>
                Cancel
              </SecondaryButton>
            </div>
          </form>
        )}
      </div>

      {/* Rates table */}
      <Panel title="Stored rates" subtitle={`${rates.length} rates`} noPad>
        {loading ? (
          <p className="px-6 py-8 text-sm text-on-surface-variant">Loading…</p>
        ) : rates.length === 0 ? (
          <p className="px-6 py-8 text-center text-sm text-on-surface-variant">No rates stored. Sync or add manually.</p>
        ) : (
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-outline-variant/10">
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">From</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">To</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Rate</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Source</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Last updated</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Delete</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {rates.map((rate) => (
                <tr key={rate.id} className="hover:bg-surface-container-low/50">
                  <td className="px-6 py-4 font-mono text-xs font-bold text-on-surface">{rate.from_currency}</td>
                  <td className="px-6 py-4 font-mono text-xs font-bold text-on-surface">{rate.to_currency}</td>
                  <td className="px-6 py-4 font-mono text-xs text-on-surface">{rate.rate}</td>
                  <td className="px-6 py-4">
                    <Badge tone={rate.source === "frankfurter" ? "good" : "default"}>
                      {rate.source === "frankfurter" ? "auto" : "manual"}
                    </Badge>
                  </td>
                  <td className="px-6 py-4 text-xs text-on-surface-variant">
                    {new Date(rate.effective_at).toLocaleDateString()}
                  </td>
                  <td className="px-6 py-4">
                    <button
                      type="button"
                      onClick={() => void deleteRate(rate.id)}
                      className="inline-flex items-center gap-1 rounded-lg border border-error/30 bg-error-container/10 px-3 py-1.5 text-xs font-semibold text-error transition hover:bg-error-container/30"
                    >
                      <span className="material-symbols-outlined text-sm">delete</span>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab 4: Shipping
// ---------------------------------------------------------------------------

function ShippingTab() {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [zones, setZones] = useState<ShippingZone[]>([]);
  const [zonesLoading, setZonesLoading] = useState(true);
  const [ratesCache, setRatesCache] = useState<Record<string, ShippingRate[]>>({});
  const [ratesLoading, setRatesLoading] = useState<Record<string, boolean>>({});
  const [expandedZoneId, setExpandedZoneId] = useState<string | null>(null);

  // New zone form
  const [showNewZone, setShowNewZone] = useState(false);
  const [newZoneChannelId, setNewZoneChannelId] = useState("");
  const [newZoneName, setNewZoneName] = useState("");
  const [newZoneCatchAll, setNewZoneCatchAll] = useState(false);
  const [creatingZone, setCreatingZone] = useState(false);
  const [zoneErr, setZoneErr] = useState<string | null>(null);

  // Per-zone add-rate form state
  const [addRateZoneId, setAddRateZoneId] = useState<string | null>(null);
  const [rateName, setRateName] = useState("");
  const [ratePrice, setRatePrice] = useState("");
  const [rateCurrency, setRateCurrency] = useState("INR");
  const [rateFreeAbove, setRateFreeAbove] = useState("");
  const [addingRate, setAddingRate] = useState(false);
  const [rateErr, setRateErr] = useState<string | null>(null);

  const loadZones = useCallback(async () => {
    setZonesLoading(true);
    try {
      const r = await fetch("/api/ims/v1/admin/shipping/zones");
      if (r.ok) setZones((await r.json()) as ShippingZone[]);
    } finally {
      setZonesLoading(false);
    }
  }, []);

  const loadZoneRates = useCallback(async (zoneId: string) => {
    setRatesLoading((prev) => ({ ...prev, [zoneId]: true }));
    try {
      const r = await fetch(`/api/ims/v1/admin/shipping/zones/${zoneId}/rates`);
      if (r.ok) {
        const data = (await r.json()) as ShippingRate[];
        setRatesCache((prev) => ({ ...prev, [zoneId]: data }));
      }
    } finally {
      setRatesLoading((prev) => ({ ...prev, [zoneId]: false }));
    }
  }, []);

  useEffect(() => {
    void (async () => {
      const r = await fetch("/api/ims/v1/admin/channels");
      if (r.ok) {
        const data = (await r.json()) as Channel[];
        setChannels(data);
        if (data.length > 0 && data[0]) setNewZoneChannelId(data[0].id);
      }
    })();
    void loadZones();
  }, [loadZones]);

  function toggleZoneExpand(zoneId: string) {
    if (expandedZoneId === zoneId) {
      setExpandedZoneId(null);
    } else {
      setExpandedZoneId(zoneId);
      if (!ratesCache[zoneId]) {
        void loadZoneRates(zoneId);
      }
    }
  }

  async function createZone(e: React.FormEvent) {
    e.preventDefault();
    if (!newZoneChannelId || !newZoneName.trim()) {
      setZoneErr("Channel and name are required.");
      return;
    }
    setCreatingZone(true);
    setZoneErr(null);
    const r = await fetch("/api/ims/v1/admin/shipping/zones", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        channel_id: newZoneChannelId,
        name: newZoneName.trim(),
        is_catch_all: newZoneCatchAll,
        countries: [],
      }),
    });
    if (r.ok) {
      setShowNewZone(false);
      setNewZoneName("");
      setNewZoneCatchAll(false);
      void loadZones();
    } else {
      const body = await r.json().catch(() => ({})) as { detail?: string };
      setZoneErr(body.detail ?? `Failed (${r.status})`);
    }
    setCreatingZone(false);
  }

  async function deleteZone(zoneId: string) {
    if (!confirm("Delete this shipping zone and all its rates?")) return;
    await fetch(`/api/ims/v1/admin/shipping/zones/${zoneId}`, { method: "DELETE" });
    void loadZones();
    if (expandedZoneId === zoneId) setExpandedZoneId(null);
  }

  function startAddRate(zoneId: string) {
    setAddRateZoneId(zoneId);
    setRateName("");
    setRatePrice("");
    setRateCurrency("INR");
    setRateFreeAbove("");
    setRateErr(null);
  }

  async function submitAddRate(e: React.FormEvent, zoneId: string) {
    e.preventDefault();
    const priceCents = parseInt(ratePrice, 10);
    if (!rateName.trim() || isNaN(priceCents)) {
      setRateErr("Name and a valid price (in cents) are required.");
      return;
    }
    const freeAboveCents = rateFreeAbove.trim() ? parseInt(rateFreeAbove, 10) : null;
    setAddingRate(true);
    setRateErr(null);
    const r = await fetch(`/api/ims/v1/admin/shipping/zones/${zoneId}/rates`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: rateName.trim(),
        base_price_cents: priceCents,
        currency_code: rateCurrency.trim().toUpperCase() || "INR",
        free_above_cents: freeAboveCents,
        condition_type: "none",
      }),
    });
    if (r.ok) {
      setAddRateZoneId(null);
      void loadZoneRates(zoneId);
    } else {
      const body = await r.json().catch(() => ({})) as { detail?: string };
      setRateErr(body.detail ?? `Failed (${r.status})`);
    }
    setAddingRate(false);
  }

  async function deleteRate(zoneId: string, rateId: string) {
    await fetch(`/api/ims/v1/admin/shipping/zones/${zoneId}/rates/${rateId}`, {
      method: "DELETE",
    });
    void loadZoneRates(zoneId);
  }

  const channelName = (channelId: string) =>
    channels.find((c) => c.id === channelId)?.name ?? channelId;

  return (
    <div className="space-y-6">
      {/* New zone button */}
      <div className="flex justify-end">
        <PrimaryButton
          type="button"
          onClick={() => { setShowNewZone((p) => !p); setZoneErr(null); }}
        >
          <span className="material-symbols-outlined text-lg">{showNewZone ? "close" : "add"}</span>
          {showNewZone ? "Cancel" : "New zone"}
        </PrimaryButton>
      </div>

      {/* New zone form */}
      {showNewZone && (
        <form
          onSubmit={(e) => void createZone(e)}
          className="rounded-xl border border-outline-variant/10 bg-surface-container-low p-5 space-y-4"
        >
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">
                Channel
              </label>
              <SelectInput
                value={newZoneChannelId}
                onChange={setNewZoneChannelId}
                options={channels.map((c) => ({ value: c.id, label: c.name }))}
                placeholder="Select channel"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">
                Zone name
              </label>
              <TextInput
                value={newZoneName}
                onChange={(e) => setNewZoneName(e.target.value)}
                placeholder="Domestic"
                required
              />
            </div>
          </div>
          <label className="flex cursor-pointer items-start gap-3">
            <input
              type="checkbox"
              checked={newZoneCatchAll}
              onChange={(e) => setNewZoneCatchAll(e.target.checked)}
              className="mt-0.5 h-4 w-4 rounded border-outline-variant accent-primary"
            />
            <div>
              <p className="text-sm font-medium text-on-surface">Catch-all zone</p>
              <p className="text-xs text-on-surface-variant">
                Apply to all countries not covered by other zones
              </p>
            </div>
          </label>
          {zoneErr && <p className="text-sm text-error">{zoneErr}</p>}
          <PrimaryButton type="submit" disabled={creatingZone}>
            {creatingZone ? "Creating…" : "Create zone"}
          </PrimaryButton>
        </form>
      )}

      {/* Zones list */}
      <Panel title="Shipping zones" subtitle={`${zones.length} zones`} noPad>
        {zonesLoading ? (
          <p className="px-6 py-8 text-sm text-on-surface-variant">Loading…</p>
        ) : zones.length === 0 ? (
          <p className="px-6 py-8 text-center text-sm text-on-surface-variant">No shipping zones configured.</p>
        ) : (
          <div className="divide-y divide-outline-variant/10">
            {zones.map((zone) => {
              const isExpanded = expandedZoneId === zone.id;
              const zoneRates = ratesCache[zone.id] ?? [];
              const isRatesLoading = ratesLoading[zone.id] ?? false;
              const isAddingToZone = addRateZoneId === zone.id;

              return (
                <div key={zone.id}>
                  {/* Zone row */}
                  <div className="flex items-center justify-between gap-4 px-6 py-4 hover:bg-surface-container-low/40">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-on-surface">{zone.name}</span>
                        {zone.is_catch_all && (
                          <Badge tone="default">catch-all</Badge>
                        )}
                      </div>
                      <p className="mt-0.5 text-xs text-on-surface-variant">
                        Channel: {channelName(zone.channel_id)}
                        {zone.countries && zone.countries.length > 0 && (
                          <> · {zone.countries.join(", ")}</>
                        )}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => void deleteZone(zone.id)}
                        className="inline-flex items-center gap-1 rounded-lg border border-error/30 bg-error-container/10 px-3 py-1.5 text-xs font-semibold text-error transition hover:bg-error-container/30"
                      >
                        <span className="material-symbols-outlined text-sm">delete</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => toggleZoneExpand(zone.id)}
                        className="inline-flex items-center gap-1 rounded-lg border border-outline-variant/30 px-3 py-1.5 text-xs font-semibold text-on-surface transition hover:bg-surface-container"
                      >
                        <span className="material-symbols-outlined text-sm">
                          {isExpanded ? "expand_less" : "expand_more"}
                        </span>
                        Rates
                      </button>
                    </div>
                  </div>

                  {/* Expanded rates */}
                  {isExpanded && (
                    <div className="border-t border-outline-variant/10 bg-surface-container-low/30 px-6 pb-5 pt-4">
                      {isRatesLoading ? (
                        <p className="text-sm text-on-surface-variant">Loading rates…</p>
                      ) : (
                        <>
                          {zoneRates.length > 0 && (
                            <table className="mb-4 min-w-full text-left text-sm">
                              <thead>
                                <tr className="border-b border-outline-variant/10">
                                  <th className="pb-2 pr-6 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Name</th>
                                  <th className="pb-2 pr-6 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Price (cents)</th>
                                  <th className="pb-2 pr-6 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Currency</th>
                                  <th className="pb-2 pr-6 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Free above (cents)</th>
                                  <th className="pb-2 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Actions</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-outline-variant/10">
                                {zoneRates.map((rate) => (
                                  <tr key={rate.id}>
                                    <td className="py-3 pr-6 text-on-surface">{rate.name}</td>
                                    <td className="py-3 pr-6 font-mono text-xs text-on-surface-variant">{rate.base_price_cents}</td>
                                    <td className="py-3 pr-6 font-mono text-xs text-on-surface-variant">{rate.currency_code}</td>
                                    <td className="py-3 pr-6 font-mono text-xs text-on-surface-variant">
                                      {rate.free_above_cents ?? "—"}
                                    </td>
                                    <td className="py-3">
                                      <button
                                        type="button"
                                        onClick={() => void deleteRate(zone.id, rate.id)}
                                        className="inline-flex items-center gap-1 rounded-lg border border-error/30 bg-error-container/10 px-3 py-1.5 text-xs font-semibold text-error transition hover:bg-error-container/30"
                                      >
                                        <span className="material-symbols-outlined text-sm">delete</span>
                                        Delete
                                      </button>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                          {zoneRates.length === 0 && !isAddingToZone && (
                            <p className="mb-3 text-sm text-on-surface-variant">No rates for this zone.</p>
                          )}

                          {/* Add rate form */}
                          {isAddingToZone ? (
                            <form
                              onSubmit={(e) => void submitAddRate(e, zone.id)}
                              className="mt-2 rounded-xl border border-outline-variant/10 bg-surface-container p-4 space-y-3"
                            >
                              <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-4">
                                <div>
                                  <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">
                                    Rate name
                                  </label>
                                  <TextInput
                                    value={rateName}
                                    onChange={(e) => setRateName(e.target.value)}
                                    placeholder="Standard shipping"
                                    required
                                  />
                                </div>
                                <div>
                                  <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">
                                    Price (cents)
                                  </label>
                                  <TextInput
                                    value={ratePrice}
                                    onChange={(e) => setRatePrice(e.target.value)}
                                    placeholder="500 = ₹5.00"
                                    required
                                  />
                                </div>
                                <div>
                                  <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">
                                    Currency
                                  </label>
                                  <TextInput
                                    value={rateCurrency}
                                    onChange={(e) => setRateCurrency(e.target.value)}
                                    placeholder="INR"
                                    required
                                  />
                                </div>
                                <div>
                                  <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">
                                    Free above (cents)
                                  </label>
                                  <TextInput
                                    value={rateFreeAbove}
                                    onChange={(e) => setRateFreeAbove(e.target.value)}
                                    placeholder="5000 = free above ₹50"
                                  />
                                </div>
                              </div>
                              {rateErr && <p className="text-sm text-error">{rateErr}</p>}
                              <div className="flex gap-2">
                                <PrimaryButton type="submit" disabled={addingRate}>
                                  {addingRate ? "Adding…" : "Add rate"}
                                </PrimaryButton>
                                <SecondaryButton type="button" onClick={() => setAddRateZoneId(null)}>
                                  Cancel
                                </SecondaryButton>
                              </div>
                            </form>
                          ) : (
                            <button
                              type="button"
                              onClick={() => startAddRate(zone.id)}
                              className="inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline"
                            >
                              <span className="material-symbols-outlined text-base">add</span>
                              Add rate
                            </button>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Panel>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

const TABS = [
  { id: "email", label: "Email" },
  { id: "webhooks", label: "Webhooks" },
  { id: "fx-rates", label: "FX Rates" },
  { id: "shipping", label: "Shipping" },
];

export default function EcommercePage() {
  const [tab, setTab] = useState("email");

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="Commerce"
        title="E-commerce Settings"
        subtitle="Configure email, webhooks, currencies, and shipping."
      />
      <Tabs tabs={TABS} active={tab} onChange={setTab} />
      {tab === "email" && <EmailTab />}
      {tab === "webhooks" && <WebhooksTab />}
      {tab === "fx-rates" && <FxRatesTab />}
      {tab === "shipping" && <ShippingTab />}
    </div>
  );
}
