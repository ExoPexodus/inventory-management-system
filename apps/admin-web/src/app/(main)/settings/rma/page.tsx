"use client";

import { useEffect, useState } from "react";
import {
  Breadcrumbs,
  PageHeader,
  PrimaryButton,
  TextInput,
  Toggle,
} from "@/components/ui/primitives";
import { formatMoney } from "@/lib/format";
import { useCurrency } from "@/lib/currency-context";

type RMASettings = {
  default_restock_on_refund: boolean;
  refund_window_days: number;
  rma_auto_approve_under_cents: number | null;
};

export default function SettingsRMAPage() {
  const currency = useCurrency();
  const [settings, setSettings] = useState<RMASettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [restockDefault, setRestockDefault] = useState(true);
  const [windowDays, setWindowDays] = useState("30");
  const [autoApproveInput, setAutoApproveInput] = useState("");

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const res = await fetch("/api/ims/v1/admin/tenant-settings/rma");
        if (res.ok) {
          const data = (await res.json()) as RMASettings;
          setSettings(data);
          setRestockDefault(data.default_restock_on_refund);
          setWindowDays(String(data.refund_window_days));
          if (data.rma_auto_approve_under_cents != null) {
            const divisor = Math.pow(10, currency.exponent);
            setAutoApproveInput(String(data.rma_auto_approve_under_cents / divisor));
          } else {
            setAutoApproveInput("");
          }
        }
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, [currency.exponent]);

  async function save() {
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      const divisor = Math.pow(10, currency.exponent);
      const parsedCents = autoApproveInput.trim()
        ? Math.round(parseFloat(autoApproveInput) * divisor)
        : null;

      const payload: Partial<RMASettings> = {
        default_restock_on_refund: restockDefault,
        refund_window_days: parseInt(windowDays) || 30,
      };
      if (autoApproveInput.trim() === "") {
        (payload as Record<string, unknown>).rma_auto_approve_under_cents = null;
      } else if (parsedCents != null && !isNaN(parsedCents)) {
        payload.rma_auto_approve_under_cents = parsedCents;
      }

      const res = await fetch("/api/ims/v1/admin/tenant-settings/rma", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await res.text());
      const updated = (await res.json()) as RMASettings;
      setSettings(updated);
      setMessage("RMA settings saved.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-8">
      <Breadcrumbs items={[{ label: "Settings", href: "/settings" }, { label: "Refund Requests" }]} />
      <PageHeader
        kicker="Settings"
        title="Refund Requests"
        subtitle="Configure RMA behaviour, refund windows, and auto-approval thresholds."
      />

      <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
        <h3 className="font-headline text-lg font-bold text-primary">Refund settings</h3>
        <p className="mt-1 text-sm text-on-surface-variant">
          Control how refunds and returns are handled across your store.
        </p>

        {loading ? (
          <p className="mt-4 text-sm text-on-surface-variant">Loading settings…</p>
        ) : (
          <div className="mt-5 space-y-6">
            {/* Default restock toggle */}
            <div className="flex items-start gap-4">
              <Toggle
                checked={restockDefault}
                onChange={(v) => setRestockDefault(v)}
              />
              <div>
                <p className="text-sm font-semibold text-on-surface">Restock items on refund by default</p>
                <p className="mt-0.5 text-xs text-on-surface-variant">
                  When enabled, returned items are restocked to inventory by default. Merchants can override per-approval.
                </p>
              </div>
            </div>

            {/* Refund window */}
            <div>
              <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">
                Refund window (days)
              </label>
              <TextInput
                type="number"
                min="0"
                max="365"
                value={windowDays}
                onChange={(e) => setWindowDays(e.target.value)}
                placeholder="30"
              />
              <p className="mt-1 text-xs text-on-surface-variant">
                Customers can submit a refund request within this many days of delivery (or order placement if not yet delivered). Default: 30.
              </p>
              {settings?.refund_window_days != null && (
                <p className="mt-1 text-xs text-on-surface-variant">
                  Current: <strong className="text-on-surface">{settings.refund_window_days} days</strong>
                </p>
              )}
            </div>

            {/* Auto-approve threshold */}
            <div>
              <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">
                Auto-approve refunds under ({currency.code})
              </label>
              <TextInput
                type="number"
                min="0"
                step="0.01"
                value={autoApproveInput}
                onChange={(e) => setAutoApproveInput(e.target.value)}
                placeholder={`e.g. 50 (= ${formatMoney(50 * Math.pow(10, currency.exponent), currency)})`}
              />
              <p className="mt-1 text-xs text-on-surface-variant">
                Refund requests with a total below this amount are automatically approved. Leave blank to require manual approval for all requests.
              </p>
              {settings?.rma_auto_approve_under_cents != null && (
                <p className="mt-1 text-xs text-on-surface-variant">
                  Current: auto-approve under{" "}
                  <strong className="text-on-surface">
                    {formatMoney(settings.rma_auto_approve_under_cents, currency)}
                  </strong>
                </p>
              )}
            </div>

            <PrimaryButton type="button" disabled={saving} onClick={() => void save()}>
              {saving ? "Saving…" : "Save RMA settings"}
            </PrimaryButton>

            {message && <p className="text-sm font-semibold text-primary">{message}</p>}
            {error && (
              <p className="rounded-lg border border-error/20 bg-error-container/20 px-3 py-2 text-sm text-on-error-container">
                {error}
              </p>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
