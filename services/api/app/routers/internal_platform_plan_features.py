"""Internal platform endpoint: read plan-feature values.

Returns the current plan-codename -> feature-key -> value mapping
so the platform-web UI can display it without reading plans.py directly.
Requires the X-Admin-Token header (or is open in dev when no token is configured).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.billing.features import FEATURE_CATALOG
from app.billing.plans import PLAN_FEATURES, resolve_plan_value
from app.config import settings

router = APIRouter(prefix="/v1/internal/platform", tags=["Internal Platform"])

PLAN_CODENAMES = sorted(set(list(PLAN_FEATURES.keys()) + ["legacy"]))


def _require_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    if not settings.admin_api_token:
        return  # open in dev
    if x_admin_token != settings.admin_api_token:
        raise HTTPException(status_code=401, detail="Invalid admin token")


class FeatureValueOut(BaseModel):
    key: str
    value_type: str
    description: str
    default: Any
    values: dict[str, Any]  # plan_codename -> value


@router.get(
    "/plan-features",
    response_model=list[FeatureValueOut],
    dependencies=[Depends(_require_admin_token)],
)
def get_plan_features() -> list[FeatureValueOut]:
    """Return every feature with its resolved value per known plan."""
    result = []
    for f in FEATURE_CATALOG:
        values = {plan: resolve_plan_value(plan, f.key) for plan in PLAN_CODENAMES}
        result.append(FeatureValueOut(
            key=f.key,
            value_type=f.value_type.value,
            description=f.description,
            default=f.default,
            values=values,
        ))
    return result
