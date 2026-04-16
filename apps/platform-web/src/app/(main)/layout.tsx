import { ReactNode } from "react";
import { AppShell } from "@/components/dashboard/AppShell";

export default function MainLayout({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
