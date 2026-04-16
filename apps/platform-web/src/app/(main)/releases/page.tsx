"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

type Release = {
  id: string;
  app_name: string;
  version: string;
  version_code: number;
  changelog: string | null;
  file_size_bytes: number | null;
  checksum_sha256: string | null;
  is_active: boolean;
  created_at: string;
};

function sizeMB(bytes: number | null) {
  if (!bytes) return "—";
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ReleasesPage() {
  const [releases, setReleases] = useState<Release[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [showUpload, setShowUpload] = useState(false);
  const [uploadErr, setUploadErr] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function load() {
    setLoading(true);
    const r = await fetch("/api/platform/v1/platform/releases?active_only=false");
    if (r.ok) setReleases(await r.json());
    setLoading(false);
  }

  useEffect(() => { void load(); }, []);

  async function handleUpload(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setUploading(true);
    setUploadErr(null);

    const form = new FormData(e.currentTarget);
    try {
      const r = await fetch("/api/platform/v1/platform/releases", {
        method: "POST",
        body: form,
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(d.detail ?? `Upload failed (${r.status})`);
      }
      setShowUpload(false);
      void load();
    } catch (err) {
      setUploadErr(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function toggleActive(release: Release) {
    await fetch(`/api/platform/v1/platform/releases/${release.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: !release.is_active }),
    });
    void load();
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">App distribution</p>
          <h1 className="mt-1 font-headline text-3xl font-extrabold text-on-surface">App Releases</h1>
          <p className="mt-1 text-sm text-on-surface-variant">Upload APK builds and manage versions.</p>
        </div>
        <button
          type="button"
          onClick={() => setShowUpload(true)}
          className="ink-gradient inline-flex items-center gap-2 rounded-lg px-6 py-2.5 text-sm font-semibold text-on-primary shadow-sm transition hover:opacity-90"
        >
          <span className="material-symbols-outlined text-lg">upload</span>
          Upload APK
        </button>
      </div>

      {/* Upload modal */}
      {showUpload ? (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/50 p-4" onClick={() => setShowUpload(false)}>
          <div className="w-full max-w-md rounded-2xl bg-surface p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-headline text-lg font-bold text-on-surface">Upload APK</h3>
            <form onSubmit={handleUpload} className="mt-4 space-y-4">
              <div>
                <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">App</label>
                <select name="app_name" required className="w-full rounded-lg border border-outline-variant/30 bg-surface-container-lowest px-4 py-2.5 text-sm outline-none focus:border-primary">
                  <option value="cashier">Cashier POS</option>
                  <option value="admin_mobile">Admin Mobile</option>
                </select>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">Version</label>
                  <input name="version" required placeholder="1.0.0" className="w-full rounded-lg border border-outline-variant/30 bg-surface-container-lowest px-4 py-2.5 text-sm outline-none focus:border-primary" />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">Version code</label>
                  <input name="version_code" type="number" required placeholder="1" className="w-full rounded-lg border border-outline-variant/30 bg-surface-container-lowest px-4 py-2.5 text-sm outline-none focus:border-primary" />
                </div>
              </div>
              <div>
                <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">Changelog</label>
                <textarea name="changelog" rows={3} placeholder="What's new in this version..." className="w-full rounded-lg border border-outline-variant/30 bg-surface-container-lowest px-4 py-2.5 text-sm outline-none focus:border-primary" />
              </div>
              <div>
                <label className="mb-1 block text-xs font-bold uppercase tracking-widest text-on-surface-variant">APK file</label>
                <input ref={fileRef} name="file" type="file" accept=".apk" required className="w-full text-sm text-on-surface-variant file:mr-3 file:rounded-lg file:border-0 file:bg-primary/10 file:px-4 file:py-2 file:text-xs file:font-semibold file:text-primary hover:file:bg-primary/20" />
              </div>
              {uploadErr ? <p className="text-sm text-error">{uploadErr}</p> : null}
              <div className="flex justify-end gap-3">
                <button type="button" onClick={() => setShowUpload(false)} className="rounded-lg border border-outline-variant/20 px-5 py-2 text-sm font-semibold text-on-surface-variant">Cancel</button>
                <button type="submit" disabled={uploading} className="ink-gradient rounded-lg px-6 py-2 text-sm font-semibold text-on-primary disabled:opacity-50">
                  {uploading ? "Uploading..." : "Upload"}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {/* Releases table */}
      <div className="overflow-hidden rounded-xl border border-outline-variant/10 bg-surface-container-lowest shadow-sm">
        <table className="min-w-full text-left text-sm">
          <thead>
            <tr className="border-b border-outline-variant/10">
              <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">App</th>
              <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Version</th>
              <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Code</th>
              <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Size</th>
              <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Status</th>
              <th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Uploaded</th>
              <th className="px-6 py-3 text-center text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-outline-variant/10">
            {loading ? (
              <tr><td colSpan={7} className="px-6 py-12 text-center text-on-surface-variant">Loading...</td></tr>
            ) : releases.length === 0 ? (
              <tr><td colSpan={7} className="px-6 py-12 text-center text-on-surface-variant">No releases uploaded yet. Click &quot;Upload APK&quot; to get started.</td></tr>
            ) : releases.map((r) => (
              <tr key={r.id} className="hover:bg-surface-container-low/60">
                <td className="px-6 py-3 font-semibold capitalize">{r.app_name.replace(/_/g, " ")}</td>
                <td className="px-6 py-3 font-mono text-xs">{r.version}</td>
                <td className="px-6 py-3 text-xs text-on-surface-variant">{r.version_code}</td>
                <td className="px-6 py-3 text-xs text-on-surface-variant">{sizeMB(r.file_size_bytes)}</td>
                <td className="px-6 py-3">
                  <span className={`inline-flex rounded-full px-2.5 py-0.5 text-[10px] font-bold uppercase ${r.is_active ? "bg-tertiary-fixed text-on-tertiary-fixed-variant" : "bg-surface-container-highest text-on-surface"}`}>
                    {r.is_active ? "Active" : "Inactive"}
                  </span>
                </td>
                <td className="px-6 py-3 text-xs text-on-surface-variant">{new Date(r.created_at).toLocaleDateString()}</td>
                <td className="px-6 py-3 text-center">
                  <button
                    type="button"
                    onClick={() => toggleActive(r)}
                    className="inline-flex items-center gap-1 rounded-lg border border-outline-variant/20 px-3 py-1.5 text-xs font-semibold text-on-surface transition hover:bg-surface-container-high"
                  >
                    {r.is_active ? "Deactivate" : "Activate"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
