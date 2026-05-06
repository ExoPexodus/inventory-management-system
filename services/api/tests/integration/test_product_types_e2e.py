"""End-to-end smoke test for product type expansion + catalog enrichment."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Product, Tenant


@pytest.fixture()
def auth(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=None, tenant_id=tenant.id,
        role="owner", role_id=None, is_legacy_token=False,
        permissions=frozenset({"catalog:read", "catalog:write"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield
    app.dependency_overrides.clear()


PRODUCT_TYPES = [
    ("PHYS-E2E",   "Physical Widget",    1999, "physical",  {"track_quantity": True,  "weight_grams": 200}),
    ("DIG-E2E",    "Digital eBook",       999, "digital",   {"track_quantity": False, "digital_files": [{"name": "ebook.pdf", "url": "https://cdn.test/book.pdf"}]}),
    ("SVC-E2E",    "Consultation",       5000, "service",   {"track_quantity": False}),
    ("DONATE-E2E", "Plant a Tree",          0, "donation",  {"track_quantity": False}),
    ("GC-E2E",     "Gift Card",             0, "gift_card", {"track_quantity": False, "gift_card_amounts_cents": [2500, 5000]}),
]


def test_all_five_product_types_create_successfully(db, tenant: Tenant, auth) -> None:
    client = TestClient(app)
    for sku, name, price, ptype, extra in PRODUCT_TYPES:
        body = {"sku": sku, "name": name, "unit_price_cents": price, "product_type": ptype, **extra}
        resp = client.post("/v1/admin/products", json=body)
        assert resp.status_code in (200, 201), f"{ptype}: {resp.text}"
        assert resp.json()["product_type"] == ptype


def test_product_type_service_aligns_with_created_products(db, tenant: Tenant, auth) -> None:
    from app.services.product_type_service import is_inventory_tracked, is_shippable

    client = TestClient(app)
    for sku, name, price, ptype, extra in PRODUCT_TYPES:
        body = {"sku": f"{sku}-SVC", "name": f"{name} SVC", "unit_price_cents": price,
                "product_type": ptype, **extra}
        resp = client.post("/v1/admin/products", json=body)
        track_qty = resp.json().get("track_quantity", True)

        shippable = is_shippable(ptype)
        tracked = is_inventory_tracked(ptype, track_quantity=track_qty)

        if ptype == "physical":
            assert shippable is True
            assert tracked is True
        elif ptype == "donation":
            assert shippable is False
            assert tracked is False
        elif ptype == "digital":
            assert shippable is False
            assert tracked is False  # track_quantity=False in fixture


def test_image_gallery_lifecycle(db, tenant: Tenant, auth) -> None:
    """Create product → add two images with sort_order → list ordered → delete one."""
    client = TestClient(app)

    resp = client.post("/v1/admin/products", json={
        "sku": "IMG-E2E", "name": "Image Gallery Widget", "unit_price_cents": 100,
    })
    assert resp.status_code in (200, 201)
    product_id = resp.json()["id"]

    i2 = client.post(f"/v1/admin/catalog/products/{product_id}/images", json={
        "url": "https://cdn.test/img2.jpg", "sort_order": 1,
    })
    i1 = client.post(f"/v1/admin/catalog/products/{product_id}/images", json={
        "url": "https://cdn.test/img1.jpg", "sort_order": 0,
    })
    assert i1.status_code == 201
    assert i2.status_code == 201
    image_id = i2.json()["id"]

    list_resp = client.get(f"/v1/admin/catalog/products/{product_id}/images")
    assert list_resp.status_code == 200
    urls = [img["url"] for img in list_resp.json()]
    assert urls[0] == "https://cdn.test/img1.jpg"
    assert urls[1] == "https://cdn.test/img2.jpg"

    detail_resp = client.get(f"/v1/admin/catalog/products/{product_id}")
    assert detail_resp.status_code == 200
    assert len(detail_resp.json()["images"]) == 2

    del_resp = client.delete(f"/v1/admin/catalog/products/{product_id}/images/{image_id}")
    assert del_resp.status_code == 204

    list_resp2 = client.get(f"/v1/admin/catalog/products/{product_id}/images")
    assert len(list_resp2.json()) == 1


def test_enrichment_fields_roundtrip(db, tenant: Tenant, auth) -> None:
    """Create product with enrichment fields, fetch via detail, confirm values."""
    client = TestClient(app)
    resp = client.post("/v1/admin/products", json={
        "sku": "ENRICH-E2E",
        "name": "Enriched Product",
        "unit_price_cents": 2999,
        "product_type": "physical",
        "subtitle": "The most enriched",
        "ribbon": "SALE",
        "discount_price_cents": 2499,
        "tags": ["sale", "featured"],
        "slug": "enriched-product",
        "meta_title": "Enriched Product | Shop",
        "weight_grams": 300,
        "shipping_class": "standard",
    })
    assert resp.status_code in (200, 201)
    product_id = resp.json()["id"]

    detail = client.get(f"/v1/admin/catalog/products/{product_id}")
    assert detail.status_code == 200
    d = detail.json()
    assert d["subtitle"] == "The most enriched"
    assert d["ribbon"] == "SALE"
    assert d["discount_price_cents"] == 2499
    assert d["tags"] == ["sale", "featured"]
    assert d["slug"] == "enriched-product"
    assert d["weight_grams"] == 300
