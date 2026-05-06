"""JSON shape checks for admin web console DTOs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from app.routers.admin_web import (
    CreateProductResponse,
    DashboardSummaryOut,
    ProductListItem,
    RecentActivityItem,
    SalesSeriesPoint,
    SalesSeriesResponse,
    StockMovementListResponse,
    StockMovementOut,
    SupplierOut,
)


def test_dashboard_summary_json_shape() -> None:
    now = datetime.now(UTC)
    m = DashboardSummaryOut(
        posted_transaction_count=3,
        gross_sales_cents=9900,
        stock_alert_count=1,
        supplier_count=2,
        shop_count=1,
        product_count=5,
        tenant_count=1,
        recent_activity=[
            RecentActivityItem(
                kind="transaction",
                ref_id=uuid4(),
                created_at=now.isoformat(),
                detail="sale:posted:3300",
            )
        ],
    )
    d = json.loads(m.model_dump_json())
    assert d["gross_sales_cents"] == 9900
    assert d["tenant_count"] == 1
    assert d["recent_activity"][0]["kind"] == "transaction"


def test_sales_series_response() -> None:
    r = SalesSeriesResponse(
        points=[
            SalesSeriesPoint(day="2025-03-01", gross_cents=100, transaction_count=2),
        ]
    )
    assert "points" in json.loads(r.model_dump_json())


def test_stock_movement_list() -> None:
    mid = uuid4()
    now = datetime.now(UTC)
    r = StockMovementListResponse(
        items=[
            StockMovementOut(
                id=mid,
                tenant_id=uuid4(),
                shop_id=uuid4(),
                shop_name="S",
                product_id=uuid4(),
                product_sku="X",
                product_name="P",
                quantity_delta=-1,
                movement_type="sale",
                transaction_id=uuid4(),
                created_at=now,
            )
        ],
        next_cursor="abc",
    )
    body = json.loads(r.model_dump_json())
    assert body["items"][0]["movement_type"] == "sale"
    assert body["next_cursor"] == "abc"


def test_supplier_out() -> None:
    s = SupplierOut(
        id=uuid4(),
        tenant_id=uuid4(),
        name="Acme",
        status="active",
        contact_email="a@b.co",
        contact_phone=None,
        notes=None,
        created_at=datetime.now(UTC),
    )
    assert json.loads(s.model_dump_json())["name"] == "Acme"


def test_create_product_response_includes_catalog_fields() -> None:
    r = CreateProductResponse(
        id=uuid4(),
        tenant_id=uuid4(),
        sku="SKU-99",
        name="Chai",
        unit_price_cents=2500,
        category="Beverages",
        barcode="8901234567890",
        cost_price_cents=1500,
        mrp_cents=3000,
        hsn_code="2101",
        negative_inventory_allowed=False,
    )
    d = r.model_dump(mode="json")
    assert d["barcode"] == "8901234567890"
    assert d["cost_price_cents"] == 1500
    assert d["mrp_cents"] == 3000
    assert d["hsn_code"] == "2101"
    assert d["negative_inventory_allowed"] is False


def test_product_list_item_includes_catalog_fields() -> None:
    item = ProductListItem(
        id=uuid4(),
        sku="SKU-1",
        name="Widget",
        status="active",
        category=None,
        unit_price_cents=500,
        reorder_point=0,
        barcode="1234567890123",
        cost_price_cents=250,
        mrp_cents=600,
    )
    d = item.model_dump(mode="json")
    assert d["barcode"] == "1234567890123"
    assert d["cost_price_cents"] == 250
    assert d["mrp_cents"] == 600


def test_product_detail_out_schema() -> None:
    from app.routers.admin_catalog import ProductDetailOut

    p = ProductDetailOut(
        id=uuid4(),
        tenant_id=uuid4(),
        sku="WIDGET-01",
        name="Widget",
        product_type="physical",
        status="active",
        unit_price_cents=1999,
        discount_price_cents=None,
        subtitle=None,
        ribbon=None,
        short_description=None,
        description=None,
        tags=[],
        track_quantity=True,
        weight_grams=None,
        shipping_class=None,
        digital_files=None,
        gift_card_amounts_cents=None,
        gift_card_expiry_months=None,
        additional_info_sections=[],
        slug=None,
        meta_title=None,
        meta_description=None,
        og_image_url=None,
        image_url=None,
        images=[],
        category=None,
        product_group_id=None,
        cost_price_cents=None,
        mrp_cents=None,
        barcode=None,
        hsn_code=None,
        negative_inventory_allowed=False,
        reorder_point=0,
        created_at=datetime.now(UTC),
    )
    d = p.model_dump(mode="json")
    assert d["product_type"] == "physical"
    assert d["track_quantity"] is True
    assert d["tags"] == []


def test_localisation_settings_schema() -> None:
    from app.routers.admin_platform import LocalisationSettingsOut

    out = LocalisationSettingsOut(timezone="Asia/Kolkata", financial_year_start_month=4)
    d = out.model_dump(mode="json")
    assert d["timezone"] == "Asia/Kolkata"
    assert d["financial_year_start_month"] == 4

    null_out = LocalisationSettingsOut(timezone=None, financial_year_start_month=None)
    d2 = null_out.model_dump(mode="json")
    assert d2["timezone"] is None
    assert d2["financial_year_start_month"] is None


def test_shop_out_includes_timezone() -> None:
    from app.routers.admin_shops import ShopOut

    s = ShopOut(
        id=uuid4(),
        tenant_id=uuid4(),
        name="Test Shop",
        default_tax_rate_bps=0,
        auto_resolve_shortage_cents_override=None,
        auto_resolve_overage_cents_override=None,
        timezone="Asia/Jakarta",
    )
    d = s.model_dump(mode="json")
    assert d["timezone"] == "Asia/Jakarta"

    s_null = ShopOut(
        id=uuid4(),
        tenant_id=uuid4(),
        name="Test Shop",
        default_tax_rate_bps=0,
        auto_resolve_shortage_cents_override=None,
        auto_resolve_overage_cents_override=None,
    )
    assert s_null.model_dump(mode="json")["timezone"] is None


def test_customer_group_out_schema() -> None:
    from app.routers.admin_customers import CustomerGroupOut

    g = CustomerGroupOut(
        id=uuid4(),
        tenant_id=uuid4(),
        name="VIP",
        colour="#7C3AED",
        created_at=datetime.now(UTC),
    )
    d = g.model_dump(mode="json")
    assert d["name"] == "VIP"
    assert d["colour"] == "#7C3AED"


def test_customer_out_schema() -> None:
    from app.routers.admin_customers import CustomerOut

    c = CustomerOut(
        id=uuid4(),
        tenant_id=uuid4(),
        group_id=None,
        group_name=None,
        phone="9876543210",
        name="Rajesh Kumar",
        email=None,
        city=None,
        created_at=datetime.now(UTC),
    )
    d = c.model_dump(mode="json")
    assert d["phone"] == "9876543210"
    assert d["name"] == "Rajesh Kumar"
    assert d["group_id"] is None


def test_tenant_feature_override_out_schema() -> None:
    from app.routers.admin_entitlements import TenantFeatureOverrideOut

    o = TenantFeatureOverrideOut(
        id=uuid4(),
        tenant_id=uuid4(),
        feature_key="headless_api",
        value=True,
        reason="Beta access for design partner",
        expires_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    d = o.model_dump(mode="json")
    assert d["feature_key"] == "headless_api"
    assert d["value"] is True
    assert d["reason"] == "Beta access for design partner"


def test_feature_flag_out_schema() -> None:
    from app.routers.admin_entitlements import FeatureFlagOut

    f = FeatureFlagOut(
        id=uuid4(),
        key="stock_reservations_enabled",
        default_state=False,
        rollout_rules={"percent": 25, "allowlist": []},
        description="Soft TTL stock reservation engine",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    d = f.model_dump(mode="json")
    assert d["key"] == "stock_reservations_enabled"
    assert d["default_state"] is False
    assert d["rollout_rules"]["percent"] == 25


def test_channel_out_schema() -> None:
    from app.routers.admin_channels import ChannelOut

    c = ChannelOut(
        id=uuid4(),
        tenant_id=uuid4(),
        type="pos",
        name="POS at Main Street",
        status="active",
        config={},
        inventory_pool_id=uuid4(),
        currency_code="INR",
        shop_id=uuid4(),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    d = c.model_dump(mode="json")
    assert d["type"] == "pos"
    assert d["status"] == "active"
    assert d["currency_code"] == "INR"


def test_inventory_pool_out_schema() -> None:
    from app.routers.admin_inventory_pools import InventoryPoolOut

    p = InventoryPoolOut(
        id=uuid4(),
        tenant_id=uuid4(),
        name="All Shops",
        fulfillment_policy="fulfill_from_primary",
        shop_ids=[uuid4(), uuid4()],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    d = p.model_dump(mode="json")
    assert d["name"] == "All Shops"
    assert len(d["shop_ids"]) == 2
    assert d["fulfillment_policy"] == "fulfill_from_primary"


def test_stock_reservation_out_schema() -> None:
    from app.routers.admin_reservations import StockReservationOut

    r = StockReservationOut(
        id=uuid4(),
        tenant_id=uuid4(),
        channel_id=uuid4(),
        product_id=uuid4(),
        shop_id=uuid4(),
        quantity=3,
        cart_token="cart_abc123",
        purpose="cart",
        status="active",
        expires_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    d = r.model_dump(mode="json")
    assert d["quantity"] == 3
    assert d["status"] == "active"
    assert d["purpose"] == "cart"


def test_product_price_out_schema() -> None:
    from app.routers.admin_product_prices import ProductPriceOut

    p = ProductPriceOut(
        id=uuid4(),
        tenant_id=uuid4(),
        product_id=uuid4(),
        channel_id=None,
        currency_code="USD",
        amount_cents=1999,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    d = p.model_dump(mode="json")
    assert d["currency_code"] == "USD"
    assert d["amount_cents"] == 1999


def test_fx_rate_out_schema() -> None:
    from app.routers.admin_fx_rates import FxRateOut

    r = FxRateOut(
        id=uuid4(),
        tenant_id=uuid4(),
        from_currency="USD",
        to_currency="INR",
        rate="83.250000",
        source="manual",
        effective_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    d = r.model_dump(mode="json")
    assert d["from_currency"] == "USD"
    assert d["to_currency"] == "INR"
    assert d["rate"] == "83.250000"


def test_shipping_zone_out_schema() -> None:
    from app.routers.admin_shipping import ShippingZoneOut

    z = ShippingZoneOut(
        id=uuid4(),
        tenant_id=uuid4(),
        channel_id=uuid4(),
        name="Domestic",
        countries=["IN"],
        is_catch_all=False,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    d = z.model_dump(mode="json")
    assert d["name"] == "Domestic"
    assert d["countries"] == ["IN"]
    assert d["is_catch_all"] is False


def test_shipping_rate_out_schema() -> None:
    from app.routers.admin_shipping import ShippingRateOut

    r = ShippingRateOut(
        id=uuid4(),
        tenant_id=uuid4(),
        zone_id=uuid4(),
        name="Standard",
        base_price_cents=500,
        currency_code="INR",
        free_above_cents=None,
        condition_type="none",
        condition_min=None,
        condition_max=None,
        applies_to_classes=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    d = r.model_dump(mode="json")
    assert d["name"] == "Standard"
    assert d["base_price_cents"] == 500


def test_tax_region_out_schema() -> None:
    from app.routers.admin_tax import TaxRegionOut

    r = TaxRegionOut(
        id=uuid4(),
        tenant_id=uuid4(),
        name="India GST",
        country_code="IN",
        state_code=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    d = r.model_dump(mode="json")
    assert d["country_code"] == "IN"
    assert d["state_code"] is None


def test_tax_rule_out_schema() -> None:
    from app.routers.admin_tax import TaxRuleOut

    r = TaxRuleOut(
        id=uuid4(),
        tenant_id=uuid4(),
        region_id=uuid4(),
        tax_class="standard",
        label="GST 18%",
        components=[{"label": "CGST", "rate_bps": 900}, {"label": "SGST", "rate_bps": 900}],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    d = r.model_dump(mode="json")
    assert d["tax_class"] == "standard"
    assert len(d["components"]) == 2
    assert d["components"][0]["rate_bps"] == 900
    assert d["condition_type"] == "none"


def test_business_type_out_schema() -> None:
    from app.routers.admin_business_type import BusinessTypeOut

    b = BusinessTypeOut(
        business_type="online",
        show_shops_management=False,
        show_pos_features=False,
        show_ecommerce_features=True,
        can_add_physical_store=True,
        can_add_online_channel=False,
    )
    d = b.model_dump(mode="json")
    assert d["business_type"] == "online"
    assert d["show_shops_management"] is False
    assert d["show_ecommerce_features"] is True
    assert d["can_add_physical_store"] is True


def test_discount_out_schema() -> None:
    from app.routers.admin_discounts import DiscountOut

    d = DiscountOut(
        id=uuid4(),
        tenant_id=uuid4(),
        channel_id=None,
        name="Summer Sale",
        code="SUMMER20",
        discount_type="percentage",
        value_bps=2000,
        value_cents=None,
        status="active",
        stackable=False,
        priority=0,
        min_subtotal_cents=None,
        max_uses_total=None,
        max_uses_per_customer=None,
        starts_at=None,
        expires_at=None,
        times_used=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    dumped = d.model_dump(mode="json")
    assert dumped["code"] == "SUMMER20"
    assert dumped["discount_type"] == "percentage"
    assert dumped["value_bps"] == 2000
    assert dumped["times_used"] == 0
