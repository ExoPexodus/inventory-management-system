/** Base URL for server-side calls to the central API (Docker service name on the compose network). */
export function internalApiUrl(): string {
  const u = process.env.API_INTERNAL_URL ?? process.env.API_URL ?? "http://localhost:8001";
  return u.replace(/\/$/, "");
}

/** Base URL for server-side calls to the platform service (billing / downloads). */
export function internalPlatformUrl(): string {
  const u = process.env.PLATFORM_INTERNAL_URL ?? "http://localhost:8002";
  return u.replace(/\/$/, "");
}
