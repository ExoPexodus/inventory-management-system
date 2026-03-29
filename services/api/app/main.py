from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import (
    admin,
    admin_analytics,
    admin_catalog,
    admin_inventory,
    admin_orders,
    admin_platform,
    admin_staff,
    admin_suppliers,
    admin_web,
    audit,
    devices,
    health,
    inventory,
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
app.include_router(devices.router)
app.include_router(sync.router)
app.include_router(transactions.router)
app.include_router(admin.router)
app.include_router(admin_web.router)
app.include_router(admin_catalog.router)
app.include_router(admin_inventory.router)
app.include_router(admin_orders.router)
app.include_router(admin_suppliers.router)
app.include_router(admin_staff.router)
app.include_router(admin_analytics.router)
app.include_router(admin_platform.router)
app.include_router(tenants.router)
app.include_router(shops.router)
app.include_router(inventory.router)
app.include_router(reporting.router)
app.include_router(audit.router)
app.include_router(notifications.router)
