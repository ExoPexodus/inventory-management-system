import { ReactNode } from "react";
import { cookies } from "next/headers";
import { DashboardChrome } from "@/components/dashboard/DashboardChrome";
import { CurrencyProvider } from "@/lib/currency-context";
import { LocalisationProvider } from "@/lib/localisation-context";
import { OPERATOR_META_COOKIE } from "@/lib/auth/constants";
import { parseMetaCookie } from "@/lib/auth/parse-meta-cookie";
import { UserProvider } from "@/lib/auth/user-context";

export default async function MainLayout({ children }: { children: ReactNode }) {
  const jar = await cookies();
  const rawMeta = jar.get(OPERATOR_META_COOKIE)?.value;
  const { role, permissions } = parseMetaCookie(rawMeta);
  return (
    <UserProvider role={role} permissions={permissions}>
      <DashboardChrome>
        <CurrencyProvider>
          <LocalisationProvider>{children}</LocalisationProvider>
        </CurrencyProvider>
      </DashboardChrome>
    </UserProvider>
  );
}
