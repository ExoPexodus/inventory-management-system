/** HttpOnly cookie storing operator JWT for server-side API calls and BFF proxy. */
export const OPERATOR_JWT_COOKIE = "ims_operator_jwt";
/** HttpOnly cookie storing resolved tenant slug for URL routing. */
export const OPERATOR_TENANT_SLUG_COOKIE = "ims_operator_tenant_slug";
/** Non-HttpOnly cookie carrying { role, permissions } for client-side gating (informational — API enforces truth). */
export const OPERATOR_META_COOKIE = "ims_operator_meta";
