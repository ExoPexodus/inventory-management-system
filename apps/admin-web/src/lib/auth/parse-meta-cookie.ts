/** Pure utility — no React, no browser APIs. Safe to import in server components. */

interface UserState {
  role: string | null;
  permissions: string[];
}

export function parseMetaCookie(rawCookieValue: string | undefined): UserState {
  if (!rawCookieValue) return { role: null, permissions: [] };
  try {
    const parsed = JSON.parse(rawCookieValue) as { role?: string | null; permissions?: string[] };
    return {
      role: parsed.role ?? null,
      permissions: Array.isArray(parsed.permissions) ? parsed.permissions : [],
    };
  } catch {
    return { role: null, permissions: [] };
  }
}
