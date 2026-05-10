"use client";

import { useEffect, useState } from "react";
import { Breadcrumbs, PageHeader, PrimaryButton } from "@/components/ui/primitives";
import { useBusinessType } from "@/lib/business-type-context";

export default function SettingsBusinessTypePage() {
  const { invalidate: invalidateBusinessType } = useBusinessType();
  const [businessType, setBusinessType] = useState<"online" | "retail" | "hybrid">("retail");
  const [btLoading, setBtLoading] = useState(true);
  const [btSaving, setBtSaving] = useState(false);
  const [btMsg, setBtMsg] = useState<string | null>(null);
  const [btErr, setBtErr] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const r = await fetch("/api/ims/v1/admin/tenant-settings/business-type");
        if (r.ok) {
          const d = (await r.json()) as { business_type: string };
          if (d.business_type === "online" || d.business_type === "retail" || d.business_type === "hybrid") {
            setBusinessType(d.business_type);
          }
        }
      } catch {
        // leave default
      } finally {
        setBtLoading(false);
      }
    })();
  }, []);

  async function handleSave() {
    setBtSaving(true);
    setBtMsg(null);
    setBtErr(null);
    try {
      const r = await fetch("/api/ims/v1/admin/tenant-settings/business-type", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ business_type: businessType }),
      });
      if (r.ok) {
        invalidateBusinessType();
        if (businessType === "hybrid") {
          setBtMsg("Hybrid mode active — both POS and ecommerce features are now available in the sidebar.");
        } else if (businessType === "online") {
          setBtMsg("Switched to online-only. Existing POS data is preserved; you can switch back anytime.");
        } else {
          setBtMsg("Switched to retail. Ecommerce sections are hidden; existing data is preserved and can be restored anytime.");
        }
      } else {
        const d = await r.json().catch(() => ({})) as { detail?: string };
        setBtErr(d.detail ?? "Failed to save.");
      }
    } catch {
      setBtErr("Network error. Please try again.");
    } finally {
      setBtSaving(false);
    }
  }

  return (
    <div className="space-y-8">
      <Breadcrumbs items={[{ label: "Settings", href: "/settings" }, { label: "Business Type" }]} />
      <PageHeader kicker="Settings" title="Business Type" subtitle="Switch between online, retail, or hybrid mode to control which features are available." />

      <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
        <h3 className="font-headline text-base font-bold text-on-surface">Business type</h3>
        <p className="mt-1 text-sm text-on-surface-variant">
          Controls which features are available. &ldquo;Online&rdquo; enables e-commerce channels and hosted checkout.
          &ldquo;Retail&rdquo; focuses on POS. &ldquo;Hybrid&rdquo; enables both.
        </p>
        {btLoading ? (
          <p className="mt-4 text-sm text-on-surface-variant">Loading…</p>
        ) : (
          <div className="mt-4 space-y-3">
            <div className="grid grid-cols-3 gap-3">
              {(["online", "retail", "hybrid"] as const).map((bt) => (
                <button
                  key={bt}
                  type="button"
                  onClick={() => setBusinessType(bt)}
                  className={`flex flex-col items-center rounded-xl border px-4 py-3 text-sm font-semibold transition ${
                    businessType === bt
                      ? "border-primary bg-primary/10 text-primary"
                      : "border-outline-variant/30 text-on-surface-variant hover:border-primary/40 hover:text-on-surface"
                  }`}
                >
                  <span className="material-symbols-outlined text-xl mb-1">
                    {bt === "online" ? "language" : bt === "retail" ? "store" : "merge"}
                  </span>
                  {bt.charAt(0).toUpperCase() + bt.slice(1)}
                </button>
              ))}
            </div>
            {btMsg && <p className="text-sm font-semibold text-primary">{btMsg}</p>}
            {btErr && <p className="text-sm text-error">{btErr}</p>}
            <PrimaryButton type="button" onClick={() => void handleSave()} disabled={btSaving}>
              {btSaving ? "Saving…" : "Save business type"}
            </PrimaryButton>
          </div>
        )}
      </section>
    </div>
  );
}
