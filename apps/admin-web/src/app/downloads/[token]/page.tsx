import { internalPlatformUrl } from "@/lib/api/internal-url";
import { notFound } from "next/navigation";

type AppItem = {
  app_name: string;
  display_name: string;
  description: string;
  version: string | null;
  changelog: string | null;
  size_mb: number | null;
  available: boolean;
};

type Manifest = {
  tenant_name: string;
  apps: AppItem[];
};

async function getManifest(token: string): Promise<Manifest | null> {
  try {
    const r = await fetch(`${internalPlatformUrl()}/downloads/${token}/manifest`, {
      cache: "no-store",
    });
    if (!r.ok) return null;
    return r.json();
  } catch {
    return null;
  }
}

const APP_ICONS: Record<string, string> = {
  cashier: "point_of_sale",
  admin_mobile: "admin_panel_settings",
};

export default async function PublicDownloadPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  const manifest = await getManifest(token);
  if (!manifest) notFound();

  return (
    <div className="min-h-screen bg-surface">
      <div className="bg-on-surface px-6 py-10 text-center">
        <p className="text-xs font-bold uppercase tracking-widest text-surface/70">
          {manifest.tenant_name}
        </p>
        <h1 className="mt-2 font-headline text-3xl font-extrabold text-surface">
          Download Apps
        </h1>
        <p className="mt-2 text-sm text-surface/70">
          Install the latest apps on your Android device. No login required.
        </p>
      </div>

      <div className="mx-auto max-w-2xl space-y-4 px-6 py-10">
        {manifest.apps.map((app) => (
          <div
            key={app.app_name}
            className="rounded-2xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm"
          >
            <div className="flex items-start gap-4">
              <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-primary/10">
                <span className="material-symbols-outlined text-3xl text-primary">
                  {APP_ICONS[app.app_name] ?? "android"}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <h2 className="font-headline text-xl font-extrabold text-on-surface">
                  {app.display_name}
                </h2>
                <p className="mt-0.5 text-sm text-on-surface-variant">{app.description}</p>
                {app.version && (
                  <div className="mt-2 flex flex-wrap gap-3 text-xs text-on-surface-variant">
                    <span className="inline-flex items-center gap-1">
                      <span className="material-symbols-outlined text-sm">tag</span>
                      v{app.version}
                    </span>
                    {app.size_mb && (
                      <span className="inline-flex items-center gap-1">
                        <span className="material-symbols-outlined text-sm">storage</span>
                        {app.size_mb} MB
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>

            {app.changelog && (
              <div className="mt-4 rounded-lg bg-surface-container-low px-4 py-3 text-xs text-on-surface-variant">
                <p className="mb-1 font-semibold uppercase tracking-wider">What&apos;s new</p>
                <p className="whitespace-pre-wrap leading-relaxed">{app.changelog}</p>
              </div>
            )}

            <div className="mt-5">
              {app.available ? (
                <a
                  href={`/downloads/${token}/${app.app_name}`}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-on-surface px-6 py-3 text-sm font-semibold text-surface shadow-sm transition hover:opacity-90 active:scale-[0.98]"
                >
                  <span className="material-symbols-outlined text-lg">download</span>
                  Download APK
                </a>
              ) : (
                <div className="rounded-xl border border-outline-variant/20 bg-surface-container px-6 py-3 text-center text-sm text-on-surface-variant">
                  Not yet available
                </div>
              )}
            </div>
          </div>
        ))}

        <p className="pt-4 text-center text-xs text-on-surface-variant">
          Enable &ldquo;Install from unknown sources&rdquo; on your Android device before installing.
        </p>
      </div>
    </div>
  );
}
