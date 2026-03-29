"use client";

import { useRouter } from "next/navigation";

export function LogoutButton() {
  const router = useRouter();
  return (
    <button
      type="button"
      className="w-full rounded-lg border border-outline-variant/30 px-3 py-2 text-left text-xs font-medium text-on-surface-variant transition hover:bg-surface-container-lowest/60 hover:text-on-surface"
      onClick={async () => {
        await fetch("/api/auth/logout", { method: "POST" });
        router.push("/login");
        router.refresh();
      }}
    >
      Log out
    </button>
  );
}
