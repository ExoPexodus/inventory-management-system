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

type TransferSettings = {
  transfer_auto_approve_under_cents: number | null;
  transfer_allow_self_approval: boolean;
};

export default function SettingsTransfersPage() {
  const currency = useCurrency();

  const [settings, setSettings] = useState<TransferSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Local editable state — display as whole currency units (e.g. "50" = 5000 cents if exponent=2)
  const [autoApproveInput, setAutoApproveInput] = useState("");
  const [allowSelfApproval, setAllowSelfApproval] = useState(false);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const res = await fetch("/api/ims/v1/admin/tenant-settings/transfers");
        if (res.ok) {
          const data = (await res.json()) as TransferSettings;
          setSettings(data);
          setAllowSelfApproval(data.transfer_allow_self_approval);
          if (data.transfer_auto_approve_under_cents != null) {
            const divisor = Math.pow(10, currency.exponent);
            setAutoApproveInput(String(data.transfer_auto_approve_under_cents / divisor));
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
      const parsed = autoApproveInput.trim() ? parseFloat(autoApproveInput) : null;
      const cents = parsed != null && !isNaN(parsed) ? Math.round(parsed * divisor) : null;

      const payload: Partial<TransferSettings> = {
        transfer_allow_self_approval: allowSelfApproval,
      };
      // Send the field explicitly (even as null) to clear the threshold
      if (autoApproveInput.trim() === "") {
        (payload as Record<string, unknown>).transfer_auto_approve_under_cents = null;
      } else if (cents != null) {
        payload.transfer_auto_approve_under_cents = cents;
      }

      const res = await fetch("/api/ims/v1/admin/tenant-settings/transfers", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await res.text());
      const updated = (await res.json()) as TransferSettings;
      setSettings(updated);
      setMessage("Transfer settings saved.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-8">
      <Breadcrumbs items={[{ label: "Settings", href: "/settings" }, { label: "Transfers" }]} />
      <PageHeader
        kicker="Settings"
        title="Transfer Orders"
        subtitle="Configure inter-shop transfer approval behaviour."
      />

      <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
        <h3 className="font-headline text-lg font-bold text-primary">Approval settings</h3>
        <p className="mt-1 text-sm text-on-surface-variant">
          Control when transfers are auto-approved and who can approve them.
        </p>

        {loading ? (
          <p className="mt-4 text-sm text-on-surface-variant">Loading settings…</p>
        ) : (
          <div className="mt-5 space-y-6">
            {/* Auto-approve threshold */}
            <div>
              <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">
                Auto-approve transfers under ({currency.code})
              </label>
              <TextInput
                type="number"
                min="0"
                step="0.01"
                value={autoApproveInput}
                onChange={(e) => setAutoApproveInput(e.target.value)}
                placeholder={`e.g. 500 (= ${formatMoney(500 * Math.pow(10, currency.exponent), currency)})`}
              />
              <p className="mt-1 text-xs text-on-surface-variant">
                When the total line cost of a submitted transfer is below this amount, it is automatically
                approved. Leave blank to require manual approval for all transfers.
              </p>
              {settings?.transfer_auto_approve_under_cents != null && (
                <p className="mt-1 text-xs text-on-surface-variant">
                  Current: auto-approve under{" "}
                  <strong className="text-on-surface">
                    {formatMoney(settings.transfer_auto_approve_under_cents, currency)}
                  </strong>
                </p>
              )}
            </div>

            {/* Self-approval toggle */}
            <div className="flex items-start gap-4">
              <Toggle
                checked={allowSelfApproval}
                onChange={(v) => setAllowSelfApproval(v)}
              />
              <div>
                <p className="text-sm font-semibold text-on-surface">Allow creator to approve their own transfer</p>
                <p className="mt-0.5 text-xs text-on-surface-variant">
                  When off, the person who created a transfer cannot also approve it (four-eyes principle).
                </p>
              </div>
            </div>

            <PrimaryButton type="button" disabled={saving} onClick={() => void save()}>
              {saving ? "Saving…" : "Save transfer settings"}
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
