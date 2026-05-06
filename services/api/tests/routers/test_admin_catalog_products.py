# NOTE: `from __future__ import annotations` deliberately absent.

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Product, ProductImage, Tenant


@pytest.fixture()
def product(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id, sku=f"sku-{uuid.uuid4().hex[:6]}",
        name="Widget", unit_price_cents=1999, product_type="physical",
    )
    db.add(p)
    db.flush()
    return p


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


def test_get_product_detail(db, tenant: Tenant, product: Product, auth_headers) -> None:
    client = TestClient(app)
    resp = client.get(f"/v1/admin/catalog/products/{product.id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == str(product.id)
    assert body["product_type"] == "physical"
    assert body["track_quantity"] is True
    assert body["images"] == []


def test_get_product_detail_404_for_unknown(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.get(f"/v1/admin/catalog/products/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


def test_add_image_to_product(db, tenant: Tenant, product: Product, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post(f"/v1/admin/catalog/products/{product.id}/images", json={
        "url": "https://cdn.example.com/widget.jpg",
        "alt_text": "A beautiful widget",
        "sort_order": 0,
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["url"] == "https://cdn.example.com/widget.jpg"
    assert body["alt_text"] == "A beautiful widget"
    assert body["product_id"] == str(product.id)


def test_list_product_images(db, tenant: Tenant, product: Product, auth_headers) -> None:
    db.add(ProductImage(
        tenant_id=tenant.id, product_id=product.id,
        url="https://cdn.example.com/a.jpg", sort_order=1,
    ))
    db.add(ProductImage(
        tenant_id=tenant.id, product_id=product.id,
        url="https://cdn.example.com/b.jpg", sort_order=0,
    ))
    db.commit()

    client = TestClient(app)
    resp = client.get(f"/v1/admin/catalog/products/{product.id}/images", headers=auth_headers)
    assert resp.status_code == 200
    urls = [img["url"] for img in resp.json()]
    assert urls[0] == "https://cdn.example.com/b.jpg"  # sort_order=0 first


def test_delete_image(db, tenant: Tenant, product: Product, auth_headers) -> None:
    img = ProductImage(
        tenant_id=tenant.id, product_id=product.id,
        url="https://cdn.example.com/doomed.jpg", sort_order=0,
    )
    db.add(img)
    db.commit()

    client = TestClient(app)
    resp = client.delete(f"/v1/admin/catalog/products/{product.id}/images/{img.id}", headers=auth_headers)
    assert resp.status_code == 204


def test_cross_tenant_product_image_blocked(db, tenant: Tenant, auth_headers) -> None:
    other = Tenant(name=f"other-{uuid.uuid4().hex[:6]}", slug=f"other-{uuid.uuid4().hex[:8]}")
    db.add(other)
    db.flush()
    other_p = Product(
        tenant_id=other.id, sku=f"sku-{uuid.uuid4().hex[:6]}",
        name="Other", unit_price_cents=100,
    )
    db.add(other_p)
    db.commit()

    client = TestClient(app)
    resp = client.post(f"/v1/admin/catalog/products/{other_p.id}/images", json={
        "url": "https://cdn.example.com/stolen.jpg",
    }, headers=auth_headers)
    assert resp.status_code == 404
