"use client";
import { createContext, useContext, useEffect, useState, ReactNode } from "react";

interface LocalisationConfig {
  timezone: string;
  financialYearStartMonth: number;
}

const DEFAULT: LocalisationConfig = {
  timezone: "UTC",
  financialYearStartMonth: 1,
};

const LocalisationContext = createContext<LocalisationConfig>(DEFAULT);

export function LocalisationProvider({ children }: { children: ReactNode }) {
  const [cfg, setCfg] = useState<LocalisationConfig>(DEFAULT);

  useEffect(() => {
    void (async () => {
      try {
        const r = await fetch("/api/ims/v1/admin/tenant-settings/localisation");
        if (!r.ok) return;
        const data = await r.json() as { timezone: string | null; financial_year_start_month: number | null };
        setCfg({
          timezone: data.timezone ?? "UTC",
          financialYearStartMonth: data.financial_year_start_month ?? 1,
        });
      } catch {
        // Network failures leave defaults in place.
      }
    })();
  }, []);

  return (
    <LocalisationContext.Provider value={cfg}>
      {children}
    </LocalisationContext.Provider>
  );
}

export function useShopTimezone(): string {
  return useContext(LocalisationContext).timezone;
}

export function useFinancialYearStartMonth(): number {
  return useContext(LocalisationContext).financialYearStartMonth;
}
