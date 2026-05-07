"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Badge,
  PageHeader,
  Panel,
  PrimaryButton,
  SecondaryButton,
  Tabs,
  TextInput,
} from "@/components/ui/primitives";
import { SelectInput } from "@/components/ui/SelectInput";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Webhook = {
  id: string;
  type: string;
  status: string;
  config_url: string | null;
  config_events: string[];
  last_sync_at: string | null;
  created_at: string;
};

type ApiToken = {
  id: string;
  name: string;
  token_prefix: string;
  scopes: string[];
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
  created_at: string;
};

type ImportResult = {
  inserted: number;
  updated: number;
  errors: string[];
};

type ChannelBasic = { id: string; name: string; type: string };
type ShopifyConnectOut = { shop_name: string; currency: string | null; location_id: string; location_name: string };
type WooCommerceConnectOut = { store_name: string; store_url: string; currency: string | null };

const WEBHOOK_EVENTS = [
  "transaction.completed",
  "transaction.refunded",
  "stock.low",
  "stock.movement",
  "shift.closed",
  "product.created",
  "product.updated",
];

// ---------------------------------------------------------------------------
// Webhook tab
// ---------------------------------------------------------------------------

function WebhookTab() {
  const [webhooks, setWebhooks] = useState<Webhook[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [url, setUrl] = useState("");
  const [secret, setSecret] = useState("");
  const [events, setEvents] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/ims/v1/admin/integrations/webhooks");
      if (r.ok) setWebhooks(((await r.json()) as Webhook[]) ?? []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim() || events.length === 0) { setErr("URL and at least one event are required"); return; }
    setSaving(true);
    setErr(null);
    const r = await fetch("/api/ims/v1/admin/integrations/webhooks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: url.trim(), events, secret: secret.trim() || null }),
    });
    if (r.ok) {
      setShowForm(false);
      setUrl(""); setSecret(""); setEvents([]);
      void load();
    } else {
      const body = await r.json().catch(() => ({})) as { detail?: string };
      setErr(body.detail ?? `Failed (${r.status})`);
    }
    setSaving(false);
  }

  async function del(id: string) {
    if (!confirm("Delete this webhook?")) return;
    await fetch(`/api/ims/v1/admin/integrations/webhooks/${id}`, { method: "DELETE" });
    void load();
  }

  const toggleEvent = (ev: string) =>
    setEvents((prev) => (prev.includes(ev) ? prev.filter((e) => e !== ev) : [...prev, ev]));

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <PrimaryButton type="button" onClick={() => { setShowForm((p) => !p); setErr(null); }}>
          <span className="material-symbols-outlined text-lg">{showForm ? "close" : "add"}</span>
          {showForm ? "Cancel" : "New webhook"}
        </PrimaryButton>
      </div>

      {showForm && (
        <form onSubmit={(e) => void create(e)} className="rounded-xl border border-outline-variant/10 bg-surface-container-low p-5 space-y-4">
          <div>
            <label className="block text-sm font-medium text-on-surface">
              Endpoint URL
              <TextInput className="mt-1" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://yourapp.com/webhook" required />
            </label>
          </div>
          <div>
            <label className="block text-sm font-medium text-on-surface">
              Signing secret (optional)
              <TextInput type="password" className="mt-1" value={secret} onChange={(e) => setSecret(e.target.value)} placeholder="Used to verify HMAC signature" />
            </label>
          </div>
          <div>
            <p className="text-sm font-medium text-on-surface">Events to send</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {WEBHOOK_EVENTS.map((ev) => (
                <button
                  key={ev}
                  type="button"
                  onClick={() => toggleEvent(ev)}
                  className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${
                    events.includes(ev)
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-outline-variant/30 text-on-surface-variant hover:border-primary/40"
                  }`}
                >
                  {ev}
                </button>
              ))}
            </div>
          </div>
          {err && <p className="text-sm text-error">{err}</p>}
          <div className="flex gap-2">
            <PrimaryButton type="submit" disabled={saving}>{saving ? "Creating…" : "Create webhook"}</PrimaryButton>
          </div>
        </form>
      )}

      <Panel title="Active webhooks" subtitle={`${webhooks.length} endpoints`} noPad>
        {loading ? (
          <p className="px-6 py-8 text-sm text-on-surface-variant">Loading…</p>
        ) : webhooks.length === 0 ? (
          <p className="px-6 py-8 text-center text-sm text-on-surface-variant">No webhooks configured.</p>
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
              {webhooks.map((w) => (
                <tr key={w.id} className="hover:bg-surface-container-low/50">
                  <td className="px-6 py-4 font-mono text-xs text-on-surface">{w.config_url ?? "—"}</td>
                  <td className="px-6 py-4">
                    <div className="flex flex-wrap gap-1">
                      {(w.config_events ?? []).map((ev) => (
                        <span key={ev} className="rounded-full bg-surface-container px-2 py-0.5 text-[10px] text-on-surface-variant">{ev}</span>
                      ))}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <Badge tone={w.status === "active" ? "good" : "warn"}>{w.status}</Badge>
                  </td>
                  <td className="px-6 py-4">
                    <button
                      type="button"
                      onClick={() => void del(w.id)}
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
// Shopify tab
// ---------------------------------------------------------------------------

function ShopifyTab() {
  const [channels, setChannels] = useState<ChannelBasic[]>([]);
  const [channelId, setChannelId] = useState("");
  const [domain, setDomain] = useState("");
  const [token, setToken] = useState("");
  const [secret, setSecret] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [connectResult, setConnectResult] = useState<ShopifyConnectOut | null>(null);
  const [connectErr, setConnectErr] = useState<string | null>(null);
  const [syncResult, setSyncResult] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const loadChannels = useCallback(async () => {
    const r = await fetch("/api/ims/v1/admin/channels");
    if (r.ok) setChannels((await r.json()) as ChannelBasic[]);
  }, []);

  useEffect(() => { void loadChannels(); }, [loadChannels]);

  const channelOptions = channels.map((c) => ({ value: c.id, label: `${c.name} (${c.type})` }));

  async function handleConnect(e: React.FormEvent) {
    e.preventDefault();
    if (!channelId) { setConnectErr("Select a channel first"); return; }
    setConnecting(true);
    setConnectErr(null);
    setConnectResult(null);
    try {
      const r = await fetch(`/api/ims/v1/admin/channels/${channelId}/shopify/connect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          shopify_shop_domain: domain.trim(),
          shopify_access_token: token.trim(),
          shopify_api_secret: secret.trim(),
        }),
      });
      if (r.ok) {
        setConnectResult((await r.json()) as ShopifyConnectOut);
        setToken(""); setSecret("");
      } else {
        const d = await r.json().catch(() => ({})) as { detail?: string };
        setConnectErr(d.detail ?? `Failed (${r.status})`);
      }
    } catch {
      setConnectErr("Network error. Please try again.");
    } finally {
      setConnecting(false);
    }
  }

  async function runAction(action: "sync-catalog" | "sync-inventory" | "import-catalog") {
    if (!channelId) return;
    setActionLoading(action);
    setSyncResult(null);
    try {
      const r = await fetch(`/api/ims/v1/admin/channels/${channelId}/shopify/${action}`, { method: "POST" });
      const d = await r.json() as Record<string, unknown>;
      setSyncResult(JSON.stringify(d, null, 2));
    } catch {
      setSyncResult("Network error. Could not complete action.");
    } finally {
      setActionLoading(null);
    }
  }

  return (
    <div className="space-y-6">
      <Panel title="Connect Shopify store" subtitle="Link a Shopify store to an IMS channel.">
        <form onSubmit={(e) => void handleConnect(e)} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-on-surface mb-1">Channel</label>
            <SelectInput options={channelOptions} value={channelId} onChange={setChannelId} placeholder="Select channel" />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-on-surface">
                Shop domain
                <TextInput className="mt-1" value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="mystore.myshopify.com" required />
              </label>
            </div>
            <div>
              <label className="block text-sm font-medium text-on-surface">
                Access token
                <TextInput type="password" className="mt-1" value={token} onChange={(e) => setToken(e.target.value)} placeholder="shpat_…" required />
              </label>
            </div>
            <div>
              <label className="block text-sm font-medium text-on-surface">
                API secret (webhook signing)
                <TextInput type="password" className="mt-1" value={secret} onChange={(e) => setSecret(e.target.value)} placeholder="shpss_…" required />
              </label>
            </div>
          </div>
          {connectErr && <p className="text-sm text-error">{connectErr}</p>}
          {connectResult && (
            <div className="rounded-xl border border-tertiary/20 bg-tertiary-fixed/20 p-4 text-sm">
              <p className="font-semibold text-on-surface">Connected: {connectResult.shop_name}</p>
              <p className="text-on-surface-variant">Location: {connectResult.location_name} · Currency: {connectResult.currency ?? "—"}</p>
            </div>
          )}
          <PrimaryButton type="submit" disabled={connecting || !channelId}>
            {connecting ? "Connecting…" : "Connect store"}
          </PrimaryButton>
        </form>
      </Panel>

      {channelId && (
        <Panel title="Sync actions" subtitle="Run sync operations against the selected channel.">
          <div className="flex flex-wrap gap-3">
            {(["sync-catalog", "sync-inventory", "import-catalog"] as const).map((action) => (
              <PrimaryButton
                key={action}
                type="button"
                disabled={actionLoading !== null}
                onClick={() => void runAction(action)}
              >
                <span className="material-symbols-outlined text-lg">sync</span>
                {actionLoading === action ? "Running…" : action.replace(/-/g, " ")}
              </PrimaryButton>
            ))}
          </div>
          {syncResult && (
            <pre className="mt-4 overflow-x-auto rounded-lg bg-surface-container p-3 font-mono text-xs text-on-surface-variant">
              {syncResult}
            </pre>
          )}
        </Panel>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// WooCommerce tab
// ---------------------------------------------------------------------------

function WooCommerceTab() {
  const [channels, setChannels] = useState<ChannelBasic[]>([]);
  const [channelId, setChannelId] = useState("");
  const [storeUrl, setStoreUrl] = useState("");
  const [consumerKey, setConsumerKey] = useState("");
  const [consumerSecret, setConsumerSecret] = useState("");
  const [webhookSecret, setWebhookSecret] = useState("");
  const [connecting, setConnecting] = useState(false);
  const [connectResult, setConnectResult] = useState<WooCommerceConnectOut | null>(null);
  const [connectErr, setConnectErr] = useState<string | null>(null);
  const [syncResult, setSyncResult] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const loadChannels = useCallback(async () => {
    const r = await fetch("/api/ims/v1/admin/channels");
    if (r.ok) setChannels((await r.json()) as ChannelBasic[]);
  }, []);

  useEffect(() => { void loadChannels(); }, [loadChannels]);

  const channelOptions = channels.map((c) => ({ value: c.id, label: `${c.name} (${c.type})` }));

  async function handleConnect(e: React.FormEvent) {
    e.preventDefault();
    if (!channelId) { setConnectErr("Select a channel first"); return; }
    setConnecting(true);
    setConnectErr(null);
    setConnectResult(null);
    try {
      const r = await fetch(`/api/ims/v1/admin/channels/${channelId}/woocommerce/connect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          woocommerce_store_url: storeUrl.trim(),
          woocommerce_consumer_key: consumerKey.trim(),
          woocommerce_consumer_secret: consumerSecret.trim(),
          woocommerce_webhook_secret: webhookSecret.trim(),
        }),
      });
      if (r.ok) {
        setConnectResult((await r.json()) as WooCommerceConnectOut);
        setConsumerSecret(""); setWebhookSecret("");
      } else {
        const d = await r.json().catch(() => ({})) as { detail?: string };
        setConnectErr(d.detail ?? `Failed (${r.status})`);
      }
    } catch {
      setConnectErr("Network error. Please try again.");
    } finally {
      setConnecting(false);
    }
  }

  async function runAction(action: "sync-catalog" | "import-catalog") {
    if (!channelId) return;
    setActionLoading(action);
    setSyncResult(null);
    try {
      const r = await fetch(`/api/ims/v1/admin/channels/${channelId}/woocommerce/${action}`, { method: "POST" });
      const d = await r.json() as Record<string, unknown>;
      setSyncResult(JSON.stringify(d, null, 2));
    } catch {
      setSyncResult("Network error. Could not complete action.");
    } finally {
      setActionLoading(null);
    }
  }

  return (
    <div className="space-y-6">
      <Panel title="Connect WooCommerce store" subtitle="Link a WooCommerce store to an IMS channel.">
        <form onSubmit={(e) => void handleConnect(e)} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-on-surface mb-1">Channel</label>
            <SelectInput options={channelOptions} value={channelId} onChange={setChannelId} placeholder="Select channel" />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className="block text-sm font-medium text-on-surface">
                Store URL
                <TextInput className="mt-1" value={storeUrl} onChange={(e) => setStoreUrl(e.target.value)} placeholder="https://mystore.com" required />
              </label>
            </div>
            <div>
              <label className="block text-sm font-medium text-on-surface">
                Consumer key
                <TextInput className="mt-1" value={consumerKey} onChange={(e) => setConsumerKey(e.target.value)} placeholder="ck_…" required />
              </label>
            </div>
            <div>
              <label className="block text-sm font-medium text-on-surface">
                Consumer secret
                <TextInput type="password" className="mt-1" value={consumerSecret} onChange={(e) => setConsumerSecret(e.target.value)} placeholder="cs_…" required />
              </label>
            </div>
            <div>
              <label className="block text-sm font-medium text-on-surface">
                Webhook secret
                <TextInput type="password" className="mt-1" value={webhookSecret} onChange={(e) => setWebhookSecret(e.target.value)} placeholder="For HMAC verification" required />
              </label>
            </div>
          </div>
          {connectErr && <p className="text-sm text-error">{connectErr}</p>}
          {connectResult && (
            <div className="rounded-xl border border-tertiary/20 bg-tertiary-fixed/20 p-4 text-sm">
              <p className="font-semibold text-on-surface">Connected: {connectResult.store_name}</p>
              <p className="text-on-surface-variant">{connectResult.store_url} · Currency: {connectResult.currency ?? "—"}</p>
            </div>
          )}
          <PrimaryButton type="submit" disabled={connecting || !channelId}>
            {connecting ? "Connecting…" : "Connect store"}
          </PrimaryButton>
        </form>
      </Panel>

      {channelId && (
        <Panel title="Sync actions" subtitle="Sync products and import orders from WooCommerce.">
          <div className="flex flex-wrap gap-3">
            {(["sync-catalog", "import-catalog"] as const).map((action) => (
              <PrimaryButton
                key={action}
                type="button"
                disabled={actionLoading !== null}
                onClick={() => void runAction(action)}
              >
                <span className="material-symbols-outlined text-lg">sync</span>
                {actionLoading === action ? "Running…" : action.replace(/-/g, " ")}
              </PrimaryButton>
            ))}
          </div>
          {syncResult && (
            <pre className="mt-4 overflow-x-auto rounded-lg bg-surface-container p-3 font-mono text-xs text-on-surface-variant">
              {syncResult}
            </pre>
          )}
        </Panel>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// API tokens tab
// ---------------------------------------------------------------------------

function ApiTokensTab() {
  const [tokens, setTokens] = useState<ApiToken[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [newToken, setNewToken] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch("/api/ims/v1/admin/integrations/api-tokens");
      if (r.ok) setTokens(((await r.json()) as ApiToken[]) ?? []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) { setErr("Name is required"); return; }
    setSaving(true);
    setErr(null);
    const r = await fetch("/api/ims/v1/admin/integrations/api-tokens", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name.trim() }),
    });
    if (r.ok) {
      const data = (await r.json()) as { token: string };
      setNewToken(data.token);
      setShowForm(false);
      setName("");
      void load();
    } else {
      const body = await r.json().catch(() => ({})) as { detail?: string };
      setErr(body.detail ?? `Failed (${r.status})`);
    }
    setSaving(false);
  }

  async function revoke(id: string) {
    if (!confirm("Revoke this token? All requests using it will immediately fail.")) return;
    await fetch(`/api/ims/v1/admin/integrations/api-tokens/${id}`, { method: "DELETE" });
    void load();
  }

  return (
    <div className="space-y-6">
      {newToken && (
        <div className="rounded-xl border border-tertiary/20 bg-tertiary-fixed/20 p-4">
          <p className="text-sm font-bold text-on-surface">Token created — copy it now. It won&apos;t be shown again.</p>
          <code className="mt-2 block break-all rounded-lg bg-surface-container-lowest px-4 py-3 font-mono text-sm text-primary">{newToken}</code>
          <button type="button" className="mt-2 text-xs font-semibold text-primary underline" onClick={() => setNewToken(null)}>
            Dismiss
          </button>
        </div>
      )}

      <div className="flex justify-end">
        <PrimaryButton type="button" onClick={() => { setShowForm((p) => !p); setErr(null); }}>
          <span className="material-symbols-outlined text-lg">{showForm ? "close" : "add"}</span>
          {showForm ? "Cancel" : "New token"}
        </PrimaryButton>
      </div>

      {showForm && (
        <form onSubmit={(e) => void create(e)} className="rounded-xl border border-outline-variant/10 bg-surface-container-low p-5 space-y-4">
          <div>
            <label className="block text-sm font-medium text-on-surface">
              Token name
              <TextInput className="mt-1" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. CI/CD pipeline, Zapier" required />
            </label>
          </div>
          {err && <p className="text-sm text-error">{err}</p>}
          <PrimaryButton type="submit" disabled={saving}>{saving ? "Creating…" : "Create token"}</PrimaryButton>
        </form>
      )}

      <Panel title="API tokens" subtitle={`${tokens.length} tokens`} noPad>
        {loading ? (
          <p className="px-6 py-8 text-sm text-on-surface-variant">Loading…</p>
        ) : tokens.length === 0 ? (
          <p className="px-6 py-8 text-center text-sm text-on-surface-variant">No tokens yet.</p>
        ) : (
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-outline-variant/10">
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Name</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Prefix</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Last used</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Status</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {tokens.map((t) => (
                <tr key={t.id} className="hover:bg-surface-container-low/50">
                  <td className="px-6 py-4 font-medium text-on-surface">{t.name}</td>
                  <td className="px-6 py-4 font-mono text-xs text-on-surface-variant">{t.token_prefix}…</td>
                  <td className="px-6 py-4 text-on-surface-variant">
                    {t.last_used_at ? new Date(t.last_used_at).toLocaleDateString() : "Never"}
                  </td>
                  <td className="px-6 py-4">
                    <Badge tone={t.revoked_at ? "danger" : "good"}>{t.revoked_at ? "revoked" : "active"}</Badge>
                  </td>
                  <td className="px-6 py-4">
                    {!t.revoked_at && (
                      <button
                        type="button"
                        onClick={() => void revoke(t.id)}
                        className="inline-flex items-center gap-1 rounded-lg border border-error/30 bg-error-container/10 px-3 py-1.5 text-xs font-semibold text-error transition hover:bg-error-container/30"
                      >
                        <span className="material-symbols-outlined text-sm">block</span>
                        Revoke
                      </button>
                    )}
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
// CSV import tab
// ---------------------------------------------------------------------------

function CsvImportTab() {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) { setErr("Select a CSV file first"); return; }
    setUploading(true);
    setResult(null);
    setErr(null);
    const formData = new FormData();
    formData.append("file", file);
    const r = await fetch("/api/ims/v1/admin/integrations/products/import-csv", {
      method: "POST",
      body: formData,
    });
    if (r.ok) {
      const data = (await r.json()) as ImportResult;
      setResult(data);
      if (data.errors.length === 0) {
        setFile(null);
        if (fileRef.current) fileRef.current.value = "";
      }
    } else {
      const body = await r.json().catch(() => ({})) as { detail?: string };
      setErr(body.detail ?? `Upload failed (${r.status})`);
    }
    setUploading(false);
  }

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-outline-variant/10 bg-surface-container-low p-5">
        <h3 className="font-headline text-base font-bold text-on-surface">CSV product import</h3>
        <p className="mt-1 text-sm text-on-surface-variant">
          Upload a CSV with columns: <code className="rounded bg-surface-container px-1 py-0.5 text-xs">sku</code>,{" "}
          <code className="rounded bg-surface-container px-1 py-0.5 text-xs">name</code>,{" "}
          <code className="rounded bg-surface-container px-1 py-0.5 text-xs">unit_price_cents</code> (optional),{" "}
          <code className="rounded bg-surface-container px-1 py-0.5 text-xs">reorder_point</code> (optional),{" "}
          <code className="rounded bg-surface-container px-1 py-0.5 text-xs">category</code> (optional).
          Existing SKUs are updated; new ones are inserted.
        </p>

        <form onSubmit={(e) => void handleUpload(e)} className="mt-4 space-y-4">
          <input
            ref={fileRef}
            type="file"
            accept=".csv,text/csv"
            required
            className="block w-full text-sm text-on-surface file:mr-4 file:rounded-lg file:border-0 file:bg-primary file:px-4 file:py-2 file:text-xs file:font-bold file:text-on-primary file:transition hover:file:opacity-90"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          {err && <p className="text-sm text-error">{err}</p>}
          <PrimaryButton type="submit" disabled={uploading || !file}>
            <span className="material-symbols-outlined text-lg">upload</span>
            {uploading ? "Importing…" : "Import CSV"}
          </PrimaryButton>
        </form>
      </div>

      {result && (
        <div className={`rounded-xl border p-5 ${result.errors.length > 0 ? "border-error/20 bg-error-container/10" : "border-tertiary/20 bg-tertiary-fixed/10"}`}>
          <p className="font-semibold text-on-surface">
            {result.errors.length > 0 ? "Import failed — validation errors" : `Import complete: ${result.inserted} inserted, ${result.updated} updated`}
          </p>
          {result.errors.length > 0 && (
            <ul className="mt-3 space-y-1 text-sm text-error">
              {result.errors.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          )}
        </div>
      )}

      <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-5">
        <h3 className="font-headline text-base font-bold text-on-surface">CSV template</h3>
        <pre className="mt-3 overflow-x-auto rounded-lg bg-surface-container p-3 font-mono text-xs text-on-surface-variant">
          {`sku,name,unit_price_cents,reorder_point,category\nSKU-001,Widget A,1500,10,Widgets\nSKU-002,Widget B,2000,5,Widgets`}
        </pre>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

const TABS = [
  { id: "shopify",      label: "Shopify" },
  { id: "woocommerce",  label: "WooCommerce" },
  { id: "webhooks",     label: "Webhooks" },
  { id: "tokens",       label: "API Tokens" },
  { id: "csv",          label: "CSV Import" },
];

export default function IntegrationsPage() {
  const [tab, setTab] = useState("shopify");

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="Platform"
        title="Integrations"
        subtitle="Connect external systems, manage API tokens, and bulk import products."
      />

      <Tabs tabs={TABS} active={tab} onChange={setTab} />

      {tab === "shopify" && <ShopifyTab />}
      {tab === "woocommerce" && <WooCommerceTab />}
      {tab === "webhooks" && <WebhookTab />}
      {tab === "tokens" && <ApiTokensTab />}
      {tab === "csv" && <CsvImportTab />}
    </div>
  );
}
