"""Contract checks that don't require a database."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.routers.sync import AppliedEventResult, ProductDTO
from app.routers.transactions import TransactionLineOut, TransactionListResponse, TransactionOut
from app.services.sync_push import AppliedResult


def test_applied_result_includes_conflict_fields() -> None:
    pid = UUID("00000000-0000-0000-0000-000000000001")
    r = AppliedResult(
        "mut-1",
        None,
        "rejected",
        "insufficient_stock",
        {
            "code": "insufficient_stock",
            "product_id": str(pid),
            "available_quantity": 1,
            "requested_quantity": 3,
        },
    )
    assert r.conflict is not None
    assert r.conflict["code"] == "insufficient_stock"


def test_push_batch_response_model_json() -> None:
    m = AppliedEventResult(
        client_mutation_id="mut-1",
        server_transaction_id=None,
        status="rejected",
        detail="insufficient_stock",
        conflict={
            "code": "insufficient_stock",
            "available_quantity": 0,
            "requested_quantity": 2,
        },
    )
    payload = m.model_dump(mode="json", exclude_none=True)
    assert payload["status"] == "rejected"
    assert payload["conflict"]["available_quantity"] == 0


def test_product_dto_sync_pull_optional_variant_fields() -> None:
    pid = uuid4()
    gid = uuid4()
    p = ProductDTO(
        id=pid,
        sku="SKU-1",
        name="Widget",
        category="c",
        unit_price_cents=100,
        active=True,
        effective_tax_rate_bps=0,
        tax_exempt=False,
        product_group_id=gid,
        group_title="Family",
        variant_label="Size M",
    )
    out = p.model_dump(mode="json")
    assert out["group_title"] == "Family"
    assert out["variant_label"] == "Size M"
    minimal = ProductDTO(
        id=pid,
        sku="SKU-1",
        name="Widget",
        category=None,
        unit_price_cents=100,
        active=True,
        effective_tax_rate_bps=0,
        tax_exempt=False,
    ).model_dump(mode="json")
    assert minimal.get("product_group_id") is None


def test_transaction_list_response_json_shape() -> None:
    tid = uuid4()
    sid = uuid4()
    pid = uuid4()
    now = datetime.now(UTC)
    page = TransactionListResponse(
        items=[
            TransactionOut(
                id=tid,
                shop_id=sid,
                kind="sale",
                status="posted",
                total_cents=1099,
                tax_cents=99,
                client_mutation_id="m1",
                created_at=now,
                lines=[
                    TransactionLineOut(
                        product_id=pid,
                        product_sku="SKU-1",
                        product_name="Widget",
                        quantity=1,
                        unit_price_cents=1000,
                    )
                ],
                payments=[],
            )
        ],
        next_cursor="abc",
    )
    out = page.model_dump(mode="json")
    assert out["next_cursor"] == "abc"
    assert len(out["items"]) == 1
    assert out["items"][0]["tax_cents"] == 99
    assert out["items"][0]["lines"][0]["product_name"] == "Widget"


def test_product_dto_includes_new_catalog_fields() -> None:
    pid = uuid4()
    p = ProductDTO(
        id=pid,
        sku="SKU-1",
        name="Widget",
        category=None,
        unit_price_cents=100,
        active=True,
        effective_tax_rate_bps=0,
        tax_exempt=False,
        barcode="5901234123457",
        mrp_cents=120,
        negative_inventory_allowed=False,
    )
    out = p.model_dump(mode="json")
    assert out["barcode"] == "5901234123457"
    assert out["mrp_cents"] == 120
    assert out["negative_inventory_allowed"] is False

    minimal = ProductDTO(
        id=pid,
        sku="SKU-1",
        name="Widget",
        category=None,
        unit_price_cents=100,
        active=True,
        effective_tax_rate_bps=0,
        tax_exempt=False,
    )
    out2 = minimal.model_dump(mode="json")
    assert out2["barcode"] is None
    assert out2["mrp_cents"] is None
    assert out2["negative_inventory_allowed"] is False
