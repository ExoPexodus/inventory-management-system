from __future__ import annotations

import pytest


def test_feature_catalog_keys_unique() -> None:
    from app.billing.features import FEATURE_CATALOG
    keys = [f.key for f in FEATURE_CATALOG]
    assert len(keys) == len(set(keys)), "Duplicate keys in FEATURE_CATALOG"


def test_feature_catalog_has_known_features() -> None:
    from app.billing.features import FEATURE_CATALOG
    keys = {f.key for f in FEATURE_CATALOG}
    # These are the bare-minimum entries the e-commerce pivot relies on.
    expected = {
        "max_channels",
        "shopify_connector",
        "woocommerce_connector",
        "headless_api",
        "hosted_checkout",
        "max_products",
    }
    missing = expected - keys
    assert not missing, f"Catalog missing expected feature keys: {missing}"


def test_feature_value_types_are_supported() -> None:
    from app.billing.features import FEATURE_CATALOG, ValueType
    for f in FEATURE_CATALOG:
        assert f.value_type in {ValueType.BOOL, ValueType.NUMERIC, ValueType.ENUM}, \
            f"Unsupported value_type on {f.key}: {f.value_type}"


def test_plan_map_lookup_falls_back_to_default() -> None:
    from app.billing.features import resolve_default
    from app.billing.plans import resolve_plan_value

    # An unknown plan codename should still resolve via the catalog default.
    val = resolve_plan_value("plan-that-does-not-exist", "headless_api")
    assert val == resolve_default("headless_api")


def test_plan_map_pro_plan_includes_headless_api() -> None:
    from app.billing.plans import resolve_plan_value
    assert resolve_plan_value("pro", "headless_api") is True


def test_plan_map_free_plan_does_not_include_headless_api() -> None:
    from app.billing.plans import resolve_plan_value
    assert resolve_plan_value("free", "headless_api") is False
