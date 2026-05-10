"use client";

import Link from "next/link";

const SETTINGS_CARDS = [
  {
    href: "/settings/email",
    icon: "mail",
    title: "Email",
    description: "Configure SMTP or SendGrid for staff invites and notifications",
  },
  {
    href: "/settings/currency",
    icon: "payments",
    title: "Currency",
    description: "View your default currency and symbol",
  },
  {
    href: "/settings/localisation",
    icon: "language",
    title: "Localisation",
    description: "Set your timezone and financial year start month",
  },
  {
    href: "/settings/devices",
    icon: "devices",
    title: "Devices",
    description: "POS device security and employee session timeouts",
  },
  {
    href: "/settings/reconciliation",
    icon: "account_balance",
    title: "Reconciliation",
    description: "Auto-resolve thresholds for shift close variances",
  },
  {
    href: "/settings/customer-groups",
    icon: "groups",
    title: "Customer Groups",
    description: "Manage customer segment labels for reporting",
  },
  {
    href: "/settings/business-type",
    icon: "storefront",
    title: "Business Type",
    description: "Switch between online, retail, or hybrid mode",
  },
];

export default function SettingsIndexPage() {
  return (
    <div className="space-y-10">
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Platform</p>
        <h2 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">Settings</h2>
        <p className="mt-2 font-light text-on-surface-variant">Choose a section to configure.</p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {SETTINGS_CARDS.map((card) => (
          <Link
            key={card.href}
            href={card.href}
            className="flex items-start gap-4 rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-6 shadow-sm transition-all hover:border-primary/30 hover:bg-primary/5 hover:shadow-md"
          >
            <span className="material-symbols-outlined mt-0.5 text-2xl text-primary" aria-hidden="true">
              {card.icon}
            </span>
            <div className="flex-1">
              <p className="font-headline text-base font-bold text-on-surface">{card.title}</p>
              <p className="mt-0.5 text-sm text-on-surface-variant">{card.description}</p>
            </div>
            <span className="material-symbols-outlined shrink-0 text-xl text-on-surface-variant/40" aria-hidden="true">
              chevron_right
            </span>
          </Link>
        ))}
      </div>

      {/* Danger zone */}
      <section className="rounded-xl border border-error/20 bg-error-container/20 p-6 shadow-sm">
        <h3 className="font-headline text-lg font-bold text-error">Danger zone</h3>
        <p className="mt-2 text-sm text-on-error-container">
          Reset demo data and cached UI preferences for this tenant. This cannot be undone from the console alone.
        </p>
        <div className="mt-4">
          <button
            type="button"
            className="rounded-lg border border-error/40 px-4 py-2 text-sm font-semibold text-error hover:bg-error-container/30"
          >
            Reset tenant preferences
          </button>
        </div>
      </section>
    </div>
  );
}
