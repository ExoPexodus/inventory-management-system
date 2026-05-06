# NOTE: `from __future__ import annotations` deliberately absent.

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Product, Tenant


@pytest.fixture()
def auth_headers(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=None,
        tenant_id=tenant.id,
        role="owner",
        role_id=None,
        is_legacy_token=False,
        permissions=frozenset({"catalog:read", "catalog:write"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def test_create_physical_product_with_enrichment(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/products", json={
        "sku": "WIDGET-001",
        "name": "Widget",
        "unit_price_cents": 1999,
        "product_type": "physical",
        "subtitle": "The best widget",
        "ribbon": "NEW",
        "discount_price_cents": 1499,
        "track_quantity": True,
        "tags": ["bestseller", "widget"],
        "weight_grams": 250,
        "shipping_class": "standard",
    }, headers=auth_headers)
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    assert body["product_type"] == "physical"
    assert body["subtitle"] == "The best widget"
    assert body["ribbon"] == "NEW"
    assert body["discount_price_cents"] == 1499
    assert body["tags"] == ["bestseller", "widget"]
    assert body["weight_grams"] == 250


def test_create_digital_product(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/products", json={
        "sku": "EBOOK-001",
        "name": "My eBook",
        "unit_price_cents": 999,
        "product_type": "digital",
        "track_quantity": False,
        "digital_files": [
            {"name": "ebook.pdf", "url": "https://cdn.example.com/ebook.pdf", "file_type": "pdf"},
        ],
    }, headers=auth_headers)
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    assert body["product_type"] == "digital"
    assert body["track_quantity"] is False
    assert len(body["digital_files"]) == 1


def test_create_donation_product(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/products", json={
        "sku": "DONATE-001",
        "name": "Plant a Tree",
        "unit_price_cents": 0,
        "product_type": "donation",
        "track_quantity": False,
    }, headers=auth_headers)
    assert resp.status_code in (200, 201), resp.text
    assert resp.json()["product_type"] == "donation"


def test_create_gift_card(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/products", json={
        "sku": "GC-001",
        "name": "Gift Card",
        "unit_price_cents": 0,
        "product_type": "gift_card",
        "gift_card_amounts_cents": [2500, 5000, 10000],
        "gift_card_expiry_months": 12,
        "track_quantity": False,
    }, headers=auth_headers)
    assert resp.status_code in (200, 201), resp.text
    body = resp.json()
    assert body["product_type"] == "gift_card"
    assert body["gift_card_amounts_cents"] == [2500, 5000, 10000]
    assert body["gift_card_expiry_months"] == 12


def test_list_products_includes_product_type(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    client.post("/v1/admin/products", json={
        "sku": "PHYS-01", "name": "Physical", "unit_price_cents": 100, "product_type": "physical",
    }, headers=auth_headers)
    client.post("/v1/admin/products", json={
        "sku": "DIG-01", "name": "Digital", "unit_price_cents": 50, "product_type": "digital",
        "track_quantity": False,
    }, headers=auth_headers)

    resp = client.get("/v1/admin/products", headers=auth_headers)
    assert resp.status_code == 200
    types = {p["product_type"] for p in resp.json()}
    assert "physical" in types
    assert "digital" in types


def test_default_product_type_is_physical(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/products", json={
        "sku": "LEGACY-01", "name": "Legacy Product", "unit_price_cents": 100,
    }, headers=auth_headers)
    assert resp.status_code in (200, 201)
    assert resp.json()["product_type"] == "physical"


def test_patch_adds_seo_fields(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    create = client.post("/v1/admin/products", json={
        "sku": "SEO-01", "name": "SEO Product", "unit_price_cents": 100,
    }, headers=auth_headers)
    product_id = create.json()["id"]

    resp = client.patch(f"/v1/admin/products/{product_id}", json={
        "slug": "seo-product",
        "meta_title": "Best SEO Product",
        "meta_description": "This is the best SEO product in the world.",
    }, headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == "seo-product"
    assert body["meta_title"] == "Best SEO Product"
