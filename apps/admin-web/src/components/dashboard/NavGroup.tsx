"use client";

import Link from "next/link";
import { useState } from "react";

export interface NavItem {
  href: string;
  label: string;
  icon: string;
}

interface Props {
  label: string;
  items: NavItem[];
  activePath: string;
  tenantPrefix: string;
  initiallyExpanded: boolean;
  onToggle: (expanded: boolean) => void;
}

export function NavGroup({ label, items, activePath, tenantPrefix, initiallyExpanded, onToggle }: Props) {
  const [expanded, setExpanded] = useState(initiallyExpanded);
  if (items.length === 0) return null;

  const handleToggle = () => {
    setExpanded((prev) => {
      const next = !prev;
      onToggle(next);
      return next;
    });
  };

  return (
    <div className="space-y-0.5">
      <button
        type="button"
        onClick={handleToggle}
        className="flex w-full items-center justify-between rounded-md px-4 py-1.5 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant/70 hover:text-on-surface-variant"
      >
        <span>{label}</span>
        <span
          className={`material-symbols-outlined text-[16px] transition-transform ${expanded ? "rotate-90" : ""}`}
          aria-hidden="true"
        >
          chevron_right
        </span>
      </button>
      {expanded && items.map((item) => {
        const active = activePath === item.href;
        return (
          <Link
            key={item.href}
            href={`${tenantPrefix}${item.href}`}
            className={`flex items-center gap-3 rounded-lg px-4 py-2.5 text-[13px] transition-colors duration-150 ${
              active
                ? "bg-primary/10 font-bold text-primary"
                : "font-medium text-on-surface-variant hover:bg-surface-container-lowest/60 hover:text-on-surface"
            }`}
          >
            <span className={`material-symbols-outlined text-[20px] leading-none ${active ? "" : "opacity-70"}`} aria-hidden="true">
              {item.icon}
            </span>
            {item.label}
          </Link>
        );
      })}
    </div>
  );
}
