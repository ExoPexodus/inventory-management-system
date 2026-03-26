export function formatMoneyUSD(cents: number, exponent = 2): string {
  const major = cents / 10 ** exponent;
  return major.toLocaleString(undefined, { style: "currency", currency: "USD" });
}
