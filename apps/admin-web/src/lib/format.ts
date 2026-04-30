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

export function fmtDatetime(iso: string, timeZone: string = "UTC"): string {
  return new Date(iso).toLocaleString(undefined, {
    timeZone,
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}
