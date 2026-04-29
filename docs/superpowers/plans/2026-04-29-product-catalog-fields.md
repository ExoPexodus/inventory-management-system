# Product Catalog Fields — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add five missing product fields (`barcode`, `cost_price_cents`, `hsn_code`, `negative_inventory_allowed`, `mrp_cents`) to the Product model, propagate them through the API, sync protocol, Flutter cashier, and admin web UI, and show inline price guard warnings in the admin when selling price is below cost or above MRP.

**Architecture:** Schema-only change — no new models, no new services. A single migration adds five nullable/defaulted columns to `products`. Pydantic schemas in `admin_web.py` and `sync.py` are updated. Three of the five fields (`barcode`, `mrp_cents`, `negative_inventory_allowed`) are included in the sync payload to the Flutter cashier — `cost_price_cents` and `hsn_code` are admin-only (margin data is sensitive; HSN is server-side only). The admin web gets new form fields and inline price guard warnings.

**Tech Stack:** PostgreSQL + Alembic (migration), FastAPI + SQLAlchemy 2.x mapped columns (model + API), Pydantic v2 (schemas), Next.js 15 + TypeScript (admin web), Flutter + Dart (cashier)

---

### Task 1: DB migration + SQLAlchemy model

**Files:**
- Modify: `services/api/app/models/tables.py` (lines 247–251 — inside `Product` class)
- Create: `services/api/alembic/versions/20260429000001_product_catalog_fields.py`

- [ ] **Step 1: Write failing contract test for new ProductDTO fields**

Add to `services/api/tests/test_contract_models.py`:

```python
def test_product_dto_includes_new_catalog_fields() -> None:
    pid = uuid4()
    p = ProductDTO(
        id=pid,
        sku="SKU-1",
        name="Widget",
        category=None,
        unit_price_cents=100,
        active=True,
        effective_tax_rate_bps=0,
        tax_exempt=False,
        barcode="5901234123457",
        mrp_cents=120,
        negative_inventory_allowed=False,
    )
    out = p.model_dump(mode="json")
    assert out["barcode"] == "5901234123457"
    assert out["mrp_cents"] == 120
    assert out["negative_inventory_allowed"] is False

    minimal = ProductDTO(
        id=pid,
        sku="SKU-1",
        name="Widget",
        category=None,
        unit_price_cents=100,
        active=True,
        effective_tax_rate_bps=0,
        tax_exempt=False,
    )
    out2 = minimal.model_dump(mode="json")
    assert out2["barcode"] is None
    assert out2["mrp_cents"] is None
    assert out2["negative_inventory_allowed"] is False
```

- [ ] **Step 2: Run test to confirm failure**

```bash
cd services/api && python -m pytest tests/test_contract_models.py::test_product_dto_includes_new_catalog_fields -v
```
Expected: FAIL — `ProductDTO` does not yet accept `barcode`, `mrp_cents`, `negative_inventory_allowed`.

- [ ] **Step 3: Add 5 columns to the SQLAlchemy Product model**

In `services/api/app/models/tables.py`, replace lines 247–251 (the block from `reorder_point` through `active`):

```python
    reorder_point: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    unit_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_price_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mrp_cents: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    barcode: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    hsn_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    negative_inventory_allowed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    variant_label: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 4: Create the Alembic migration**

Create `services/api/alembic/versions/20260429000001_product_catalog_fields.py`:

```python
"""product catalog fields — barcode, cost_price_cents, mrp_cents, hsn_code, negative_inventory_allowed

Revision ID: 20260429000001
Revises: 33707ff7b81f
Create Date: 2026-04-29 00:00:01.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260429000001"
down_revision = "33707ff7b81f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("cost_price_cents", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("mrp_cents", sa.Integer(), nullable=True))
    op.add_column("products", sa.Column("barcode", sa.String(128), nullable=True))
    op.add_column("products", sa.Column("hsn_code", sa.String(32), nullable=True))
    op.add_column(
        "products",
        sa.Column("negative_inventory_allowed", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("products", "negative_inventory_allowed")
    op.drop_column("products", "hsn_code")
    op.drop_column("products", "barcode")
    op.drop_column("products", "mrp_cents")
    op.drop_column("products", "cost_price_cents")
```

- [ ] **Step 5: Run migration**

```bash
cd services/api && alembic upgrade head
```
Expected: Migration applies with no errors. Confirm with:
```bash
alembic current
```
Expected: `20260429000001 (head)`.

- [ ] **Step 6: Commit**

```bash
git add services/api/app/models/tables.py \
        services/api/alembic/versions/20260429000001_product_catalog_fields.py \
        services/api/tests/test_contract_models.py
git commit -m "feat: add barcode, cost_price_cents, mrp_cents, hsn_code, negative_inventory_allowed columns to products"
```

---

### Task 2: Admin API — schemas and CRUD endpoints

**Files:**
- Modify: `services/api/app/routers/admin_web.py`
  - `CreateProductBody` (lines 1073–1079)
  - `CreateProductResponse` (lines 1082–1092)
  - `ProductListItem` (lines 1109–1118)
  - `PatchProductBody` (lines 1268–1275)
  - `admin_create_product` handler — `Product()` constructor + return statement
  - `admin_patch_product` handler — patch block + return statement
  - `admin_list_products` handler — `ProductListItem(...)` construction
- Modify: `services/api/tests/test_admin_console_contracts.py`

- [ ] **Step 1: Write failing contract tests for admin product schemas**

Add to `services/api/tests/test_admin_console_contracts.py`.

First, ensure `uuid4` is imported (it may already be — check the top of the file):
```python
from uuid import uuid4
```

Then add the tests:
```python
from app.routers.admin_web import CreateProductResponse, ProductListItem


def test_create_product_response_includes_catalog_fields() -> None:
    r = CreateProductResponse(
        id=uuid4(),
        tenant_id=uuid4(),
        sku="SKU-99",
        name="Chai",
        unit_price_cents=2500,
        category="Beverages",
        barcode="8901234567890",
        cost_price_cents=1500,
        mrp_cents=3000,
        hsn_code="2101",
        negative_inventory_allowed=False,
    )
    d = r.model_dump(mode="json")
    assert d["barcode"] == "8901234567890"
    assert d["cost_price_cents"] == 1500
    assert d["mrp_cents"] == 3000
    assert d["hsn_code"] == "2101"
    assert d["negative_inventory_allowed"] is False


def test_product_list_item_includes_catalog_fields() -> None:
    item = ProductListItem(
        id=uuid4(),
        sku="SKU-1",
        name="Widget",
        status="active",
        category=None,
        unit_price_cents=500,
        reorder_point=0,
        barcode="1234567890123",
        cost_price_cents=250,
        mrp_cents=600,
    )
    d = item.model_dump(mode="json")
    assert d["barcode"] == "1234567890123"
    assert d["cost_price_cents"] == 250
    assert d["mrp_cents"] == 600
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
cd services/api && python -m pytest tests/test_admin_console_contracts.py::test_create_product_response_includes_catalog_fields tests/test_admin_console_contracts.py::test_product_list_item_includes_catalog_fields -v
```
Expected: FAIL — `CreateProductResponse` and `ProductListItem` don't accept the new fields.

- [ ] **Step 3: Update `CreateProductBody`**

In `services/api/app/routers/admin_web.py`, replace the `CreateProductBody` class (lines 1073–1079):

```python
class CreateProductBody(BaseModel):
    sku: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    unit_price_cents: int = Field(ge=0)
    category: str | None = Field(default=None, max_length=128)
    product_group_id: UUID | None = None
    variant_label: str | None = Field(default=None, max_length=128)
    barcode: str | None = Field(default=None, max_length=128)
    cost_price_cents: int | None = Field(default=None, ge=0)
    mrp_cents: int | None = Field(default=None, ge=0)
    hsn_code: str | None = Field(default=None, max_length=32)
    negative_inventory_allowed: bool = False
```

- [ ] **Step 4: Update `CreateProductResponse`**

Replace the `CreateProductResponse` class (lines 1082–1092):

```python
class CreateProductResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    sku: str
    name: str
    unit_price_cents: int
    category: str | None
    product_group_id: UUID | None = None
    group_title: str | None = None
    variant_label: str | None = None
    reorder_point: int = 0
    barcode: str | None = None
    cost_price_cents: int | None = None
    mrp_cents: int | None = None
    hsn_code: str | None = None
    negative_inventory_allowed: bool = False
```

- [ ] **Step 5: Update `ProductListItem`**

Replace the `ProductListItem` class (lines 1109–1118):

```python
class ProductListItem(BaseModel):
    id: UUID
    sku: str
    name: str
    status: str
    category: str | None
    unit_price_cents: int
    reorder_point: int
    variant_label: str | None = None
    group_title: str | None = None
    barcode: str | None = None
    cost_price_cents: int | None = None
    mrp_cents: int | None = None
```

- [ ] **Step 6: Update `PatchProductBody`**

Replace the `PatchProductBody` class (lines 1268–1275):

```python
class PatchProductBody(BaseModel):
    product_group_id: UUID | None = None
    variant_label: str | None = Field(default=None, max_length=128)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: str | None = None
    category: str | None = Field(default=None, max_length=128)
    unit_price_cents: int | None = Field(default=None, ge=0)
    reorder_point: int | None = Field(default=None, ge=0)
    barcode: str | None = Field(default=None, max_length=128)
    cost_price_cents: int | None = Field(default=None, ge=0)
    mrp_cents: int | None = Field(default=None, ge=0)
    hsn_code: str | None = Field(default=None, max_length=32)
    negative_inventory_allowed: bool | None = None
```

- [ ] **Step 7: Update `admin_create_product` — Product constructor**

In `admin_create_product` (around line 1164), replace the `Product(...)` constructor:

```python
    prod = Product(
        tenant_id=tenant_id,
        product_group_id=group.id if group else None,
        sku=body.sku.strip(),
        name=body.name.strip(),
        unit_price_cents=body.unit_price_cents,
        category=body.category.strip() if body.category else None,
        variant_label=body.variant_label.strip() if body.variant_label else None,
        barcode=body.barcode.strip() if body.barcode else None,
        cost_price_cents=body.cost_price_cents,
        mrp_cents=body.mrp_cents,
        hsn_code=body.hsn_code.strip() if body.hsn_code else None,
        negative_inventory_allowed=body.negative_inventory_allowed,
    )
```

- [ ] **Step 8: Update `admin_create_product` — return statement**

Replace the `CreateProductResponse(...)` return (around line 1190):

```python
    return CreateProductResponse(
        id=prod.id,
        tenant_id=prod.tenant_id,
        sku=prod.sku,
        name=prod.name,
        unit_price_cents=prod.unit_price_cents,
        category=prod.category,
        product_group_id=prod.product_group_id,
        group_title=group.title if group else None,
        variant_label=prod.variant_label,
        reorder_point=prod.reorder_point,
        barcode=prod.barcode,
        cost_price_cents=prod.cost_price_cents,
        mrp_cents=prod.mrp_cents,
        hsn_code=prod.hsn_code,
        negative_inventory_allowed=prod.negative_inventory_allowed,
    )
```

- [ ] **Step 9: Update `admin_patch_product` — patch block**

In `admin_patch_product`, after the existing `if "reorder_point"` block (around line 1317), add:

```python
    if "barcode" in patch:
        bc = patch["barcode"]
        prod.barcode = bc.strip() if isinstance(bc, str) and bc.strip() else None

    if "cost_price_cents" in patch:
        prod.cost_price_cents = patch["cost_price_cents"]

    if "mrp_cents" in patch:
        prod.mrp_cents = patch["mrp_cents"]

    if "hsn_code" in patch:
        hs = patch["hsn_code"]
        prod.hsn_code = hs.strip() if isinstance(hs, str) and hs.strip() else None

    if "negative_inventory_allowed" in patch and patch["negative_inventory_allowed"] is not None:
        prod.negative_inventory_allowed = patch["negative_inventory_allowed"]
```

- [ ] **Step 10: Update `admin_patch_product` — return statement**

Replace the `CreateProductResponse(...)` return at the end of `admin_patch_product` (around line 1345):

```python
    return CreateProductResponse(
        id=prod.id,
        tenant_id=prod.tenant_id,
        sku=prod.sku,
        name=prod.name,
        unit_price_cents=prod.unit_price_cents,
        category=prod.category,
        product_group_id=prod.product_group_id,
        group_title=group_title,
        variant_label=prod.variant_label,
        reorder_point=prod.reorder_point,
        barcode=prod.barcode,
        cost_price_cents=prod.cost_price_cents,
        mrp_cents=prod.mrp_cents,
        hsn_code=prod.hsn_code,
        negative_inventory_allowed=prod.negative_inventory_allowed,
    )
```

- [ ] **Step 11: Update `admin_list_products` — ProductListItem construction**

Replace the list comprehension return in `admin_list_products` (around line 1140):

```python
    return [
        ProductListItem(
            id=r.id,
            sku=r.sku,
            name=r.name,
            status=r.status,
            category=r.category,
            unit_price_cents=r.unit_price_cents,
            reorder_point=r.reorder_point,
            variant_label=r.variant_label,
            group_title=r.product_group.title if r.product_group else None,
            barcode=r.barcode,
            cost_price_cents=r.cost_price_cents,
            mrp_cents=r.mrp_cents,
        )
        for r in rows
    ]
```

- [ ] **Step 12: Run all contract tests**

```bash
cd services/api && python -m pytest tests/test_admin_console_contracts.py tests/test_contract_models.py -v
```
Expected: All PASS.

- [ ] **Step 13: Commit**

```bash
git add services/api/app/routers/admin_web.py \
        services/api/tests/test_admin_console_contracts.py
git commit -m "feat: expose barcode, cost_price_cents, mrp_cents, hsn_code, negative_inventory_allowed in admin product API"
```

---

### Task 3: Sync protocol — ProductDTO

`barcode`, `mrp_cents`, and `negative_inventory_allowed` must reach the Flutter cashier via sync pull. `cost_price_cents` and `hsn_code` are deliberately excluded (margin is sensitive; HSN is server-side only).

**Files:**
- Modify: `services/api/app/routers/sync.py` — `ProductDTO` class and `sync_pull` handler
- Modify: `packages/sync-protocol/openapi.yaml` — `ProductDTO` schema

- [ ] **Step 1: Run the new contract test — confirm it still fails**

```bash
cd services/api && python -m pytest tests/test_contract_models.py::test_product_dto_includes_new_catalog_fields -v
```
Expected: FAIL — `ProductDTO` in `sync.py` does not yet have the three new fields.

- [ ] **Step 2: Update `ProductDTO` in sync.py**

In `services/api/app/routers/sync.py`, replace the `ProductDTO` class (lines 31–42):

```python
class ProductDTO(BaseModel):
    id: UUID
    sku: str
    name: str
    category: str | None = None
    unit_price_cents: int
    active: bool
    effective_tax_rate_bps: int
    tax_exempt: bool
    product_group_id: UUID | None = None
    group_title: str | None = None
    variant_label: str | None = None
    barcode: str | None = None
    mrp_cents: int | None = None
    negative_inventory_allowed: bool = False
```

- [ ] **Step 3: Update `sync_pull` handler — pass new fields**

In `sync_pull` (around line 153), replace the `ProductDTO(...)` construction:

```python
        product_dtos.append(
            ProductDTO(
                id=p.id,
                sku=p.sku,
                name=p.name,
                category=p.category,
                unit_price_cents=p.unit_price_cents,
                active=p.active,
                effective_tax_rate_bps=bps,
                tax_exempt=exempt,
                product_group_id=gid,
                group_title=group_title_by_id.get(gid) if gid is not None else None,
                variant_label=p.variant_label,
                barcode=p.barcode,
                mrp_cents=p.mrp_cents,
                negative_inventory_allowed=p.negative_inventory_allowed,
            )
        )
```

- [ ] **Step 4: Run all contract tests — confirm they all pass**

```bash
cd services/api && python -m pytest tests/test_contract_models.py -v
```
Expected: All PASS including `test_product_dto_includes_new_catalog_fields` and the existing `test_product_dto_sync_pull_optional_variant_fields`.

- [ ] **Step 5: Update OpenAPI spec**

In `packages/sync-protocol/openapi.yaml`, replace the `ProductDTO` schema block (starting at line 1033, ending before `StockSnapshotDTO`):

```yaml
    ProductDTO:
      type: object
      properties:
        id:
          type: string
          format: uuid
        sku:
          type: string
        name:
          type: string
        category:
          type: string
          nullable: true
        unit_price_cents:
          type: integer
        active:
          type: boolean
        effective_tax_rate_bps:
          type: integer
          description: Applicable rate for this shop after overrides (0 if exempt).
        tax_exempt:
          type: boolean
        product_group_id:
          type: string
          format: uuid
          nullable: true
        group_title:
          type: string
          nullable: true
        variant_label:
          type: string
          nullable: true
        barcode:
          type: string
          nullable: true
          description: UPC/EAN barcode for POS scan lookup. Null if not assigned.
        mrp_cents:
          type: integer
          nullable: true
          description: Maximum Retail Price in minor currency units. POS must warn if selling price exceeds this.
        negative_inventory_allowed:
          type: boolean
          default: false
          description: When false, POS must block a sale that would drive stock below zero.
```

- [ ] **Step 6: Commit**

```bash
git add services/api/app/routers/sync.py \
        packages/sync-protocol/openapi.yaml
git commit -m "feat: add barcode, mrp_cents, negative_inventory_allowed to sync ProductDTO"
```

---

### Task 4: Flutter cashier — ProductRow

**Files:**
- Modify: `apps/cashier/lib/services/inventory_api.dart` (lines 15–57)

- [ ] **Step 1: Replace `ProductRow` class and `merged` factory**

In `apps/cashier/lib/services/inventory_api.dart`, replace lines 15–57 with:

```dart
class ProductRow {
  ProductRow({
    required this.id,
    required this.sku,
    required this.name,
    required this.unitPriceCents,
    required this.quantity,
    this.category,
    this.effectiveTaxRateBps = 0,
    this.taxExempt = false,
    this.productGroupId,
    this.groupTitle,
    this.variantLabel,
    this.barcode,
    this.mrpCents,
    this.negativeInventoryAllowed = false,
  });

  final String id;
  final String sku;
  final String name;
  final String? category;
  /// Basis points applicable at synced shop (0 when [taxExempt]).
  final int effectiveTaxRateBps;
  final bool taxExempt;
  final int unitPriceCents;
  final int quantity;
  final String? productGroupId;
  final String? groupTitle;
  final String? variantLabel;
  final String? barcode;
  final int? mrpCents;
  final bool negativeInventoryAllowed;

  factory ProductRow.merged(Map<String, dynamic> product, int quantity) {
    return ProductRow(
      id: product['id'] as String,
      sku: product['sku'] as String,
      name: product['name'] as String,
      unitPriceCents: product['unit_price_cents'] as int,
      quantity: quantity,
      category: product['category'] as String?,
      effectiveTaxRateBps: (product['effective_tax_rate_bps'] as num?)?.toInt() ?? 0,
      taxExempt: product['tax_exempt'] as bool? ?? false,
      productGroupId: product['product_group_id'] as String?,
      groupTitle: product['group_title'] as String?,
      variantLabel: product['variant_label'] as String?,
      barcode: product['barcode'] as String?,
      mrpCents: (product['mrp_cents'] as num?)?.toInt(),
      negativeInventoryAllowed: product['negative_inventory_allowed'] as bool? ?? false,
    );
  }
}
```

- [ ] **Step 2: Run Flutter analyze**

```bash
cd apps/cashier && ../../tools/flutter/bin/flutter analyze lib/services/inventory_api.dart
```
Expected: No errors or warnings.

- [ ] **Step 3: Commit**

```bash
git add apps/cashier/lib/services/inventory_api.dart
git commit -m "feat: add barcode, mrpCents, negativeInventoryAllowed to cashier ProductRow"
```

---

### Task 5: Admin web — product list table and edit dialog

**Files:**
- Modify: `apps/admin-web/src/app/(main)/products/page.tsx`

- [ ] **Step 1: Update the `Product` type**

In `apps/admin-web/src/app/(main)/products/page.tsx`, replace the `Product` type (lines 21–31):

```typescript
type Product = {
  id: string;
  sku: string;
  name: string;
  status: string;
  category: string | null;
  unit_price_cents: number;
  reorder_point: number;
  variant_label?: string | null;
  group_title?: string | null;
  barcode?: string | null;
  cost_price_cents?: number | null;
  mrp_cents?: number | null;
  hsn_code?: string | null;
  negative_inventory_allowed?: boolean;
};
```

- [ ] **Step 2: Add MRP and Barcode columns to the table header**

In the `<thead>` row (around line 170), after the `Unit price` `<th>`:

```tsx
<th className="px-6 py-3 text-right text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">MRP</th>
<th className="px-6 py-3 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">Barcode</th>
```

Also update both `colSpan` values in the loading and empty-state rows from `8` to `10`:

```tsx
<LoadingRow colSpan={10} label="Loading products…" />
```
```tsx
<td colSpan={10} className="p-0">
```

- [ ] **Step 3: Add MRP and Barcode cells to the table row**

In the `<tbody>` row (around line 211), after the `unit_price_cents` cell:

```tsx
<td className="px-6 py-3 text-right tabular-nums text-on-surface-variant">
  {row.mrp_cents != null
    ? formatMoney(row.mrp_cents, currency)
    : <span className="text-on-surface-variant/40">—</span>}
</td>
<td className="px-6 py-3 font-mono text-xs text-on-surface-variant">
  {row.barcode ?? <span className="text-on-surface-variant/40">—</span>}
</td>
```

- [ ] **Step 4: Add new state variables to `EditProductDialog`**

In the `EditProductDialog` component (starting around line 293), after the existing `useState` declarations, add:

```typescript
  const [barcode, setBarcode] = useState(product.barcode ?? "");
  const [costPrice, setCostPrice] = useState(
    product.cost_price_cents != null ? (product.cost_price_cents / 100).toFixed(2) : ""
  );
  const [mrpPrice, setMrpPrice] = useState(
    product.mrp_cents != null ? (product.mrp_cents / 100).toFixed(2) : ""
  );
  const [hsnCode, setHsnCode] = useState(product.hsn_code ?? "");
  const [negativeInventory, setNegativeInventory] = useState(product.negative_inventory_allowed ?? false);
```

- [ ] **Step 5: Add price guard warning to `EditProductDialog`**

After the `negativeInventory` state declaration, add:

```typescript
  const priceGuardWarning = (() => {
    const p = Math.round(parseFloat(priceUsd) * 100);
    const cost = costPrice.trim() ? Math.round(parseFloat(costPrice) * 100) : null;
    const mrp = mrpPrice.trim() ? Math.round(parseFloat(mrpPrice) * 100) : null;
    if (!isNaN(p)) {
      if (cost !== null && p < cost) return "Selling price is below cost price.";
      if (mrp !== null && p > mrp) return "Selling price exceeds MRP.";
    }
    return null;
  })();
```

- [ ] **Step 6: Update `onSubmit` in `EditProductDialog`**

After the existing `priceCents` computation (around line 303), add:

```typescript
    const costCents = costPrice.trim() ? Math.round(parseFloat(costPrice) * 100) : null;
    const mrpCents = mrpPrice.trim() ? Math.round(parseFloat(mrpPrice) * 100) : null;
```

Replace the PATCH body in `onSubmit` (around line 318):

```typescript
      body: JSON.stringify({
        name: name.trim(),
        category: cat.trim() || null,
        status: prodStatus,
        unit_price_cents: priceCents,
        reorder_point: rp,
        barcode: barcode.trim() || null,
        cost_price_cents: costCents,
        mrp_cents: mrpCents,
        hsn_code: hsnCode.trim() || null,
        negative_inventory_allowed: negativeInventory,
      }),
```

- [ ] **Step 7: Add new form fields to `EditProductDialog`**

In the form body (around line 370), after the existing price/reorder-point grid, add:

```tsx
          <div className="grid grid-cols-2 gap-4">
            <label className="block text-sm font-medium text-on-surface">
              Cost price
              <TextInput
                type="number"
                min="0"
                step="0.01"
                className="mt-1"
                value={costPrice}
                onChange={(e) => setCostPrice(e.target.value)}
                placeholder="e.g. 8.00"
              />
            </label>
            <label className="block text-sm font-medium text-on-surface">
              MRP
              <TextInput
                type="number"
                min="0"
                step="0.01"
                className="mt-1"
                value={mrpPrice}
                onChange={(e) => setMrpPrice(e.target.value)}
                placeholder="e.g. 25.00"
              />
            </label>
          </div>
          {priceGuardWarning ? (
            <p className="text-sm text-error">{priceGuardWarning}</p>
          ) : null}
          <label className="block text-sm font-medium text-on-surface">
            Barcode (UPC / EAN)
            <TextInput
              className="mt-1"
              value={barcode}
              onChange={(e) => setBarcode(e.target.value)}
              placeholder="e.g. 8901234567890"
            />
          </label>
          <label className="block text-sm font-medium text-on-surface">
            HSN code
            <TextInput
              className="mt-1"
              value={hsnCode}
              onChange={(e) => setHsnCode(e.target.value)}
              placeholder="e.g. 2101"
            />
          </label>
          <label className="flex items-center gap-3 text-sm font-medium text-on-surface">
            <input
              type="checkbox"
              checked={negativeInventory}
              onChange={(e) => setNegativeInventory(e.target.checked)}
              className="rounded border-outline-variant/40 accent-primary"
            />
            Allow sales when stock is zero
          </label>
```

- [ ] **Step 8: Run TypeScript build check**

```bash
cd apps/admin-web && npm run build 2>&1 | grep -E "error TS|Error:" | head -20
```
Expected: No errors from `products/page.tsx`.

- [ ] **Step 9: Commit**

```bash
git add apps/admin-web/src/app/(main)/products/page.tsx
git commit -m "feat: add barcode/MRP columns and cost/mrp/hsn/negative_inventory fields to product edit UI"
```

---

### Task 6: Admin web — product creation (entries page)

**Files:**
- Modify: `apps/admin-web/src/app/(main)/entries/page.tsx`

- [ ] **Step 1: Add new state variables**

In `apps/admin-web/src/app/(main)/entries/page.tsx`, after the existing `useState` declarations (around line 29), add:

```typescript
  const [barcode, setBarcode] = useState("");
  const [costPrice, setCostPrice] = useState("");
  const [mrpPrice, setMrpPrice] = useState("");
  const [hsnCode, setHsnCode] = useState("");
  const [negativeInventory, setNegativeInventory] = useState(false);
```

- [ ] **Step 2: Add price guard warning**

After the `priceOk` declaration (around line 41), add:

```typescript
  const previewCostCents = costPrice.trim() ? Math.round(parseFloat(costPrice) * 100) : null;
  const previewMrpCents = mrpPrice.trim() ? Math.round(parseFloat(mrpPrice) * 100) : null;
  const priceGuardWarning = (() => {
    if (!priceOk) return null;
    if (previewCostCents !== null && previewPriceCents < previewCostCents)
      return "Selling price is below cost price.";
    if (previewMrpCents !== null && previewPriceCents > previewMrpCents)
      return "Selling price exceeds MRP.";
    return null;
  })();
```

- [ ] **Step 3: Update the POST body in `addProduct`**

Replace the body construction in `addProduct` (around lines 74–82):

```typescript
    const body: Record<string, unknown> = {
      sku,
      name: pname,
      unit_price_cents: unit,
      category: category || null,
      barcode: barcode.trim() || null,
      cost_price_cents: previewCostCents,
      mrp_cents: previewMrpCents,
      hsn_code: hsnCode.trim() || null,
      negative_inventory_allowed: negativeInventory,
    };
    if (productGroupId) body.product_group_id = productGroupId;
    const vl = variantLabel.trim();
    if (vl) body.variant_label = vl;
```

After the `if (r.ok)` block that resets `sku`, `pname`, `variantLabel` on success, add resets for the new fields:

```typescript
      setBarcode("");
      setCostPrice("");
      setMrpPrice("");
      setHsnCode("");
      setNegativeInventory(false);
```

- [ ] **Step 4: Add new form fields to the UI**

Inside the product details section (inside the form, after the existing SKU/name/price/category fields), add:

```tsx
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block text-sm font-medium text-on-surface">
                Cost price
                <TextInput
                  type="number"
                  min="0"
                  step="0.01"
                  className="mt-1"
                  value={costPrice}
                  onChange={(e) => setCostPrice(e.target.value)}
                  placeholder="e.g. 8.00"
                />
              </label>
              <label className="block text-sm font-medium text-on-surface">
                MRP
                <TextInput
                  type="number"
                  min="0"
                  step="0.01"
                  className="mt-1"
                  value={mrpPrice}
                  onChange={(e) => setMrpPrice(e.target.value)}
                  placeholder="e.g. 25.00"
                />
              </label>
            </div>
            {priceGuardWarning ? (
              <p className="text-sm text-error">{priceGuardWarning}</p>
            ) : null}
            <label className="block text-sm font-medium text-on-surface">
              Barcode (UPC / EAN)
              <TextInput
                className="mt-1"
                value={barcode}
                onChange={(e) => setBarcode(e.target.value)}
                placeholder="e.g. 8901234567890"
              />
            </label>
            <label className="block text-sm font-medium text-on-surface">
              HSN code
              <TextInput
                className="mt-1"
                value={hsnCode}
                onChange={(e) => setHsnCode(e.target.value)}
                placeholder="e.g. 2101"
              />
            </label>
            <label className="flex items-center gap-3 text-sm font-medium text-on-surface">
              <input
                type="checkbox"
                checked={negativeInventory}
                onChange={(e) => setNegativeInventory(e.target.checked)}
                className="rounded border-outline-variant/40 accent-primary"
              />
              Allow sales when stock is zero
            </label>
```

- [ ] **Step 5: Run TypeScript build check**

```bash
cd apps/admin-web && npm run build 2>&1 | grep -E "error TS|Error:" | head -20
```
Expected: No errors from `entries/page.tsx`.

- [ ] **Step 6: Commit**

```bash
git add apps/admin-web/src/app/(main)/entries/page.tsx
git commit -m "feat: add barcode, cost/mrp, hsn_code, negative_inventory fields to product creation form"
```

---

## Spec Coverage Check

| Requirement | Task(s) |
|---|---|
| `barcode` field on products | 1 (model/migration), 2 (admin API), 3 (sync), 4 (Flutter), 5+6 (admin web) |
| `cost_price_cents` on products | 1 (model/migration), 2 (admin API), 5+6 (admin web + price guard) |
| `hsn_code` on products | 1 (model/migration), 2 (admin API), 5+6 (admin web) |
| `negative_inventory_allowed` flag | 1 (model/migration), 2 (admin API), 3 (sync), 4 (Flutter), 5+6 (admin web) |
| `mrp_cents` field | 1 (model/migration), 2 (admin API), 3 (sync), 4 (Flutter), 5+6 (admin web + price guard) |
| Price guard: warn if unit_price < cost | 5 (edit dialog), 6 (create form) |
| Price guard: warn if unit_price > MRP | 5 (edit dialog), 6 (create form) |
| `cost_price_cents` NOT sent to cashier | 3 (deliberately excluded from ProductDTO) |
| `hsn_code` NOT sent to cashier | 3 (deliberately excluded from ProductDTO) |
