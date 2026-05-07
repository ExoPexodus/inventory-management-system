"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Badge,
  PageHeader,
  Panel,
  PrimaryButton,
  SelectInput,
  Tabs,
  TextInput,
} from "@/components/ui/primitives";

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

      <Panel title="Channels" subtitle={`${channels.length} channel${channels.length === 1 ? "" : "s"}`} noPad>
        {loading ? (
          <p className="px-6 py-8 text-sm text-on-surface-variant">Loading…</p>
        ) : channels.length === 0 ? (
          <p className="px-6 py-8 text-center text-sm text-on-surface-variant">No channels yet.</p>
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
];

export default function ChannelsPage() {
  const [tab, setTab] = useState<"channels" | "payment">("channels");
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

      <Tabs tabs={TABS} active={tab} onChange={(id) => setTab(id as "channels" | "payment")} />

      {tab === "channels" && <ChannelsTab />}
      {tab === "payment" && <PaymentTab channels={channels} />}
    </div>
  );
}
