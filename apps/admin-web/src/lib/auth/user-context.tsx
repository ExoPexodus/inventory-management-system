"use client";

import { createContext, ReactNode, useContext, useMemo } from "react";
import { OPERATOR_META_COOKIE } from "./constants";

interface UserState {
  role: string | null;
  permissions: string[];
}

const UserContext = createContext<UserState>({ role: null, permissions: [] });

function readMetaCookie(): UserState {
  if (typeof document === "undefined") return { role: null, permissions: [] };
  const raw = document.cookie
    .split("; ")
    .find((c) => c.startsWith(`${OPERATOR_META_COOKIE}=`))
    ?.split("=")
    .slice(1)
    .join("=");
  if (!raw) return { role: null, permissions: [] };
  try {
    const parsed = JSON.parse(decodeURIComponent(raw)) as { role?: string | null; permissions?: string[] };
    return {
      role: parsed.role ?? null,
      permissions: Array.isArray(parsed.permissions) ? parsed.permissions : [],
    };
  } catch {
    return { role: null, permissions: [] };
  }
}

export function UserProvider({
  role,
  permissions,
  children,
}: {
  role: string | null;
  permissions: string[];
  children: ReactNode;
}) {
  const value = useMemo(() => ({ role, permissions }), [role, permissions]);
  return <UserContext.Provider value={value}>{children}</UserContext.Provider>;
}

export function useUser(): UserState {
  return useContext(UserContext);
}

export function useHasPermission(...codenames: string[]): boolean {
  const { permissions } = useUser();
  if (codenames.length === 0) return true;
  return codenames.some((c) => permissions.includes(c));
}

export { readMetaCookie };
