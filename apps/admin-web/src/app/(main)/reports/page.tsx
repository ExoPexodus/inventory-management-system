"use client";

import { useState } from "react";
import { SecondaryButton, TextInput } from "@/components/ui/primitives";

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

  const exportReport = (id: string) => {
    const sp = new URLSearchParams();
    sp.set("report", id);
    if (from) sp.set("from", from);
    if (to) sp.set("to", to);
    void fetch(`/api/ims/v1/admin/reports/export?${sp.toString()}`);
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
          <TextInput type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="rounded-lg border border-outline-variant/20 bg-surface-container-lowest px-3" />
        </label>
        <label className="flex min-w-[10rem] flex-col gap-1">
          <span className="text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">To</span>
          <TextInput type="date" value={to} onChange={(e) => setTo(e.target.value)} className="rounded-lg border border-outline-variant/20 bg-surface-container-lowest px-3" />
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
              <SecondaryButton type="button" onClick={() => exportReport(r.id)}>
                <span className="material-symbols-outlined text-base">download</span>
                Export
              </SecondaryButton>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
