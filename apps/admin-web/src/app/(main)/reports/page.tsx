"use client";

import { useState } from "react";
import { SecondaryButton } from "@/components/ui/primitives";
import { DateInput } from "@/components/ui/DateInput";

const REPORTS = [
  {
    id: "sales",
    icon: "payments",
    title: "Sales summary",
    description: "Net sales, tax, and tenders by day and location.",
  },
  {
    id: "inventory",
    icon: "inventory_2",
    title: "Inventory valuation",
    description: "On-hand quantities and extended cost by SKU.",
  },
  {
    id: "movements",
    icon: "swap_horiz",
    title: "Stock movements",
    description: "Receipts, transfers, adjustments, and shrink.",
  },
  {
    id: "suppliers",
    icon: "local_shipping",
    title: "Supplier performance",
    description: "Fill rates, lead times, and purchase history.",
  },
  {
    id: "staff",
    icon: "groups",
    title: "Staff activity",
    description: "Shift overlap, voids, and discount patterns.",
  },
  {
    id: "audit",
    icon: "shield_person",
    title: "Audit extract",
    description: "Security and configuration changes for compliance.",
  },
] as const;

export default function ReportsPage() {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");

  const [exporting, setExporting] = useState<string | null>(null);
  const [exportErr, setExportErr] = useState<string | null>(null);

  const exportReport = async (id: string) => {
    setExporting(id);
    setExportErr(null);
    const sp = new URLSearchParams();
    sp.set("report", id);
    if (from) sp.set("from", from);
    if (to) sp.set("to", to);
    try {
      const res = await fetch(`/api/ims/v1/admin/reports/export?${sp.toString()}`);
      if (!res.ok) { setExportErr(`Export failed (${res.status})`); return; }
      const blob = await res.blob();
      const cd = res.headers.get("Content-Disposition") ?? "";
      const match = /filename="([^"]+)"/.exec(cd);
      const filename = match?.[1] ?? `${id}_export.csv`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(null);
    }
  };

  return (
    <div className="space-y-8">
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-on-surface-variant">Finance</p>
        <h2 className="font-headline text-4xl font-extrabold tracking-tight text-on-surface">Reports</h2>
        <p className="mt-2 font-light text-on-surface-variant">Generate exports for accounting, ops, and compliance.</p>
      </div>

      <div className="flex flex-wrap items-end gap-4 rounded-xl border border-outline-variant/10 bg-surface-container-low p-4 shadow-sm">
        <label className="flex min-w-[10rem] flex-col gap-1">
          <span className="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">From</span>
          <DateInput value={from} onChange={setFrom} />
        </label>
        <label className="flex min-w-[10rem] flex-col gap-1">
          <span className="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">To</span>
          <DateInput value={to} onChange={setTo} />
        </label>
      </div>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
        {REPORTS.map((r) => (
          <div
            key={r.id}
            className="flex flex-col rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-6 shadow-sm"
          >
            <div className="flex items-start gap-4">
              <span className="material-symbols-outlined rounded-lg bg-surface-container-low p-2 text-2xl text-primary">
                {r.icon}
              </span>
              <div className="min-w-0 flex-1">
                <h3 className="font-headline text-lg font-bold text-on-surface">{r.title}</h3>
                <p className="mt-1 text-sm text-on-surface-variant">{r.description}</p>
              </div>
            </div>
            <div className="mt-6 flex justify-end">
              <SecondaryButton type="button" disabled={exporting === r.id} onClick={() => void exportReport(r.id)}>
                <span className="material-symbols-outlined text-base">{exporting === r.id ? "hourglass_top" : "download"}</span>
                {exporting === r.id ? "Exporting…" : "Export CSV"}
              </SecondaryButton>
            </div>
          </div>
        ))}
      </div>
      {exportErr && (
        <p className="rounded-lg border border-error/20 bg-error-container/20 px-4 py-3 text-sm text-on-error-container">{exportErr}</p>
      )}
    </div>
  );
}
