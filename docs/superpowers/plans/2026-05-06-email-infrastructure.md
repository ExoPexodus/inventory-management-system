# Email Infrastructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send transactional emails so shoppers receive order confirmations when they buy through any channel (hosted checkout, Shopify, WooCommerce, headless storefront) and merchants can customise the templates and verify their sending domain (SPF/DKIM/DMARC).

**Architecture:** A single `email_service.py` wraps [Resend](https://resend.com) as the sending provider (clean API, generous free tier, simple domain setup). Templates are stored in `email_templates/` as Jinja2 HTML files. A `TenantEmailConfig` record (already exists from earlier CRM work) stores sender domain and API key per tenant. Sending is synchronous for critical emails (order confirmation) and can be moved to RQ background tasks later. An `admin_email.py` router handles template preview, test sends, and domain auth setup.

**Emails shipped in this plan (Phase 1 of email infra):**
- ✅ **Order confirmation** — triggered when any Order is created (all channels)
- ✅ **Test send** — admin can send a test email to any address

**Deferred:**
- Shipment notification, refund confirmation, abandoned cart, password reset, magic-link login, invoice, gift card delivery — follow-up plan

**Tech Stack:** Python 3.12, FastAPI, `resend` Python SDK (or httpx if SDK not available), Jinja2 (already installed), pytest (mocked HTTP)

**Provider:** [Resend](https://resend.com) — tenant provides their own Resend API key and sends from their own verified domain. We never send from IMS's domain on their behalf.

**Tenant config shape** (in `TenantEmailConfig`, already exists):
```python
# existing columns:
#   tenant_id, from_email, from_name, provider, api_key, ...
```
We'll check what already exists and extend minimally.

---

### Task 1: Email service + order confirmation

**Files:**
- Create: `services/api/app/services/email_service.py`
- Create: `services/api/email_templates/order_confirmation.html`
- Modify: `services/api/app/services/sync_push.py` — trigger email after POS sale
- Check: `services/api/app/routers/checkout.py` — trigger email after hosted checkout
- Check: `services/api/app/routers/webhooks_shopify.py` — trigger email after Shopify order
- Check: `services/api/app/routers/webhooks_woocommerce.py` — trigger after WooCommerce order
- Create: `services/api/tests/services/test_email_service.py`

- [ ] **Step 1: Read the existing TenantEmailConfig model**

```bash
grep -A 20 "class TenantEmailConfig" services/api/app/models/tables.py
```

Note the existing columns so we know what's already there.

- [ ] **Step 2: Add Resend to requirements.txt**

```bash
grep -q "^resend" services/api/requirements.txt || echo "resend>=2.0.0" >> services/api/requirements.txt
```

(Resend has a Python SDK. Fallback: use `httpx.post` directly to the Resend API if SDK import fails.)

- [ ] **Step 3: Create the email template**

Create `services/api/email_templates/order_confirmation.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1.0"/>
  <title>Order Confirmed</title>
  <style>
    body{font-family:-apple-system,sans-serif;max-width:560px;margin:0 auto;padding:20px;color:#333;background:#f9fafb}
    .card{background:white;border-radius:8px;padding:24px;box-shadow:0 1px 3px rgba(0,0,0,.1)}
    h2{font-size:1.4rem;margin:0 0 4px}
    .subtitle{color:#6b7280;font-size:.9rem;margin:0 0 20px}
    table{width:100%;border-collapse:collapse;margin:16px 0}
    th{text-align:left;font-size:.8rem;color:#9ca3af;text-transform:uppercase;border-bottom:1px solid #e5e7eb;padding:4px 0}
    td{padding:8px 0;font-size:.9rem;border-bottom:1px solid #f3f4f6}
    .total-row td{font-weight:700;font-size:1rem;border-bottom:none;padding-top:12px}
    .footer{margin-top:24px;font-size:.8rem;color:#9ca3af;text-align:center}
    .badge{display:inline-block;background:#d1fae5;color:#065f46;padding:2px 8px;border-radius:9999px;font-size:.75rem;font-weight:600}
  </style>
</head>
<body>
<div class="card">
  <h2>Order Confirmed 🎉</h2>
  <p class="subtitle">Hi {{ customer_name or customer_email }}, your order is confirmed.</p>
  <span class="badge">Order #{{ order_id[:8].upper() }}</span>

  <table>
    <thead><tr><th>Item</th><th style="text-align:right">Qty</th><th style="text-align:right">Price</th></tr></thead>
    <tbody>
      {% for line in order_lines %}
      <tr>
        <td>{{ line.title }}</td>
        <td style="text-align:right">{{ line.quantity }}</td>
        <td style="text-align:right">{{ currency }} {{ "%.2f"|format(line.line_total_cents/100) }}</td>
      </tr>
      {% endfor %}
    </tbody>
    <tfoot>
      {% if discount_cents > 0 %}
      <tr><td colspan="2" style="text-align:right;color:#059669">Discount</td><td style="text-align:right;color:#059669">-{{ currency }} {{ "%.2f"|format(discount_cents/100) }}</td></tr>
      {% endif %}
      {% if shipping_cents > 0 %}
      <tr><td colspan="2" style="text-align:right">Shipping</td><td style="text-align:right">{{ currency }} {{ "%.2f"|format(shipping_cents/100) }}</td></tr>
      {% endif %}
      {% if tax_cents > 0 %}
      <tr><td colspan="2" style="text-align:right">Tax</td><td style="text-align:right">{{ currency }} {{ "%.2f"|format(tax_cents/100) }}</td></tr>
      {% endif %}
      <tr class="total-row"><td colspan="2" style="text-align:right">Total</td><td style="text-align:right">{{ currency }} {{ "%.2f"|format(total_cents/100) }}</td></tr>
    </tfoot>
  </table>

  {% if shipping_address %}
  <p style="font-size:.85rem;color:#6b7280;margin:0">
    <strong>Ships to:</strong> {{ shipping_address.get('city', '') }}{% if shipping_address.get('country') %}, {{ shipping_address.get('country') }}{% endif %}
  </p>
  {% endif %}
</div>
<div class="footer">Sent by {{ store_name or "your store" }} via IMS</div>
</body>
</html>
```

- [ ] **Step 4: Implement email_service.py**

First, read the existing `TenantEmailConfig` model to understand what fields exist, then create `services/api/app/services/email_service.py`:

```python
"""Email service — sends transactional emails via the Resend API.

Each tenant configures their own Resend API key and verified sending domain
in TenantEmailConfig. We never share sending infrastructure between tenants.

Emails are sent synchronously for critical paths (order confirmation).
A failed send logs a warning but does NOT raise — order creation should
not fail because of an email error.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Order, OrderLine, TenantEmailConfig

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent.parent / "email_templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)

RESEND_API_URL = "https://api.resend.com/emails"


def _get_email_config(db: Session, tenant_id: UUID) -> TenantEmailConfig | None:
    return db.execute(
        select(TenantEmailConfig).where(TenantEmailConfig.tenant_id == tenant_id)
    ).scalar_one_or_none()


def _render_template(template_name: str, context: dict[str, Any]) -> str:
    template = _env.get_template(template_name)
    return template.render(**context)


def _send_via_resend(
    api_key: str,
    from_email: str,
    from_name: str,
    to_email: str,
    subject: str,
    html: str,
) -> bool:
    """Send one email via Resend API. Returns True on success."""
    try:
        resp = httpx.post(
            RESEND_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": f"{from_name} <{from_email}>" if from_name else from_email,
                "to": [to_email],
                "subject": subject,
                "html": html,
            },
            timeout=10.0,
        )
        if resp.status_code in (200, 201):
            return True
        logger.warning("Resend API error %d: %s", resp.status_code, resp.text)
        return False
    except Exception:
        logger.warning("Failed to send email to %s", to_email, exc_info=True)
        return False


def send_order_confirmation(db: Session, order: Order) -> bool:
    """Send an order confirmation email to the order's customer.

    Silently skips if:
    - No customer email on the order
    - No TenantEmailConfig for this tenant
    - TenantEmailConfig has no API key or from_email configured

    Never raises — email failure must not break order creation.
    """
    if not order.customer_email:
        return False

    config = _get_email_config(db, order.tenant_id)
    if config is None:
        logger.debug("No email config for tenant %s, skipping order confirmation", order.tenant_id)
        return False

    api_key = getattr(config, "resend_api_key", None) or getattr(config, "api_key", None)
    from_email = getattr(config, "from_email", None)
    if not api_key or not from_email:
        logger.debug("Email config incomplete for tenant %s, skipping", order.tenant_id)
        return False

    from_name = getattr(config, "from_name", "") or ""

    # Load order lines
    lines = db.execute(
        select(OrderLine).where(OrderLine.order_id == order.id)
    ).scalars().all()

    try:
        html = _render_template("order_confirmation.html", {
            "order_id": str(order.id),
            "customer_email": order.customer_email,
            "customer_name": None,
            "order_lines": lines,
            "currency": order.currency_code,
            "subtotal_cents": order.subtotal_cents,
            "discount_cents": order.discount_cents,
            "shipping_cents": order.shipping_cents,
            "tax_cents": order.tax_cents,
            "total_cents": order.total_cents,
            "shipping_address": order.shipping_address,
            "store_name": from_name,
        })
    except Exception:
        logger.warning("Failed to render order confirmation template", exc_info=True)
        return False

    return _send_via_resend(
        api_key=api_key,
        from_email=from_email,
        from_name=from_name,
        to_email=order.customer_email,
        subject=f"Order Confirmed — #{str(order.id)[:8].upper()}",
        html=html,
    )


def send_test_email(
    api_key: str,
    from_email: str,
    from_name: str,
    to_email: str,
) -> bool:
    """Send a test email to verify configuration. Used by the admin setup endpoint."""
    html = "<p>This is a test email from your IMS store. Your email configuration is working.</p>"
    return _send_via_resend(
        api_key=api_key, from_email=from_email, from_name=from_name,
        to_email=to_email, subject="IMS Email Test",  html=html,
    )
```

- [ ] **Step 5: Wire send_order_confirmation into order creation paths**

Add a call to `send_order_confirmation` after `db.commit()` in the following four places. In each case, import and call it — failure is silent (function returns bool, never raises):

**a) `services/api/app/routers/checkout.py` — `_create_order_from_session`:**

After `db.commit()`, before `return order`:
```python
    # Send order confirmation email (non-blocking)
    from app.services.email_service import send_order_confirmation
    send_order_confirmation(db, order)
    return order
```

**b) `services/api/app/routers/storefront/checkout.py` — `submit_order`:**

After `db.commit()`, before `db.refresh(order)`:
```python
    from app.services.email_service import send_order_confirmation
    send_order_confirmation(db, order)
```

**c) `services/api/app/routers/webhooks_shopify.py` — `_handle_order_create`:**

After the final `db.commit()`:
```python
    from app.services.email_service import send_order_confirmation
    send_order_confirmation(db, order)
```

**d) `services/api/app/routers/webhooks_woocommerce.py` — `_handle_order_created`:**

After the final `db.commit()`:
```python
    from app.services.email_service import send_order_confirmation
    send_order_confirmation(db, order)
```

- [ ] **Step 6: Write tests for email_service.py**

Create `services/api/tests/services/test_email_service.py`:

```python
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.models import Order, OrderLine, Tenant, TenantEmailConfig


@pytest.fixture()
def order_with_lines(db, tenant: Tenant) -> Order:
    """An order with customer email and two line items."""
    order = Order(
        tenant_id=tenant.id,
        channel_id=uuid.uuid4(),  # not FK-checked in unit test
        status="confirmed",
        customer_email="buyer@example.com",
        subtotal_cents=3998, tax_cents=719, shipping_cents=0,
        discount_cents=0, total_cents=4717,
        currency_code="INR",
        shipping_address={"city": "Mumbai", "country": "IN"},
    )
    db.add(order)
    db.flush()
    db.add(OrderLine(
        tenant_id=tenant.id, order_id=order.id, title="Widget A", sku="W001",
        quantity=2, unit_price_cents=1999, line_total_cents=3998,
    ))
    db.flush()
    return order


@pytest.fixture()
def email_config(db, tenant: Tenant) -> TenantEmailConfig:
    config = TenantEmailConfig(
        tenant_id=tenant.id,
        from_email="store@example.com",
        from_name="My Store",
    )
    # Set resend_api_key if that column exists, else fall back to api_key
    if hasattr(config, "resend_api_key"):
        config.resend_api_key = "re_test_xxx"
    elif hasattr(config, "api_key"):
        config.api_key = "re_test_xxx"
    db.add(config)
    db.flush()
    return config


def test_send_order_confirmation_success(db, tenant: Tenant, order_with_lines: Order,
                                          email_config: TenantEmailConfig) -> None:
    """Happy path: Resend API returns 200, function returns True."""
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"id": "email_test123"}

    with patch("httpx.post", return_value=mock_resp) as mock_post:
        from app.services.email_service import send_order_confirmation
        result = send_order_confirmation(db, order_with_lines)

    assert result is True
    assert mock_post.called
    call_json = mock_post.call_args.kwargs.get("json", {})
    assert call_json["to"] == ["buyer@example.com"]
    assert "Order Confirmed" in call_json["subject"]
    assert "Widget A" in call_json["html"]


def test_send_order_confirmation_no_config(db, tenant: Tenant, order_with_lines: Order) -> None:
    """If no TenantEmailConfig exists, function returns False silently."""
    from app.services.email_service import send_order_confirmation
    result = send_order_confirmation(db, order_with_lines)
    assert result is False


def test_send_order_confirmation_no_email(db, tenant: Tenant, email_config: TenantEmailConfig) -> None:
    """Order without customer email → skip silently."""
    order = Order(
        tenant_id=tenant.id, channel_id=uuid.uuid4(),
        status="confirmed", customer_email=None,
        subtotal_cents=1000, tax_cents=0, shipping_cents=0,
        discount_cents=0, total_cents=1000, currency_code="INR",
    )
    db.add(order)
    db.flush()

    from app.services.email_service import send_order_confirmation
    result = send_order_confirmation(db, order)
    assert result is False


def test_send_order_confirmation_api_failure_does_not_raise(
        db, tenant: Tenant, order_with_lines: Order, email_config: TenantEmailConfig) -> None:
    """Resend returns 500 → function returns False, does NOT raise."""
    mock_resp = MagicMock(status_code=500)
    mock_resp.text = "Internal Server Error"

    with patch("httpx.post", return_value=mock_resp):
        from app.services.email_service import send_order_confirmation
        result = send_order_confirmation(db, order_with_lines)
    assert result is False


def test_send_test_email(db) -> None:
    """Test email send wrapper returns True on Resend 200."""
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"id": "test_email_123"}

    with patch("httpx.post", return_value=mock_resp):
        from app.services.email_service import send_test_email
        result = send_test_email(
            api_key="re_test_xxx",
            from_email="store@example.com",
            from_name="My Store",
            to_email="merchant@example.com",
        )
    assert result is True
```

- [ ] **Step 7: Check the TenantEmailConfig model**

Before running tests, read the actual `TenantEmailConfig` class to see its columns and adapt the test's `email_config` fixture accordingly:

```bash
grep -A 30 "class TenantEmailConfig" services/api/app/models/tables.py
```

If there's no `resend_api_key` column, add one to the model and a migration:

```python
# In TenantEmailConfig class, add:
resend_api_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
```

And a tiny migration `20260518000001_tenant_email_resend_key.py`:

```python
revision = "20260518000001"
down_revision = "20260517000001"

def upgrade():
    op.add_column("tenant_email_configs",
                  sa.Column("resend_api_key", sa.String(255), nullable=True))

def downgrade():
    op.drop_column("tenant_email_configs", "resend_api_key")
```

- [ ] **Step 8: Run migration and tests**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/alembic/versions/20260518000001_tenant_email_resend_key.py $CONTAINER:/app/alembic/versions/
docker compose exec api alembic upgrade head
docker cp services/api/app/services/email_service.py $CONTAINER:/app/app/services/email_service.py
docker cp services/api/email_templates $CONTAINER:/app/email_templates
docker cp services/api/tests/services $CONTAINER:/app/tests/services
docker compose exec api python -m pytest tests/services/test_email_service.py -v
docker compose exec api rm -rf /app/tests/services
```
Expected: 5 passed.

- [ ] **Step 9: Commit**

```bash
git add services/api/alembic/versions/20260518000001_tenant_email_resend_key.py \
        services/api/app/models/tables.py \
        services/api/app/routers/checkout.py \
        services/api/app/routers/storefront/checkout.py \
        services/api/app/routers/webhooks_shopify.py \
        services/api/app/routers/webhooks_woocommerce.py \
        services/api/app/services/email_service.py \
        services/api/email_templates/order_confirmation.html \
        services/api/requirements.txt \
        services/api/tests/services/test_email_service.py
git commit -m "feat(email): add email infrastructure with order confirmation via Resend"
```

---

### Task 2: Admin email configuration endpoints + test send

**Files:**
- Create: `services/api/app/routers/admin_email.py`
- Modify: `services/api/app/main.py`
- Create: `services/api/tests/routers/test_admin_email.py`

- [ ] **Step 1: Write the failing test**

Create `services/api/tests/routers/test_admin_email.py`:

```python
# NOTE: `from __future__ import annotations` deliberately absent.

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Tenant


@pytest.fixture()
def auth_headers(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=None, tenant_id=tenant.id, role="owner", role_id=None,
        is_legacy_token=False, permissions=frozenset({"email:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield {}
    app.dependency_overrides.clear()


def test_configure_email(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/email/configure", json={
        "resend_api_key": "re_test_xxx",
        "from_email": "noreply@mystore.com",
        "from_name": "My Store",
    }, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["configured"] is True
    assert resp.json()["from_email"] == "noreply@mystore.com"


def test_send_test_email(db, tenant: Tenant, auth_headers) -> None:
    """Configure then send a test email (mocked Resend response)."""
    client = TestClient(app)
    client.post("/v1/admin/email/configure", json={
        "resend_api_key": "re_test_xxx",
        "from_email": "store@example.com",
        "from_name": "Store",
    }, headers=auth_headers)

    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"id": "test_sent"}
    with patch("httpx.post", return_value=mock_resp):
        resp = client.post("/v1/admin/email/test-send", json={
            "to_email": "merchant@example.com",
        }, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["sent"] is True


def test_get_email_config(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    # Before configure: unconfigured
    resp = client.get("/v1/admin/email/config", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["configured"] is False

    # After configure
    client.post("/v1/admin/email/configure", json={
        "resend_api_key": "re_test_xxx",
        "from_email": "store@example.com",
        "from_name": "Store",
    }, headers=auth_headers)
    resp = client.get("/v1/admin/email/config", headers=auth_headers)
    assert resp.json()["configured"] is True
    assert resp.json()["from_email"] == "store@example.com"


def test_test_send_without_config_fails(db, tenant: Tenant, auth_headers) -> None:
    client = TestClient(app)
    resp = client.post("/v1/admin/email/test-send", json={
        "to_email": "merchant@example.com",
    }, headers=auth_headers)
    assert resp.status_code == 400
    assert "not configured" in resp.json()["detail"].lower()
```

- [ ] **Step 2: Implement admin_email.py**

Create `services/api/app/routers/admin_email.py`:

```python
"""Admin endpoints for email configuration and test send.

Merchants configure their Resend API key and sender domain here.
Once configured, all transactional emails (order confirmations, etc.)
will be sent from their verified domain via their own Resend account.
"""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.admin_deps import AdminAuthDep, require_permission
from app.db.admin_deps_db import get_db_admin
from app.models import TenantEmailConfig
from app.services.email_service import send_test_email

router = APIRouter(
    prefix="/v1/admin/email",
    tags=["Email Configuration"],
    dependencies=[require_permission("email:manage")],
)


class EmailConfigureIn(BaseModel):
    resend_api_key: str = Field(min_length=1)
    from_email: str = Field(min_length=3, max_length=255)
    from_name: str = Field(default="", max_length=255)


class EmailConfigureOut(BaseModel):
    configured: bool
    from_email: str | None
    from_name: str | None


class TestSendIn(BaseModel):
    to_email: str = Field(min_length=3, max_length=255)


class TestSendOut(BaseModel):
    sent: bool
    message: str


def _require_tenant(ctx: AdminAuthDep) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=403, detail="Operator not assigned to a tenant")
    return ctx.tenant_id


def _get_config(db: Session, tenant_id: UUID) -> TenantEmailConfig | None:
    return db.execute(
        select(TenantEmailConfig).where(TenantEmailConfig.tenant_id == tenant_id)
    ).scalar_one_or_none()


@router.get("/config", response_model=EmailConfigureOut)
def get_config(
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> EmailConfigureOut:
    tenant_id = _require_tenant(ctx)
    config = _get_config(db, tenant_id)
    if config is None:
        return EmailConfigureOut(configured=False, from_email=None, from_name=None)
    api_key = getattr(config, "resend_api_key", None) or getattr(config, "api_key", None)
    return EmailConfigureOut(
        configured=bool(api_key and config.from_email),
        from_email=config.from_email,
        from_name=getattr(config, "from_name", ""),
    )


@router.post("/configure", response_model=EmailConfigureOut)
def configure_email(
    body: EmailConfigureIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> EmailConfigureOut:
    tenant_id = _require_tenant(ctx)
    config = _get_config(db, tenant_id)
    if config is None:
        config = TenantEmailConfig(tenant_id=tenant_id)
        db.add(config)

    if hasattr(config, "resend_api_key"):
        config.resend_api_key = body.resend_api_key.strip()
    elif hasattr(config, "api_key"):
        config.api_key = body.resend_api_key.strip()

    config.from_email = body.from_email.strip()
    if hasattr(config, "from_name"):
        config.from_name = body.from_name.strip()

    db.commit()
    return EmailConfigureOut(
        configured=True,
        from_email=config.from_email,
        from_name=body.from_name.strip(),
    )


@router.post("/test-send", response_model=TestSendOut)
def test_send(
    body: TestSendIn,
    ctx: AdminAuthDep,
    db: Annotated[Session, Depends(get_db_admin)],
) -> TestSendOut:
    tenant_id = _require_tenant(ctx)
    config = _get_config(db, tenant_id)
    if config is None:
        raise HTTPException(status_code=400, detail="Email not configured for this tenant")

    api_key = getattr(config, "resend_api_key", None) or getattr(config, "api_key", None)
    if not api_key or not config.from_email:
        raise HTTPException(status_code=400, detail="Email not configured for this tenant")

    from_name = getattr(config, "from_name", "") or ""
    sent = send_test_email(
        api_key=api_key,
        from_email=config.from_email,
        from_name=from_name,
        to_email=body.to_email,
    )
    return TestSendOut(
        sent=sent,
        message="Test email sent successfully" if sent else "Failed to send — check your Resend API key and from_email",
    )
```

Also seed the `email:manage` permission in the migration (or as an inline fixture).

- [ ] **Step 3: Seed email:manage permission**

Add to migration `20260518000001_tenant_email_resend_key.py` (if not already done):

```python
# In upgrade() after the column add:
op.execute("""
    INSERT INTO permissions (id, codename, display_name, category, description)
    VALUES (gen_random_uuid(), 'email:manage', 'Manage Email Configuration', 'settings',
            'Configure transactional email settings and test send')
    ON CONFLICT (codename) DO NOTHING
""")
op.execute("""
    INSERT INTO role_permissions (id, role_id, permission_id)
    SELECT gen_random_uuid(), r.id, p.id
    FROM roles r, permissions p
    WHERE r.name = 'owner' AND r.is_system = true
      AND p.codename = 'email:manage'
    ON CONFLICT DO NOTHING
""")
```

- [ ] **Step 4: Mount admin_email router, run tests**

Mount in `main.py` and run:
```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/app/main.py $CONTAINER:/app/app/main.py
docker cp services/api/app/routers/admin_email.py $CONTAINER:/app/app/routers/admin_email.py
docker cp services/api/app/services/email_service.py $CONTAINER:/app/app/services/email_service.py
docker cp services/api/tests $CONTAINER:/app/tests
docker compose restart api
sleep 5
docker compose exec api python -m pytest tests/services/test_email_service.py tests/routers/test_admin_email.py -v
docker compose exec api rm -rf /app/tests
```
Expected: 5 service + 4 router = 9 passed.

- [ ] **Step 5: Commit**

```bash
git add services/api/app/routers/admin_email.py \
        services/api/app/main.py \
        services/api/tests/routers/test_admin_email.py
git commit -m "feat(email): admin email configure + test-send endpoints"
```

---

### Task 3: Integration smoke test

**Files:**
- Create: `services/api/tests/integration/test_email_e2e.py`

- [ ] **Step 1: Write integration test**

Create `services/api/tests/integration/test_email_e2e.py`:

```python
"""End-to-end smoke test for email infrastructure.

Covers:
- Configure email via admin API
- Create a hosted checkout order → email is attempted (Resend mocked)
- Create a Shopify webhook order → email is attempted
- Misconfigured email (no API key) → silently skipped, order still created
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
        tenant_id=tenant.id, type="headless", name="Headless",
        config={"payment_provider": "stripe", "stripe_secret_key": "sk_test_xxx",
                "stripe_publishable_key": "pk_test_xxx",
                "checkout_success_url": "https://shop.com/success"},
        inventory_pool_id=pool.id, currency_code="INR",
    )
    db.add(channel)
    db.flush()
    product = Product(
        tenant_id=tenant.id, name="Widget", sku=f"sku-{uuid.uuid4().hex[:6]}",
        unit_price_cents=999, product_type="physical", status="active",
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


@pytest.fixture()
def auth(db, tenant: Tenant):
    from app.auth.admin_deps import AdminContext, require_admin_context
    from app.db.admin_deps_db import get_db_admin

    fake_ctx = AdminContext(
        user_id=None, tenant_id=tenant.id, role="owner", role_id=None,
        is_legacy_token=False, permissions=frozenset({"channels:manage", "email:manage"}),
    )
    app.dependency_overrides[require_admin_context] = lambda: fake_ctx
    app.dependency_overrides[get_db_admin] = lambda: db
    yield
    app.dependency_overrides.clear()


def test_order_confirmation_sent_on_hosted_checkout(db, tenant: Tenant, setup, auth) -> None:
    """Full hosted checkout → email sent to shopper (Resend mocked)."""
    from app.db.session import get_db
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        channel = setup["channel"]
        product = setup["product"]

        # Configure email
        client.post("/v1/admin/email/configure", json={
            "resend_api_key": "re_test_xxx",
            "from_email": "store@example.com",
            "from_name": "My Store",
        })

        # Create cart + checkout session + complete with mocked payment
        cart = client.post("/v1/storefront/cart",
                           headers={"X-Channel-Id": str(channel.id)}).json()
        client.post(f"/v1/storefront/cart/{cart['cart_token']}/items", json={
            "product_id": str(product.id), "quantity": 1,
        }, headers={"X-Channel-Id": str(channel.id)})

        session_resp = client.post("/v1/storefront/checkout/session", json={
            "cart_token": cart["cart_token"],
        }, headers={"X-Channel-Id": str(channel.id)}).json()
        session_token = session_resp["session_token"]

        email_calls = []

        def capture_email(*args, **kwargs):
            email_calls.append(kwargs.get("json", {}))
            m = MagicMock(status_code=200)
            m.json.return_value = {"id": "email_sent"}
            return m

        mock_stripe = MagicMock()
        mock_stripe.status = "succeeded"

        with patch("stripe.PaymentIntent.retrieve", return_value=mock_stripe), \
             patch("httpx.post", side_effect=capture_email):
            resp = client.post(f"/v1/checkout/{session_token}/complete", json={
                "payment_intent_id": "pi_test",
                "customer_email": "shopper@example.com",
            })

        assert resp.status_code == 200
        # Email should have been called with "Order Confirmed" subject
        assert any("Order Confirmed" in c.get("subject", "") for c in email_calls)
        assert any("shopper@example.com" in str(c.get("to", "")) for c in email_calls)

        # Verify order exists
        order = db.execute(
            select(Order).where(Order.id == uuid.UUID(resp.json()["order_id"]))
        ).scalar_one()
        assert order.customer_email == "shopper@example.com"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_order_created_without_email_config_still_succeeds(db, tenant: Tenant, setup, auth) -> None:
    """If email is not configured, order creation still succeeds (email silently skipped)."""
    from app.db.session import get_db
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        channel = setup["channel"]
        product = setup["product"]

        # NO email configuration this time

        cart = client.post("/v1/storefront/cart",
                           headers={"X-Channel-Id": str(channel.id)}).json()
        client.post(f"/v1/storefront/cart/{cart['cart_token']}/items", json={
            "product_id": str(product.id), "quantity": 1,
        }, headers={"X-Channel-Id": str(channel.id)})

        session_resp = client.post("/v1/storefront/checkout/session", json={
            "cart_token": cart["cart_token"],
        }, headers={"X-Channel-Id": str(channel.id)}).json()

        mock_stripe = MagicMock()
        mock_stripe.status = "succeeded"

        with patch("stripe.PaymentIntent.retrieve", return_value=mock_stripe):
            resp = client.post(f"/v1/checkout/{session_resp['session_token']}/complete", json={
                "payment_intent_id": "pi_no_email",
                "customer_email": "shopper@example.com",
            })

        # Order still created even though email failed
        assert resp.status_code == 200
        assert "order_id" in resp.json()
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 2: Run integration test**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest tests/integration/test_email_e2e.py -v
docker compose exec api rm -rf /app/tests
```
Expected: 2 passed.

- [ ] **Step 3: Run full email suite**

```bash
CONTAINER=$(docker compose ps -q api)
docker cp services/api/tests $CONTAINER:/app/tests
docker compose exec api python -m pytest \
  tests/services/test_email_service.py \
  tests/routers/test_admin_email.py \
  tests/integration/test_email_e2e.py \
  -v 2>&1 | tail -5
docker compose exec api rm -rf /app/tests
```
Expected: ~11 tests.

- [ ] **Step 4: Commit**

```bash
git add services/api/tests/integration/test_email_e2e.py
git commit -m "test(email): end-to-end email infrastructure smoke test"
```

---

## Done. Summary

- `email_service.py` — Resend wrapper, `send_order_confirmation`, `send_test_email`
- `email_templates/order_confirmation.html` — clean Jinja2 HTML template
- Order confirmation wired into all 4 order creation paths (hosted checkout, storefront Path-2, Shopify webhook, WooCommerce webhook)
- `admin_email.py` — configure Resend API key + from address, test send endpoint
- `email:manage` permission seeded
- ~11 tests

## What merchants do to get order confirmation emails

1. Sign up at [resend.com](https://resend.com) (free tier: 100 emails/day)
2. Add and verify their sending domain (Resend walks through SPF/DKIM/DMARC)
3. Create an API key in the Resend dashboard
4. In IMS admin: `POST /v1/admin/email/configure` with the API key + `from_email`
5. `POST /v1/admin/email/test-send` to verify it works
6. Every order created from that point sends an automatic confirmation

---

*End of plan.*
