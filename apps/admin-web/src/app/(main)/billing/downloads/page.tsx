"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/ui/primitives";

type DownloadInfo = {
  download_token: string | null;
  download_url_template: string;
};

function AppCard({ name, icon, description, downloadUrl }: { name: string; icon: string; description: string; downloadUrl: string | null }) {
  return (
    <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
      <div className="flex items-start gap-4">
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary/10">
          <span className="material-symbols-outlined text-2xl text-primary">{icon}</span>
        </div>
        <div className="flex-1">
          <h3 className="font-headline text-lg font-bold text-on-surface">{name}</h3>
          <p className="mt-1 text-sm text-on-surface-variant">{description}</p>
        </div>
      </div>
      <div className="mt-5">
        {downloadUrl ? (
          <a
            href={downloadUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="ink-gradient inline-flex w-full items-center justify-center gap-2 rounded-lg px-6 py-2.5 text-sm font-semibold text-on-primary shadow-sm transition hover:opacity-90"
          >
            <span className="material-symbols-outlined text-lg">download</span>
            Download APK
          </a>
        ) : (
          <div className="rounded-lg border border-outline-variant/20 bg-surface-container px-6 py-2.5 text-center text-sm text-on-surface-variant">
            Download not available
          </div>
        )}
      </div>
    </div>
  );
}

export default function DownloadsPage() {
  const [info, setInfo] = useState<DownloadInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const r = await fetch("/api/ims/v1/admin/billing/app-downloads");
        if (r.ok) setInfo(await r.json());
      } finally {
        setLoading(false);
      }
    }
    void load();
  }, []);

  const publicUrl = info?.download_token
    ? `${window.location.origin}/downloads/${info.download_token}`
    : null;

  const handleCopy = () => {
    if (publicUrl) {
      void navigator.clipboard.writeText(publicUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="space-y-8">
      <PageHeader
        kicker="Mobile apps"
        title="App Downloads"
        subtitle="Share the download link with your team so they can install the mobile apps."
        action={
          <Link
            href="/billing"
            className="inline-flex items-center gap-2 rounded-lg border border-outline-variant/20 bg-surface-container px-5 py-2.5 text-sm font-semibold text-on-surface transition hover:bg-surface-container-high"
          >
            <span className="material-symbols-outlined text-lg">arrow_back</span>
            Back to Billing
          </Link>
        }
      />

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        </div>
      ) : (
        <>
          {/* Share link section */}
          {publicUrl ? (
            <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
              <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Public download link</p>
              <p className="mt-1 text-sm text-on-surface-variant">
                Share this link with your team. No login required — anyone with the link can download the apps.
              </p>
              <div className="mt-4 flex gap-2">
                <div className="flex-1 rounded-lg border border-outline-variant/20 bg-surface-container px-4 py-2.5 font-mono text-sm text-on-surface">
                  {publicUrl}
                </div>
                <button
                  type="button"
                  onClick={handleCopy}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-outline-variant/20 bg-surface-container px-4 py-2.5 text-sm font-semibold text-on-surface transition hover:bg-surface-container-high"
                >
                  <span className="material-symbols-outlined text-lg">{copied ? "check" : "content_copy"}</span>
                  {copied ? "Copied!" : "Copy"}
                </button>
              </div>
            </section>
          ) : (
            <section className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-8 text-center shadow-sm">
              <span className="material-symbols-outlined text-4xl text-on-surface-variant">link_off</span>
              <p className="mt-2 text-sm text-on-surface-variant">
                No download link configured. Contact support to set up app distribution.
              </p>
            </section>
          )}

          {/* App cards */}
          <section>
            <h3 className="mb-4 text-xs font-bold uppercase tracking-widest text-on-surface-variant">Available apps</h3>
            <div className="grid gap-4 sm:grid-cols-2">
              <AppCard
                name="Cashier POS"
                icon="point_of_sale"
                description="Offline-first point-of-sale app for your staff. Handles sales, inventory lookup, and shift management."
                downloadUrl={publicUrl ? `${publicUrl}` : null}
              />
              <AppCard
                name="Admin Mobile"
                icon="admin_panel_settings"
                description="Mobile companion for store owners. View orders, analytics, and manage staff on the go."
                downloadUrl={publicUrl ? `${publicUrl}` : null}
              />
            </div>
          </section>
        </>
      )}
    </div>
  );
}
