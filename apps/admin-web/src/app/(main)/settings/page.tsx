"use client";

import { useState } from "react";
import { PrimaryButton, SecondaryButton, Toggle } from "@/components/ui/primitives";

export default function SettingsPage() {
  const [emailDigest, setEmailDigest] = useState(true);
  const [lowStockAlerts, setLowStockAlerts] = useState(true);
  const [pushNotify, setPushNotify] = useState(false);

  const [twoFactor, setTwoFactor] = useState(false);
  const [sessionNotify, setSessionNotify] = useState(true);
  const [apiKeyRotation, setApiKeyRotation] = useState(false);

  const [compactTables, setCompactTables] = useState(false);
  const [highContrast, setHighContrast] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);

  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    setSaved(false);
    try {
      await new Promise((r) => setTimeout(r, 400));
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Platform</p>
        <h2 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">Settings</h2>
        <p className="mt-2 font-light text-on-surface-variant">Tune notifications, security posture, and UI density.</p>
      </div>

      <div className="space-y-6">
        <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <h3 className="font-headline text-lg font-bold text-primary">Notifications</h3>
          <p className="mt-1 text-sm text-on-surface-variant">Choose how we reach you about inventory and orders.</p>
          <ul className="mt-6 divide-y divide-outline-variant/10">
            <li className="flex items-center justify-between gap-4 py-4 first:pt-0">
              <div>
                <p className="font-medium text-on-surface">Email digest</p>
                <p className="text-sm text-on-surface-variant">Daily summary of exceptions and low stock.</p>
              </div>
              <Toggle checked={emailDigest} onChange={setEmailDigest} />
            </li>
            <li className="flex items-center justify-between gap-4 py-4">
              <div>
                <p className="font-medium text-on-surface">Low-stock alerts</p>
                <p className="text-sm text-on-surface-variant">Immediate email when SKUs cross reorder points.</p>
              </div>
              <Toggle checked={lowStockAlerts} onChange={setLowStockAlerts} />
            </li>
            <li className="flex items-center justify-between gap-4 py-4 last:pb-0">
              <div>
                <p className="font-medium text-on-surface">Push (browser)</p>
                <p className="text-sm text-on-surface-variant">Requires permission; best for on-call managers.</p>
              </div>
              <Toggle checked={pushNotify} onChange={setPushNotify} />
            </li>
          </ul>
        </section>

        <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <h3 className="font-headline text-lg font-bold text-primary">Security</h3>
          <p className="mt-1 text-sm text-on-surface-variant">Harden access to the admin console and APIs.</p>
          <ul className="mt-6 divide-y divide-outline-variant/10">
            <li className="flex items-center justify-between gap-4 py-4 first:pt-0">
              <div>
                <p className="font-medium text-on-surface">Two-factor authentication</p>
                <p className="text-sm text-on-surface-variant">Require TOTP for all operator accounts.</p>
              </div>
              <Toggle checked={twoFactor} onChange={setTwoFactor} />
            </li>
            <li className="flex items-center justify-between gap-4 py-4">
              <div>
                <p className="font-medium text-on-surface">New session alerts</p>
                <p className="text-sm text-on-surface-variant">Email when a login occurs from a new device.</p>
              </div>
              <Toggle checked={sessionNotify} onChange={setSessionNotify} />
            </li>
            <li className="flex items-center justify-between gap-4 py-4 last:pb-0">
              <div>
                <p className="font-medium text-on-surface">API key rotation reminders</p>
                <p className="text-sm text-on-surface-variant">Nudge before long-lived keys expire.</p>
              </div>
              <Toggle checked={apiKeyRotation} onChange={setApiKeyRotation} />
            </li>
          </ul>
        </section>

        <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
          <h3 className="font-headline text-lg font-bold text-primary">Appearance</h3>
          <p className="mt-1 text-sm text-on-surface-variant">Adjust density and visual comfort.</p>
          <ul className="mt-6 divide-y divide-outline-variant/10">
            <li className="flex items-center justify-between gap-4 py-4 first:pt-0">
              <div>
                <p className="font-medium text-on-surface">Compact tables</p>
                <p className="text-sm text-on-surface-variant">Tighter row height for dense data review.</p>
              </div>
              <Toggle checked={compactTables} onChange={setCompactTables} />
            </li>
            <li className="flex items-center justify-between gap-4 py-4">
              <div>
                <p className="font-medium text-on-surface">High contrast</p>
                <p className="text-sm text-on-surface-variant">Stronger borders and focus rings.</p>
              </div>
              <Toggle checked={highContrast} onChange={setHighContrast} />
            </li>
            <li className="flex items-center justify-between gap-4 py-4 last:pb-0">
              <div>
                <p className="font-medium text-on-surface">Reduce motion</p>
                <p className="text-sm text-on-surface-variant">Minimize transitions and parallax.</p>
              </div>
              <Toggle checked={reducedMotion} onChange={setReducedMotion} />
            </li>
          </ul>
        </section>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <PrimaryButton type="button" disabled={saving} onClick={() => void save()}>
          {saving ? "Saving…" : "Save changes"}
        </PrimaryButton>
        {saved ? <span className="text-sm font-semibold text-primary">Settings saved.</span> : null}
      </div>

      <section className="rounded-xl border border-error/20 bg-error-container/20 p-6 shadow-sm">
        <h3 className="font-headline text-lg font-bold text-error">Danger zone</h3>
        <p className="mt-2 text-sm text-on-error-container">
          Reset demo data and cached UI preferences for this tenant. This cannot be undone from the console alone.
        </p>
        <div className="mt-4">
          <SecondaryButton type="button" className="border-error/40 text-error hover:bg-error-container/30">
            Reset tenant preferences
          </SecondaryButton>
        </div>
      </section>
    </div>
  );
}
