from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.storefront import catalog as storefront_catalog
from app.routers.storefront import cart as storefront_cart
from app.routers.storefront import checkout as storefront_checkout
from app.routers import checkout
from app.routers import webhooks_shopify
from app.routers import webhooks_woocommerce
from app.routers import (
    app_updates,
    admin,
    admin_analytics,
    admin_audit,
    admin_billing,
    admin_business_type,
    admin_catalog,
    admin_channels,
    admin_customers,
    admin_discounts,
    admin_email,
    admin_entitlements,
    admin_webhooks,
    admin_fx_rates,
    admin_inventory,
    admin_inventory_pools,
    admin_integrations,
    admin_notifications,
    admin_orders,
    admin_payment,
    admin_platform,
    admin_product_prices,
    admin_reconciliation,
    admin_reports,
    admin_reservations,
    admin_shipping,
    admin_shopify,
    admin_roles,
    admin_shifts,
    admin_shops,
    admin_staff,
    admin_suppliers,
    admin_tax,
    admin_web,
    admin_woocommerce,
    audit,
    auth,
    device_shifts,
    devices,
    health,
    internal_sync,
    inventory,
    platform_provision,
    notifications,
    reporting,
    shops,
    sync,
    tenants,
    transactions,
)

# Application composition root. Domain areas: health, devices (onboarding), sync, admin (operator API).
app = FastAPI(
    title="Inventory Platform API",
    version="0.1.0",
    description="Ledger-based inventory + device sync. Card tenders require online submission by default.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(sync.router)
app.include_router(transactions.router)
app.include_router(device_shifts.router)
app.include_router(admin.router)
app.include_router(admin_web.router)
app.include_router(admin_woocommerce.router)
app.include_router(admin_catalog.router)
app.include_router(admin_channels.router)
app.include_router(admin_inventory_pools.router)
app.include_router(admin_customers.router)
app.include_router(admin_discounts.router)
app.include_router(admin_entitlements.router)
app.include_router(admin_inventory.router)
app.include_router(admin_orders.router)
app.include_router(admin_email.router)
app.include_router(admin_webhooks.router)
app.include_router(admin_payment.router)
app.include_router(admin_suppliers.router)
app.include_router(admin_tax.router)
app.include_router(admin_roles.router)
app.include_router(admin_staff.router)
app.include_router(admin_analytics.router)
app.include_router(admin_integrations.router)
app.include_router(admin_notifications.router)
app.include_router(admin_reconciliation.router)
app.include_router(admin_shifts.router)
app.include_router(admin_platform.router)
app.include_router(admin_billing.router)
app.include_router(admin_business_type.router)
app.include_router(tenants.router)
app.include_router(shops.router)
app.include_router(admin_shops.router)
app.include_router(inventory.router)
app.include_router(reporting.router)
app.include_router(admin_audit.router)
app.include_router(admin_reports.router)
app.include_router(admin_reservations.router)
app.include_router(admin_shipping.router)
app.include_router(admin_shopify.router)
app.include_router(audit.router)
app.include_router(notifications.router)
app.include_router(internal_sync.router)
app.include_router(platform_provision.router)
app.include_router(admin_fx_rates.router)
app.include_router(admin_product_prices.router)
app.include_router(app_updates.router)
app.include_router(storefront_catalog.router)
app.include_router(storefront_cart.router)
app.include_router(storefront_checkout.router)
app.include_router(checkout.router)
app.include_router(webhooks_shopify.router)
app.include_router(webhooks_woocommerce.router)
