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


def test_resolve_plan_value_falls_back_to_default_when_no_cache() -> None:
    """resolve_plan_value returns the catalog default when no cache row exists."""
    from unittest.mock import MagicMock
    from sqlalchemy import select
    from app.billing.features import resolve_default
    from app.billing.plans import resolve_plan_value

    # Mock db that returns None for TenantLicenseCache lookup
    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = None

    import uuid
    tenant_id = uuid.uuid4()
    val = resolve_plan_value(mock_db, tenant_id, "headless_api")
    assert val == resolve_default("headless_api")


def test_resolve_plan_value_reads_from_cache() -> None:
    """resolve_plan_value returns the value from TenantLicenseCache.plan_features."""
    from unittest.mock import MagicMock
    from app.billing.plans import resolve_plan_value

    import uuid
    tenant_id = uuid.uuid4()

    # Simulate a cache row with plan_features populated
    mock_cache = MagicMock()
    mock_cache.plan_features = {"headless_api": True, "max_channels": 5}

    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = mock_cache

    assert resolve_plan_value(mock_db, tenant_id, "headless_api") is True
    assert resolve_plan_value(mock_db, tenant_id, "max_channels") == 5


def test_resolve_plan_value_falls_back_when_key_not_in_cache() -> None:
    """resolve_plan_value falls back to catalog default for unknown keys in cache."""
    from unittest.mock import MagicMock
    from app.billing.features import resolve_default
    from app.billing.plans import resolve_plan_value

    import uuid
    tenant_id = uuid.uuid4()

    mock_cache = MagicMock()
    mock_cache.plan_features = {}  # empty — key not present

    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = mock_cache

    val = resolve_plan_value(mock_db, tenant_id, "headless_api")
    assert val == resolve_default("headless_api")
