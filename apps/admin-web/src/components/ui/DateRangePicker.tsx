"use client";

import { useState } from "react";
import { DateInput } from "@/components/ui/DateInput";

type Preset = "today" | "7d" | "30d" | "custom" | null;

function isoDate(d: Date): string {
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

interface Props {
  from: string;
  to: string;
  onChange: (from: string, to: string) => void;
  className?: string;
}

export function DateRangePicker({ from, to, onChange, className = "" }: Props) {
  // Detect which preset matches the current values (rough check)
  const detectPreset = (): Preset => {
    const today = isoDate(new Date());
    if (!from && !to) return null;
    if (from === today && to === today) return "today";
    const d7 = isoDate(new Date(Date.now() - 7 * 86400000));
    const d30 = isoDate(new Date(Date.now() - 30 * 86400000));
    if (from === d7 && to === today) return "7d";
    if (from === d30 && to === today) return "30d";
    return "custom";
  };

  const [active, setActive] = useState<Preset>(detectPreset());

  function applyPreset(p: Preset) {
    setActive(p);
    const today = new Date();
    if (p === "today") {
      const d = isoDate(today);
      onChange(d, d);
    } else if (p === "7d") {
      onChange(isoDate(new Date(today.getTime() - 7 * 86400000)), isoDate(today));
    } else if (p === "30d") {
      onChange(isoDate(new Date(today.getTime() - 30 * 86400000)), isoDate(today));
    } else if (p === null) {
      onChange("", "");
    }
    // "custom" keeps existing values; reveals inputs
  }

  return (
    <div className={`space-y-3 ${className}`}>
      <div className="flex flex-wrap gap-2">
        {([
          { id: "today", label: "Today" },
          { id: "7d", label: "Last 7 days" },
          { id: "30d", label: "Last 30 days" },
          { id: "custom", label: "Custom" },
        ] as const).map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => applyPreset(p.id as Preset)}
            className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${
              active === p.id
                ? "bg-primary text-on-primary"
                : "bg-surface-container-low text-on-surface-variant hover:bg-surface-container"
            }`}
          >
            {p.label}
          </button>
        ))}
        {(from || to) && (
          <button
            type="button"
            onClick={() => applyPreset(null)}
            className="rounded-full bg-surface-container-low px-3 py-1.5 text-xs font-semibold text-on-surface-variant hover:bg-surface-container"
          >
            Clear
          </button>
        )}
      </div>
      {active === "custom" && (
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">From</label>
            <DateInput value={from} onChange={(v) => onChange(v, to)} />
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">To</label>
            <DateInput value={to} onChange={(v) => onChange(from, v)} />
          </div>
        </div>
      )}
    </div>
  );
}
