"""Internal platform endpoint: read feature catalog.

Returns the feature catalog (key → value_type, default, description) so the
platform-web UI can render type-appropriate inputs for each feature key.

Per-plan values are now managed in the platform DB via
`GET /v1/platform/plans/{id}/features` (platform service). This endpoint
only exposes the catalog schema — not per-plan values.

Requires the X-Admin-Token header (or is open in dev when no token is configured).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.billing.features import FEATURE_CATALOG
from app.config import settings

router = APIRouter(prefix="/v1/internal/platform", tags=["Internal Platform"])


def _require_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    if not settings.admin_api_token:
        return  # open in dev
    if x_admin_token != settings.admin_api_token:
        raise HTTPException(status_code=401, detail="Invalid admin token")


class FeatureCatalogOut(BaseModel):
    key: str
    value_type: str
    description: str
    default: Any


@router.get(
    "/plan-features",
    response_model=list[FeatureCatalogOut],
    dependencies=[Depends(_require_admin_token)],
)
def get_plan_features() -> list[FeatureCatalogOut]:
    """Return the feature catalog (schema only; no per-plan values).

    Per-plan values are managed in the platform DB and fetched per-plan via
    the platform service's GET /v1/platform/plans/{id}/features endpoint.
    """
    return [
        FeatureCatalogOut(
            key=f.key,
            value_type=f.value_type.value,
            description=f.description,
            default=f.default,
        )
        for f in FEATURE_CATALOG
    ]
