"use client";

import { useEffect, useState } from "react";
import { Breadcrumbs, PageHeader, PrimaryButton, TextInput } from "@/components/ui/primitives";

export default function SettingsDevicesPage() {
  const [deviceSecurity, setDeviceSecurity] = useState<{ max_offline_minutes: number; employee_session_timeout_minutes: number } | null>(null);
  const [maxOfflineMinutes, setMaxOfflineMinutes] = useState("60");
  const [sessionTimeoutMinutes, setSessionTimeoutMinutes] = useState("30");
  const [deviceSecurityLoading, setDeviceSecurityLoading] = useState(true);
  const [deviceSecuritySaving, setDeviceSecuritySaving] = useState(false);
  const [deviceSecurityMessage, setDeviceSecurityMessage] = useState<string | null>(null);
  const [deviceSecurityError, setDeviceSecurityError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setDeviceSecurityLoading(true);
      try {
        const res = await fetch("/api/ims/v1/admin/tenant-settings/device-security");
        if (res.ok) {
          const cfg = (await res.json()) as { max_offline_minutes: number; employee_session_timeout_minutes: number };
          setDeviceSecurity(cfg);
          setMaxOfflineMinutes(String(cfg.max_offline_minutes));
          setSessionTimeoutMinutes(String(cfg.employee_session_timeout_minutes));
        }
      } finally {
        setDeviceSecurityLoading(false);
      }
    }
    void load();
  }, []);

  async function saveDeviceSecurity() {
    setDeviceSecuritySaving(true);
    setDeviceSecurityMessage(null);
    setDeviceSecurityError(null);
    try {
      const payload: Record<string, number> = {};
      const offline = parseInt(maxOfflineMinutes, 10);
      const timeout = parseInt(sessionTimeoutMinutes, 10);
      if (!isNaN(offline) && offline >= 1) payload.max_offline_minutes = offline;
      if (!isNaN(timeout) && timeout >= 1) payload.employee_session_timeout_minutes = timeout;
      const res = await fetch("/api/ims/v1/admin/tenant-settings/device-security", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await res.text());
      const updated = (await res.json()) as { max_offline_minutes: number; employee_session_timeout_minutes: number };
      setDeviceSecurity(updated);
      setDeviceSecurityMessage("Device security settings saved.");
    } catch (e) {
      setDeviceSecurityError(e instanceof Error ? e.message : "Failed to save device security settings");
    } finally {
      setDeviceSecuritySaving(false);
    }
  }

  return (
    <div className="space-y-8">
      <Breadcrumbs items={[{ label: "Settings", href: "/settings" }, { label: "Devices" }]} />
      <PageHeader kicker="Settings" title="Devices" subtitle="POS device security and employee session timeouts." />

      <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
        <h3 className="font-headline text-lg font-bold text-primary">Device security</h3>
        <p className="mt-1 text-sm text-on-surface-variant">
          Controls how long cashier devices can operate offline and how quickly employee sessions expire after inactivity.
        </p>
        {deviceSecurityLoading ? (
          <p className="mt-4 text-sm text-on-surface-variant">Loading device security settings…</p>
        ) : (
          <div className="mt-5 space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">Max offline minutes</label>
                <TextInput type="number" min="1" max="1440" value={maxOfflineMinutes} onChange={(e) => setMaxOfflineMinutes(e.target.value)} placeholder="60" />
                <p className="mt-1 text-xs text-on-surface-variant">Cashier app blocks usage after this many minutes without a server sync. Default: 60.</p>
              </div>
              <div>
                <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">Employee session timeout (minutes)</label>
                <TextInput type="number" min="1" max="1440" value={sessionTimeoutMinutes} onChange={(e) => setSessionTimeoutMinutes(e.target.value)} placeholder="30" />
                <p className="mt-1 text-xs text-on-surface-variant">Employee must re-enter PIN/password after this many minutes of inactivity. Default: 30.</p>
              </div>
            </div>
            {deviceSecurity && (
              <div className="rounded-lg border border-outline-variant/10 bg-surface-container-low p-3 text-sm text-on-surface-variant">
                Current: offline limit <strong className="text-on-surface">{deviceSecurity.max_offline_minutes} min</strong>
                {" · "}session timeout <strong className="text-on-surface">{deviceSecurity.employee_session_timeout_minutes} min</strong>
              </div>
            )}
            <PrimaryButton type="button" disabled={deviceSecuritySaving} onClick={() => void saveDeviceSecurity()}>
              {deviceSecuritySaving ? "Saving…" : "Save device security"}
            </PrimaryButton>
            {deviceSecurityMessage && <p className="text-sm font-semibold text-primary">{deviceSecurityMessage}</p>}
            {deviceSecurityError && (
              <p className="rounded-lg border border-error/20 bg-error-container/20 px-3 py-2 text-sm text-on-error-container">{deviceSecurityError}</p>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
