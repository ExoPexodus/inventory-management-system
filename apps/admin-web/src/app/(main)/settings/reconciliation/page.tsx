"use client";

import { useEffect, useState } from "react";
import { Breadcrumbs, PageHeader, PrimaryButton, TextInput } from "@/components/ui/primitives";

export default function SettingsReconciliationPage() {
  const [reconShortage, setReconShortage] = useState<string>("0");
  const [reconOverage, setReconOverage] = useState<string>("0");
  const [reconLoading, setReconLoading] = useState(true);
  const [reconSaving, setReconSaving] = useState(false);
  const [reconMessage, setReconMessage] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/ims/v1/admin/tenant-settings/reconciliation")
      .then((r) => { if (!r.ok) throw new Error("load failed"); return r.json(); })
      .then((data: { auto_resolve_shortage_cents: number; auto_resolve_overage_cents: number }) => {
        setReconShortage(String(data.auto_resolve_shortage_cents));
        setReconOverage(String(data.auto_resolve_overage_cents));
      })
      .catch(() => setReconMessage("Failed to load reconciliation settings"))
      .finally(() => setReconLoading(false));
  }, []);

  async function saveReconciliation() {
    setReconSaving(true);
    setReconMessage(null);
    const shortage = parseInt(reconShortage, 10);
    const overage = parseInt(reconOverage, 10);
    if (Number.isNaN(shortage) || shortage < 0 || Number.isNaN(overage) || overage < 0) {
      setReconMessage("Thresholds must be non-negative integers (in cents).");
      setReconSaving(false);
      return;
    }
    const resp = await fetch("/api/ims/v1/admin/tenant-settings/reconciliation", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ auto_resolve_shortage_cents: shortage, auto_resolve_overage_cents: overage }),
    });
    if (!resp.ok) {
      setReconMessage("Save failed.");
    } else {
      const data = (await resp.json()) as { auto_resolve_shortage_cents: number; auto_resolve_overage_cents: number };
      setReconShortage(String(data.auto_resolve_shortage_cents));
      setReconOverage(String(data.auto_resolve_overage_cents));
      setReconMessage("Saved.");
    }
    setReconSaving(false);
  }

  return (
    <div className="space-y-8">
      <Breadcrumbs items={[{ label: "Settings", href: "/settings" }, { label: "Reconciliation" }]} />
      <PageHeader kicker="Settings" title="Reconciliation" subtitle="Auto-resolve thresholds for shift close variances." />

      <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
        <h3 className="font-headline text-lg font-bold text-primary">Reconciliation auto-resolve</h3>
        <p className="mt-1 text-sm text-on-surface-variant">
          Variances within these thresholds are automatically marked resolved at shift close. Set to 0 to disable auto-resolve. Shops can override these values individually.
        </p>
        {reconLoading ? (
          <p className="mt-4 text-sm text-on-surface-variant">Loading reconciliation settings…</p>
        ) : (
          <div className="mt-5 space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">Shortage limit (cents)</label>
                <TextInput type="number" min="0" value={reconShortage} onChange={(e) => setReconShortage(e.target.value)} placeholder="0" />
                <p className="mt-1 text-xs text-on-surface-variant">Cashier counted less than expected. 0 disables.</p>
              </div>
              <div>
                <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">Overage limit (cents)</label>
                <TextInput type="number" min="0" value={reconOverage} onChange={(e) => setReconOverage(e.target.value)} placeholder="0" />
                <p className="mt-1 text-xs text-on-surface-variant">Cashier counted more than expected. 0 disables.</p>
              </div>
            </div>
            <PrimaryButton type="button" disabled={reconSaving} onClick={() => void saveReconciliation()}>
              {reconSaving ? "Saving…" : "Save reconciliation"}
            </PrimaryButton>
            {reconMessage && <p className="text-sm font-semibold text-primary">{reconMessage}</p>}
          </div>
        )}
      </section>
    </div>
  );
}
