# Channel Setup Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a guided 2–3 step wizard at `/channels/setup` that takes a merchant from zero to a working headless ecommerce channel (inventory pool + channel + optional payment) in one flow, and routes Shopify/WooCommerce merchants to the integrations page.

**Architecture:** Single `"use client"` page at `apps/admin-web/src/app/(main)/channels/setup/page.tsx` containing all wizard state and sub-components inline (TypePicker, StepIndicator, ShopsStep, ChannelDetailsStep, PaymentStep). State machine: `type-picker` phase → `wizard` phase with step index. On completion, three sequential API calls (pool → channel → optional payment), then `router.push('/channels?created={id}')`. Entry points in AppShell, overview page, and channels empty state are updated to point here. No backend changes needed.

**Tech Stack:** Next.js 15 / React 19 / TypeScript / Tailwind / Material Symbols. Existing hooks: `useBusinessType()` from `@/lib/business-type-context`, `useCurrency()` from `@/lib/currency-context`, `useRouter`/`useSearchParams` from `next/navigation`.

---

## Codebase context

### Key existing patterns
- `"use client"` page with inline sub-components: established pattern (channels/page.tsx is 789 lines doing the same)
- `useBusinessType()` returns `{ flags, loading }` where `flags.business_type` is `"online" | "retail" | "hybrid"`
- `useCurrency()` returns `CurrencyConfig { code: string, exponent: number, symbolOverride: string | null }`
- `RequiresBusinessType` from `@/components/dashboard/RequiresBusinessType` — wrap the page export
- Channels page already imports `useSearchParams` — the `?created` banner can read that param

### ShopOut API shape
`GET /api/ims/v1/admin/shops` → `Array<{ id: string, tenant_id: string, name: string, default_tax_rate_bps: number, auto_resolve_shortage_cents_override: number | null, auto_resolve_overage_cents_override: number | null, timezone: string | null }>`

Note: `kind` field (physical/virtual) is NOT in the API response. For online tenants, all shops are used automatically (the virtual shop is the only one). For hybrid tenants, all shops are shown for selection.

### Inventory pool create
`POST /api/ims/v1/admin/inventory-pools` body: `{ name: string, shop_ids: string[] }` → `{ id: string, name: string, shop_ids: string[] }`

### Channel create
`POST /api/ims/v1/admin/channels` body: `{ type: "headless", name: string, inventory_pool_id: string, currency_code: string }` → `{ id: string, ... }`

### Payment setup
`POST /api/ims/v1/admin/channels/{id}/payment/setup-stripe` body: `{ stripe_secret_key: string, stripe_publishable_key: string, checkout_success_url: string }`
`POST /api/ims/v1/admin/channels/{id}/payment/setup-razorpay` body: `{ razorpay_key_id: string, razorpay_key_secret: string, checkout_success_url: string }`

### Entry points to update
- `apps/admin-web/src/app/(main)/overview/page.tsx` line with `key: "first_channel"` → `href: "/channels?new=1"` → change to `href: "/channels/setup"`
- `apps/admin-web/src/components/dashboard/AppShell.tsx` `NEW_ENTRY_ITEMS` → `href: "/channels?new=1"` → `/channels/setup`
- `apps/admin-web/src/app/(main)/channels/page.tsx` empty state `actionHref="?new=1"` → `/channels/setup`

---

## File map

| File | Status |
|---|---|
| `apps/admin-web/src/app/(main)/channels/setup/page.tsx` | NEW |
| `apps/admin-web/src/app/(main)/overview/page.tsx` | MODIFY (1 line) |
| `apps/admin-web/src/components/dashboard/AppShell.tsx` | MODIFY (1 line) |
| `apps/admin-web/src/app/(main)/channels/page.tsx` | MODIFY (empty state href + created banner) |

---

## Task 1: Create the wizard page

**Files:**
- Create: `apps/admin-web/src/app/(main)/channels/setup/page.tsx`

- [ ] **Step 1: Create the file**

Create `apps/admin-web/src/app/(main)/channels/setup/page.tsx` with this complete content:

```tsx
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

      {/* Provider picker */}
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

      {/* Stripe form */}
      {choice === "stripe" && (
        <div className="space-y-4">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-on-surface">Secret key</span>
            <input
              type="password"
              value={stripeSecretKey}
              onChange={(e) => onStripeChange("secret", e.target.value)}
              placeholder="sk_live_..."
              className="w-full rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-on-surface">Publishable key</span>
            <input
              type="text"
              value={stripePublishableKey}
              onChange={(e) => onStripeChange("publishable", e.target.value)}
              placeholder="pk_live_..."
              className="w-full rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-on-surface">Checkout success URL</span>
            <input
              type="url"
              value={stripeSuccessUrl}
              onChange={(e) => onStripeChange("success_url", e.target.value)}
              placeholder="https://yourstore.com/order/success"
              className="w-full rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </label>
        </div>
      )}

      {/* Razorpay form */}
      {choice === "razorpay" && (
        <div className="space-y-4">
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-on-surface">Key ID</span>
            <input
              type="text"
              value={razorpayKeyId}
              onChange={(e) => onRazorpayChange("key_id", e.target.value)}
              placeholder="rzp_live_..."
              className="w-full rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-on-surface">Key secret</span>
            <input
              type="password"
              value={razorpayKeySecret}
              onChange={(e) => onRazorpayChange("key_secret", e.target.value)}
              className="w-full rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium text-on-surface">Checkout success URL</span>
            <input
              type="url"
              value={razorpaySuccessUrl}
              onChange={(e) => onRazorpayChange("success_url", e.target.value)}
              placeholder="https://yourstore.com/order/success"
              className="w-full rounded-lg border border-outline-variant/30 bg-surface-container-low px-3 py-2 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary"
            />
          </label>
        </div>
      )}

      {/* Skip note */}
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

  // Phase
  const [phase, setPhase] = useState<Phase>("type-picker");
  const [step, setStep] = useState(0);

  // Step data
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

  // Submission
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch shops when entering wizard
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

  // Step indices
  const shopsStepIndex = isHybrid ? 0 : -1;
  const channelStepIndex = isHybrid ? 1 : 0;
  const paymentStepIndex = isHybrid ? 2 : 1;

  async function handleComplete() {
    setError(null);
    setSubmitting(true);
    try {
      // 1. Create inventory pool
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

      // 2. Create channel
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

      // 3. Payment (optional)
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
          // Channel exists — navigate with error flag so channels page can show a message
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
        <ShopsStep
          shops={shops}
          loading={shopsLoading}
          selectedIds={selectedShopIds}
          onChange={setSelectedShopIds}
        />
      )}
      {step === channelStepIndex && (
        <ChannelDetailsStep
          name={channelName}
          onNameChange={setChannelName}
          currencyCode={currency.code}
        />
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

      {/* Navigation */}
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
```

- [ ] **Step 2: Verify build**

```bash
docker compose up --build -d admin-web 2>&1 | grep -E "✓ Compiled|error TS|Error:|failed" | tail -10
```

Expected: `✓ Compiled successfully`. If TypeScript flags `onStripeChange` type errors (union string literal), the field param types are `"secret" | "publishable" | "success_url"` and `"key_id" | "key_secret" | "success_url"` — they're already typed correctly in the component signatures.

If TypeScript fails on `steps.length - 1` used in the conditional, ensure `steps` is typed as `string[]` or a tuple.

- [ ] **Step 3: Commit**

```bash
git add 'apps/admin-web/src/app/(main)/channels/setup/page.tsx'
git commit -m "feat(admin-web): add channel setup wizard (type picker + 2-3 step headless wizard)"
```

---

## Task 2: Wire 3 entry points + channels success banner

**Files:**
- Modify: `apps/admin-web/src/app/(main)/overview/page.tsx`
- Modify: `apps/admin-web/src/components/dashboard/AppShell.tsx`
- Modify: `apps/admin-web/src/app/(main)/channels/page.tsx`

- [ ] **Step 1: Update first_channel href in overview/page.tsx**

In `apps/admin-web/src/app/(main)/overview/page.tsx`, find the `allSetupItems` array and the item with `key: "first_channel"`. Change its `href` field:

```tsx
// Before:
    href: "/channels?new=1",
// After:
    href: "/channels/setup",
```

- [ ] **Step 2: Update New Entry "Create Channel" in AppShell.tsx**

In `apps/admin-web/src/components/dashboard/AppShell.tsx`, find `NEW_ENTRY_ITEMS`. Change the Channel item:

```tsx
// Before:
  { href: "/channels?new=1",     label: "Create Channel",  icon: "storefront",  allowedTypes: ["online", "hybrid"] },
// After:
  { href: "/channels/setup",     label: "Create Channel",  icon: "storefront",  allowedTypes: ["online", "hybrid"] },
```

- [ ] **Step 3: Update channels page empty state + add success banner**

In `apps/admin-web/src/app/(main)/channels/page.tsx`:

**a) Update empty state actionHref** — find the `<EmptyState` component near line 225 and change:

```tsx
// Before:
            actionHref="?new=1"
// After:
            actionHref="/channels/setup"
```

**b) Add success banner inside `ChannelsTab`** — find the `ChannelsTab` component. It already imports `useSearchParams` and reads `newParams`. After the existing `useEffect` that checks `newParams.get("new") === "1"`, add these two state declarations and a new `useEffect`:

```tsx
  const [createdBanner, setCreatedBanner] = useState<string | null>(null);
  const [paymentErrorBanner, setPaymentErrorBanner] = useState(false);

  useEffect(() => {
    const created = newParams.get("created");
    const paymentErr = newParams.get("payment_error");
    if (created) {
      setCreatedBanner(created);
      if (paymentErr === "1") setPaymentErrorBanner(true);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
```

Then, inside the `return (...)` of `ChannelsTab`, just before the `<Panel>` component, add the conditional banners:

```tsx
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
```

- [ ] **Step 4: Verify build**

```bash
docker compose up --build -d admin-web 2>&1 | grep -E "✓ Compiled|error TS|Error:|failed" | tail -5
```

Expected: `✓ Compiled successfully`.

- [ ] **Step 5: Smoke test in browser**

1. Log in. On the dashboard, the setup checklist's "Set up a sales channel → Start" button should now navigate to `/channels/setup`.
2. Open the New Entry menu — "Create Channel" should navigate to `/channels/setup` (not open `?new=1` form).
3. Go to the Channels page (if empty), the CTA should navigate to `/channels/setup`.
4. On the wizard page:
   - Type picker shows 3 cards. Click Shopify/WooCommerce → redirects to `/integrations`.
   - Click Headless → wizard appears with step indicator.
   - For retail business type → `RequiresBusinessType` guard shows the "switch business type" card (wizard is online/hybrid only).

- [ ] **Step 6: Commit**

```bash
git add 'apps/admin-web/src/app/(main)/overview/page.tsx' \
        'apps/admin-web/src/components/dashboard/AppShell.tsx' \
        'apps/admin-web/src/app/(main)/channels/page.tsx'
git commit -m "feat(admin-web): wire channel setup wizard to all entry points + success/error banners"
```

---

## Task 3: Full rebuild + push

- [ ] **Step 1: Run backend tests (no backend changes, but verify no regression)**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest /app/tests/ -q --tb=no 2>&1 | tail -4
docker compose exec api rm -rf /app/tests
```

Expected: 529+ passing, same pre-existing failure.

- [ ] **Step 2: Full stack rebuild**

```bash
docker compose down && docker compose up --build -d 2>&1 | grep -E "✓ Compiled|error TS|Error:|failed" | tail -5
sleep 12
docker compose ps --format "table {{.Name}}\t{{.Status}}"
```

Expected: all containers Up, admin-web `✓ Compiled successfully`.

- [ ] **Step 3: End-to-end wizard smoke test**

In a browser on a tenant with `online` or `hybrid` business type:

1. Navigate to `/channels/setup`
2. Type picker appears → click "Headless storefront" → wizard enters with step indicator
3. **Online tenant:** step indicator shows "Channel details → Payment" (2 steps)
4. **Hybrid tenant:** step indicator shows "Pick shops → Channel details → Payment" (3 steps)
5. Fill in channel name, click Continue → payment step
6. Select "Skip for now" → click "Complete setup →"
7. Should navigate to `/channels?created={id}` → channels page shows the green success banner
8. New channel appears in the channels list

- [ ] **Step 4: Push**

```bash
git push origin main
```

---

## Self-review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| Type picker: 3 cards (Headless / Shopify / WooCommerce) | Task 1 |
| Shopify / WooCommerce → `router.push('/integrations')` | Task 1 |
| Headless → enters wizard | Task 1 |
| Online: 2-step wizard (Channel details → Payment) | Task 1 |
| Hybrid: 3-step wizard (Pick shops → Channel details → Payment) | Task 1 |
| Step indicator with back-navigation to previous steps | Task 1 |
| ShopsStep: shop checkboxes, all pre-selected, no-shops fallback | Task 1 |
| ChannelDetailsStep: name input + read-only currency | Task 1 |
| PaymentStep: Stripe / Razorpay / Skip radio cards + conditional forms | Task 1 |
| API sequence: pool → channel → optional payment | Task 1 |
| Pool failure: inline error, retry | Task 1 |
| Channel failure: inline error, retry | Task 1 |
| Payment failure: navigate to `/channels?created={id}&payment_error=1` | Task 1 |
| Success: navigate to `/channels?created={id}` | Task 1 |
| `RequiresBusinessType types={["online","hybrid"]}` | Task 1 |
| Dashboard checklist href: `/channels/setup` | Task 2 |
| New Entry menu href: `/channels/setup` | Task 2 |
| Channels empty state href: `/channels/setup` | Task 2 |
| Success banner on channels page (`?created`) | Task 2 |
| Payment error banner on channels page (`?payment_error=1`) | Task 2 |

**Placeholder scan:** None.

**Type consistency:**
- `PaymentChoice = "stripe" | "razorpay" | "skip"` used consistently in wizard state and `PaymentStep` props ✅
- `onStripeChange(field: "secret" | "publishable" | "success_url", value: string)` — field union matches the three `if` branches in the handler ✅
- `onRazorpayChange(field: "key_id" | "key_secret" | "success_url", value: string)` — same ✅
- `shopsStepIndex`, `channelStepIndex`, `paymentStepIndex` computed from `isHybrid` consistently ✅
- `step < steps.length - 1` vs `step === paymentStepIndex` — both point to the same condition (last step) ✅
