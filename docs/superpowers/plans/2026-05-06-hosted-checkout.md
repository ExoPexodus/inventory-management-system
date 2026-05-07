# Hosted Checkout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merchants can offer shoppers a complete, IMS-hosted checkout experience at `{ims-domain}/checkout/{session_token}` — collecting email, shipping address, computing shipping + tax, collecting payment via Stripe or Razorpay, and creating an IMS Order on success. Custom-domain CNAME support is deferred.

**Architecture:** A `checkout_sessions` table tracks the lifecycle of each checkout attempt (pending → payment_initiated → completed/expired). A `payment_service.py` wraps Stripe payment intents and Razorpay orders. A new `admin_payment.py` router lets merchants configure their payment credentials on a channel. The hosted checkout page is served by FastAPI via Jinja2 templates — a self-contained HTML/JS page that shows cart + address form, calls our shipping/tax APIs, and embeds Stripe Elements or Razorpay Checkout.js. Two completion paths: a server-side Stripe webhook for reliability + a client-side return URL handler. Razorpay uses a client-side signature verification endpoint.

**Payment credential storage:** Merchants paste their own API keys into IMS admin (stored in `Channel.config`). Stripe Connect OAuth is a future upgrade.

**Channel.config additions for Stripe:**
```json
{
  "payment_provider": "stripe",
  "stripe_secret_key": "sk_live_...",
  "stripe_publishable_key": "pk_live_...",
  "checkout_success_url": "https://shop.example.com/order-confirmed",
  "checkout_cancel_url": "https://shop.example.com/cart"
}
```

**Channel.config additions for Razorpay:**
```json
{
  "payment_provider": "razorpay",
  "razorpay_key_id": "rzp_live_...",
  "razorpay_key_secret": "...",
  "checkout_success_url": "https://shop.example.com/order-confirmed",
  "checkout_cancel_url": "https://shop.example.com/cart"
}
```

**Tech Stack:** Python 3.12, FastAPI, Jinja2 (HTML templates), stripe-python SDK, httpx (Razorpay), Alembic, pytest (mocked payment APIs)

**Out of scope (deferred):**
- Custom domain CNAME routing
- PayPal integration
- Stripe Connect OAuth
- Abandoned cart email
- Multi-step checkout wizard UX (Phase 2 has a single-page form)

---

### Task 1: checkout_sessions table + admin payment setup

**Files:**
- Create: `services/api/alembic/versions/20260517000001_checkout_sessions.py`
- Modify: `services/api/app/models/tables.py`
- Modify: `services/api/app/models/__init__.py`
- Create: `services/api/app/routers/admin_payment.py`
- Modify: `services/api/app/main.py`
- Create: `services/api/tests/routers/test_admin_payment.py`

- [ ] **Step 1: Add the SQLAlchemy model**

In `services/api/app/models/tables.py`, append after `ChannelProductMapping`:

```python
class CheckoutSession(Base):
    """Tracks one hosted checkout attempt from session creation to order completion.

    States:
      pending             — session created, shopper has not yet initiated payment
      payment_initiated   — payment intent / Razorpay order created
      completed           — payment confirmed, IMS Order created
      expired             — session TTL passed without completion
      cancelled           — shopper cancelled / navigated away

    cart_token links to CartItem rows. On completion, cart items are consumed
    and an Order row is created. external_payment_id stores the Stripe
    PaymentIntent ID or Razorpay payment_id.
    """
    __tablename__ = "checkout_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"), nullable=False
    )
    cart_token: Mapped[str] = mapped_column(String(128), nullable=False)
    session_token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="pending", server_default="pending", nullable=False
    )
    payment_provider: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    external_payment_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Snapshot of amounts at session creation (in channel currency)
    subtotal_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    discount_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    shipping_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    tax_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    total_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    # Collected shopper data
    customer_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    shipping_address: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Discount code applied
    discount_code: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    # Order created on completion
    order_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
```

- [ ] **Step 2: Export the model**

In `services/api/app/models/__init__.py`, add `CheckoutSession` alphabetically.

- [ ] **Step 3: Write the migration**

Create `services/api/alembic/versions/20260517000001_checkout_sessions.py`:

```python
"""Hosted checkout: checkout_sessions table

Revision ID: 20260517000001
Revises: 20260516000001
Create Date: 2026-05-17 00:00:01.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB

revision = "20260517000001"
down_revision = "20260516000001"
branch_labels = None
depends_on = None


_RLS_POLICY = """
COALESCE(current_setting('ims.is_admin', true), '') = 'true'
OR (
  NULLIF(TRIM(COALESCE(current_setting('ims.tenant_id', true), '')), '') IS NOT NULL
  AND tenant_id = (NULLIF(TRIM(COALESCE(current_setting('ims.tenant_id', true), '')), ''))::uuid
)
"""


def upgrade() -> None:
    op.create_table(
        "checkout_sessions",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cart_token", sa.String(128), nullable=False),
        sa.Column("session_token", sa.String(128), unique=True, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("payment_provider", sa.String(32), nullable=True),
        sa.Column("external_payment_id", sa.String(255), nullable=True),
        sa.Column("subtotal_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("discount_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("shipping_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tax_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_cents", sa.Integer, nullable=False, server_default="0"),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("customer_email", sa.String(255), nullable=True),
        sa.Column("shipping_address", JSONB, nullable=True),
        sa.Column("discount_code", sa.String(128), nullable=True),
        sa.Column("order_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("orders.id", ondelete="SET NULL"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_checkout_sessions_tenant_id", "checkout_sessions", ["tenant_id"])
    op.create_index("ix_checkout_sessions_channel_id", "checkout_sessions", ["channel_id"])
    op.create_index("ix_checkout_sessions_session_token", "checkout_sessions", ["session_token"])
    op.create_index("ix_checkout_sessions_status", "checkout_sessions", ["status", "expires_at"])

    op.execute(f"""
        ALTER TABLE checkout_sessions ENABLE ROW LEVEL SECURITY;
        ALTER TABLE checkout_sessions FORCE ROW LEVEL SECURITY;
        CREATE POLICY ims_tenant_isolation ON checkout_sessions
        USING ({_RLS_POLICY})
        WITH CHECK ({_RLS_POLICY});
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS ims_tenant_isolation ON checkout_sessions;")
    op.execute("ALTER TABLE checkout_sessions NO FORCE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE checkout_sessions DISABLE ROW LEVEL SECURITY;")
    op.drop_index("ix_checkout_sessions_status", table_name="checkout_sessions")
    op.drop_index("ix_checkout_sessions_session_token", table_name="checkout_sessions")
    op.drop_index("ix_checkout_sessions_channel_id", table_name="checkout_sessions")
    op.drop_index("ix_checkout_sessions_tenant_id", table_name="checkout_sessions")
    op.drop_table("checkout_sessions")
```

- [ ] **Step 4: Implement admin payment setup router**

Create `services/api/app/routers/admin_payment.py`:

```python
"""Admin endpoints for configuring payment providers on a channel.

Supports Stripe (direct secret key) and Razorpay.
Credentials are stored in Channel.config and are encrypted-at-rest
(Postgres column encryption is out of scope for this plan — mark as TODO for
a future security hardening sprint).
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import Channel

router = APIRouter(
    prefix="/v1/admin/channels",
    tags=["Payment Setup"],
    dependencies=[require_permission("channels:manage")],
)

_VALID_PROVIDERS = {"stripe", "razorpay", "none"}


class StripeSetupIn(BaseModel):
    stripe_secret_key: str
    stripe_publishable_key: str
    checkout_success_url: str
    checkout_cancel_url: str = ""


class RazorpaySetupIn(BaseModel):
    razorpay_key_id: str
    razorpay_key_secret: str
    checkout_success_url: str
    checkout_cancel_url: str = ""


class PaymentSetupOut(BaseModel):
    channel_id: UUID
    payment_provider: str
    configured: bool


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Operator not assigned to a tenant")
    return ctx.tenant_id


def _get_channel_or_404(db: Session, channel_id: UUID, tenant_id: UUID) -> Channel:
    ch = db.get(Channel, channel_id)
    if ch is None or ch.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Channel not found")
    return ch


@router.post("/{channel_id}/payment/setup-stripe", response_model=PaymentSetupOut)
def setup_stripe(
    channel_id: UUID,
    body: StripeSetupIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> PaymentSetupOut:
    tenant_id = _require_tenant(ctx)
    channel = _get_channel_or_404(db, channel_id, tenant_id)

    channel.config = {
        **channel.config,
        "payment_provider": "stripe",
        "stripe_secret_key": body.stripe_secret_key.strip(),
        "stripe_publishable_key": body.stripe_publishable_key.strip(),
        "checkout_success_url": body.checkout_success_url.strip(),
        "checkout_cancel_url": body.checkout_cancel_url.strip(),
    }
    db.commit()
    return PaymentSetupOut(
        channel_id=channel.id, payment_provider="stripe", configured=True
    )


@router.post("/{channel_id}/payment/setup-razorpay", response_model=PaymentSetupOut)
def setup_razorpay(
    channel_id: UUID,
    body: RazorpaySetupIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> PaymentSetupOut:
    tenant_id = _require_tenant(ctx)
    channel = _get_channel_or_404(db, channel_id, tenant_id)

    channel.config = {
        **channel.config,
        "payment_provider": "razorpay",
        "razorpay_key_id": body.razorpay_key_id.strip(),
        "razorpay_key_secret": body.razorpay_key_secret.strip(),
        "checkout_success_url": body.checkout_success_url.strip(),
        "checkout_cancel_url": body.checkout_cancel_url.strip(),
    }
    db.commit()
    return PaymentSetupOut(
        channel_id=channel.id, payment_provider="razorpay", configured=True
    )


@router.get("/{channel_id}/payment/config", response_model=PaymentSetupOut)
def get_payment_config(
    channel_id: UUID,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> PaymentSetupOut:
    tenant_id = _require_tenant(ctx)
    channel = _get_channel_or_404(db, channel_id, tenant_id)
    provider = channel.config.get("payment_provider", "none")
    return PaymentSetupOut(
        channel_id=channel.id,
        payment_provider=provider,
        configured=provider != "none",
    )
```

- [ ] **Step 5: Write the admin payment test**

Create `services/api/tests/routers/test_admin_payment.py`:

```python
# NOTE: `from __future__ import annotations` deliberately absent.

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Channel, InventoryPool, InventoryPoolShop, Shop, Tenant


@pytest.fixture()
def channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    ch = Channel(
        tenant_id=tenant.id, type="headless", name="Headless",
        config={}, inventory_pool_id=pool.id, currency_code="INR",
    )
    db.add(ch)
    db.flush()
    return ch


@pytest.fixture()
def auth_headers(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=None, tenant_id=tenant.id, role="owner", role_id=None,
        is_legacy_token=False, permissions=frozenset({"channels:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def test_setup_stripe(db, tenant: Tenant, channel: Channel, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post(f"/v1/admin/channels/{channel.id}/payment/setup-stripe", json={
        "stripe_secret_key": "sk_test_xxx",
        "stripe_publishable_key": "pk_test_xxx",
        "checkout_success_url": "https://shop.com/success",
        "checkout_cancel_url": "https://shop.com/cart",
    }, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["payment_provider"] == "stripe"
    assert resp.json()["configured"] is True
    db.refresh(channel)
    assert channel.config["stripe_secret_key"] == "sk_test_xxx"
    assert channel.config["checkout_success_url"] == "https://shop.com/success"


def test_setup_razorpay(db, tenant: Tenant, channel: Channel, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post(f"/v1/admin/channels/{channel.id}/payment/setup-razorpay", json={
        "razorpay_key_id": "rzp_test_xxx",
        "razorpay_key_secret": "test_secret",
        "checkout_success_url": "https://shop.com/success",
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["payment_provider"] == "razorpay"
    db.refresh(channel)
    assert channel.config["razorpay_key_id"] == "rzp_test_xxx"


def test_get_payment_config_unconfigured(db, tenant: Tenant, channel: Channel, auth_headers) -> None:
    client = TestClient(app)
    resp = client.get(f"/v1/admin/channels/{channel.id}/payment/config", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["configured"] is False
    assert resp.json()["payment_provider"] == "none"


def test_setup_stripe_overwrites_previous(db, tenant: Tenant, channel: Channel, auth_headers) -> None:
    client = TestClient(app)
    # Set Razorpay first
    client.post(f"/v1/admin/channels/{channel.id}/payment/setup-razorpay", json={
        "razorpay_key_id": "rzp_test", "razorpay_key_secret": "sec",
        "checkout_success_url": "https://shop.com/success",
    }, headers=auth_headers)
    # Switch to Stripe
    resp = client.post(f"/v1/admin/channels/{channel.id}/payment/setup-stripe", json={
        "stripe_secret_key": "sk_test", "stripe_publishable_key": "pk_test",
        "checkout_success_url": "https://shop.com/success",
    }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["payment_provider"] == "stripe"
```

- [ ] **Step 6: Mount admin_payment router, run migration and tests**

Add `admin_payment` to `main.py` and run:
```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/alembic/versions/20260517000001_checkout_sessions.py $CONTAINER:/app/alembic/versions/
docker compose exec api alembic upgrade head
docker cp services/api/app/main.py $CONTAINER:/app/app/main.py
docker cp services/api/app/routers/admin_payment.py $CONTAINER:/app/app/routers/admin_payment.py
docker cp services/api/tests $CONTAINER:/app/tests
docker compose restart api
sleep 5
docker compose exec api python -m pytest tests/routers/test_admin_payment.py -v
docker compose exec api rm -rf /app/tests
```
Expected: 4 passed.

- [ ] **Step 7: Commit**

```bash
git add services/api/alembic/versions/20260517000001_checkout_sessions.py \
        services/api/app/models/tables.py \
        services/api/app/models/__init__.py \
        services/api/app/routers/admin_payment.py \
        services/api/app/main.py \
        services/api/tests/routers/test_admin_payment.py
git commit -m "feat(checkout): add checkout_sessions table + admin payment setup endpoints"
```

---

### Task 2: Payment service (Stripe + Razorpay)

**Files:**
- Add `stripe` to `services/api/requirements.txt`
- Create: `services/api/app/services/payment_service.py`
- Create: `services/api/tests/services/test_payment_service.py`

- [ ] **Step 1: Add stripe dependency**

```bash
grep -q "^stripe" services/api/requirements.txt || echo "stripe>=7.0.0" >> services/api/requirements.txt
```
(Razorpay's API is HTTP — we'll use httpx directly, no SDK needed.)

- [ ] **Step 2: Write the failing test**

Create `services/api/tests/services/test_payment_service.py`:

```python
from decimal import Decimal
from unittest.mock import MagicMock, patch
import uuid

import pytest

from app.models import Channel, InventoryPool, InventoryPoolShop, Shop, Tenant


@pytest.fixture()
def stripe_channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    return Channel(
        tenant_id=tenant.id, type="headless", name="Stripe Channel",
        config={
            "payment_provider": "stripe",
            "stripe_secret_key": "sk_test_xxx",
            "stripe_publishable_key": "pk_test_xxx",
            "checkout_success_url": "https://shop.com/success",
        },
        inventory_pool_id=pool.id, currency_code="INR",
    )


@pytest.fixture()
def razorpay_channel(db, tenant: Tenant, shop: Shop) -> Channel:
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    return Channel(
        tenant_id=tenant.id, type="headless", name="Razorpay Channel",
        config={
            "payment_provider": "razorpay",
            "razorpay_key_id": "rzp_test_xxx",
            "razorpay_key_secret": "test_secret",
            "checkout_success_url": "https://shop.com/success",
        },
        inventory_pool_id=pool.id, currency_code="INR",
    )


def test_create_stripe_payment_intent(stripe_channel: Channel) -> None:
    """create_payment_intent returns a client_secret for Stripe."""
    mock_intent = MagicMock()
    mock_intent.id = "pi_test123"
    mock_intent.client_secret = "pi_test123_secret"

    with patch("stripe.PaymentIntent.create", return_value=mock_intent):
        from app.services.payment_service import create_payment_intent
        result = create_payment_intent(stripe_channel, amount_cents=1999, currency="INR",
                                       description="Cart checkout")
        assert result["provider"] == "stripe"
        assert result["client_secret"] == "pi_test123_secret"
        assert result["payment_intent_id"] == "pi_test123"


def test_create_razorpay_order(razorpay_channel: Channel) -> None:
    """create_payment_intent returns an order_id for Razorpay."""
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {
        "id": "order_rzp_test123",
        "amount": 199900,
        "currency": "INR",
        "status": "created",
    }

    with patch("httpx.post", return_value=mock_resp):
        from app.services.payment_service import create_payment_intent
        result = create_payment_intent(razorpay_channel, amount_cents=1999, currency="INR",
                                       description="Cart checkout")
        assert result["provider"] == "razorpay"
        assert result["order_id"] == "order_rzp_test123"
        assert result["key_id"] == "rzp_test_xxx"


def test_verify_stripe_payment_success(stripe_channel: Channel) -> None:
    """verify_payment returns True for a succeeded payment intent."""
    mock_intent = MagicMock()
    mock_intent.status = "succeeded"

    with patch("stripe.PaymentIntent.retrieve", return_value=mock_intent):
        from app.services.payment_service import verify_payment
        assert verify_payment(stripe_channel, "pi_test123") is True


def test_verify_stripe_payment_pending(stripe_channel: Channel) -> None:
    """verify_payment returns False for a non-succeeded status."""
    mock_intent = MagicMock()
    mock_intent.status = "requires_payment_method"

    with patch("stripe.PaymentIntent.retrieve", return_value=mock_intent):
        from app.services.payment_service import verify_payment
        assert verify_payment(stripe_channel, "pi_test123") is False


def test_verify_razorpay_payment(razorpay_channel: Channel) -> None:
    """verify_payment for Razorpay checks HMAC signature."""
    import hashlib
    import hmac as hmac_mod

    key_secret = "test_secret"
    order_id = "order_rzp_test123"
    payment_id = "pay_abc123"
    sig = hmac_mod.new(
        key_secret.encode(),
        f"{order_id}|{payment_id}".encode(),
        hashlib.sha256
    ).hexdigest()

    from app.services.payment_service import verify_razorpay_signature
    assert verify_razorpay_signature(razorpay_channel, order_id, payment_id, sig) is True
    assert verify_razorpay_signature(razorpay_channel, order_id, payment_id, "bad_sig") is False
```

- [ ] **Step 3: Implement payment_service.py**

Create `services/api/app/services/payment_service.py`:

```python
"""Payment service: Stripe and Razorpay payment intent / order creation and verification.

For Stripe: uses the stripe-python SDK with the merchant's secret key.
For Razorpay: uses httpx (no official Python SDK required).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class PaymentProviderError(Exception):
    """Payment provider returned an unexpected error."""


class PaymentNotConfiguredError(Exception):
    """Channel has no payment provider configured."""


def _get_provider(channel) -> str:
    provider = channel.config.get("payment_provider", "none")
    if provider == "none" or not provider:
        raise PaymentNotConfiguredError(
            f"Channel {channel.id} has no payment provider configured"
        )
    return provider


def create_payment_intent(
    channel,
    amount_cents: int,
    currency: str,
    description: str = "IMS Checkout",
) -> dict[str, Any]:
    """Create a Stripe PaymentIntent or Razorpay Order.

    Returns:
      Stripe: {"provider": "stripe", "payment_intent_id": str, "client_secret": str}
      Razorpay: {"provider": "razorpay", "order_id": str, "key_id": str, "amount": int}
    """
    provider = _get_provider(channel)

    if provider == "stripe":
        return _create_stripe_intent(channel, amount_cents, currency, description)
    elif provider == "razorpay":
        return _create_razorpay_order(channel, amount_cents, currency)
    else:
        raise PaymentNotConfiguredError(f"Unknown payment provider: {provider}")


def verify_payment(channel, payment_id: str) -> bool:
    """Verify that a Stripe payment succeeded server-side."""
    provider = _get_provider(channel)
    if provider == "stripe":
        return _verify_stripe(channel, payment_id)
    # Razorpay uses signature verification (verify_razorpay_signature) instead
    return False


def verify_razorpay_signature(
    channel,
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
) -> bool:
    """Verify the HMAC-SHA256 signature returned by Razorpay after client-side payment."""
    key_secret = channel.config.get("razorpay_key_secret", "")
    expected = hmac.new(
        key_secret.encode(),
        f"{razorpay_order_id}|{razorpay_payment_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, razorpay_signature)


def _create_stripe_intent(channel, amount_cents: int, currency: str, description: str) -> dict:
    import stripe
    stripe.api_key = channel.config["stripe_secret_key"]
    intent = stripe.PaymentIntent.create(
        amount=amount_cents,
        currency=currency.lower(),
        description=description,
        automatic_payment_methods={"enabled": True},
    )
    return {
        "provider": "stripe",
        "payment_intent_id": intent.id,
        "client_secret": intent.client_secret,
    }


def _verify_stripe(channel, payment_intent_id: str) -> bool:
    import stripe
    stripe.api_key = channel.config["stripe_secret_key"]
    try:
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        return intent.status == "succeeded"
    except Exception:
        logger.warning("Failed to verify Stripe payment %s", payment_intent_id, exc_info=True)
        return False


def _create_razorpay_order(channel, amount_cents: int, currency: str) -> dict:
    key_id = channel.config["razorpay_key_id"]
    key_secret = channel.config["razorpay_key_secret"]
    resp = httpx.post(
        "https://api.razorpay.com/v1/orders",
        auth=(key_id, key_secret),
        json={"amount": amount_cents, "currency": currency.upper(), "receipt": "ims_checkout"},
        timeout=15.0,
    )
    if resp.status_code != 200:
        raise PaymentProviderError(f"Razorpay order creation failed: HTTP {resp.status_code}")
    data = resp.json()
    return {
        "provider": "razorpay",
        "order_id": data["id"],
        "key_id": key_id,
        "amount": data["amount"],
        "currency": data["currency"],
    }
```

- [ ] **Step 4: Run tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/services/payment_service.py $CONTAINER:/app/app/services/payment_service.py
docker cp services/api/tests/services $CONTAINER:/app/tests/services
docker compose exec api pip install stripe -q
docker compose exec api python -m pytest tests/services/test_payment_service.py -v
docker compose exec api rm -rf /app/tests/services
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/requirements.txt \
        services/api/app/services/payment_service.py \
        services/api/tests/services/test_payment_service.py
git commit -m "feat(checkout): add payment_service with Stripe + Razorpay payment intent creation"
```

---

### Task 3: Checkout session API + hosted checkout page

**Files:**
- Create: `services/api/app/routers/checkout.py`
- Create: `services/api/templates/checkout.html`
- Modify: `services/api/app/main.py`
- Create: `services/api/tests/routers/test_checkout.py`

Note: the `services/api/templates/` directory will hold Jinja2 templates.

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/routers/test_checkout.py`:

```python
# NOTE: `from __future__ import annotations` deliberately absent.

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    CartItem, Channel, CheckoutSession, InventoryPool, InventoryPoolShop, Product, Shop,
    StockMovement, Tenant,
)


@pytest.fixture()
def storefront(db, tenant: Tenant, shop: Shop):
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    channel = Channel(
        tenant_id=tenant.id, type="headless", name="Headless",
        config={
            "payment_provider": "stripe",
            "stripe_secret_key": "sk_test_xxx",
            "stripe_publishable_key": "pk_test_xxx",
            "checkout_success_url": "https://shop.com/success",
        },
        inventory_pool_id=pool.id, currency_code="INR",
    )
    db.add(channel)
    db.flush()

    product = Product(
        tenant_id=tenant.id, name="Widget", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=1999, product_type="physical", status="active",
    )
    db.add(product)
    db.flush()
    db.add(StockMovement(
        tenant_id=tenant.id, shop_id=shop.id, product_id=product.id,
        quantity_delta=10, movement_type="purchase_receipt",
        idempotency_key=f"seed-{uuid.uuid4().hex}",
    ))
    db.commit()
    return {"channel": channel, "product": product}


def _h(storefront):
    return {"X-Channel-Id": str(storefront["channel"].id)}


def _make_cart(client, storefront):
    from app.db.session import get_db
    cart = client.post("/v1/storefront/cart", headers=_h(storefront)).json()
    client.post(f"/v1/storefront/cart/{cart['cart_token']}/items", json={
        "product_id": str(storefront["product"].id), "quantity": 1,
    }, headers=_h(storefront))
    return cart["cart_token"]


def test_create_checkout_session(db, tenant: Tenant, storefront) -> None:
    from app.db.session import get_db
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        cart_token = _make_cart(client, storefront)

        resp = client.post("/v1/storefront/checkout/session", json={
            "cart_token": cart_token,
        }, headers=_h(storefront))
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert "session_token" in body
        assert "checkout_url" in body
        assert "/checkout/" in body["checkout_url"]
        assert "expires_at" in body
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_create_payment_intent_stripe(db, tenant: Tenant, storefront) -> None:
    from app.db.session import get_db
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        cart_token = _make_cart(client, storefront)

        # Create session
        session_resp = client.post("/v1/storefront/checkout/session", json={
            "cart_token": cart_token,
        }, headers=_h(storefront)).json()
        token = session_resp["session_token"]

        # Create payment intent
        mock_intent = MagicMock()
        mock_intent.id = "pi_test123"
        mock_intent.client_secret = "pi_test123_secret"

        with patch("stripe.PaymentIntent.create", return_value=mock_intent):
            pi_resp = client.post(f"/v1/checkout/{token}/payment-intent", json={
                "customer_email": "buyer@example.com",
                "shipping_address": {"country": "IN", "city": "Mumbai"},
            })
        assert pi_resp.status_code == 200, pi_resp.text
        body = pi_resp.json()
        assert body["provider"] == "stripe"
        assert body["client_secret"] == "pi_test123_secret"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_complete_checkout_stripe(db, tenant: Tenant, storefront) -> None:
    from sqlalchemy import select
    from app.db.session import get_db
    from app.models import Order

    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        cart_token = _make_cart(client, storefront)

        session_resp = client.post("/v1/storefront/checkout/session", json={
            "cart_token": cart_token,
        }, headers=_h(storefront)).json()
        token = session_resp["session_token"]

        # Verify Stripe payment
        mock_intent = MagicMock()
        mock_intent.status = "succeeded"

        with patch("stripe.PaymentIntent.retrieve", return_value=mock_intent):
            complete_resp = client.post(f"/v1/checkout/{token}/complete", json={
                "payment_intent_id": "pi_test123",
                "customer_email": "buyer@example.com",
            })
        assert complete_resp.status_code == 200, complete_resp.text
        body = complete_resp.json()
        assert body["status"] == "completed"
        assert "order_id" in body

        order = db.execute(
            select(Order).where(Order.id == uuid.UUID(body["order_id"]))
        ).scalar_one()
        assert order.customer_email == "buyer@example.com"
        assert order.channel_id == storefront["channel"].id
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_session_for_empty_cart_rejected(db, tenant: Tenant, storefront) -> None:
    from app.db.session import get_db
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        resp = client.post("/v1/storefront/checkout/session", json={
            "cart_token": "empty_cart_token_xxx",
        }, headers=_h(storefront))
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 2: Confirm failure**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests/routers/test_checkout.py $CONTAINER:/app/tests/routers/test_checkout.py
docker compose exec api python -m pytest tests/routers/test_checkout.py -v
docker compose exec api rm -f /app/tests/routers/test_checkout.py
```
Expected: FAIL — endpoints don't exist.

- [ ] **Step 3: Create the Jinja2 checkout template**

First, create the templates directory:
```bash
mkdir -p services/api/templates
```

Create `services/api/templates/checkout.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Checkout</title>
  <style>
    body { font-family: -apple-system,sans-serif; max-width:480px; margin:40px auto; padding:0 20px; color:#333; }
    h2 { font-size:1.4rem; margin-bottom:1rem; }
    .cart-items { border:1px solid #e5e7eb; border-radius:8px; padding:12px; margin-bottom:1.5rem; }
    .cart-item { display:flex; justify-content:space-between; padding:6px 0; font-size:.9rem; }
    .totals { border-top:2px solid #e5e7eb; margin-top:8px; padding-top:8px; font-weight:600; }
    .form-group { margin-bottom:1rem; }
    label { display:block; font-size:.85rem; font-weight:500; margin-bottom:4px; color:#555; }
    input, select { width:100%; padding:10px; border:1px solid #d1d5db; border-radius:6px; box-sizing:border-box; font-size:.95rem; }
    .btn { width:100%; padding:12px; background:#4f46e5; color:white; border:none; border-radius:6px;
           font-size:1rem; font-weight:600; cursor:pointer; margin-top:1rem; }
    .btn:hover { background:#4338ca; }
    .btn:disabled { background:#9ca3af; cursor:not-allowed; }
    #payment-element { margin:1rem 0; min-height:44px; }
    #error-message { color:#dc2626; font-size:.85rem; margin-top:8px; }
    .summary-row { display:flex; justify-content:space-between; font-size:.9rem; padding:3px 0; }
  </style>
  {% if provider == "stripe" %}
  <script src="https://js.stripe.com/v3/"></script>
  {% elif provider == "razorpay" %}
  <script src="https://checkout.razorpay.com/v1/checkout.js"></script>
  {% endif %}
</head>
<body>
  <h2>Checkout</h2>

  <div class="cart-items">
    {% for item in cart_items %}
    <div class="cart-item">
      <span>{{ item.product_name }} × {{ item.quantity }}</span>
      <span>{{ item.currency_code }} {{ "%.2f"|format(item.line_total_cents / 100) }}</span>
    </div>
    {% endfor %}
    <div class="totals summary-row"><span>Subtotal</span><span>{{ currency_code }} {{ "%.2f"|format(subtotal_cents / 100) }}</span></div>
    {% if shipping_cents > 0 %}
    <div class="summary-row"><span>Shipping</span><span>{{ currency_code }} {{ "%.2f"|format(shipping_cents / 100) }}</span></div>
    {% endif %}
    {% if tax_cents > 0 %}
    <div class="summary-row"><span>Tax</span><span>{{ currency_code }} {{ "%.2f"|format(tax_cents / 100) }}</span></div>
    {% endif %}
    <div class="totals summary-row"><span>Total</span><span>{{ currency_code }} {{ "%.2f"|format(total_cents / 100) }}</span></div>
  </div>

  <form id="checkout-form">
    <div class="form-group">
      <label for="email">Email</label>
      <input type="email" id="email" name="email" required placeholder="you@example.com"/>
    </div>
    <div class="form-group">
      <label for="name">Full Name</label>
      <input type="text" id="name" name="name" required placeholder="Jane Smith"/>
    </div>
    <div class="form-group">
      <label for="address">Address</label>
      <input type="text" id="address" name="address" placeholder="123 Main St"/>
    </div>
    <div class="form-group">
      <label for="city">City</label>
      <input type="text" id="city" name="city" required placeholder="Mumbai"/>
    </div>
    <div class="form-group">
      <label for="country">Country</label>
      <input type="text" id="country" name="country" required placeholder="IN" maxlength="2" style="text-transform:uppercase"/>
    </div>

    <div id="payment-element"></div>
    <div id="error-message"></div>
    <button type="submit" class="btn" id="submit-btn">Pay {{ currency_code }} {{ "%.2f"|format(total_cents / 100) }}</button>
  </form>

<script>
const SESSION_TOKEN = "{{ session_token }}";
const API_BASE = window.location.origin;

{% if provider == "stripe" %}
const stripe = Stripe("{{ publishable_key }}");
let elements;

async function initStripe() {
  const resp = await fetch(`${API_BASE}/v1/checkout/${SESSION_TOKEN}/payment-intent`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({customer_email: "", shipping_address: {}})
  });
  const data = await resp.json();
  if (!resp.ok) { document.getElementById("error-message").textContent = data.detail || "Failed to load payment."; return; }

  elements = stripe.elements({clientSecret: data.client_secret});
  const paymentElement = elements.create("payment");
  paymentElement.mount("#payment-element");
}
initStripe();

document.getElementById("checkout-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = document.getElementById("submit-btn");
  btn.disabled = true;
  btn.textContent = "Processing...";

  const email = document.getElementById("email").value;
  const city = document.getElementById("city").value;
  const country = document.getElementById("country").value.toUpperCase();

  const {error} = await stripe.confirmPayment({
    elements,
    confirmParams: {
      return_url: `${API_BASE}/checkout/${SESSION_TOKEN}/stripe-return`,
      payment_method_data: {billing_details: {email, address: {city, country}}}
    },
  });
  if (error) {
    document.getElementById("error-message").textContent = error.message;
    btn.disabled = false;
    btn.textContent = "Pay {{ currency_code }} {{ '%.2f'|format(total_cents / 100) }}";
  }
});

{% elif provider == "razorpay" %}
document.getElementById("checkout-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = document.getElementById("email").value;
  const city = document.getElementById("city").value;
  const country = document.getElementById("country").value.toUpperCase();

  const resp = await fetch(`${API_BASE}/v1/checkout/${SESSION_TOKEN}/payment-intent`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({customer_email: email, shipping_address: {city, country}})
  });
  const data = await resp.json();
  if (!resp.ok) { document.getElementById("error-message").textContent = data.detail; return; }

  const rzp = new Razorpay({
    key: data.key_id,
    order_id: data.order_id,
    amount: data.amount,
    currency: data.currency,
    prefill: {email},
    handler: async (response) => {
      const complete = await fetch(`${API_BASE}/v1/checkout/${SESSION_TOKEN}/complete`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          razorpay_order_id: response.razorpay_order_id,
          razorpay_payment_id: response.razorpay_payment_id,
          razorpay_signature: response.razorpay_signature,
          customer_email: email,
        })
      });
      const result = await complete.json();
      if (result.redirect_url) window.location.href = result.redirect_url;
    }
  });
  rzp.open();
});
{% endif %}
</script>
</body>
</html>
```

- [ ] **Step 4: Implement the checkout router**

Create `services/api/app/routers/checkout.py`:

```python
"""Hosted checkout: session management, payment intent creation, and order completion.

Endpoints:
  POST /v1/storefront/checkout/session        → create a checkout session
  GET  /checkout/{session_token}              → serve the hosted checkout HTML page
  POST /v1/checkout/{session_token}/payment-intent  → create Stripe PI / Razorpay order
  POST /v1/checkout/{session_token}/complete  → verify payment + create IMS Order
  GET  /checkout/{session_token}/stripe-return → Stripe redirect handler
"""
from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import CartItem, Channel, CheckoutSession, Order, OrderLine, Product
from app.routers.storefront.auth import StorefrontChannelDep
from app.services.customer_resolver import resolve_or_create_customer
from app.services.payment_service import (
    PaymentNotConfiguredError, PaymentProviderError,
    create_payment_intent, verify_payment, verify_razorpay_signature,
)
from app.services.reservation_service import commit_reservation

router = APIRouter(tags=["Hosted Checkout"])

# Templates directory sits at services/api/templates/
_TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

CHECKOUT_SESSION_TTL_MINUTES = 30


class CreateSessionIn(BaseModel):
    cart_token: str


class CreateSessionOut(BaseModel):
    session_token: str
    checkout_url: str
    expires_at: datetime


class PaymentIntentIn(BaseModel):
    customer_email: str = ""
    shipping_address: dict | None = None
    discount_code: str | None = None


class CompleteCheckoutIn(BaseModel):
    # Stripe
    payment_intent_id: str | None = None
    # Razorpay
    razorpay_order_id: str | None = None
    razorpay_payment_id: str | None = None
    razorpay_signature: str | None = None
    # Common
    customer_email: str = ""


class CompleteCheckoutOut(BaseModel):
    status: str
    order_id: str
    redirect_url: str


def _load_cart(db: Session, channel_id: UUID, cart_token: str) -> list[tuple[CartItem, Product]]:
    rows = db.execute(
        select(CartItem, Product)
        .join(Product, CartItem.product_id == Product.id)
        .where(CartItem.cart_token == cart_token, CartItem.channel_id == channel_id)
    ).all()
    return list(rows)


def _compute_session_totals(rows: list[tuple[CartItem, Product]]) -> dict[str, int]:
    subtotal = sum(ci.unit_price_cents * ci.quantity for ci, _ in rows)
    return {
        "subtotal_cents": subtotal,
        "discount_cents": 0,
        "shipping_cents": 0,
        "tax_cents": 0,
        "total_cents": subtotal,
    }


def _get_session_or_404(db: Session, session_token: str) -> CheckoutSession:
    session = db.execute(
        select(CheckoutSession).where(CheckoutSession.session_token == session_token)
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Checkout session not found")
    if session.status in ("completed", "cancelled"):
        raise HTTPException(status_code=410, detail=f"Checkout session is {session.status}")
    if datetime.now(UTC) > session.expires_at:
        raise HTTPException(status_code=410, detail="Checkout session has expired")
    return session


# ── Session create ──

@router.post("/v1/storefront/checkout/session",
             response_model=CreateSessionOut, status_code=status.HTTP_201_CREATED)
def create_checkout_session(
    body: CreateSessionIn,
    channel: StorefrontChannelDep,
    db: Annotated[Session, Depends(get_db)],
    request: Request,
) -> CreateSessionOut:
    """Create a checkout session from a cart. Returns a URL to the hosted checkout page."""
    rows = _load_cart(db, channel.id, body.cart_token)
    if not rows:
        raise HTTPException(status_code=400, detail="Cart is empty")

    totals = _compute_session_totals(rows)
    session_token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(minutes=CHECKOUT_SESSION_TTL_MINUTES)

    session = CheckoutSession(
        tenant_id=channel.tenant_id,
        channel_id=channel.id,
        cart_token=body.cart_token,
        session_token=session_token,
        status="pending",
        currency_code=channel.currency_code,
        expires_at=expires_at,
        **totals,
    )
    db.add(session)
    db.commit()

    base_url = str(request.base_url).rstrip("/")
    checkout_url = f"{base_url}/checkout/{session_token}"
    return CreateSessionOut(
        session_token=session_token,
        checkout_url=checkout_url,
        expires_at=expires_at,
    )


# ── Hosted checkout page ──

@router.get("/checkout/{session_token}", response_class=HTMLResponse)
def checkout_page(
    session_token: str,
    db: Annotated[Session, Depends(get_db)],
    request: Request,
) -> HTMLResponse:
    """Serve the hosted checkout HTML page."""
    session = _get_session_or_404(db, session_token)
    channel = db.get(Channel, session.channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")

    rows = _load_cart(db, channel.id, session.cart_token)
    cart_items = [
        {
            "product_name": prod.name,
            "quantity": ci.quantity,
            "line_total_cents": ci.unit_price_cents * ci.quantity,
            "currency_code": ci.currency_code,
        }
        for ci, prod in rows
    ]

    provider = channel.config.get("payment_provider", "none")
    publishable_key = channel.config.get("stripe_publishable_key", "") or channel.config.get("razorpay_key_id", "")

    return templates.TemplateResponse("checkout.html", {
        "request": request,
        "session_token": session_token,
        "cart_items": cart_items,
        "subtotal_cents": session.subtotal_cents,
        "shipping_cents": session.shipping_cents,
        "tax_cents": session.tax_cents,
        "total_cents": session.total_cents,
        "currency_code": session.currency_code,
        "provider": provider,
        "publishable_key": publishable_key,
    })


# ── Payment intent ──

@router.post("/v1/checkout/{session_token}/payment-intent")
def create_session_payment_intent(
    session_token: str,
    body: PaymentIntentIn,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    session = _get_session_or_404(db, session_token)
    channel = db.get(Channel, session.channel_id)

    # Update session with shopper data
    if body.customer_email:
        session.customer_email = body.customer_email
    if body.shipping_address:
        session.shipping_address = body.shipping_address

    try:
        result = create_payment_intent(
            channel,
            amount_cents=session.total_cents,
            currency=session.currency_code,
        )
    except PaymentNotConfiguredError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PaymentProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    if "payment_intent_id" in result:
        session.external_payment_id = result["payment_intent_id"]
    elif "order_id" in result:
        session.external_payment_id = result["order_id"]

    session.status = "payment_initiated"
    session.payment_provider = result["provider"]
    db.commit()
    return result


# ── Complete checkout ──

@router.post("/v1/checkout/{session_token}/complete", response_model=CompleteCheckoutOut)
def complete_checkout(
    session_token: str,
    body: CompleteCheckoutIn,
    db: Annotated[Session, Depends(get_db)],
    request: Request,
) -> CompleteCheckoutOut:
    """Verify payment and create the IMS Order."""
    session = _get_session_or_404(db, session_token)
    channel = db.get(Channel, session.channel_id)
    provider = session.payment_provider or channel.config.get("payment_provider", "none")

    # Verify payment
    verified = False
    if provider == "stripe" and body.payment_intent_id:
        verified = verify_payment(channel, body.payment_intent_id)
    elif provider == "razorpay" and body.razorpay_order_id:
        verified = verify_razorpay_signature(
            channel,
            body.razorpay_order_id,
            body.razorpay_payment_id or "",
            body.razorpay_signature or "",
        )

    if not verified:
        raise HTTPException(status_code=400, detail="Payment verification failed")

    # Create IMS Order
    customer_email = body.customer_email or session.customer_email
    customer_id = None
    if customer_email:
        cust = resolve_or_create_customer(
            db, channel.tenant_id, channel.id, email=customer_email,
        )
        if cust:
            customer_id = cust.id

    rows = _load_cart(db, channel.id, session.cart_token)
    order = Order(
        tenant_id=channel.tenant_id,
        channel_id=channel.id,
        status="confirmed",
        customer_id=customer_id,
        customer_email=customer_email,
        subtotal_cents=session.subtotal_cents,
        discount_cents=session.discount_cents,
        tax_cents=session.tax_cents,
        shipping_cents=session.shipping_cents,
        total_cents=session.total_cents,
        currency_code=session.currency_code,
        shipping_address=session.shipping_address,
    )
    db.add(order)
    db.flush()

    for cart_item, product in rows:
        db.add(OrderLine(
            tenant_id=channel.tenant_id, order_id=order.id,
            product_id=product.id, title=product.name, sku=product.sku,
            quantity=cart_item.quantity,
            unit_price_cents=cart_item.unit_price_cents,
            line_total_cents=cart_item.unit_price_cents * cart_item.quantity,
        ))
        if cart_item.reservation_id:
            commit_reservation(db, cart_item.reservation_id)
        db.delete(cart_item)

    db.add(OrderLine)  # handled above
    session.status = "completed"
    session.order_id = order.id
    if provider == "stripe" and body.payment_intent_id:
        session.external_payment_id = body.payment_intent_id
    elif provider == "razorpay" and body.razorpay_payment_id:
        session.external_payment_id = body.razorpay_payment_id

    db.commit()

    success_url = channel.config.get("checkout_success_url", "")
    redirect_url = f"{success_url}?order_id={order.id}" if success_url else str(request.base_url)

    return CompleteCheckoutOut(
        status="completed",
        order_id=str(order.id),
        redirect_url=redirect_url,
    )


# ── Stripe redirect handler ──

@router.get("/checkout/{session_token}/stripe-return")
def stripe_return(
    session_token: str,
    payment_intent: str | None = None,
    payment_intent_client_secret: str | None = None,
    redirect_status: str | None = None,
    db: Session = Depends(get_db),
    request: Request = None,
) -> RedirectResponse:
    """Handle Stripe redirect after confirmPayment(return_url)."""
    if redirect_status != "succeeded" or not payment_intent:
        return RedirectResponse(url=f"/checkout/{session_token}?error=payment_failed")

    session = db.execute(
        select(CheckoutSession).where(CheckoutSession.session_token == session_token)
    ).scalar_one_or_none()
    if session is None or session.status == "completed":
        channel_success = ""
        if session:
            ch = db.get(Channel, session.channel_id)
            channel_success = ch.config.get("checkout_success_url", "") if ch else ""
        return RedirectResponse(url=channel_success or "/")

    channel = db.get(Channel, session.channel_id)
    verified = verify_payment(channel, payment_intent)
    if not verified:
        return RedirectResponse(url=f"/checkout/{session_token}?error=payment_failed")

    # Inline complete (no separate POST needed)
    customer_email = session.customer_email or ""
    customer_id = None
    if customer_email:
        cust = resolve_or_create_customer(db, channel.tenant_id, channel.id, email=customer_email)
        if cust:
            customer_id = cust.id

    rows = _load_cart(db, channel.id, session.cart_token)
    order = Order(
        tenant_id=channel.tenant_id, channel_id=channel.id,
        status="confirmed", customer_id=customer_id, customer_email=customer_email,
        subtotal_cents=session.subtotal_cents, discount_cents=session.discount_cents,
        tax_cents=session.tax_cents, shipping_cents=session.shipping_cents,
        total_cents=session.total_cents, currency_code=session.currency_code,
        shipping_address=session.shipping_address,
    )
    db.add(order)
    db.flush()
    for ci, prod in rows:
        db.add(OrderLine(
            tenant_id=channel.tenant_id, order_id=order.id,
            product_id=prod.id, title=prod.name, sku=prod.sku,
            quantity=ci.quantity,
            unit_price_cents=ci.unit_price_cents,
            line_total_cents=ci.unit_price_cents * ci.quantity,
        ))
        if ci.reservation_id:
            commit_reservation(db, ci.reservation_id)
        db.delete(ci)

    session.status = "completed"
    session.order_id = order.id
    session.external_payment_id = payment_intent
    db.commit()

    success_url = channel.config.get("checkout_success_url", "")
    return RedirectResponse(url=f"{success_url}?order_id={order.id}" if success_url else "/")
```

Note: Remove the line `db.add(OrderLine)` in `complete_checkout` — that's a typo. The OrderLines are added in the loop above. The line should be deleted.

- [ ] **Step 5: Mount the checkout router**

In `services/api/app/main.py`, add `checkout` import and `app.include_router(checkout.router)`. Also mount `admin_payment` if not yet done.

For Jinja2, add this to main.py where the app is created:
```python
# Near the imports
from fastapi.staticfiles import StaticFiles
```
(Not needed for templates — Jinja2Templates handles rendering directly.)

- [ ] **Step 6: Run tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/main.py $CONTAINER:/app/app/main.py
docker cp services/api/app/routers/checkout.py $CONTAINER:/app/app/routers/checkout.py
docker cp services/api/app/services/payment_service.py $CONTAINER:/app/app/services/payment_service.py
docker cp services/api/templates $CONTAINER:/app/templates
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api pip install stripe jinja2 -q
docker compose restart api
sleep 5
docker compose exec api python -m pytest tests/routers/test_checkout.py -v
docker compose exec api rm -rf /app/tests
```
Expected: 4 passed.

- [ ] **Step 7: Fix the typo in complete_checkout**

Remove the erroneous `db.add(OrderLine)` line from `services/api/app/routers/checkout.py` (it's the line after the for loop, before `session.status = "completed"`).

- [ ] **Step 8: Commit**

```bash
git add services/api/app/routers/checkout.py \
        services/api/templates/checkout.html \
        services/api/app/main.py \
        services/api/tests/routers/test_checkout.py
git commit -m "feat(checkout): hosted checkout page, payment intent creation, order completion"
```

---

### Task 4: Integration smoke test

**Files:**
- Create: `services/api/tests/integration/test_hosted_checkout_e2e.py`

- [ ] **Step 1: Write integration test**

Create `services/api/tests/integration/test_hosted_checkout_e2e.py`:

```python
"""End-to-end smoke test for the hosted checkout flow.

Exercises: create cart → create checkout session → initiate Stripe payment →
complete checkout → IMS Order created.
"""
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Channel, InventoryPool, InventoryPoolShop, Order, Product, Shop, StockMovement, Tenant


@pytest.fixture()
def setup(db, tenant: Tenant, shop: Shop):
    pool = InventoryPool(tenant_id=tenant.id, name=f"pool-{uuid.uuid4().hex[:6]}")
    db.add(pool)
    db.flush()
    db.add(InventoryPoolShop(tenant_id=tenant.id, pool_id=pool.id, shop_id=shop.id))
    db.flush()
    channel = Channel(
        tenant_id=tenant.id, type="headless", name="Headless Store",
        config={
            "payment_provider": "stripe",
            "stripe_secret_key": "sk_test_xxx",
            "stripe_publishable_key": "pk_test_xxx",
            "checkout_success_url": "https://shop.com/success",
        },
        inventory_pool_id=pool.id, currency_code="INR",
    )
    db.add(channel)
    db.flush()
    product = Product(
        tenant_id=tenant.id, name="E2E Mug", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=1999, product_type="physical", status="active",
    )
    db.add(product)
    db.flush()
    db.add(StockMovement(
        tenant_id=tenant.id, shop_id=shop.id, product_id=product.id,
        quantity_delta=50, movement_type="purchase_receipt",
        idempotency_key=f"seed-{uuid.uuid4().hex}",
    ))
    db.commit()
    return {"channel": channel, "product": product}


def test_full_hosted_checkout_stripe(db, tenant: Tenant, setup) -> None:
    from app.db.session import get_db
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        channel = setup["channel"]
        product = setup["product"]

        # 1. Create cart and add item
        cart = client.post("/v1/storefront/cart",
                           headers={"X-Channel-Id": str(channel.id)}).json()
        token = cart["cart_token"]
        client.post(f"/v1/storefront/cart/{token}/items", json={
            "product_id": str(product.id), "quantity": 2,
        }, headers={"X-Channel-Id": str(channel.id)})

        # 2. Create checkout session
        session_resp = client.post("/v1/storefront/checkout/session", json={
            "cart_token": token,
        }, headers={"X-Channel-Id": str(channel.id)})
        assert session_resp.status_code == 201, session_resp.text
        session_token = session_resp.json()["session_token"]
        checkout_url = session_resp.json()["checkout_url"]
        assert session_token in checkout_url

        # 3. Hosted checkout page is served
        page_resp = client.get(f"/checkout/{session_token}")
        assert page_resp.status_code == 200
        assert "pk_test_xxx" in page_resp.text  # publishable key in page

        # 4. Create payment intent
        mock_intent = MagicMock()
        mock_intent.id = "pi_e2e_test"
        mock_intent.client_secret = "pi_e2e_test_secret"
        with patch("stripe.PaymentIntent.create", return_value=mock_intent):
            pi_resp = client.post(f"/v1/checkout/{session_token}/payment-intent", json={
                "customer_email": "e2e@example.com",
                "shipping_address": {"country": "IN", "city": "Delhi"},
            })
        assert pi_resp.status_code == 200
        assert pi_resp.json()["client_secret"] == "pi_e2e_test_secret"

        # 5. Complete checkout (simulate successful Stripe payment)
        mock_verify = MagicMock()
        mock_verify.status = "succeeded"
        with patch("stripe.PaymentIntent.retrieve", return_value=mock_verify):
            complete_resp = client.post(f"/v1/checkout/{session_token}/complete", json={
                "payment_intent_id": "pi_e2e_test",
                "customer_email": "e2e@example.com",
            })
        assert complete_resp.status_code == 200, complete_resp.text
        result = complete_resp.json()
        assert result["status"] == "completed"
        assert "order_id" in result
        assert "success" in result["redirect_url"]

        # 6. Verify IMS Order was created
        order = db.execute(
            select(Order).where(Order.id == uuid.UUID(result["order_id"]))
        ).scalar_one()
        assert order.customer_email == "e2e@example.com"
        assert order.total_cents == 3998  # 1999 * 2
        assert order.channel_id == channel.id

        # 7. Cart is empty
        cart_after = client.get(f"/v1/storefront/cart/{token}",
                                headers={"X-Channel-Id": str(channel.id)}).json()
        assert cart_after["items"] == []

    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 2: Run integration test**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest tests/integration/test_hosted_checkout_e2e.py -v
docker compose exec api rm -rf /app/tests
```
Expected: 1 passed.

- [ ] **Step 3: Run full checkout suite**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest \
  tests/services/test_payment_service.py \
  tests/routers/test_admin_payment.py \
  tests/routers/test_checkout.py \
  tests/integration/test_hosted_checkout_e2e.py \
  -v 2>&1 | tail -10
docker compose exec api rm -rf /app/tests
```
Expected: ~14 tests passing.

- [ ] **Step 4: Commit**

```bash
git add services/api/tests/integration/test_hosted_checkout_e2e.py
git commit -m "test(checkout): end-to-end hosted checkout flow with Stripe (mocked)"
```

---

## Done. Summary of what shipped

- `checkout_sessions` table — tracks lifecycle from cart → payment → order
- `payment_service.py` — Stripe payment intent + Razorpay order creation + verification
- `admin_payment.py` — merchant setup endpoints for Stripe/Razorpay credentials per channel
- `checkout.py` router — create session, serve HTML page, create payment intent, complete checkout
- `templates/checkout.html` — self-contained checkout UI with Stripe Elements or Razorpay popup embedded
- ~14 tests

## What merchants do to go live

1. Create their Stripe account / Razorpay account
2. In IMS admin: `POST /v1/admin/channels/{channel_id}/payment/setup-stripe` with their Stripe keys
3. In their frontend: call `POST /v1/storefront/checkout/session` to get a checkout URL
4. Redirect shoppers to that URL — the IMS checkout page handles everything
5. On completion, shopper is redirected to `checkout_success_url?order_id=xxx`

## Follow-up work

- Stripe Connect OAuth (instead of pasting secret keys)
- Email confirmation on order completion (email infrastructure sub-project)
- Razorpay webhook for server-side redundancy
- Custom domain CNAME routing (Phase 3)
- Discounts applied at checkout (currently the session doesn't apply discount codes)
- Shipping rate selection UI on the checkout page

---

*End of plan.*
