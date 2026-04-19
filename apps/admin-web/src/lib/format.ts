export function formatMoneyUSD(cents: number, exponent = 2): string {
  const major = cents / 10 ** exponent;
  return major.toLocaleString(undefined, { style: "currency", currency: "USD" });
}

export interface CurrencyConfig {
  code: string;
  exponent: number;
}

export function formatMoney(cents: number, cfg: CurrencyConfig): string {
  const major = cents / 10 ** cfg.exponent;
  return major.toLocaleString(undefined, {
    style: "currency",
    currency: cfg.code,
    minimumFractionDigits: cfg.exponent,
    maximumFractionDigits: cfg.exponent,
  });
}
