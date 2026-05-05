"""Feature catalog — config-as-code source of truth for what features exist.

This file declares every feature key that any part of the IMS may gate behind a plan
or override. Adding a new feature gate begins by adding an entry here. Lookups for
unknown keys return ``None`` from ``resolve_default``; the resolver in
``entitlements.py`` is the right place to surface a warning if that ever
happens at runtime.

Plan-codename -> value mapping lives in plans.py. Per-tenant overrides live in
the tenant_feature_overrides table. The resolver in entitlements.py merges the
three sources: tenant override > plan value > catalog default.

When platform-side plan management ships, the seam to swap is plans.py (single
file). This file stays untouched.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ValueType(str, Enum):
    BOOL = "bool"
    NUMERIC = "numeric"  # integer limit (e.g. max_channels)
    ENUM = "enum"        # one-of string (reserved for future)


@dataclass(frozen=True)
class FeatureDefinition:
    key: str
    value_type: ValueType
    default: Any
    description: str


# Canonical catalog. Order is irrelevant; the resolver looks up by key.
FEATURE_CATALOG: list[FeatureDefinition] = [
    # --- Channel + integration features (pivot Phase 1) ---
    FeatureDefinition(
        key="max_channels",
        value_type=ValueType.NUMERIC,
        default=1,
        description="Maximum number of sales channels (Shopify/Woo/headless/POS) per tenant",
    ),
    FeatureDefinition(
        key="shopify_connector",
        value_type=ValueType.BOOL,
        default=False,
        description="Allow connecting Shopify stores",
    ),
    FeatureDefinition(
        key="woocommerce_connector",
        value_type=ValueType.BOOL,
        default=False,
        description="Allow connecting WooCommerce stores",
    ),
    FeatureDefinition(
        key="headless_api",
        value_type=ValueType.BOOL,
        default=False,
        description="Allow custom storefronts to consume the public storefront REST/GraphQL API",
    ),
    FeatureDefinition(
        key="hosted_checkout",
        value_type=ValueType.BOOL,
        default=False,
        description="Allow IMS-hosted checkout for custom storefronts",
    ),
    FeatureDefinition(
        key="byo_stripe",
        value_type=ValueType.BOOL,
        default=False,
        description="Allow connecting a merchant's own Stripe account",
    ),
    FeatureDefinition(
        key="byo_razorpay",
        value_type=ValueType.BOOL,
        default=False,
        description="Allow connecting a merchant's own Razorpay account",
    ),
    FeatureDefinition(
        key="byo_paypal",
        value_type=ValueType.BOOL,
        default=False,
        description="Allow connecting a merchant's own PayPal account",
    ),
    # --- Catalog + commerce primitives (pivot Phase 0) ---
    FeatureDefinition(
        key="max_products",
        value_type=ValueType.NUMERIC,
        default=100,
        description="Maximum products in catalog",
    ),
    FeatureDefinition(
        key="multi_currency_advanced",
        value_type=ValueType.BOOL,
        default=False,
        description="Per-listing currency overrides + shopper-facing currency switching",
    ),
    FeatureDefinition(
        key="ai_product_generation",
        value_type=ValueType.BOOL,
        default=False,
        description="Generate product descriptions/images with AI",
    ),
    FeatureDefinition(
        key="email_volume_per_month",
        value_type=ValueType.NUMERIC,
        default=500,
        description="Transactional emails per month before throttling",
    ),
]


_BY_KEY: dict[str, FeatureDefinition] = {f.key: f for f in FEATURE_CATALOG}


def get_definition(key: str) -> FeatureDefinition | None:
    return _BY_KEY.get(key)


def resolve_default(key: str) -> Any:
    """Return the catalog default for a feature key, or None if unknown."""
    f = _BY_KEY.get(key)
    return f.default if f else None
