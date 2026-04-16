"use client";

import Link from "next/link";
import { ReactNode, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { PLATFORM_META_COOKIE } from "@/lib/auth/constants";

const NAV = [
  { href: "/dashboard",   label: "Dashboard",    icon: "space_dashboard" },
  { href: "/tenants",     label: "Tenants",       icon: "apartment" },
  { href: "/plans",       label: "Plans & Add-ons", icon: "sell" },
  { href: "/payments",    label: "Payments",      icon: "payments" },
  { href: "/invoices",    label: "Invoices",      icon: "receipt_long" },
  { href: "/releases",    label: "App Releases",  icon: "phone_android" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [operatorName, setOperatorName] = useState("Operator");

  useEffect(() => {
    try {
      const raw = document.cookie.split("; ").find((c) => c.startsWith(`${PLATFORM_META_COOKIE}=`));
      if (raw) {
        const val = decodeURIComponent(raw.split("=").slice(1).join("="));
        const parsed = JSON.parse(val);
        if (parsed.display_name) setOperatorName(parsed.display_name);
      }
    } catch { /* ignore */ }
  }, []);

  async function handleLogout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
  }

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="flex w-64 shrink-0 flex-col border-r border-outline-variant/10 bg-surface-container-lowest">
        <div className="px-6 py-5">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary">
              <span className="material-symbols-outlined text-lg text-on-primary">admin_panel_settings</span>
            </div>
            <div>
              <p className="font-headline text-sm font-extrabold text-on-surface">IMS Platform</p>
              <p className="text-[10px] text-on-surface-variant">Control Plane</p>
            </div>
          </div>
        </div>

        <nav className="flex-1 space-y-0.5 px-3 py-2">
          {NAV.map((item) => {
            const active = pathname === item.href || pathname.startsWith(item.href + "/");
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition ${
                  active
                    ? "bg-primary/10 font-semibold text-primary"
                    : "text-on-surface-variant hover:bg-surface-container-high"
                }`}
              >
                <span className="material-symbols-outlined text-[20px]">{item.icon}</span>
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-outline-variant/10 px-4 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10">
              <span className="text-xs font-bold text-primary">
                {operatorName[0]?.toUpperCase() ?? "O"}
              </span>
            </div>
            <div className="flex-1 overflow-hidden">
              <p className="truncate text-xs font-semibold text-on-surface">{operatorName}</p>
              <p className="text-[10px] text-on-surface-variant">Platform operator</p>
            </div>
            <button onClick={handleLogout} className="text-on-surface-variant transition hover:text-error" title="Sign out">
              <span className="material-symbols-outlined text-[20px]">logout</span>
            </button>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto p-8">{children}</main>
    </div>
  );
}
