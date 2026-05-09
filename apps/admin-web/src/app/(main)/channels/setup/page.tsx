"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { RequiresBusinessType } from "@/components/dashboard/RequiresBusinessType";
import { useBusinessType } from "@/lib/business-type-context";
import { useCurrency } from "@/lib/currency-context";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type Phase = "type-picker" | "wizard";
type PaymentChoice = "stripe" | "razorpay" | "skip";
interface Shop { id: string; name: string; }

// ---------------------------------------------------------------------------
// TypePicker
// ---------------------------------------------------------------------------

function TypePickerCard({
  icon, title, description, onClick,
}: {
  icon: string; title: string; description: string; onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex w-full items-start gap-4 rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-6 text-left shadow-sm transition-all hover:border-primary/30 hover:bg-primary/5 hover:shadow-md"
    >
      <span className="material-symbols-outlined mt-0.5 text-3xl text-primary" aria-hidden="true">{icon}</span>
      <div>
        <p className="font-headline text-base font-bold text-on-surface">{title}</p>
        <p className="mt-1 text-sm text-on-surface-variant">{description}</p>
      </div>
      <span className="material-symbols-outlined ml-auto mt-0.5 shrink-0 text-xl text-on-surface-variant" aria-hidden="true">chevron_right</span>
    </button>
  );
}

function TypePicker({ onHeadless, onRedirect }: { onHeadless: () => void; onRedirect: (path: string) => void }) {
  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">New channel</p>
        <h2 className="font-headline text-3xl font-extrabold tracking-tight text-on-surface">What kind of storefront?</h2>
        <p className="mt-2 text-sm text-on-surface-variant">Choose the platform you&apos;ll use to sell online.</p>
      </div>
      <div className="space-y-4">
        <TypePickerCard
          icon="code"
          title="Headless storefront"
          description="Build a custom store using the IMS Storefront SDK or your own frontend"
          onClick={onHeadless}
        />
        <TypePickerCard
          icon="shopping_bag"
          title="Shopify"
          description="Connect an existing Shopify store to sync inventory and orders"
          onClick={() => onRedirect("/integrations")}
        />
        <TypePickerCard
          icon="shopping_cart"
          title="WooCommerce"
          description="Connect an existing WooCommerce store to sync inventory and orders"
          onClick={() => onRedirect("/integrations")}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// StepIndicator
// ---------------------------------------------------------------------------

function StepIndicator({
  steps, currentStep, onStepClick,
}: {
  steps: string[]; currentStep: number; onStepClick: (i: number) => void;
}) {
  return (
    <div className="flex items-center gap-0">
      {steps.map((label, i) => (
        <div key={label} className="flex flex-1 items-center">
          <button
            type="button"
            onClick={() => { if (i < currentStep) onStepClick(i); }}
            disabled={i >= currentStep}
            className="flex items-center gap-2 disabled:cursor-default"
          >
            <span
              className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                i === currentStep
                  ? "bg-primary text-on-primary"
                  : i < currentStep
                  ? "bg-primary/20 text-primary"
                  : "bg-surface-container-low text-on-surface-variant"
              }`}
            >
              {i < currentStep ? (
                <span className="material-symbols-outlined text-[14px]">check</span>
              ) : (
                i + 1
              )}
            </span>
            <span className={`text-sm font-medium ${i === currentStep ? "text-on-surface" : "text-on-surface-variant"}`}>
              {label}
            </span>
          </button>
          {i < steps.length - 1 && (
            <div className={`mx-3 flex-1 border-t ${i < currentStep ? "border-primary/40" : "border-outline-variant/20"}`} />
          )}
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ShopsStep
// ---------------------------------------------------------------------------

function ShopsStep({
  shops, loading, selectedIds, onChange,
}: {
  shops: Shop[]; loading: boolean; selectedIds: string[]; onChange: (ids: string[]) => void;
}) {
  if (loading) {
    return <p className="py-8 text-center text-sm text-on-surface-variant">Loading shops…</p>;
  }
  if (shops.length === 0) {
    return (
      <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-8 text-center">
        <span className="material-symbols-outlined text-4xl text-on-surface-variant/40">storefront</span>
        <p className="mt-3 text-sm font-semibold text-on-surface">No shops yet</p>
        <p className="mt-1 text-sm text-on-surface-variant">You need at least one shop before setting up an online channel.</p>
        <a
          href="/shops/new"
          className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-on-primary hover:opacity-90"
        >
          Add a shop →
        </a>
      </div>
    );
  }
  return (
    <div className="space-y-4">
      <div>
        <h3 className="font-headline text-lg font-bold text-on-surface">Which shops will fulfil online orders?</h3>
        <p className="mt-1 text-sm text-on-surface-variant">Online orders draw stock from the shops you select.</p>
      </div>
      <div className="space-y-2">
        {shops.map((shop) => {
          const checked = selectedIds.includes(shop.id);
          return (
            <label key={shop.id} className="flex cursor-pointer items-center gap-3 rounded-xl border border-outline-variant/10 bg-surface-container-lowest px-4 py-3 hover:bg-surface-container-low/60">
              <input
                type="checkbox"
                checked={checked}
                onChange={(e) => {
                  if (e.target.checked) onChange([...selectedIds, shop.id]);
                  else onChange(selectedIds.filter((id) => id !== shop.id));
                }}
                className="h-4 w-4 rounded accent-primary"
              />
              <span className="text-sm font-medium text-on-surface">{shop.name}</span>
            </label>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ChannelDetailsStep
// ---------------------------------------------------------------------------

function ChannelDetailsStep({
  name, onNameChange, currencyCode,
}: {
  name: string; onNameChange: (v: string) => void; currencyCode: string;
}) {
  return (
    <div className="space-y-6">
      <div>
        <h3 className="font-headline text-lg font-bold text-on-surface">Name your channel</h3>
        <p className="mt-1 text-sm text-on-surface-variant">This name appears on the Channels page.</p>
      </div>
      <label className="block">
        <span className="mb-1 block text-sm font-medium text-on-surface">Channel name</span>
        <input
          type="text"
          value={name}
          onChange={(e) => onNameChange(e.target.value)}
          required
          className="w-full rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-2 text-sm text-on-surface outline-none focus:border-primary focus:ring-1 focus:ring-primary"
        />
      </label>
      <div className="rounded-xl border border-outline-variant/10 bg-surface-container-low px-4 py-3">
        <span className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Currency</span>
        <p className="mt-1 text-sm font-semibold text-on-surface">{currencyCode}</p>
        <a href="/settings" className="mt-1 text-xs text-primary hover:underline">
          Wrong currency? Change in Settings →
        </a>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// PaymentStep
// ---------------------------------------------------------------------------

function PaymentStep({
  choice, onChoiceChange,
  stripeSecretKey, stripePublishableKey, stripeSuccessUrl,
  onStripeChange,
  razorpayKeyId, razorpayKeySecret, razorpaySuccessUrl,
  onRazorpayChange,
}: {
  choice: PaymentChoice; onChoiceChange: (c: PaymentChoice) => void;
  stripeSecretKey: string; stripePublishableKey: string; stripeSuccessUrl: string;
  onStripeChange: (field: "secret" | "publishable" | "success_url", value: string) => void;
  razorpayKeyId: string; razorpayKeySecret: string; razorpaySuccessUrl: string;
  onRazorpayChange: (field: "key_id" | "key_secret" | "success_url", value: string) => void;
}) {
  const options: { value: PaymentChoice; label: string; icon: string }[] = [
    { value: "stripe", label: "Stripe", icon: "credit_card" },
    { value: "razorpay", label: "Razorpay", icon: "payments" },
    { value: "skip", label: "Skip for now", icon: "schedule" },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h3 className="font-headline text-lg font-bold text-on-surface">Accept payments</h3>
        <p className="mt-1 text-sm text-on-surface-variant">Choose a payment provider for your checkout.</p>
      </div>
      <div className="grid grid-cols-3 gap-3">
        {options.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChoiceChange(opt.value)}
            className={`flex flex-col items-center gap-2 rounded-xl border px-4 py-4 text-sm font-semibold transition-all ${
              choice === opt.value
                ? "border-primary bg-primary/10 text-primary"
                : "border-outline-variant/20 bg-surface-container-lowest text-on-surface-variant hover:border-outline-variant/50"
            }`}
          >
            <span className="material-symbols-outlined text-2xl" aria-hidden="true">{opt.icon}</span>
            {opt.label}
          </button>
        ))}
      </div>
      {choice === "stripe" && (
        <div className="space-y-4">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-on-surface">Secret key</span>
            <input type="password" value={stripeSecretKey} onChange={(e) => onStripeChange("secret", e.target.value)} placeholder="sk_live_..." className="w-full rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-on-surface">Publishable key</span>
            <input type="text" value={stripePublishableKey} onChange={(e) => onStripeChange("publishable", e.target.value)} placeholder="pk_live_..." className="w-full rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-on-surface">Checkout success URL</span>
            <input type="url" value={stripeSuccessUrl} onChange={(e) => onStripeChange("success_url", e.target.value)} placeholder="https://yourstore.com/order/success" className="w-full rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
          </label>
        </div>
      )}
      {choice === "razorpay" && (
        <div className="space-y-4">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-on-surface">Key ID</span>
            <input type="text" value={razorpayKeyId} onChange={(e) => onRazorpayChange("key_id", e.target.value)} placeholder="rzp_live_..." className="w-full rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-on-surface">Key secret</span>
            <input type="password" value={razorpayKeySecret} onChange={(e) => onRazorpayChange("key_secret", e.target.value)} className="w-full rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-on-surface">Checkout success URL</span>
            <input type="url" value={razorpaySuccessUrl} onChange={(e) => onRazorpayChange("success_url", e.target.value)} placeholder="https://yourstore.com/order/success" className="w-full rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary" />
          </label>
        </div>
      )}
      {choice === "skip" && (
        <p className="rounded-xl border border-outline-variant/10 bg-surface-container-low px-4 py-3 text-sm text-on-surface-variant">
          You can add a payment provider from the Channels page after setup.
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main wizard
// ---------------------------------------------------------------------------

function ChannelSetupWizard() {
  const router = useRouter();
  const { flags } = useBusinessType();
  const currency = useCurrency();
  const businessType = flags?.business_type ?? "online";
  const isHybrid = businessType === "hybrid";

  const steps = isHybrid
    ? ["Pick shops", "Channel details", "Payment"]
    : ["Channel details", "Payment"];

  const [phase, setPhase] = useState<Phase>("type-picker");
  const [step, setStep] = useState(0);
  const [shops, setShops] = useState<Shop[]>([]);
  const [selectedShopIds, setSelectedShopIds] = useState<string[]>([]);
  const [shopsLoading, setShopsLoading] = useState(false);
  const [channelName, setChannelName] = useState("Online Store");
  const [paymentChoice, setPaymentChoice] = useState<PaymentChoice>("skip");
  const [stripeSecretKey, setStripeSecretKey] = useState("");
  const [stripePublishableKey, setStripePublishableKey] = useState("");
  const [stripeSuccessUrl, setStripeSuccessUrl] = useState("");
  const [razorpayKeyId, setRazorpayKeyId] = useState("");
  const [razorpayKeySecret, setRazorpayKeySecret] = useState("");
  const [razorpaySuccessUrl, setRazorpaySuccessUrl] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchShops = useCallback(async () => {
    setShopsLoading(true);
    try {
      const r = await fetch("/api/ims/v1/admin/shops");
      if (r.ok) {
        const data = (await r.json()) as Shop[];
        setShops(data);
        setSelectedShopIds(data.map((s) => s.id));
      }
    } finally {
      setShopsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (phase === "wizard") void fetchShops();
  }, [phase, fetchShops]);

  const shopsStepIndex = isHybrid ? 0 : -1;
  const channelStepIndex = isHybrid ? 1 : 0;
  const paymentStepIndex = isHybrid ? 2 : 1;

  async function handleComplete() {
    setError(null);
    setSubmitting(true);
    try {
      const shopIds = isHybrid ? selectedShopIds : shops.map((s) => s.id);
      const poolRes = await fetch("/api/ims/v1/admin/inventory-pools", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: `${channelName} Pool`, shop_ids: shopIds }),
      });
      if (!poolRes.ok) {
        const d = await poolRes.json().catch(() => ({})) as { detail?: string };
        setError(d.detail ?? "Failed to create inventory pool. Please try again.");
        return;
      }
      const pool = (await poolRes.json()) as { id: string };

      const channelRes = await fetch("/api/ims/v1/admin/channels", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type: "headless",
          name: channelName,
          inventory_pool_id: pool.id,
          currency_code: currency.code,
        }),
      });
      if (!channelRes.ok) {
        const d = await channelRes.json().catch(() => ({})) as { detail?: string };
        setError(d.detail ?? "Failed to create channel. Please try again.");
        return;
      }
      const channel = (await channelRes.json()) as { id: string };

      if (paymentChoice !== "skip") {
        const paymentEndpoint =
          paymentChoice === "stripe"
            ? `/api/ims/v1/admin/channels/${channel.id}/payment/setup-stripe`
            : `/api/ims/v1/admin/channels/${channel.id}/payment/setup-razorpay`;
        const paymentBody =
          paymentChoice === "stripe"
            ? { stripe_secret_key: stripeSecretKey, stripe_publishable_key: stripePublishableKey, checkout_success_url: stripeSuccessUrl }
            : { razorpay_key_id: razorpayKeyId, razorpay_key_secret: razorpayKeySecret, checkout_success_url: razorpaySuccessUrl };
        const paymentRes = await fetch(paymentEndpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(paymentBody),
        });
        if (!paymentRes.ok) {
          router.push(`/channels?created=${channel.id}&payment_error=1`);
          return;
        }
      }

      router.push(`/channels?created=${channel.id}`);
    } finally {
      setSubmitting(false);
    }
  }

  if (phase === "type-picker") {
    return (
      <TypePicker
        onHeadless={() => { setPhase("wizard"); setStep(0); }}
        onRedirect={(path) => router.push(path)}
      />
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-8">
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">New channel</p>
        <h2 className="font-headline text-3xl font-extrabold tracking-tight text-on-surface">Set up your store</h2>
        <p className="mt-2 text-sm text-on-surface-variant">Follow these steps to launch your online store.</p>
      </div>
      <StepIndicator steps={steps} currentStep={step} onStepClick={(i) => setStep(i)} />
      {error && (
        <div className="rounded-xl border border-error/20 bg-error-container/30 px-4 py-3 text-sm text-on-error-container">
          {error}
        </div>
      )}
      {step === shopsStepIndex && isHybrid && (
        <ShopsStep shops={shops} loading={shopsLoading} selectedIds={selectedShopIds} onChange={setSelectedShopIds} />
      )}
      {step === channelStepIndex && (
        <ChannelDetailsStep name={channelName} onNameChange={setChannelName} currencyCode={currency.code} />
      )}
      {step === paymentStepIndex && (
        <PaymentStep
          choice={paymentChoice}
          onChoiceChange={setPaymentChoice}
          stripeSecretKey={stripeSecretKey}
          stripePublishableKey={stripePublishableKey}
          stripeSuccessUrl={stripeSuccessUrl}
          onStripeChange={(f, v) => {
            if (f === "secret") setStripeSecretKey(v);
            else if (f === "publishable") setStripePublishableKey(v);
            else setStripeSuccessUrl(v);
          }}
          razorpayKeyId={razorpayKeyId}
          razorpayKeySecret={razorpayKeySecret}
          razorpaySuccessUrl={razorpaySuccessUrl}
          onRazorpayChange={(f, v) => {
            if (f === "key_id") setRazorpayKeyId(v);
            else if (f === "key_secret") setRazorpayKeySecret(v);
            else setRazorpaySuccessUrl(v);
          }}
        />
      )}
      <div className="flex justify-between pt-2">
        <button
          type="button"
          onClick={() => (step === 0 ? setPhase("type-picker") : setStep(step - 1))}
          className="rounded-lg border border-outline-variant/30 px-4 py-2 text-sm font-medium text-on-surface hover:bg-surface-container-low"
        >
          ← Back
        </button>
        {step < steps.length - 1 ? (
          <button
            type="button"
            onClick={() => { setError(null); setStep(step + 1); }}
            className="rounded-lg bg-primary px-5 py-2 text-sm font-semibold text-on-primary hover:opacity-90"
          >
            Continue →
          </button>
        ) : (
          <button
            type="button"
            onClick={() => void handleComplete()}
            disabled={submitting}
            className="rounded-lg bg-primary px-5 py-2 text-sm font-semibold text-on-primary hover:opacity-90 disabled:opacity-50"
          >
            {submitting ? "Setting up…" : "Complete setup →"}
          </button>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page export
// ---------------------------------------------------------------------------

export default function ChannelSetupPage() {
  return (
    <RequiresBusinessType types={["online", "hybrid"]}>
      <ChannelSetupWizard />
    </RequiresBusinessType>
  );
}
