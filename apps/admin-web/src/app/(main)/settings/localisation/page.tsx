"use client";

import { useEffect, useState } from "react";
import { Breadcrumbs, PageHeader, PrimaryButton, SelectInput } from "@/components/ui/primitives";
import { TIMEZONE_OPTIONS, MONTH_OPTIONS } from "@/lib/timezones";

export default function SettingsLocalisationPage() {
  const [localisationTimezone, setLocalisationTimezone] = useState("");
  const [localisationFyMonth, setLocalisationFyMonth] = useState("");
  const [localisationLoading, setLocalisationLoading] = useState(true);
  const [localisationMessage, setLocalisationMessage] = useState<string | null>(null);
  const [localisationError, setLocalisationError] = useState<string | null>(null);
  const [localisationSaving, setLocalisationSaving] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const r = await fetch("/api/ims/v1/admin/tenant-settings/localisation");
        if (!r.ok) { setLocalisationLoading(false); return; }
        const data = await r.json() as { timezone: string | null; financial_year_start_month: number | null };
        setLocalisationTimezone(data.timezone ?? "");
        setLocalisationFyMonth(data.financial_year_start_month ? String(data.financial_year_start_month) : "");
        setLocalisationLoading(false);
      } catch {
        setLocalisationLoading(false);
      }
    })();
  }, []);

  async function saveLocalisation() {
    setLocalisationMessage(null);
    setLocalisationError(null);
    setLocalisationSaving(true);
    try {
      const body: Record<string, string | number | null> = {
        timezone: localisationTimezone || null,
        financial_year_start_month: localisationFyMonth ? parseInt(localisationFyMonth, 10) : null,
      };
      const r = await fetch("/api/ims/v1/admin/tenant-settings/localisation", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (r.ok) {
        setLocalisationMessage("Localisation settings saved.");
      } else {
        const b = await r.json().catch(() => ({})) as { detail?: string };
        setLocalisationError(b.detail ?? `Save failed (${r.status})`);
      }
    } catch {
      setLocalisationError("Network error. Please try again.");
    } finally {
      setLocalisationSaving(false);
    }
  }

  return (
    <div className="space-y-8">
      <Breadcrumbs items={[{ label: "Settings", href: "/settings" }, { label: "Localisation" }]} />
      <PageHeader kicker="Settings" title="Localisation" subtitle="Set your timezone and financial year start month." />

      <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm space-y-4">
        <h3 className="font-headline text-lg font-bold text-primary">Localisation</h3>
        {localisationLoading ? (
          <p className="text-sm text-on-surface-variant">Loading localisation settings…</p>
        ) : (
          <>
            <label className="block text-sm font-medium text-on-surface">
              Timezone
              <SelectInput className="mt-1" value={localisationTimezone} onChange={setLocalisationTimezone} placeholder="Select timezone…"
                options={[{ value: "", label: "— Use UTC (default) —" }, ...TIMEZONE_OPTIONS.map((t) => ({ value: t.value, label: t.label }))]} />
            </label>
            <label className="block text-sm font-medium text-on-surface">
              Financial year start month
              <SelectInput className="mt-1" value={localisationFyMonth} onChange={setLocalisationFyMonth} placeholder="Select month…"
                options={[{ value: "", label: "— January (default) —" }, ...MONTH_OPTIONS.map((m) => ({ value: String(m.value), label: m.label }))]} />
            </label>
            {localisationMessage && <p className="text-sm text-primary">{localisationMessage}</p>}
            {localisationError && <p className="text-sm text-error">{localisationError}</p>}
            <PrimaryButton type="button" disabled={localisationSaving} onClick={() => void saveLocalisation()}>
              {localisationSaving ? "Saving…" : "Save localisation"}
            </PrimaryButton>
          </>
        )}
      </section>
    </div>
  );
}
