"use client";
import { createContext, useContext, useEffect, useState, ReactNode } from "react";

export interface CurrencyConfig {
  code: string;
  exponent: number;
  symbolOverride: string | null;
  displayMode: "symbol" | "convert";
  conversionRate: number | null;
}

const DEFAULT: CurrencyConfig = {
  code: "USD",
  exponent: 2,
  symbolOverride: null,
  displayMode: "symbol",
  conversionRate: null,
};

const CurrencyContext = createContext<CurrencyConfig>(DEFAULT);

export function CurrencyProvider({ children }: { children: ReactNode }) {
  const [cfg, setCfg] = useState<CurrencyConfig>(DEFAULT);

  useEffect(() => {
    fetch("/api/ims/v1/admin/tenant-settings/currency")
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!data) return;
        setCfg({
          code: data.currency_code ?? "USD",
          exponent: data.currency_exponent ?? 2,
          symbolOverride: data.symbol_override ?? null,
          displayMode: data.display_mode ?? "symbol",
          conversionRate: data.conversion_rate ?? null,
        });
      })
      .catch(() => {});
  }, []);

  return <CurrencyContext.Provider value={cfg}>{children}</CurrencyContext.Provider>;
}

export function useCurrency(): CurrencyConfig {
  return useContext(CurrencyContext);
}
