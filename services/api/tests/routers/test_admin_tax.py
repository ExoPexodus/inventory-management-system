# NOTE: `from __future__ import annotations` deliberately absent.

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import TaxRegion, TaxRule, Tenant


@pytest.fixture()
def auth_headers(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=None, tenant_id=tenant.id, role="owner", role_id=None,
        is_legacy_token=False, permissions=frozenset({"tax:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def test_create_tax_region(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/tax/regions", json={
        "name": "India GST", "country_code": "IN",
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["country_code"] == "IN"
    assert body["name"] == "India GST"
    assert body["state_code"] is None


def test_list_regions(db, tenant: Tenant, auth_headers) -> None:
    db.add(TaxRegion(tenant_id=tenant.id, name="UK VAT", country_code="GB"))
    db.commit()

    client = TestClient(app)
    resp = client.get("/v1/admin/tax/regions", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_create_rule(db, tenant: Tenant, auth_headers) -> None:
    region = TaxRegion(tenant_id=tenant.id, name="India", country_code="IN")
    db.add(region)
    db.commit()

    client = TestClient(app)
    resp = client.post(f"/v1/admin/tax/regions/{region.id}/rules", json={
        "tax_class": "standard",
        "label": "GST 18%",
        "components": [
            {"label": "CGST", "rate_bps": 900},
            {"label": "SGST", "rate_bps": 900},
        ],
    }, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["tax_class"] == "standard"
    assert len(body["components"]) == 2


def test_list_rules(db, tenant: Tenant, auth_headers) -> None:
    region = TaxRegion(tenant_id=tenant.id, name="India", country_code="IN")
    db.add(region)
    db.flush()
    db.add(TaxRule(
        tenant_id=tenant.id, region_id=region.id,
        tax_class="standard", label="GST 18%",
        components=[{"label": "GST", "rate_bps": 1800}],
    ))
    db.commit()

    client = TestClient(app)
    resp = client.get(f"/v1/admin/tax/regions/{region.id}/rules", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_delete_region(db, tenant: Tenant, auth_headers) -> None:
    region = TaxRegion(tenant_id=tenant.id, name="Doomed", country_code="ZZ")
    db.add(region)
    db.commit()

    client = TestClient(app)
    resp = client.delete(f"/v1/admin/tax/regions/{region.id}", headers=auth_headers)
    assert resp.status_code == 204


def test_delete_rule(db, tenant: Tenant, auth_headers) -> None:
    region = TaxRegion(tenant_id=tenant.id, name="India", country_code="IN")
    db.add(region)
    db.flush()
    rule = TaxRule(
        tenant_id=tenant.id, region_id=region.id,
        tax_class="standard", label="GST", components=[],
    )
    db.add(rule)
    db.commit()

    client = TestClient(app)
    resp = client.delete(f"/v1/admin/tax/regions/{region.id}/rules/{rule.id}", headers=auth_headers)
    assert resp.status_code == 204


def test_negative_rate_rejected(db, tenant: Tenant, auth_headers) -> None:
    region = TaxRegion(tenant_id=tenant.id, name="India", country_code="IN")
    db.add(region)
    db.commit()

    client = TestClient(app)
    resp = client.post(f"/v1/admin/tax/regions/{region.id}/rules", json={
        "tax_class": "standard", "label": "Bad",
        "components": [{"label": "GST", "rate_bps": -100}],
    }, headers=auth_headers)
    assert resp.status_code == 422
