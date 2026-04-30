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
