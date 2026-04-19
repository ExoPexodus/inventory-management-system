"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter, usePathname } from "next/navigation";
import {
  ErrorState,
  PageHeader,
  Panel,
  PrimaryButton,
  SecondaryButton,
  TextInput,
  Toggle,
} from "@/components/ui/primitives";

type ShopDetail = {
  id: string;
  tenant_id: string;
  name: string;
  default_tax_rate_bps: number;
  auto_resolve_shortage_cents_override: number | null;
  auto_resolve_overage_cents_override: number | null;
};

type TenantReconSettings = {
  auto_resolve_shortage_cents: number;
  auto_resolve_overage_cents: number;
};

const ROOT_ROUTES = new Set([
  "overview",
  "inventory",
  "staff",
  "team",
  "orders",
  "analytics",
  "suppliers",
  "products",
  "purchase-orders",
  "settings",
]);

export default function EditShopPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const pathname = usePathname();
  const segments = pathname.split("/").filter(Boolean);
  const tenantPrefix =
    segments.length > 0 && !ROOT_ROUTES.has(segments[0]) ? `/${segments[0]}` : "";

  const [shop, setShop] = useState<ShopDetail | null>(null);
  const [tenantRecon, setTenantRecon] = useState<TenantReconSettings | null>(null);
  const [loadErr, setLoadErr] = useState<string | null>(null);

  // Form state
  const [shortageOverrideOn, setShortageOverrideOn] = useState(false);
  const [shortageValue, setShortageValue] = useState("0");
  const [overageOverrideOn, setOverageOverrideOn] = useState(false);
  const [overageValue, setOverageValue] = useState("0");
  const [saving, setSaving] = useState(false);
  const [saveErr, setSaveErr] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const [shopResp, reconResp] = await Promise.all([
          fetch(`/api/ims/v1/admin/shops/${params.id}`),
          fetch("/api/ims/v1/admin/tenant-settings/reconciliation"),
        ]);
        if (!shopResp.ok) {
          setLoadErr(`Failed to load shop (${shopResp.status})`);
          return;
        }
        if (!reconResp.ok) {
          setLoadErr(`Failed to load tenant settings (${reconResp.status})`);
          return;
        }
        const shopData = (await shopResp.json()) as ShopDetail;
        const reconData = (await reconResp.json()) as TenantReconSettings;
        setShop(shopData);
        setTenantRecon(reconData);
        setShortageOverrideOn(shopData.auto_resolve_shortage_cents_override !== null);
        setShortageValue(String(shopData.auto_resolve_shortage_cents_override ?? 0));
        setOverageOverrideOn(shopData.auto_resolve_overage_cents_override !== null);
        setOverageValue(String(shopData.auto_resolve_overage_cents_override ?? 0));
      } catch {
        setLoadErr("Network error loading shop.");
      }
    })();
  }, [params.id]);

  async function save() {
    setSaving(true);
    setSaveErr(null);

    const body: Record<string, number | null> = {};
    if (shortageOverrideOn) {
      const v = parseInt(shortageValue, 10);
      if (Number.isNaN(v) || v < 0) {
        setSaveErr("Shortage override must be a non-negative integer.");
        setSaving(false);
        return;
      }
      body.auto_resolve_shortage_cents_override = v;
    } else {
      body.auto_resolve_shortage_cents_override = null;
    }
    if (overageOverrideOn) {
      const v = parseInt(overageValue, 10);
      if (Number.isNaN(v) || v < 0) {
        setSaveErr("Overage override must be a non-negative integer.");
        setSaving(false);
        return;
      }
      body.auto_resolve_overage_cents_override = v;
    } else {
      body.auto_resolve_overage_cents_override = null;
    }

    try {
      const resp = await fetch(`/api/ims/v1/admin/shops/${params.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });

      if (!resp.ok) {
        setSaveErr(`Save failed (${resp.status}).`);
        setSaving(false);
        return;
      }
      router.push(`${tenantPrefix}/shops`);
    } catch {
      setSaveErr("Network error. Please try again.");
      setSaving(false);
    }
  }

  if (loadErr) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-8">
        <ErrorState detail={loadErr} />
      </div>
    );
  }

  if (!shop || !tenantRecon) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-8 text-sm text-on-surface-variant">
        Loading…
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-8">
      <PageHeader title={`Edit shop: ${shop.name}`} />

      <Panel
        title="Reconciliation overrides"
        subtitle="Optional per-shop overrides for the tenant auto-resolve thresholds."
      >
        <div className="space-y-6">
          <div>
            <div className="flex items-center gap-3">
              <Toggle
                checked={shortageOverrideOn}
                onChange={(v: boolean) => setShortageOverrideOn(v)}
              />
              <span className="text-sm text-on-surface-variant">
                {shortageOverrideOn
                  ? "Override shortage threshold for this shop"
                  : `Use tenant default (${tenantRecon.auto_resolve_shortage_cents} cents)`}
              </span>
            </div>
            {shortageOverrideOn && (
              <div className="mt-2">
                <TextInput
                  type="number"
                  min={0}
                  value={shortageValue}
                  onChange={(e) => setShortageValue(e.target.value)}
                />
                <span className="mt-1 block text-xs text-on-surface-variant">
                  Shortage threshold in cents (0 disables auto-resolve for this shop&apos;s shortages).
                </span>
              </div>
            )}
          </div>

          <div>
            <div className="flex items-center gap-3">
              <Toggle
                checked={overageOverrideOn}
                onChange={(v: boolean) => setOverageOverrideOn(v)}
              />
              <span className="text-sm text-on-surface-variant">
                {overageOverrideOn
                  ? "Override overage threshold for this shop"
                  : `Use tenant default (${tenantRecon.auto_resolve_overage_cents} cents)`}
              </span>
            </div>
            {overageOverrideOn && (
              <div className="mt-2">
                <TextInput
                  type="number"
                  min={0}
                  value={overageValue}
                  onChange={(e) => setOverageValue(e.target.value)}
                />
                <span className="mt-1 block text-xs text-on-surface-variant">
                  Overage threshold in cents (0 disables auto-resolve for this shop&apos;s overages).
                </span>
              </div>
            )}
          </div>
        </div>
      </Panel>

      {saveErr && <p className="text-sm text-red-600">{saveErr}</p>}

      <div className="flex gap-3">
        <PrimaryButton onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </PrimaryButton>
        <SecondaryButton onClick={() => router.push(`${tenantPrefix}/shops`)}>
          Cancel
        </SecondaryButton>
      </div>
    </div>
  );
}
