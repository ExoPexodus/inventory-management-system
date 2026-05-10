"use client";

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  Badge,
  EmptyState,
  PageHeader,
  Panel,
  PrimaryButton,
  SelectInput,
  Tabs,
  TextInput,
} from "@/components/ui/primitives";
import { RequiresBusinessType } from "@/components/dashboard/RequiresBusinessType";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type InventoryPool = { id: string; name: string };

type Channel = {
  id: string;
  type: string;
  name: string;
  status: string;
  currency_code: string;
  inventory_pool_id: string;
  config: Record<string, string>;
  created_at: string;
};

type PaymentConfig = {
  payment_provider: string | null;
  configured: boolean;
};

// ---------------------------------------------------------------------------
// Channels tab
// ---------------------------------------------------------------------------

function ChannelsTab() {
  const newParams = useSearchParams();
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [pools, setPools] = useState<InventoryPool[]>([]);

  const [type, setType] = useState("headless");
  const [name, setName] = useState("");
  const [currency, setCurrency] = useState("");
  const [poolId, setPoolId] = useState("");

  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [statusErr, setStatusErr] = useState<string | null>(null);

  const [createdBanner, setCreatedBanner] = useState<string | null>(null);
  const [paymentErrorBanner, setPaymentErrorBanner] = useState(false);

  useEffect(() => {
    if (newParams.get("new") === "1") {
      setShowForm(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [newParams]);

  useEffect(() => {
    const created = newParams.get("created");
    const paymentErr = newParams.get("payment_error");
    if (created) {
      setCreatedBanner(created);
      if (paymentErr === "1") setPaymentErrorBanner(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [chRes, poolRes] = await Promise.all([
        fetch("/api/ims/v1/admin/channels"),
        fetch("/api/ims/v1/admin/inventory-pools"),
      ]);
      if (chRes.ok) setChannels((await chRes.json()) as Channel[]);
      if (poolRes.ok) {
        const fetchedPools = (await poolRes.json()) as InventoryPool[];
        setPools(fetchedPools);
        if (!poolId && fetchedPools.length > 0) {
          setPoolId(fetchedPools[0]!.id);
        }
      }
    } finally {
      setLoading(false);
    }
  }, [poolId]);

  useEffect(() => { void load(); }, [load]);

  function openForm() {
    setShowForm(true);
    setErr(null);
    setType("headless");
    setName("");
    setCurrency("");
    if (pools.length > 0) setPoolId(pools[0]!.id);
  }

  function closeForm() {
    setShowForm(false);
    setErr(null);
  }

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!poolId) { setErr("Select an inventory pool"); return; }
    setSaving(true);
    setErr(null);
    const r = await fetch("/api/ims/v1/admin/channels", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        type,
        name: name.trim(),
        currency_code: currency.trim() || "INR",
        inventory_pool_id: poolId,
      }),
    });
    if (r.ok) {
      closeForm();
      void load();
    } else {
      const body = await r.json().catch(() => ({})) as { detail?: string };
      setErr(body.detail ?? `Failed (${r.status})`);
    }
    setSaving(false);
  }

  async function patchStatus(id: string, status: "active" | "disabled") {
    setStatusErr(null);
    const r = await fetch(`/api/ims/v1/admin/channels/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    if (r.ok) {
      void load();
    } else {
      const body = await r.json().catch(() => ({})) as { detail?: string };
      setStatusErr(body.detail ?? `Failed to update status (${r.status})`);
    }
  }

  const typeOptions = [
    { value: "headless", label: "Headless (API)" },
    { value: "manual", label: "Manual Orders" },
  ];

  const poolOptions = pools.map((p) => ({ value: p.id, label: p.name }));

  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <PrimaryButton type="button" onClick={showForm ? closeForm : openForm}>
          <span className="material-symbols-outlined text-lg">{showForm ? "close" : "add"}</span>
          {showForm ? "Cancel" : "New channel"}
        </PrimaryButton>
      </div>

      {showForm && (
        <form
          onSubmit={(e) => void create(e)}
          className="rounded-xl border border-outline-variant/10 bg-surface-container-low p-5 space-y-4"
        >
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-on-surface mb-1">Type</label>
              <SelectInput
                options={typeOptions}
                value={type}
                onChange={setType}
                placeholder="Select type"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-on-surface">
                Name
                <TextInput
                  className="mt-1"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Online Store"
                  required
                />
              </label>
            </div>
            <div>
              <label className="block text-sm font-medium text-on-surface">
                Currency
                <TextInput
                  className="mt-1"
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                  placeholder="INR"
                />
              </label>
            </div>
            <div>
              <label className="block text-sm font-medium text-on-surface mb-1">Inventory Pool</label>
              <SelectInput
                options={poolOptions}
                value={poolId}
                onChange={setPoolId}
                placeholder="Select pool"
              />
            </div>
          </div>
          {err && <p className="text-sm text-error">{err}</p>}
          <div className="flex gap-2">
            <PrimaryButton type="submit" disabled={saving}>
              {saving ? "Creating…" : "Create channel"}
            </PrimaryButton>
          </div>
        </form>
      )}

      {statusErr && (
        <p className="rounded-xl border border-error/20 bg-error-container/20 px-4 py-3 text-sm text-on-error-container">
          {statusErr}
        </p>
      )}

      {createdBanner && !paymentErrorBanner && (
        <div className="mb-4 flex items-center justify-between rounded-xl border border-green-400/30 bg-green-50 px-5 py-3">
          <div className="flex items-center gap-3">
            <span className="material-symbols-outlined text-xl text-green-600">check_circle</span>
            <p className="text-sm font-semibold text-green-900">Channel created successfully — your storefront is ready to connect.</p>
          </div>
          <button type="button" onClick={() => setCreatedBanner(null)} className="text-green-700 hover:opacity-70">
            <span className="material-symbols-outlined text-xl">close</span>
          </button>
        </div>
      )}
      {paymentErrorBanner && (
        <div className="mb-4 flex items-center justify-between rounded-xl border border-amber-400/30 bg-amber-50 px-5 py-3">
          <div className="flex items-center gap-3">
            <span className="material-symbols-outlined text-xl text-amber-600">warning</span>
            <p className="text-sm font-semibold text-amber-900">Your channel was created, but payment setup failed. Configure it from the channel settings below.</p>
          </div>
          <button type="button" onClick={() => setPaymentErrorBanner(false)} className="text-amber-700 hover:opacity-70">
            <span className="material-symbols-outlined text-xl">close</span>
          </button>
        </div>
      )}

      <Panel title="Channels" subtitle={`${channels.length} channel${channels.length === 1 ? "" : "s"}`} noPad>
        {loading ? (
          <p className="px-6 py-8 text-sm text-on-surface-variant">Loading…</p>
        ) : channels.length === 0 ? (
          <EmptyState
            title="No channels yet"
            detail="Channels are sales surfaces (your storefront, Shopify, etc.). Create one to start selling online."
            actionLabel="Set up your first channel"
            actionHref="/channels/setup"
          />
        ) : (
          <table className="min-w-full text-left text-sm">
            <thead>
              <tr className="border-b border-outline-variant/10">
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Name</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Type</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Currency</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Status</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Checkout URL</th>
                <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/10">
              {channels.map((ch) => (
                <tr key={ch.id} className="hover:bg-surface-container-low/50">
                  <td className="px-6 py-4 font-medium text-on-surface">{ch.name}</td>
                  <td className="px-6 py-4 text-on-surface-variant">{ch.type}</td>
                  <td className="px-6 py-4 text-on-surface-variant">{ch.currency_code}</td>
                  <td className="px-6 py-4">
                    <Badge tone={ch.status === "active" ? "good" : ch.status === "disabled" ? "warn" : "default"}>
                      {ch.status}
                    </Badge>
                  </td>
                  <td className="px-6 py-4 text-on-surface-variant">
                    {ch.type === "headless" ? (
                      <span className="rounded-full bg-surface-container px-2 py-1 font-mono text-[10px] text-on-surface-variant">
                        Use /checkout API
                      </span>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-6 py-4">
                    {ch.status === "active" ? (
                      <button
                        type="button"
                        onClick={() => void patchStatus(ch.id, "disabled")}
                        className="inline-flex items-center gap-1 rounded-lg border border-error/30 bg-error-container/10 px-3 py-1.5 text-xs font-semibold text-error transition hover:bg-error-container/30"
                      >
                        <span className="material-symbols-outlined text-sm">block</span>
                        Disable
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => void patchStatus(ch.id, "active")}
                        className="inline-flex items-center gap-1 rounded-lg border border-outline-variant/40 px-3 py-1.5 text-xs font-semibold text-on-surface transition hover:bg-surface-container"
                      >
                        <span className="material-symbols-outlined text-sm">check_circle</span>
                        Enable
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
// Checkout domain panel
// ---------------------------------------------------------------------------

function CheckoutDomainPanel({ channelId }: { channelId: string }) {
  const [domain, setDomain] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMsg(null);
    setErr(null);
    try {
      const r = await fetch(`/api/ims/v1/admin/channels/${channelId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          config: { checkout_domain: domain.trim() || null },
        }),
      });
      if (r.ok) {
        setMsg("Checkout domain saved.");
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
    <Panel
      title="Custom checkout domain"
      subtitle="Serve checkout from your own domain — e.g. checkout.yourstore.com."
    >
      <form onSubmit={(e) => void handleSave(e)} className="space-y-3">
        <div>
          <label className="block text-sm font-medium text-on-surface mb-1">
            Checkout domain
          </label>
          <TextInput
            value={domain}
            onChange={(e) => setDomain(e.target.value)}
            placeholder="checkout.yourstore.com"
          />
          <p className="mt-1 text-xs text-on-surface-variant">
            Leave blank to use the default API URL. Point this domain to your API via DNS/reverse proxy.
            No &ldquo;https://&rdquo; needed.
          </p>
        </div>
        {msg && <p className="text-sm font-semibold text-primary">{msg}</p>}
        {err && <p className="text-sm text-error">{err}</p>}
        <PrimaryButton type="submit" disabled={saving}>
          {saving ? "Saving…" : "Save domain"}
        </PrimaryButton>
      </form>
    </Panel>
  );
}

// ---------------------------------------------------------------------------
// Shipping tab
// ---------------------------------------------------------------------------

function ShippingTab({ channels }: { channels: Channel[] }) {
  const [selectedChannelId, setSelectedChannelId] = useState("");
  const [config, setConfig] = useState<{
    configured: boolean; provider: string | null;
    pickup_location: string | null; email: string | null;
  } | null>(null);
  const [configLoading, setConfigLoading] = useState(false);
  const [activeProvider, setActiveProvider] = useState<"shiprocket" | null>(null);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pickupLocation, setPickupLocation] = useState("");
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const channelOptions = channels.map((c) => ({ value: c.id, label: c.name }));

  const loadConfig = useCallback(async (channelId: string) => {
    if (!channelId) return;
    setConfigLoading(true);
    try {
      const r = await fetch(`/api/ims/v1/admin/channels/${channelId}/shipping/config`);
      if (r.ok) {
        const cfg = (await r.json()) as typeof config;
        setConfig(cfg);
        if (cfg?.configured && cfg?.provider === "shiprocket") {
          setActiveProvider("shiprocket");
        }
      }
    } catch { /* ignore */ }
    finally { setConfigLoading(false); }
  }, []);

  function selectChannel(id: string) {
    setSelectedChannelId(id);
    setActiveProvider(null);
    setMsg(null); setErr(null);
    void loadConfig(id);
  }

  async function handleSetup(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true); setMsg(null); setErr(null);
    try {
      const r = await fetch(
        `/api/ims/v1/admin/channels/${selectedChannelId}/shipping/setup-shiprocket`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: email.trim(), password,
            pickup_location: pickupLocation.trim(),
          }),
        }
      );
      if (r.ok) {
        setMsg("Shiprocket configured successfully.");
        setPassword("");
        void loadConfig(selectedChannelId);
      } else {
        const d = await r.json().catch(() => ({})) as { detail?: string };
        setErr(d.detail ?? `Failed (${r.status})`);
      }
    } catch { setErr("Network error. Please try again."); }
    finally { setSaving(false); }
  }

  async function handleDisconnect() {
    if (!confirm("Remove Shiprocket from this channel?")) return;
    try {
      await fetch(
        `/api/ims/v1/admin/channels/${selectedChannelId}/shipping/config`,
        { method: "DELETE" }
      );
      setConfig(null); setMsg("Shipping provider removed.");
    } catch { setErr("Network error."); }
  }

  return (
    <div className="space-y-6">
      <Panel title="Shipping configuration" subtitle="Select a channel to configure Shiprocket.">
        <div className="max-w-sm">
          <label className="block text-sm font-medium text-on-surface mb-1">Channel</label>
          <SelectInput
            options={channelOptions} value={selectedChannelId}
            onChange={selectChannel} placeholder="Select channel"
          />
        </div>

        {selectedChannelId && (
          configLoading ? (
            <p className="mt-4 text-sm text-on-surface-variant">Loading…</p>
          ) : config?.configured ? (
            <div className="mt-4 flex items-center gap-4 flex-wrap">
              <Badge tone="good">Shiprocket connected</Badge>
              <span className="text-xs text-on-surface-variant">
                {config.email} · Pickup: {config.pickup_location}
              </span>
              <button
                type="button" onClick={() => void handleDisconnect()}
                className="text-xs text-error hover:underline"
              >
                Disconnect
              </button>
            </div>
          ) : (
            <p className="mt-4 text-sm text-on-surface-variant">Not configured yet.</p>
          )
        )}

        {selectedChannelId && (
          <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <button
              type="button"
              onClick={() => setActiveProvider("shiprocket")}
              className={`flex flex-col items-center justify-center rounded-xl border-2 px-4 py-5 text-sm font-semibold transition ${
                activeProvider === "shiprocket"
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-outline-variant/20 bg-surface-container-lowest text-on-surface hover:border-primary/30 hover:bg-primary/5"
              }`}
            >
              <span className="material-symbols-outlined text-2xl mb-1">local_shipping</span>
              Shiprocket
              {config?.configured && config?.provider === "shiprocket" && (
                <span className="mt-1 text-[10px] font-bold uppercase tracking-widest text-primary">Active</span>
              )}
            </button>
            {(["Delhivery", "DTDC", "Bluedart"] as const).map((name) => (
              <button
                key={name}
                type="button"
                disabled
                className="flex flex-col items-center justify-center rounded-xl border-2 border-outline-variant/10 bg-surface-container-lowest/50 px-4 py-5 text-sm font-semibold text-on-surface-variant/60 cursor-not-allowed"
              >
                <span className="material-symbols-outlined text-2xl mb-1 opacity-50">local_shipping</span>
                {name}
                <span className="mt-1 rounded-full bg-secondary/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest text-on-secondary-container">
                  Coming soon
                </span>
              </button>
            ))}
          </div>
        )}
      </Panel>

      {selectedChannelId && !activeProvider && (
        <Panel title="Choose a carrier" subtitle="Select a shipping carrier above to configure it for this channel.">
          <p className="text-sm text-on-surface-variant">No carrier selected.</p>
        </Panel>
      )}

      {activeProvider === "shiprocket" && (
        <Panel
          title="Connect Shiprocket"
          subtitle="Credentials are verified and stored encrypted. Pickup location must match exactly in your Shiprocket account."
        >
          <form onSubmit={(e) => void handleSetup(e)} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label className="block text-sm font-medium text-on-surface">
                  Shiprocket email
                  <TextInput className="mt-1" type="email" value={email}
                    onChange={(e) => setEmail(e.target.value)} required />
                </label>
              </div>
              <div>
                <label className="block text-sm font-medium text-on-surface">
                  Shiprocket password
                  <TextInput className="mt-1" type="password" value={password}
                    onChange={(e) => setPassword(e.target.value)} required />
                </label>
              </div>
              <div className="sm:col-span-2">
                <label className="block text-sm font-medium text-on-surface">
                  Pickup location name
                  <TextInput
                    className="mt-1" value={pickupLocation}
                    onChange={(e) => setPickupLocation(e.target.value)}
                    placeholder="Warehouse-Mumbai"
                    required
                  />
                </label>
              </div>
            </div>
            {msg && <p className="text-sm font-semibold text-primary">{msg}</p>}
            {err && <p className="text-sm text-error">{err}</p>}
            <PrimaryButton type="submit" disabled={saving}>
              {saving ? "Connecting…" : "Connect Shiprocket"}
            </PrimaryButton>
          </form>
        </Panel>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Payment tab
// ---------------------------------------------------------------------------

function PaymentTab({ channels }: { channels: Channel[] }) {
  const [selectedChannelId, setSelectedChannelId] = useState("");
  const [paymentConfig, setPaymentConfig] = useState<PaymentConfig | null>(null);
  const [configLoading, setConfigLoading] = useState(false);

  // Stripe form state
  const [stripeSecret, setStripeSecret] = useState("");
  const [stripePublishable, setStripePublishable] = useState("");
  const [stripeSuccess, setStripeSuccess] = useState("");
  const [stripeSaving, setStripeSaving] = useState(false);
  const [stripeErr, setStripeErr] = useState<string | null>(null);
  const [stripeOk, setStripeOk] = useState(false);

  // Razorpay form state
  const [razorKeyId, setRazorKeyId] = useState("");
  const [razorKeySecret, setRazorKeySecret] = useState("");
  const [razorSuccess, setRazorSuccess] = useState("");
  const [razorSaving, setRazorSaving] = useState(false);
  const [razorErr, setRazorErr] = useState<string | null>(null);
  const [razorOk, setRazorOk] = useState(false);

  const channelOptions = channels.map((ch) => ({ value: ch.id, label: ch.name }));

  const loadConfig = useCallback(async (channelId: string) => {
    if (!channelId) return;
    setConfigLoading(true);
    setPaymentConfig(null);
    try {
      const r = await fetch(`/api/ims/v1/admin/channels/${channelId}/payment/config`);
      if (r.ok) setPaymentConfig((await r.json()) as PaymentConfig);
    } finally {
      setConfigLoading(false);
    }
  }, []);

  function selectChannel(id: string) {
    setSelectedChannelId(id);
    setStripeSecret(""); setStripePublishable(""); setStripeSuccess("");
    setStripeErr(null); setStripeOk(false);
    setRazorKeyId(""); setRazorKeySecret(""); setRazorSuccess("");
    setRazorErr(null); setRazorOk(false);
    void loadConfig(id);
  }

  async function setupStripe(e: React.FormEvent) {
    e.preventDefault();
    setStripeSaving(true);
    setStripeErr(null);
    setStripeOk(false);
    const r = await fetch(`/api/ims/v1/admin/channels/${selectedChannelId}/payment/setup-stripe`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        stripe_secret_key: stripeSecret,
        stripe_publishable_key: stripePublishable,
        checkout_success_url: stripeSuccess,
      }),
    });
    if (r.ok) {
      setStripeOk(true);
      void loadConfig(selectedChannelId);
    } else {
      const body = await r.json().catch(() => ({})) as { detail?: string };
      setStripeErr(body.detail ?? `Failed (${r.status})`);
    }
    setStripeSaving(false);
  }

  async function setupRazorpay(e: React.FormEvent) {
    e.preventDefault();
    setRazorSaving(true);
    setRazorErr(null);
    setRazorOk(false);
    const r = await fetch(`/api/ims/v1/admin/channels/${selectedChannelId}/payment/setup-razorpay`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        razorpay_key_id: razorKeyId,
        razorpay_key_secret: razorKeySecret,
        checkout_success_url: razorSuccess,
      }),
    });
    if (r.ok) {
      setRazorOk(true);
      void loadConfig(selectedChannelId);
    } else {
      const body = await r.json().catch(() => ({})) as { detail?: string };
      setRazorErr(body.detail ?? `Failed (${r.status})`);
    }
    setRazorSaving(false);
  }

  return (
    <div className="space-y-6">
      <Panel title="Payment configuration" subtitle="Select a channel to configure its payment provider.">
        <div className="max-w-sm">
          <label className="block text-sm font-medium text-on-surface mb-1">Channel</label>
          <SelectInput
            options={channelOptions}
            value={selectedChannelId}
            onChange={selectChannel}
            placeholder="Select channel"
          />
        </div>

        {selectedChannelId && (
          <div className="mt-6 space-y-2">
            {configLoading ? (
              <p className="text-sm text-on-surface-variant">Loading payment config…</p>
            ) : paymentConfig ? (
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium text-on-surface">Current provider:</span>
                {paymentConfig.configured && paymentConfig.payment_provider ? (
                  <Badge tone="good">{paymentConfig.payment_provider}</Badge>
                ) : (
                  <Badge tone="warn">Not configured</Badge>
                )}
              </div>
            ) : null}
          </div>
        )}
      </Panel>

      {selectedChannelId && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            {/* Stripe setup */}
            <Panel title="Stripe" subtitle="Accept card payments via Stripe Checkout.">
              <form onSubmit={(e) => void setupStripe(e)} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-on-surface">
                    Secret key
                    <TextInput
                      type="password"
                      className="mt-1"
                      value={stripeSecret}
                      onChange={(e) => setStripeSecret(e.target.value)}
                      placeholder="sk_live_…"
                      required
                    />
                  </label>
                </div>
                <div>
                  <label className="block text-sm font-medium text-on-surface">
                    Publishable key
                    <TextInput
                      className="mt-1"
                      value={stripePublishable}
                      onChange={(e) => setStripePublishable(e.target.value)}
                      placeholder="pk_live_…"
                      required
                    />
                  </label>
                </div>
                <div>
                  <label className="block text-sm font-medium text-on-surface">
                    Success URL
                    <TextInput
                      className="mt-1"
                      value={stripeSuccess}
                      onChange={(e) => setStripeSuccess(e.target.value)}
                      placeholder="https://yourstore.com/order/success"
                      required
                    />
                  </label>
                </div>
                {stripeErr && <p className="text-sm text-error">{stripeErr}</p>}
                {stripeOk && (
                  <div className="flex items-center justify-between rounded-xl border border-tertiary/20 bg-tertiary-fixed/20 px-4 py-3 text-sm font-semibold text-on-surface">
                    Stripe configured successfully.
                    <button type="button" className="text-xs text-primary underline" onClick={() => setStripeOk(false)}>
                      Dismiss
                    </button>
                  </div>
                )}
                <PrimaryButton type="submit" disabled={stripeSaving}>
                  {stripeSaving ? "Saving…" : "Set up Stripe"}
                </PrimaryButton>
              </form>
            </Panel>

            {/* Razorpay setup */}
            <Panel title="Razorpay" subtitle="Accept payments via Razorpay Checkout.">
              <form onSubmit={(e) => void setupRazorpay(e)} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-on-surface">
                    Key ID
                    <TextInput
                      className="mt-1"
                      value={razorKeyId}
                      onChange={(e) => setRazorKeyId(e.target.value)}
                      placeholder="rzp_live_…"
                      required
                    />
                  </label>
                </div>
                <div>
                  <label className="block text-sm font-medium text-on-surface">
                    Key Secret
                    <TextInput
                      type="password"
                      className="mt-1"
                      value={razorKeySecret}
                      onChange={(e) => setRazorKeySecret(e.target.value)}
                      placeholder="••••••••"
                      required
                    />
                  </label>
                </div>
                <div>
                  <label className="block text-sm font-medium text-on-surface">
                    Success URL
                    <TextInput
                      className="mt-1"
                      value={razorSuccess}
                      onChange={(e) => setRazorSuccess(e.target.value)}
                      placeholder="https://yourstore.com/order/success"
                      required
                    />
                  </label>
                </div>
                {razorErr && <p className="text-sm text-error">{razorErr}</p>}
                {razorOk && (
                  <div className="flex items-center justify-between rounded-xl border border-tertiary/20 bg-tertiary-fixed/20 px-4 py-3 text-sm font-semibold text-on-surface">
                    Razorpay configured successfully.
                    <button type="button" className="text-xs text-primary underline" onClick={() => setRazorOk(false)}>
                      Dismiss
                    </button>
                  </div>
                )}
                <PrimaryButton type="submit" disabled={razorSaving}>
                  {razorSaving ? "Saving…" : "Set up Razorpay"}
                </PrimaryButton>
              </form>
            </Panel>
          </div>
          <CheckoutDomainPanel channelId={selectedChannelId} />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

const TABS = [
  { id: "channels", label: "Channels" },
  { id: "payment", label: "Payment" },
  { id: "shipping", label: "Shipping" },
];

function ChannelsPageInner() {
  const [tab, setTab] = useState<"channels" | "payment" | "shipping">("channels");
  const [channels, setChannels] = useState<Channel[]>([]);

  const loadChannels = useCallback(async () => {
    const r = await fetch("/api/ims/v1/admin/channels");
    if (r.ok) setChannels((await r.json()) as Channel[]);
  }, []);

  useEffect(() => { void loadChannels(); }, [loadChannels]);

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="Commerce"
        title="Channels"
        subtitle="Manage your sales channels and configure payment providers."
      />

      <Tabs tabs={TABS} active={tab} onChange={(id) => setTab(id as "channels" | "payment" | "shipping")} />

      {tab === "channels" && <ChannelsTab />}
      {tab === "payment" && <PaymentTab channels={channels} />}
      {tab === "shipping" && <ShippingTab channels={channels} />}
    </div>
  );
}

export default function ChannelsPage() {
  return (
    <RequiresBusinessType types={["online", "hybrid"]}>
      <ChannelsPageInner />
    </RequiresBusinessType>
  );
}
