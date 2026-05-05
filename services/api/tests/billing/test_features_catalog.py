from __future__ import annotations


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


def test_plan_numeric_values_locked() -> None:
    """Lock in commercial-tier numeric values.

    Bumping any of these is a deliberate pricing change. A test failure here
    forces a conscious decision rather than letting drift ship silently.
    """
    from app.billing.plans import resolve_plan_value
    assert resolve_plan_value("free", "max_channels") == 1
    assert resolve_plan_value("starter", "max_channels") == 2
    assert resolve_plan_value("pro", "max_channels") == 5
    assert resolve_plan_value("business", "max_channels") == 20
    assert resolve_plan_value("trial", "max_channels") == 5

    assert resolve_plan_value("starter", "max_products") == 500
    assert resolve_plan_value("pro", "max_products") == 5000
    assert resolve_plan_value("business", "max_products") == 50000

    assert resolve_plan_value("starter", "email_volume_per_month") == 1000
    assert resolve_plan_value("pro", "email_volume_per_month") == 10000
    assert resolve_plan_value("business", "email_volume_per_month") == 100000


def test_starter_plan_does_not_include_headless_api() -> None:
    """Exercises the plan-dict-hit path for a False feature gate (vs the
    fallback path tested by test_plan_map_free_plan_does_not_include_headless_api)."""
    from app.billing.plans import resolve_plan_value
    assert resolve_plan_value("starter", "headless_api") is False
