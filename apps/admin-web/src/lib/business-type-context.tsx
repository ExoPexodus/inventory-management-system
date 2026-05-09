"use client";

import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";

export type BusinessType = "online" | "retail" | "hybrid";

export interface BusinessTypeFlags {
  business_type: BusinessType;
  show_shops_management: boolean;
  show_pos_features: boolean;
  show_ecommerce_features: boolean;
  can_add_physical_store: boolean;
  can_add_online_channel: boolean;
}

interface BusinessTypeState {
  flags: BusinessTypeFlags | null;
  loading: boolean;
  invalidate: () => void;
}

const DEFAULT_STATE: BusinessTypeState = {
  flags: null,
  loading: true,
  invalidate: () => undefined,
};

const BusinessTypeContext = createContext<BusinessTypeState>(DEFAULT_STATE);

const CACHE_KEY = "business-type-flags";

function readCache(): BusinessTypeFlags | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as BusinessTypeFlags;
    if (parsed && typeof parsed.business_type === "string") return parsed;
    return null;
  } catch {
    return null;
  }
}

function writeCache(flags: BusinessTypeFlags): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(CACHE_KEY, JSON.stringify(flags));
  } catch {
    // ignore quota errors
  }
}

function clearCache(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(CACHE_KEY);
  } catch {
    // ignore
  }
}

export function BusinessTypeProvider({ children }: { children: ReactNode }) {
  const cached = useMemo(readCache, []);
  const [flags, setFlags] = useState<BusinessTypeFlags | null>(cached);
  const [loading, setLoading] = useState<boolean>(cached === null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const res = await fetch("/api/ims/v1/admin/tenant-settings/business-type");
        if (!res.ok) return;
        const data = (await res.json()) as BusinessTypeFlags;
        if (cancelled) return;
        setFlags(data);
        writeCache(data);
      } catch {
        // network error — keep cached value if any
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [version]);

  const invalidate = useCallback(() => {
    clearCache();
    setVersion((v) => v + 1);
  }, []);

  const value = useMemo<BusinessTypeState>(() => ({ flags, loading, invalidate }), [flags, loading, invalidate]);

  return <BusinessTypeContext.Provider value={value}>{children}</BusinessTypeContext.Provider>;
}

export function useBusinessType(): BusinessTypeState {
  return useContext(BusinessTypeContext);
}

/** Helper for filtering nav items: returns true when the user's type matches one of `allowed`. */
export function typeAllows(flags: BusinessTypeFlags | null, allowed: BusinessType[]): boolean {
  if (!flags) return true; // permissive while loading; AppShell renders skeleton
  return allowed.includes(flags.business_type);
}
