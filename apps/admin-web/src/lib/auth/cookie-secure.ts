/**
 * Whether the operator JWT cookie should use the Secure flag.
 *
 * With NODE_ENV=production (Docker default), `secure: true` breaks logins over plain HTTP
 * (e.g. http://localhost:3000) because browsers will not store or send the cookie.
 *
 * Use COOKIE_SECURE=true only when the admin site is served over HTTPS (or behind a proxy
 * that sets X-Forwarded-Proto: https).
 */
export function shouldUseSecureCookie(req: Request): boolean {
  if (process.env.COOKIE_SECURE === "true") return true;
  if (process.env.COOKIE_SECURE === "false") return false;
  const raw = req.headers.get("x-forwarded-proto");
  const proto = raw?.split(",")[0]?.trim().toLowerCase();
  return proto === "https";
}
