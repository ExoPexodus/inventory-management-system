"use client";

import { usePathname } from "next/navigation";
import { ReactNode } from "react";
import { AppShell } from "@/components/dashboard/AppShell";

export function DashboardChrome({ children }: { children: ReactNode }) {
  const path = usePathname();
  return <AppShell current={path}>{children}</AppShell>;
}
