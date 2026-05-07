# NOTE: `from __future__ import annotations` deliberately absent.

import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Product, Tenant


@pytest.fixture()
def product(db, tenant: Tenant) -> Product:
    p = Product(
        tenant_id=tenant.id, name="T-Shirt", sku=f"tshirt-{uuid.uuid4().hex[:6]}",
        unit_price_cents=1999, product_type="physical", status="active",
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@pytest.fixture()
def auth(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin
    fake_ctx = AdminContext(
        user_id=None, tenant_id=tenant.id, role="owner", role_id=None,
        is_legacy_token=False, permissions=frozenset({"catalog:write"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield
    app.dependency_overrides.clear()


def test_create_variant(db, tenant: Tenant, product: Product, auth) -> None:
    resp = TestClient(app).post(
        f"/v1/admin/products/{product.id}/variants",
        json={"sku": f"ts-m-{uuid.uuid4().hex[:4]}", "name": "T-Shirt M",
              "options": {"size": "M", "colour": "Black"},
              "unit_price_cents": 1999},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["options"]["size"] == "M"
    assert body["product_id"] == str(product.id)


def test_list_variants(db, tenant: Tenant, product: Product, auth) -> None:
    client = TestClient(app)
    for size in ["S", "M", "L"]:
        client.post(f"/v1/admin/products/{product.id}/variants",
                    json={"sku": f"ts-{size}-{uuid.uuid4().hex[:4]}", "name": f"T-Shirt {size}",
                          "options": {"size": size}, "unit_price_cents": 1999})
    resp = client.get(f"/v1/admin/products/{product.id}/variants")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


def test_patch_variant(db, tenant: Tenant, product: Product, auth) -> None:
    client = TestClient(app)
    created = client.post(f"/v1/admin/products/{product.id}/variants",
                          json={"sku": f"ts-xl-{uuid.uuid4().hex[:4]}", "name": "T-Shirt XL",
                                "options": {"size": "XL"}, "unit_price_cents": 1999}).json()
    resp = client.patch(f"/v1/admin/products/{product.id}/variants/{created['id']}",
                        json={"unit_price_cents": 2499})
    assert resp.status_code == 200
    assert resp.json()["unit_price_cents"] == 2499


def test_delete_variant(db, tenant: Tenant, product: Product, auth) -> None:
    client = TestClient(app)
    created = client.post(f"/v1/admin/products/{product.id}/variants",
                          json={"sku": f"ts-del-{uuid.uuid4().hex[:4]}", "name": "Delete me",
                                "options": {}, "unit_price_cents": 999}).json()
    resp = client.delete(f"/v1/admin/products/{product.id}/variants/{created['id']}")
    assert resp.status_code == 204
    assert client.get(f"/v1/admin/products/{product.id}/variants").json() == []
