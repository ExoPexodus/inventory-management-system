"use client";

import { ReactNode } from "react";

interface Props {
  selectedCount: number;
  onClear: () => void;
  children: ReactNode;
  /** Optional label override (default: "selected") */
  label?: string;
}

export function BulkActionsBar({ selectedCount, onClear, children, label = "selected" }: Props) {
  if (selectedCount === 0) return null;

  return (
    <div className="sticky top-2 z-30 mb-3 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-primary/30 bg-primary/10 px-4 py-3 shadow-sm">
      <div className="flex items-center gap-3">
        <p className="text-sm font-semibold text-on-surface">
          {selectedCount} {label}
        </p>
        <button
          type="button"
          onClick={onClear}
          className="text-xs font-semibold text-on-surface-variant hover:underline"
        >
          Clear
        </button>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {children}
      </div>
    </div>
  );
}
