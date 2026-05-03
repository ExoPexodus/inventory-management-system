import { serverJsonGet } from "@/lib/api/server-json";
import { ShareCard, DownloadButton } from "./apps-client";

type AppInfo = {
  app_name: string;
  display_name: string;
  description: string;
  version: string | null;
  version_code: number | null;
  changelog: string | null;
  size_mb: number | null;
  available: boolean;
  admin_download_url: string | null;
};

type DownloadsResponse = {
  download_page_url: string;
  apps: AppInfo[];
};

const APP_ICONS: Record<string, string> = {
  cashier: "point_of_sale",
  admin_mobile: "admin_panel_settings",
};

export default async function GetAppsPage() {
  const res = await serverJsonGet<DownloadsResponse>("/v1/admin/apps/downloads");

  const downloadPageUrl = res.ok ? res.data.download_page_url : "";
  const apps: AppInfo[] = res.ok ? res.data.apps : [];

  return (
    <div className="space-y-8">
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">App distribution</p>
        <h2 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">Get Apps</h2>
        <p className="mt-2 text-on-surface-variant">
          Download and distribute the Cashier POS and Admin Mobile apps to your team.
        </p>
      </div>

      <ShareCard url={downloadPageUrl} />

      {apps.length === 0 && res.ok && (
        <p className="text-sm text-on-surface-variant">No releases published yet. Ask your platform administrator to upload APK builds.</p>
      )}

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        {apps.map((app) => (
          <div
            key={app.app_name}
            className="flex flex-col gap-4 rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm"
          >
            <div className="flex items-start gap-4">
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary/10">
                <span className="material-symbols-outlined text-2xl text-primary" aria-hidden="true">
                  {APP_ICONS[app.app_name] ?? "smartphone"}
                </span>
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <h3 className="font-headline text-lg font-bold text-on-surface">{app.display_name}</h3>
                  {app.version && (
                    <span className="rounded-full bg-primary/10 px-2 py-0.5 font-mono text-[10px] font-bold text-primary">
                      v{app.version}
                    </span>
                  )}
                </div>
                <p className="mt-0.5 text-sm text-on-surface-variant">{app.description}</p>
                {app.size_mb && (
                  <p className="mt-1 text-xs text-on-surface-variant/60">{app.size_mb.toFixed(1)} MB</p>
                )}
              </div>
            </div>

            {app.changelog && (
              <div className="rounded-lg bg-surface-container-low px-4 py-3">
                <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">What&apos;s new</p>
                <p className="mt-1 line-clamp-3 text-sm text-on-surface-variant">{app.changelog}</p>
              </div>
            )}

            {!app.available && (
              <p className="text-sm text-on-surface-variant/60">Not yet available — no active release.</p>
            )}

            <DownloadButton adminDownloadUrl={app.admin_download_url} />
          </div>
        ))}
      </div>
    </div>
  );
}
