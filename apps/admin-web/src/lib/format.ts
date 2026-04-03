export function formatMoneyUSD(cents: number, exponent = 2): string {
  const major = cents / 10 ** exponent;
  return major.toLocaleString(undefined, { style: "currency", currency: "USD" });
}

export interface CurrencyConfig {
  code: string;
  exponent: number;
  displayMode: "symbol" | "convert";
  conversionRate: number | null;
}

export function formatMoney(cents: number, cfg: CurrencyConfig): string {
  const rate = cfg.displayMode === "convert" && cfg.conversionRate ? cfg.conversionRate : 1;
  const major = (cents / 100) * rate;
  return major.toLocaleString(undefined, {
    style: "currency",
    currency: cfg.code,
    minimumFractionDigits: cfg.exponent,
    maximumFractionDigits: cfg.exponent,
  });
}
