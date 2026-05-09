"use client";

import Link from "next/link";
import { ReactNode } from "react";
import { BusinessType, useBusinessType, typeAllows } from "@/lib/business-type-context";

interface Props {
  types: BusinessType[];
  children: ReactNode;
}

export function RequiresBusinessType({ types, children }: Props) {
  const { flags, loading } = useBusinessType();

  // While loading: render a neutral placeholder so we don't flash a guard message
  if (loading && !flags) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-on-surface-variant">
        Loading…
      </div>
    );
  }

  if (typeAllows(flags, types)) {
    return <>{children}</>;
  }

  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-outline-variant/30 bg-surface-container-low px-8 py-16 text-center">
      <span className="material-symbols-outlined text-5xl text-on-surface-variant/40" aria-hidden="true">
        block
      </span>
      <h2 className="font-headline text-lg font-bold text-on-surface">
        Not part of your current setup
      </h2>
      <p className="max-w-md text-sm text-on-surface-variant">
        This feature is available for {types.join(" or ")} businesses. Switch your business type from settings to enable it.
      </p>
      <Link
        href="/settings"
        className="mt-2 rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-on-primary hover:opacity-90"
      >
        Open Settings →
      </Link>
    </div>
  );
}
