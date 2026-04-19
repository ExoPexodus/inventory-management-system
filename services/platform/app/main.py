from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, downloads, health, internal_sync, invoices, license, payments, plans, releases, subscriptions, tenant_api, tenants

app = FastAPI(
    title="IMS Platform Service",
    version="0.1.0",
    description="SaaS control plane: tenant management, licensing, billing, and app distribution.",
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
app.include_router(tenants.router)
app.include_router(plans.router)
app.include_router(subscriptions.router)
app.include_router(payments.router)
app.include_router(invoices.router)
app.include_router(releases.router)
app.include_router(downloads.router)
app.include_router(license.router)
app.include_router(tenant_api.router)
app.include_router(internal_sync.router)
