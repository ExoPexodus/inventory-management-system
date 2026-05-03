"use client";

import { useEffect, useRef, useState } from "react";
import QRCode from "qrcode";

export function ShareCard({ url }: { url: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!canvasRef.current || !url) return;
    void QRCode.toCanvas(canvasRef.current, url, { width: 160, margin: 1 });
  }, [url]);

  const handleCopy = () => {
    void navigator.clipboard.writeText(url).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  if (!url) {
    return (
      <div className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm">
        <p className="text-sm text-on-surface-variant">
          No download link configured for this tenant. Contact your platform administrator.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6 rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm sm:flex-row sm:items-start">
      <canvas ref={canvasRef} className="shrink-0 rounded-lg border border-outline-variant/10" />
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <div>
          <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Share with your team</p>
          <p className="mt-1 text-sm text-on-surface-variant">
            Scan the QR code or share this link. Opening it on an Android device lets staff download and install the apps.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            readOnly
            value={url}
            className="min-w-0 flex-1 rounded-lg border border-outline-variant/20 bg-surface-container-low px-3 py-2 font-mono text-xs text-on-surface outline-none"
          />
          <button
            type="button"
            onClick={handleCopy}
            className="shrink-0 rounded-lg border border-outline-variant/20 px-4 py-2 text-xs font-semibold text-on-surface transition hover:bg-surface-container-high"
          >
            {copied ? "Copied!" : "Copy link"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function DownloadButton({ adminDownloadUrl }: { adminDownloadUrl: string | null }) {
  if (!adminDownloadUrl) return null;
  return (
    <a
      href={`/api/ims${adminDownloadUrl}`}
      className="inline-flex items-center gap-2 rounded-lg border border-outline-variant/20 px-4 py-2 text-sm font-semibold text-on-surface transition hover:bg-surface-container-high"
      download
    >
      <span className="material-symbols-outlined text-lg leading-none" aria-hidden="true">download</span>
      Download APK
    </a>
  );
}
