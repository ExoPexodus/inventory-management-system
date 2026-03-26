import { ReactNode } from "react";
import { DashboardChrome } from "@/components/dashboard/DashboardChrome";

export default function MainLayout({ children }: { children: ReactNode }) {
  return <DashboardChrome>{children}</DashboardChrome>;
}
