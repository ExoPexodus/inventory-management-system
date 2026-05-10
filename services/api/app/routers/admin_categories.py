"""Admin endpoints for managing hierarchical product categories."""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Category, Product, ProductCategory

router = APIRouter(prefix="/v1/admin/categories", tags=["Admin Categories"])

# Separate router for product membership routes (prefix /v1/admin/products)
products_router = APIRouter(prefix="/v1/admin/products", tags=["Admin Categories"])

# ---------------------------------------------------------------------------
# Slug validation
# ---------------------------------------------------------------------------
_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def _slugify(value: str) -> str:
    """Convert an arbitrary string to a URL-safe slug."""
    s = value.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    s = s.strip("-")
    return s


def _validate_slug(slug: str) -> str:
    """Validate and return the slug; raise 400 if invalid."""
    if not _SLUG_RE.match(slug):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Invalid slug. Must contain only lowercase alphanumeric characters and "
                "hyphens, with no leading, trailing, or consecutive hyphens."
            ),
        )
    return slug


# ---------------------------------------------------------------------------
# Response / request schemas
# ---------------------------------------------------------------------------


class CategoryOut(BaseModel):
    id: UUID
    tenant_id: UUID
    parent_id: UUID | None
    slug: str
    name: str
    description: str | None
    sort_order: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(default=None, max_length=128)
    parent_id: UUID | None = None
    description: str | None = None
    sort_order: int = 0


class CategoryPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, max_length=128)
    parent_id: UUID | None = None
    description: str | None = None
    sort_order: int | None = None


class ReorderItem(BaseModel):
    id: UUID
    sort_order: int


class ReorderBody(BaseModel):
    items: list[ReorderItem] = Field(min_length=1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator not assigned to a tenant",
        )
    return ctx.tenant_id


def _get_category_or_404(db: Session, category_id: UUID, tenant_id: UUID) -> Category:
    cat = db.get(Category, category_id)
    if cat is None or cat.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return cat


def _validate_parent(
    db: Session, tenant_id: UUID, parent_id: UUID | None, self_id: UUID | None = None
) -> None:
    """Validate that parent_id exists within the tenant, is not self, and is not a descendant."""
    if parent_id is None:
        return

    # Can't parent to self
    if self_id is not None and parent_id == self_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A category cannot be its own parent.",
        )

    # Parent must exist and belong to this tenant
    parent = db.get(Category, parent_id)
    if parent is None or parent.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="parent_id does not exist in this tenant",
        )

    # Cycle check: walk up from the proposed parent; if we find self_id, it's a cycle
    if self_id is not None:
        visited: set[UUID] = set()
        current_id: UUID | None = parent_id
        hop = 0
        while current_id is not None and hop < 64:
            if current_id in visited:
                break
            if current_id == self_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Setting this parent would create a cycle in the category hierarchy.",
                )
            visited.add(current_id)
            row = db.get(Category, current_id)
            if row is None:
                break
            current_id = row.parent_id
            hop += 1


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[CategoryOut], dependencies=[require_permission("catalog:read")])
def list_categories(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> list[CategoryOut]:
    tenant_id = _require_tenant(ctx)
    rows = db.execute(
        select(Category)
        .where(Category.tenant_id == tenant_id)
        .order_by(Category.sort_order.asc(), Category.name.asc())
    ).scalars().all()
    return [CategoryOut.model_validate(r) for r in rows]


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED,
             dependencies=[require_permission("catalog:write")])
def create_category(
    body: CategoryCreate,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> CategoryOut:
    tenant_id = _require_tenant(ctx)

    # Resolve slug
    slug = body.slug if body.slug is not None else _slugify(body.name)
    if not slug:
        slug = "category-" + str(uuid.uuid4()).replace("-", "")[:6]
    _validate_slug(slug)

    _validate_parent(db, tenant_id, body.parent_id)

    cat = Category(
        tenant_id=tenant_id,
        parent_id=body.parent_id,
        slug=slug,
        name=body.name.strip(),
        description=body.description,
        sort_order=body.sort_order,
    )
    db.add(cat)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A category with this slug already exists in this tenant.",
        ) from None
    db.refresh(cat)
    return CategoryOut.model_validate(cat)


@router.patch("/{category_id}", response_model=CategoryOut,
              dependencies=[require_permission("catalog:write")])
def patch_category(
    category_id: UUID,
    body: CategoryPatch,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> CategoryOut:
    tenant_id = _require_tenant(ctx)
    cat = _get_category_or_404(db, category_id, tenant_id)

    patch = body.model_dump(exclude_unset=True)

    if "name" in patch and patch["name"] is not None:
        cat.name = patch["name"].strip()

    if "slug" in patch and patch["slug"] is not None:
        _validate_slug(patch["slug"])
        cat.slug = patch["slug"]

    if "description" in patch:
        cat.description = patch["description"]

    if "sort_order" in patch and patch["sort_order"] is not None:
        cat.sort_order = patch["sort_order"]

    if "parent_id" in patch:
        _validate_parent(db, tenant_id, patch["parent_id"], self_id=category_id)
        cat.parent_id = patch["parent_id"]

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A category with this slug already exists in this tenant.",
        ) from None
    db.refresh(cat)
    return CategoryOut.model_validate(cat)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[require_permission("catalog:write")])
def delete_category(
    category_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    cat = _get_category_or_404(db, category_id, tenant_id)

    # Orphan children to root before deleting (SET NULL via FK would work too, but
    # be explicit to avoid relying on FK trigger ordering)
    db.execute(
        Category.__table__.update()
        .where(Category.parent_id == category_id)
        .values(parent_id=None)
    )

    db.delete(cat)
    db.commit()


@router.post("/reorder", status_code=status.HTTP_204_NO_CONTENT,
             dependencies=[require_permission("catalog:write")])
def reorder_categories(
    body: ReorderBody,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> None:
    tenant_id = _require_tenant(ctx)
    ids = [item.id for item in body.items]

    # Validate all belong to this tenant
    found = db.execute(
        select(Category.id).where(Category.id.in_(ids), Category.tenant_id == tenant_id)
    ).scalars().all()
    found_set = set(found)
    missing = [str(i) for i in ids if i not in found_set]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Category IDs not found in tenant: {missing}",
        )

    for item in body.items:
        db.execute(
            Category.__table__.update()
            .where(Category.id == item.id)
            .values(sort_order=item.sort_order)
        )
    db.commit()


# ---------------------------------------------------------------------------
# Product membership endpoints
# ---------------------------------------------------------------------------


class ProductCategoriesOut(BaseModel):
    category_ids: list[UUID]


class ProductCategoriesIn(BaseModel):
    category_ids: list[UUID]


@products_router.get(
    "/{product_id}/categories",
    response_model=ProductCategoriesOut,
    dependencies=[require_permission("catalog:read")],
)
def get_product_categories(
    product_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ProductCategoriesOut:
    """Return the list of category IDs assigned to a product."""
    tenant_id = _require_tenant(ctx)

    # Ensure product exists and belongs to tenant
    prod = db.get(Product, product_id)
    if prod is None or prod.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    rows = db.execute(
        select(ProductCategory.category_id)
        .where(
            ProductCategory.product_id == product_id,
            ProductCategory.tenant_id == tenant_id,
        )
    ).scalars().all()
    return ProductCategoriesOut(category_ids=list(rows))


@products_router.put(
    "/{product_id}/categories",
    response_model=ProductCategoriesOut,
    dependencies=[require_permission("catalog:write")],
)
def set_product_categories(
    product_id: UUID,
    body: ProductCategoriesIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> ProductCategoriesOut:
    """Replace the full set of category memberships for a product."""
    tenant_id = _require_tenant(ctx)

    # Ensure product exists and belongs to tenant
    prod = db.get(Product, product_id)
    if prod is None or prod.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    # Validate all provided category_ids belong to this tenant BEFORE mutating
    if body.category_ids:
        found = db.execute(
            select(Category.id).where(
                Category.id.in_(body.category_ids),
                Category.tenant_id == tenant_id,
            )
        ).scalars().all()
        found_set = set(found)
        missing = [str(c) for c in body.category_ids if c not in found_set]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Category IDs not found in tenant: {missing}",
            )

    # Replace: delete existing rows, then insert new ones
    db.execute(
        delete(ProductCategory).where(
            ProductCategory.product_id == product_id,
            ProductCategory.tenant_id == tenant_id,
        )
    )

    for cat_id in body.category_ids:
        db.add(
            ProductCategory(
                tenant_id=tenant_id,
                product_id=product_id,
                category_id=cat_id,
            )
        )

    db.commit()

    rows = db.execute(
        select(ProductCategory.category_id)
        .where(
            ProductCategory.product_id == product_id,
            ProductCategory.tenant_id == tenant_id,
        )
    ).scalars().all()
    return ProductCategoriesOut(category_ids=list(rows))
