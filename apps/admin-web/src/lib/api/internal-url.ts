/** Base URL for server-side calls to the central API (Docker service name on the compose network). */
export function internalApiUrl(): string {
  const u = process.env.API_INTERNAL_URL ?? process.env.API_URL ?? "http://localhost:8001";
  return u.replace(/\/$/, "");
}
