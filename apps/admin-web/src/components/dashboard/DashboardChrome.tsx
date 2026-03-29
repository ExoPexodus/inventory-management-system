"use client";

import { ReactNode } from "react";
import { AppShell } from "@/components/dashboard/AppShell";

export function DashboardChrome({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
