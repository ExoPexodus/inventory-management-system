# NOTE: `from __future__ import annotations` deliberately absent.

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, InventoryPool, InventoryPoolShop, Product, Shop, Tenant


@pytest.fixture()
def storefront(db, tenant: Tenant, shop: Shop):
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    channel = Channel(
        tenant_id=tenant.id, type="headless", name=f"headless-{uuid.uuid4().hex[:6]}",
        config={}, inventory_pool_id=pool.id, currency_code="INR",
    )
    db.add(channel)
    db.flush()
    p1 = Product(
        tenant_id=tenant.id, name="Widget Alpha", sku="SKU-A",
        unit_price_cents=1999, product_type="physical", status="active",
        slug="widget-alpha", tags=["bestseller"],
    )
    p2 = Product(
        tenant_id=tenant.id, name="Widget Beta", sku="SKU-B",
        unit_price_cents=2999, product_type="physical", status="active",
        slug="widget-beta",
    )
    p3 = Product(
        tenant_id=tenant.id, name="Draft Item", sku="SKU-D",
        unit_price_cents=999, product_type="physical", status="draft",
    )
    db.add(p1)
    db.add(p2)
    db.add(p3)
    db.commit()
    return {"channel": channel, "products": [p1, p2], "draft": p3}


def test_list_products_only_active(db, tenant: Tenant, storefront) -> None:
    client = TestClient(app)
    resp = client.get("/v1/storefront/products",
                      headers={"X-Channel-Id": str(storefront["channel"].id)})
    assert resp.status_code == 200, resp.text
    names = {p["name"] for p in resp.json()["items"]}
    assert "Widget Alpha" in names
    assert "Widget Beta" in names
    assert "Draft Item" not in names


def test_list_products_search(db, tenant: Tenant, storefront) -> None:
    client = TestClient(app)
    resp = client.get("/v1/storefront/products?q=Alpha",
                      headers={"X-Channel-Id": str(storefront["channel"].id)})
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "Widget Alpha"


def test_get_product_by_slug(db, tenant: Tenant, storefront) -> None:
    client = TestClient(app)
    resp = client.get("/v1/storefront/products/widget-alpha",
                      headers={"X-Channel-Id": str(storefront["channel"].id)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["slug"] == "widget-alpha"
    assert body["unit_price_cents"] == 1999


def test_get_product_by_id(db, tenant: Tenant, storefront) -> None:
    p = storefront["products"][0]
    client = TestClient(app)
    resp = client.get(f"/v1/storefront/products/{p.id}",
                      headers={"X-Channel-Id": str(storefront["channel"].id)})
    assert resp.status_code == 200
    assert resp.json()["id"] == str(p.id)


def test_unknown_channel_rejected(db, tenant: Tenant) -> None:
    client = TestClient(app)
    resp = client.get("/v1/storefront/products",
                      headers={"X-Channel-Id": str(uuid.uuid4())})
    assert resp.status_code == 404


def test_missing_channel_header_rejected(db, tenant: Tenant) -> None:
    client = TestClient(app)
    resp = client.get("/v1/storefront/products")
    assert resp.status_code == 422


def test_non_headless_channel_rejected(db, tenant: Tenant, shop: Shop) -> None:
    pool = InventoryPool(tenant_id=tenant.id, name=f"p-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    pos_ch = Channel(
        tenant_id=tenant.id, type="pos", name="POS",
        config={}, inventory_pool_id=pool.id, currency_code="INR", shop_id=shop.id,
    )
    db.add(pos_ch)
    db.commit()

    client = TestClient(app)
    resp = client.get("/v1/storefront/products",
                      headers={"X-Channel-Id": str(pos_ch.id)})
    assert resp.status_code == 403


def test_list_products_images_field_is_null(db, tenant: Tenant, storefront) -> None:
    """List endpoint never returns the images array — always null."""
    from app.db.session import get_db
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.get("/v1/storefront/products",
                          headers={"X-Channel-Id": str(storefront["channel"].id)})
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["images"] is None
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_list_products_image_url_from_gallery(db, tenant: Tenant, storefront) -> None:
    """image_url is populated from gallery when products.image_url is null."""
    from app.models import ProductImage
    from app.db.session import get_db
    product = storefront["products"][0]
    db.add(ProductImage(
        tenant_id=tenant.id, product_id=product.id,
        url="https://cdn.example.com/img1.jpg", sort_order=0,
    ))
    db.add(ProductImage(
        tenant_id=tenant.id, product_id=product.id,
        url="https://cdn.example.com/img2.jpg", sort_order=1,
    ))
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.get("/v1/storefront/products",
                          headers={"X-Channel-Id": str(storefront["channel"].id)})
        assert resp.status_code == 200
        item = next(i for i in resp.json()["items"] if i["id"] == str(product.id))
        assert item["image_url"] == "https://cdn.example.com/img1.jpg"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_detail_returns_full_gallery(db, tenant: Tenant, storefront) -> None:
    """Detail endpoint populates the images array in sort_order."""
    from app.models import ProductImage
    from app.db.session import get_db
    product = storefront["products"][0]
    db.add(ProductImage(
        tenant_id=tenant.id, product_id=product.id,
        url="https://cdn.example.com/a.jpg", sort_order=1,
    ))
    db.add(ProductImage(
        tenant_id=tenant.id, product_id=product.id,
        url="https://cdn.example.com/b.jpg", sort_order=0,
    ))
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.get(f"/v1/storefront/products/{product.id}",
                          headers={"X-Channel-Id": str(storefront["channel"].id)})
        assert resp.status_code == 200
        body = resp.json()
        assert body["images"] is not None
        assert len(body["images"]) == 2
        assert body["images"][0]["url"] == "https://cdn.example.com/b.jpg"
        assert body["images"][1]["url"] == "https://cdn.example.com/a.jpg"
        assert body["image_url"] == "https://cdn.example.com/b.jpg"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_detail_products_image_url_overrides_gallery(db, tenant: Tenant, storefront) -> None:
    """products.image_url takes priority over the gallery (legacy override)."""
    from app.models import ProductImage
    from app.db.session import get_db
    product = storefront["products"][0]
    product.image_url = "https://legacy.example.com/hero.jpg"
    db.add(ProductImage(
        tenant_id=tenant.id, product_id=product.id,
        url="https://cdn.example.com/gallery.jpg", sort_order=0,
    ))
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.get(f"/v1/storefront/products/{product.id}",
                          headers={"X-Channel-Id": str(storefront["channel"].id)})
        assert resp.status_code == 200
        body = resp.json()
        assert body["image_url"] == "https://legacy.example.com/hero.jpg"
        assert len(body["images"]) == 1
        assert body["images"][0]["url"] == "https://cdn.example.com/gallery.jpg"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_detail_no_gallery_images_is_empty_list(db, tenant: Tenant, storefront) -> None:
    """Detail images field is an empty list (not null) when product has no gallery."""
    from app.db.session import get_db
    product = storefront["products"][0]
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.get(f"/v1/storefront/products/{product.id}",
                          headers={"X-Channel-Id": str(storefront["channel"].id)})
        assert resp.status_code == 200
        body = resp.json()
        assert body["images"] == []
        assert body["image_url"] is None
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_list_products_filter_by_tags(db, tenant: Tenant, storefront) -> None:
    """tags[] returns only products whose JSONB tags contain any of the given values."""
    from app.db.session import get_db
    # Set distinct tags on the two products
    storefront["products"][0].tags = ["anime-stickers", "featured"]
    storefront["products"][1].tags = ["car-decals"]
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        # Filter to anime-stickers — should only include product 0
        resp = client.get("/v1/storefront/products?tags%5B%5D=anime-stickers",
                          headers={"X-Channel-Id": str(storefront["channel"].id)})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["sku"] == "SKU-A"

        # Filter to multiple tags — OR match should include both
        resp = client.get("/v1/storefront/products?tags%5B%5D=anime-stickers&tags%5B%5D=car-decals",
                          headers={"X-Channel-Id": str(storefront["channel"].id)})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 2
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_list_products_filter_by_price_range(db, tenant: Tenant, storefront) -> None:
    """min_price_cents and max_price_cents filter on unit_price_cents inclusive."""
    from app.db.session import get_db
    # Products are 1999 and 2999
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        # Above 2500 — only product 2 (2999)
        resp = client.get("/v1/storefront/products?min_price_cents=2500",
                          headers={"X-Channel-Id": str(storefront["channel"].id)})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["unit_price_cents"] == 2999

        # 2000-2999 — only product 2 (1999 excluded by min, 2999 included)
        resp = client.get("/v1/storefront/products?min_price_cents=2000&max_price_cents=2999",
                          headers={"X-Channel-Id": str(storefront["channel"].id)})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["unit_price_cents"] == 2999

        # Below 2500 — only product 1 (1999)
        resp = client.get("/v1/storefront/products?max_price_cents=2500",
                          headers={"X-Channel-Id": str(storefront["channel"].id)})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["unit_price_cents"] == 1999
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_list_products_sort_by_unit_price(db, tenant: Tenant, storefront) -> None:
    """sort_by=unit_price_cents&sort_order=asc returns cheapest first."""
    from app.db.session import get_db
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.get("/v1/storefront/products?sort_by=unit_price_cents&sort_order=asc",
                          headers={"X-Channel-Id": str(storefront["channel"].id)})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        prices = [p["unit_price_cents"] for p in body["items"]]
        assert prices == sorted(prices)

        resp = client.get("/v1/storefront/products?sort_by=unit_price_cents&sort_order=desc",
                          headers={"X-Channel-Id": str(storefront["channel"].id)})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        prices = [p["unit_price_cents"] for p in body["items"]]
        assert prices == sorted(prices, reverse=True)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_list_products_sort_by_discount_excludes_null(db, tenant: Tenant, storefront) -> None:
    """sort_by=discount_price_cents excludes products without a discount."""
    from app.db.session import get_db
    # Set discount only on product 0
    storefront["products"][0].discount_price_cents = 1500
    storefront["products"][1].discount_price_cents = None
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.get("/v1/storefront/products?sort_by=discount_price_cents&sort_order=asc",
                          headers={"X-Channel-Id": str(storefront["channel"].id)})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # Only product 0 should be returned
        assert body["total"] == 1
        assert body["items"][0]["discount_price_cents"] == 1500
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_list_products_invalid_sort_by_falls_back_to_default(db, tenant: Tenant, storefront) -> None:
    """An unknown sort_by value silently falls back to created_at instead of erroring."""
    from app.db.session import get_db
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.get("/v1/storefront/products?sort_by=nonexistent_column",
                          headers={"X-Channel-Id": str(storefront["channel"].id)})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # Both active products returned, no error
        assert body["total"] == 2
    finally:
        app.dependency_overrides.pop(get_db, None)
