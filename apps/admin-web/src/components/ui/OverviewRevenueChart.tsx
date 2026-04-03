"use client";

import { InteractiveAreaChart } from "./charts";
import { formatMoney, type CurrencyConfig } from "@/lib/format";

export function OverviewRevenueChart({
  values,
  labels,
  currency,
}: {
  values: number[];
  labels: string[];
  currency: CurrencyConfig;
}) {
  return (
    <InteractiveAreaChart
      values={values}
      labels={labels}
      formatValue={(v) => formatMoney(Math.round(v * 100), currency)}
    />
  );
}
