from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from app.auth.deps import OperatorContext
from app.models import Plan, PlanFeature, PlatformOperator
from app.routers.plans import (
    PlanCreate,
    PlanPatch,
    create_plan,
    delete_plan,
    get_plan_features,
    put_plan_features,
)


def _ctx(operator: PlatformOperator) -> OperatorContext:
    return OperatorContext(operator_id=operator.id, email=operator.email)


@pytest.fixture()
def plan(db: Session) -> Plan:
    p = Plan(
        codename=f"test-plan-{uuid.uuid4().hex[:6]}",
        display_name="Test Plan",
        base_price_cents=999_00,
        currency_code="INR",
        max_shops=3,
        max_employees=10,
        storage_limit_mb=1000,
        is_active=True,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@pytest.fixture()
def inactive_plan(db: Session) -> Plan:
    p = Plan(
        codename=f"inactive-plan-{uuid.uuid4().hex[:6]}",
        display_name="Inactive Plan",
        base_price_cents=0,
        currency_code="INR",
        max_shops=1,
        max_employees=5,
        storage_limit_mb=500,
        is_active=False,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


# ---------------------------------------------------------------------------
# GET /plans/{plan_id}/features
# ---------------------------------------------------------------------------


def test_get_plan_features_empty(db: Session, plan: Plan, platform_operator: PlatformOperator) -> None:
    result = get_plan_features(plan_id=plan.id, ctx=_ctx(platform_operator), db=db)
    assert result == {}


def test_get_plan_features_returns_values(db: Session, plan: Plan, platform_operator: PlatformOperator) -> None:
    db.add(PlanFeature(plan_id=plan.id, feature_key="max_products", value=100))
    db.add(PlanFeature(plan_id=plan.id, feature_key="allow_ecommerce", value=True))
    db.commit()

    result = get_plan_features(plan_id=plan.id, ctx=_ctx(platform_operator), db=db)
    assert result["max_products"] == 100
    assert result["allow_ecommerce"] is True


def test_get_plan_features_nonexistent_plan_raises(db: Session, platform_operator: PlatformOperator) -> None:
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        get_plan_features(plan_id=uuid.uuid4(), ctx=_ctx(platform_operator), db=db)
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# PUT /plans/{plan_id}/features
# ---------------------------------------------------------------------------


def test_put_plan_features_replaces_all(db: Session, plan: Plan, platform_operator: PlatformOperator) -> None:
    # Pre-seed a feature that should be replaced
    db.add(PlanFeature(plan_id=plan.id, feature_key="old_key", value="old_value"))
    db.commit()

    # Patch feature_catalog to return None (no validation — accept any key)
    with patch("app.routers.plans.get_feature_catalog", return_value=None):
        result = put_plan_features(
            plan_id=plan.id,
            body={"max_products": 200, "allow_ecommerce": False},
            ctx=_ctx(platform_operator),
            db=db,
            apply_to_existing=False,
        )

    assert result == {"max_products": 200, "allow_ecommerce": False}

    # Verify old key is gone and new keys are present
    rows = db.query(PlanFeature).filter(PlanFeature.plan_id == plan.id).all()
    keys = {r.feature_key for r in rows}
    assert "old_key" not in keys
    assert "max_products" in keys
    assert "allow_ecommerce" in keys


def test_put_plan_features_validates_against_catalog(
    db: Session, plan: Plan, platform_operator: PlatformOperator
) -> None:
    """If catalog is available, unknown keys are rejected with 422."""
    from fastapi import HTTPException

    with patch("app.routers.plans.get_feature_catalog", return_value={"known_key": {}}):
        with pytest.raises(HTTPException) as exc_info:
            put_plan_features(
                plan_id=plan.id,
                body={"unknown_key": True},
                ctx=_ctx(platform_operator),
                db=db,
                apply_to_existing=False,
            )
    assert exc_info.value.status_code == 422


def test_put_plan_features_nonexistent_plan_raises(db: Session, platform_operator: PlatformOperator) -> None:
    from fastapi import HTTPException
    with patch("app.routers.plans.get_feature_catalog", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            put_plan_features(
                plan_id=uuid.uuid4(),
                body={"key": "val"},
                ctx=_ctx(platform_operator),
                db=db,
                apply_to_existing=False,
            )
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /plans/{plan_id}
# ---------------------------------------------------------------------------


def test_delete_inactive_plan_no_subscriptions(db: Session, inactive_plan: Plan, platform_operator: PlatformOperator) -> None:
    """Deleting an archived plan with no subscriptions should succeed."""
    delete_plan(plan_id=inactive_plan.id, ctx=_ctx(platform_operator), db=db)
    assert db.get(Plan, inactive_plan.id) is None


def test_delete_active_plan_rejected(db: Session, plan: Plan, platform_operator: PlatformOperator) -> None:
    """Deleting an active (is_active=True) plan should return 409."""
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        delete_plan(plan_id=plan.id, ctx=_ctx(platform_operator), db=db)
    assert exc_info.value.status_code == 409


def test_delete_nonexistent_plan_raises(db: Session, platform_operator: PlatformOperator) -> None:
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        delete_plan(plan_id=uuid.uuid4(), ctx=_ctx(platform_operator), db=db)
    assert exc_info.value.status_code == 404
