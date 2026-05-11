# NOTE: `from __future__ import annotations` deliberately absent.

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Category, Product, Tenant


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


# ---------------------------------------------------------------------------
# Category CRUD
# ---------------------------------------------------------------------------


def test_create_category(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/categories", json={"name": "Electronics", "slug": "electronics"}, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Electronics"
    assert body["slug"] == "electronics"
    assert body["tenant_id"] == str(tenant.id)
    assert body["parent_id"] is None


def test_create_category_auto_slug(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/categories", json={"name": "Home & Garden"}, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    # slugify should produce "home-garden"
    assert resp.json()["slug"] == "home-garden"


def test_create_category_invalid_slug_rejected(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post(
        "/v1/admin/categories",
        json={"name": "Bad Slug", "slug": "Bad Slug!!"},
        headers=auth_headers,
    )
    assert resp.status_code == 400


def test_duplicate_slug_rejected(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    client.post("/v1/admin/categories", json={"name": "First", "slug": "dup-slug"}, headers=auth_headers)
    resp = client.post("/v1/admin/categories", json={"name": "Second", "slug": "dup-slug"}, headers=auth_headers)
    assert resp.status_code == 400


def test_list_categories(db, tenant: Tenant, auth_headers) -> None:
    db.add(Category(tenant_id=tenant.id, name="Cat A", slug="cat-a"))
    db.add(Category(tenant_id=tenant.id, name="Cat B", slug="cat-b"))
    db.commit()

    client = TestClient(app)
    resp = client.get("/v1/admin/categories", headers=auth_headers)
    assert resp.status_code == 200
    names = [c["name"] for c in resp.json()]
    assert "Cat A" in names
    assert "Cat B" in names


def test_patch_category_name(db, tenant: Tenant, auth_headers) -> None:
    cat = Category(tenant_id=tenant.id, name="Old Name", slug="old-name")
    db.add(cat)
    db.commit()

    client = TestClient(app)
    resp = client.patch(f"/v1/admin/categories/{cat.id}", json={"name": "New Name"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"


def test_delete_category(db, tenant: Tenant, auth_headers) -> None:
    cat = Category(tenant_id=tenant.id, name="Deletable", slug="deletable")
    db.add(cat)
    db.commit()

    client = TestClient(app)
    resp = client.delete(f"/v1/admin/categories/{cat.id}", headers=auth_headers)
    assert resp.status_code == 204


def test_reorder_categories(db, tenant: Tenant, auth_headers) -> None:
    cat1 = Category(tenant_id=tenant.id, name="C1", slug="c1", sort_order=0)
    cat2 = Category(tenant_id=tenant.id, name="C2", slug="c2", sort_order=1)
    db.add(cat1)
    db.add(cat2)
    db.commit()

    client = TestClient(app)
    resp = client.post(
        "/v1/admin/categories/reorder",
        json={"items": [
            {"id": str(cat1.id), "sort_order": 10},
            {"id": str(cat2.id), "sort_order": 5},
        ]},
        headers=auth_headers,
    )
    assert resp.status_code == 204


def test_reorder_with_unknown_id_rejected(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post(
        "/v1/admin/categories/reorder",
        json={"items": [{"id": str(uuid.uuid4()), "sort_order": 1}]},
        headers=auth_headers,
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Product membership endpoints
# ---------------------------------------------------------------------------


def test_get_product_categories_empty(db, tenant: Tenant, auth_headers) -> None:
    product = Product(tenant_id=tenant.id, sku=f"SKU-{uuid.uuid4().hex[:6]}", name="Widget", unit_price_cents=100)
    db.add(product)
    db.commit()

    client = TestClient(app)
    resp = client.get(f"/v1/admin/products/{product.id}/categories", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["category_ids"] == []


def test_set_product_categories(db, tenant: Tenant, auth_headers) -> None:
    product = Product(tenant_id=tenant.id, sku=f"SKU-{uuid.uuid4().hex[:6]}", name="Widget", unit_price_cents=100)
    cat = Category(tenant_id=tenant.id, name="CatX", slug=f"catx-{uuid.uuid4().hex[:4]}")
    db.add(product)
    db.add(cat)
    db.commit()

    client = TestClient(app)
    resp = client.put(
        f"/v1/admin/products/{product.id}/categories",
        json={"category_ids": [str(cat.id)]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert str(cat.id) in resp.json()["category_ids"]


def test_set_product_categories_unknown_category_rejected(db, tenant: Tenant, auth_headers) -> None:
    product = Product(tenant_id=tenant.id, sku=f"SKU-{uuid.uuid4().hex[:6]}", name="Widget", unit_price_cents=100)
    db.add(product)
    db.commit()

    client = TestClient(app)
    resp = client.put(
        f"/v1/admin/products/{product.id}/categories",
        json={"category_ids": [str(uuid.uuid4())]},
        headers=auth_headers,
    )
    assert resp.status_code == 400
