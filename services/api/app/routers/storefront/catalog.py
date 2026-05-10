"""Storefront catalog: product listing and detail endpoints."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models import Category, Product, ProductCategory, ProductImage
from app.routers.storefront.auth import StorefrontChannelDep
from app.services.product_search import make_tsquery

router = APIRouter(prefix="/v1/storefront", tags=["Storefront Catalog"])


class StorefrontCategoryOut(BaseModel):
    id: UUID
    slug: str
    name: str
    parent_id: UUID | None
    description: str | None
    sort_order: int

    model_config = {"from_attributes": True}


class StorefrontImageOut(BaseModel):
    url: str
    alt_text: str | None
    sort_order: int

    model_config = {"from_attributes": True}


class StorefrontProductOut(BaseModel):
    id: UUID
    name: str
    slug: str | None
    subtitle: str | None
    ribbon: str | None
    description: str | None
    short_description: str | None
    product_type: str
    status: str
    sku: str
    unit_price_cents: int
    discount_price_cents: int | None
    currency_code: str
    image_url: str | None
    images: list[StorefrontImageOut] | None = None
    tags: list[str] | None
    track_quantity: bool
    weight_grams: int | None
    shipping_class: str | None
    digital_files: list[dict] | None
    gift_card_amounts_cents: list[int] | None
    gift_card_expiry_months: int | None
    meta_title: str | None
    meta_description: str | None

    model_config = {"from_attributes": True}


class ProductListOut(BaseModel):
    items: list[StorefrontProductOut]
    total: int
    page: int
    per_page: int


# Correlated scalar subquery: first gallery image URL per product (sort_order ASC).
# Used by list_products to avoid loading full galleries for every product on the page.
_first_image_subq = (
    select(ProductImage.url)
    .where(ProductImage.product_id == Product.id)
    .order_by(ProductImage.sort_order.asc(), ProductImage.created_at.asc())
    .limit(1)
    .correlate(Product)
    .scalar_subquery()
)


def _to_out_list(product: Product, currency: str, first_image_url: str | None) -> StorefrontProductOut:
    """Build a list-context response. images is always null to avoid over-fetching."""
    return StorefrontProductOut(
        id=product.id,
        name=product.name,
        slug=product.slug,
        subtitle=product.subtitle,
        ribbon=product.ribbon,
        description=product.description,
        short_description=product.short_description,
        product_type=product.product_type,
        status=product.status,
        sku=product.sku,
        unit_price_cents=product.unit_price_cents,
        discount_price_cents=product.discount_price_cents,
        currency_code=currency,
        image_url=product.image_url or first_image_url,
        images=None,
        tags=product.tags,
        track_quantity=product.track_quantity,
        weight_grams=product.weight_grams,
        shipping_class=product.shipping_class,
        digital_files=product.digital_files,
        gift_card_amounts_cents=product.gift_card_amounts_cents,
        gift_card_expiry_months=product.gift_card_expiry_months,
        meta_title=product.meta_title,
        meta_description=product.meta_description,
    )


def _to_out_detail(product: Product, currency: str) -> StorefrontProductOut:
    """Build a detail-context response. images is the full gallery sorted by sort_order."""
    gallery = [
        StorefrontImageOut(url=img.url, alt_text=img.alt_text, sort_order=img.sort_order)
        for img in product.images
    ]
    first_gallery_url = gallery[0].url if gallery else None
    return StorefrontProductOut(
        id=product.id,
        name=product.name,
        slug=product.slug,
        subtitle=product.subtitle,
        ribbon=product.ribbon,
        description=product.description,
        short_description=product.short_description,
        product_type=product.product_type,
        status=product.status,
        sku=product.sku,
        unit_price_cents=product.unit_price_cents,
        discount_price_cents=product.discount_price_cents,
        currency_code=currency,
        image_url=product.image_url or first_gallery_url,
        images=gallery,
        tags=product.tags,
        track_quantity=product.track_quantity,
        weight_grams=product.weight_grams,
        shipping_class=product.shipping_class,
        digital_files=product.digital_files,
        gift_card_amounts_cents=product.gift_card_amounts_cents,
        gift_card_expiry_months=product.gift_card_expiry_months,
        meta_title=product.meta_title,
        meta_description=product.meta_description,
    )


@router.get("/categories", response_model=list[StorefrontCategoryOut])
def list_categories(
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db)],
) -> list[StorefrontCategoryOut]:
    """Return all categories for the channel's tenant, ordered by sort_order then name."""
    rows = db.execute(
        select(Category)
        .where(Category.tenant_id == channel.tenant_id)
        .order_by(Category.sort_order.asc(), Category.name.asc())
    ).scalars().all()
    return [StorefrontCategoryOut.model_validate(r) for r in rows]


# Sort columns whitelist — maps the public sort_by values to ORM columns.
# Anything outside this set falls back to `created_at`.
_SORTABLE_COLUMNS: dict[str, "object"] = {
    "created_at": Product.created_at,
    "unit_price_cents": Product.unit_price_cents,
    "name": Product.name,
    "discount_price_cents": Product.discount_price_cents,
}


def _collect_descendant_ids(
    all_cats: list[Category], root_id: UUID
) -> set[UUID]:
    """Return root_id and all descendant category IDs via BFS."""
    # Build parent_id -> [child ids] map
    children: dict[UUID | None, list[UUID]] = {}
    for cat in all_cats:
        children.setdefault(cat.parent_id, []).append(cat.id)

    result: set[UUID] = set()
    queue = [root_id]
    while queue:
        current = queue.pop()
        result.add(current)
        for child_id in children.get(current, []):
            if child_id not in result:
                queue.append(child_id)
    return result


@router.get("/products", response_model=ProductListOut)
def list_products(
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db)],
    q: str | None = None,
    product_type: str | None = None,
    tags: list[str] | None = Query(default=None, alias="tags[]"),
    min_price_cents: int | None = Query(default=None, ge=0),
    max_price_cents: int | None = Query(default=None, ge=0),
    sort_by: str | None = Query(default=None),
    sort_order: str | None = Query(default=None),
    category_slug: str | None = None,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
) -> ProductListOut:
    base_where = [
        Product.tenant_id == channel.tenant_id,
        Product.status == "active",
    ]
    ts_query: str | None = None
    if q and q.strip():
        ts_query = make_tsquery(q)
        if ts_query:
            base_where.append(
                Product.search_vector.op("@@")(func.to_tsquery("simple", ts_query))
            )
    if product_type:
        base_where.append(Product.product_type == product_type)

    # Category slug filter — finds the category, collects all descendant IDs,
    # then filters products via the product_categories join.
    if category_slug and category_slug.strip():
        all_cats = db.execute(
            select(Category).where(Category.tenant_id == channel.tenant_id)
        ).scalars().all()
        matched = next((c for c in all_cats if c.slug == category_slug.strip()), None)
        if matched is None:
            # Slug doesn't match any category — return empty result set
            return ProductListOut(items=[], total=0, page=page, per_page=per_page)
        descendant_ids = _collect_descendant_ids(all_cats, matched.id)
        cat_product_subq = (
            select(ProductCategory.product_id)
            .where(ProductCategory.category_id.in_(descendant_ids))
            .scalar_subquery()
        )
        base_where.append(Product.id.in_(cat_product_subq))

    # Tag filter — OR match using PostgreSQL JSONB `?` operator per tag.
    # Product.tags is JSONB storing a list of string slugs.
    if tags:
        tag_clauses = [Product.tags.op("?")(t) for t in tags if t]
        if tag_clauses:
            base_where.append(or_(*tag_clauses))

    # Price range — inclusive bounds on unit_price_cents (the display price).
    if min_price_cents is not None:
        base_where.append(Product.unit_price_cents >= min_price_cents)
    if max_price_cents is not None:
        base_where.append(Product.unit_price_cents <= max_price_cents)

    # Sorting — validated against whitelist; default = created_at desc.
    sort_col_key = sort_by if sort_by in _SORTABLE_COLUMNS else "created_at"
    sort_col = _SORTABLE_COLUMNS[sort_col_key]
    # Default direction: desc for created_at, asc otherwise.
    if sort_order in ("asc", "desc"):
        direction = sort_order
    else:
        direction = "desc" if sort_col_key == "created_at" else "asc"

    # When sorting by discount_price_cents, exclude products without a discount.
    # The intent is "show me only discounted products, cheapest first".
    if sort_col_key == "discount_price_cents":
        base_where.append(Product.discount_price_cents.isnot(None))

    total = db.execute(
        select(func.count(Product.id)).where(*base_where)
    ).scalar_one()

    # When a text search is active and the caller hasn't asked for a specific sort,
    # order by relevance (ts_rank DESC) instead of the default created_at.
    if ts_query and not sort_by:
        order_clause = func.ts_rank(
            Product.search_vector, func.to_tsquery("simple", ts_query)
        ).desc()
    else:
        order_clause = sort_col.asc() if direction == "asc" else sort_col.desc()

    rows = db.execute(
        select(Product, _first_image_subq.label("first_image_url"))
        .where(*base_where)
        .order_by(order_clause)
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()

    items = [_to_out_list(row[0], channel.currency_code, row[1]) for row in rows]
    return ProductListOut(items=items, total=total, page=page, per_page=per_page)


@router.get("/products/{product_slug_or_id}", response_model=StorefrontProductOut)
def get_product(
    product_slug_or_id: str,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db)],
) -> StorefrontProductOut:
    product = None
    try:
        uid = UUID(product_slug_or_id)
        product = db.execute(
            select(Product)
            .options(selectinload(Product.images))
            .where(
                Product.id == uid,
                Product.tenant_id == channel.tenant_id,
                Product.status == "active",
            )
        ).scalar_one_or_none()
    except ValueError:
        pass

    if product is None:
        product = db.execute(
            select(Product)
            .options(selectinload(Product.images))
            .where(
                Product.slug == product_slug_or_id,
                Product.tenant_id == channel.tenant_id,
                Product.status == "active",
            )
        ).scalar_one_or_none()

    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    return _to_out_detail(product, channel.currency_code)
