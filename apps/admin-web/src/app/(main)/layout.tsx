import { ReactNode } from "react";
import { DashboardChrome } from "@/components/dashboard/DashboardChrome";
import { CurrencyProvider } from "@/lib/currency-context";

export default function MainLayout({ children }: { children: ReactNode }) {
  return (
    <DashboardChrome>
      <CurrencyProvider>{children}</CurrencyProvider>
    </DashboardChrome>
  );
}
