"use client";
import { createContext, useCallback, useContext, useEffect, useState, ReactNode } from "react";
import { usePathname } from "next/navigation";

export interface CurrencyConfig {
  code: string;
  exponent: number;
  symbolOverride: string | null;
}

const DEFAULT: CurrencyConfig = {
  code: "USD",
  exponent: 2,
  symbolOverride: null,
};

interface CurrencyContextValue {
  currency: CurrencyConfig;
  refreshCurrency: () => Promise<void>;
}

const CurrencyContext = createContext<CurrencyContextValue>({
  currency: DEFAULT,
  refreshCurrency: async () => {},
});

export function CurrencyProvider({ children }: { children: ReactNode }) {
  const [cfg, setCfg] = useState<CurrencyConfig>(DEFAULT);
  const pathname = usePathname();

  const refreshCurrency = useCallback(async () => {
    try {
      const r = await fetch("/api/ims/v1/admin/tenant-settings/currency");
      if (!r.ok) return;
      const data = await r.json();
      setCfg({
        code: data.currency_code ?? "USD",
        exponent: data.currency_exponent ?? 2,
        symbolOverride: data.currency_symbol ?? null,
      });
    } catch {
      // Network failures leave current values in place.
    }
  }, []);

  useEffect(() => {
    void refreshCurrency();
  }, [refreshCurrency]);

  useEffect(() => {
    void refreshCurrency();
  }, [pathname, refreshCurrency]);

  return (
    <CurrencyContext.Provider value={{ currency: cfg, refreshCurrency }}>
      {children}
    </CurrencyContext.Provider>
  );
}

export function useCurrency(): CurrencyConfig {
  return useContext(CurrencyContext).currency;
}

export function useRefreshCurrency(): () => Promise<void> {
  return useContext(CurrencyContext).refreshCurrency;
}
