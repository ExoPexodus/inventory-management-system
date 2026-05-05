"""Plan-codename -> feature-value mapping (config-as-code).

This is the LOCAL source of truth for "what does the 'pro' plan include?" until
the platform service grows a UI for editing this. Then the body of
``resolve_plan_value`` becomes the single seam to swap to a platform-synced
source (read from TenantLicenseCache.raw_payload's plan_features sub-object).

Codenames must match what the platform service emits in
TenantLicenseCache.plan_codename. See license_service.py.
"""
from __future__ import annotations

from typing import Any

from app.billing.features import resolve_default


# Per-plan overrides of catalog defaults. Anything not listed here falls back
# to FEATURE_CATALOG's default. Use the smallest possible set to keep
# review surface low; a missing entry means "use the default".
PLAN_FEATURES: dict[str, dict[str, Any]] = {
    # Trial = Pro for evaluation purposes
    "trial": {
        "max_channels": 5,
        "shopify_connector": True,
        "woocommerce_connector": True,
        "headless_api": True,
        "hosted_checkout": True,
        "byo_stripe": True,
        "byo_razorpay": True,
        "byo_paypal": True,
        "max_products": 1000,
        "multi_currency_advanced": True,
        "ai_product_generation": True,
        "email_volume_per_month": 5000,
    },
    "free": {
        "max_channels": 1,
        # everything else uses defaults (most flags off)
    },
    "starter": {
        "max_channels": 2,
        "shopify_connector": True,
        "woocommerce_connector": True,
        "max_products": 500,
        "byo_stripe": True,
        "email_volume_per_month": 1000,
    },
    "pro": {
        "max_channels": 5,
        "shopify_connector": True,
        "woocommerce_connector": True,
        "headless_api": True,
        "hosted_checkout": True,
        "byo_stripe": True,
        "byo_razorpay": True,
        "byo_paypal": True,
        "max_products": 5000,
        "multi_currency_advanced": True,
        "email_volume_per_month": 10000,
    },
    "business": {
        "max_channels": 20,
        "shopify_connector": True,
        "woocommerce_connector": True,
        "headless_api": True,
        "hosted_checkout": True,
        "byo_stripe": True,
        "byo_razorpay": True,
        "byo_paypal": True,
        "max_products": 50000,
        "multi_currency_advanced": True,
        "ai_product_generation": True,
        "email_volume_per_month": 100000,
    },
    # Legacy / unknown plans behave as catalog defaults (= mostly off, very limited)
}


def resolve_plan_value(plan_codename: str, feature_key: str) -> Any:
    """Resolve a feature value for a plan codename, falling back to the catalog default.

    This function is the single seam to replace when platform-side plan-feature
    management ships. The replacement reads from a per-tenant synced source
    (e.g. ``TenantLicenseCache.raw_payload``'s ``plan_features`` sub-object).
    The function body is the swap point — call-site signatures may need to grow
    a context parameter (e.g. ``LicenseContext`` or ``tenant_id``) at that time.
    """
    plan = PLAN_FEATURES.get(plan_codename)
    if plan is not None and feature_key in plan:
        return plan[feature_key]
    return resolve_default(feature_key)
