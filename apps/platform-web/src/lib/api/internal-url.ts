export function internalApiUrl(): string {
  const u = process.env.API_INTERNAL_URL ?? "http://localhost:8002";
  return u.replace(/\/$/, "");
}
