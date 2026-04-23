# Feature Gap Analysis — Industry-Standard IMS
**Date:** 2026-04-23  
**Author:** Rushil Rana  
**Status:** Approved  

## Context

This document maps all missing industry-standard features against what is already built in the IMS monorepo. It covers the API (`services/api`), admin web (`apps/admin-web`), and cashier POS (`apps/cashier`).

**Target market:** General retail (primary) + wholesale/distribution (primary), with mixed/horizontal coverage as a secondary goal.  
**Target customer size:** Small (1–3 locations) to medium (3–20 locations). The product must scale from simple to complex without overwhelming small users.

---

## Shippable Chunk Legend

| Chunk | Label | Description |
|---|---|---|
| **1** | Ship-blocking | Must exist before first paying customer. Losing deals without it. |
| **2** | Competitive parity | Expected within first few months. Disadvantage without it. |
| **3** | Differentiating | Edge over competitors. Build once the core is solid. |

---

## What Is Already Built

Before gaps: a summary of what exists so we don't re-build things.

| Area | Status |
|---|---|
| Multi-tenant SaaS, multi-location (shops) | ✅ Built |
| RBAC — roles, permissions, operators, staff | ✅ Built |
| SaaS billing (plans, invoices, usage, cancel/renew) | ✅ Built |
| Product catalog (SKU, name, category, description, image, reorder_point, variants, product groups) | ✅ Built |
| Immutable stock ledger (movements, adjustments pending→approved) | ✅ Built |
| Transfer orders (shop-to-shop, model + partial line tracking) | ✅ Model built, ❌ admin endpoints missing |
| Purchase orders + lines (CRUD, line-level quantity_received) | ✅ Built |
| Suppliers (CRUD endpoints in admin_web.py) | ✅ Basic built |
| Stock adjustment creation + movement listing | ✅ Built |
| Sales transactions, multi-tender (cash + card) | ✅ Built |
| Tax — per-product per-shop overrides, default shop rate | ✅ Built |
| Shift management + reconciliation (auto-resolve) | ✅ Built |
| Analytics (sales series, category revenue, top products, heatmap, payment methods, shop revenue) | ✅ Built |
| Report export (single endpoint) | ✅ Thin |
| Staff/employee management (invite, enroll, reset credentials) | ✅ Built |
| Shops management (CRUD, auto-resolve threshold overrides) | ✅ Built |
| Device enrollment + refresh | ✅ Built |
| Webhooks + API tokens | ✅ Built |
| CSV product import | ✅ Built |
| In-app notifications | ✅ Built |
| Admin audit logs | ✅ Built |
| Offline-first cashier POS (Flutter) | ✅ Built |
| Platform-managed multi-tenant currency | ✅ Built |

---

## Feature Gaps by Domain

---

### Domain 1 — Customer Management (CRM)

**What exists:** Nothing. No `Customer` model anywhere in the codebase.

**What's missing:**
- Customer profiles (name, phone, email, address, notes)
- Customer purchase history
- Customer balance / store credit (see also Domain 7 — store credit wallet is a shared concept between CRM and loyalty)
- Customer groups / segments (for pricing tiers, B2B accounts)
- Customer-specific pricing (price list A for customer X)
- Multiple delivery addresses per customer (wholesale)
- Customer credit limits and outstanding balance

**Chunk:** 1 (profiles, purchase history, groups), 2 (customer-specific pricing, credit limits), 3 (multiple delivery addresses)

---

### Domain 2 — Returns & Refunds

**What exists:** Nothing. `Transaction.kind = "sale"` only. No return kind, no credit note, no restock logic. Flagged in ADR as "next candidate."

**What's missing:**
- Return transactions linked to original sale
- Partial returns (some items from an order)
- Refund tender choice (back to cash, back to store credit, exchange)
- Auto-restock on return (creates a stock movement)
- Return reason codes (wrong item, damaged, changed mind)
- Admin return approval workflow (optional, for controlled returns)

**Chunk:** 1

---

### Domain 3 — Product Catalog (gaps)

**What exists:** SKU, name, category (free text), description, image_url, reorder_point, unit_price_cents, variants, product groups.

**What's missing:**
- `barcode` / UPC / EAN field — critical for POS scanning
- `cost_price_cents` — without it, margin and COGS are impossible
- `unit_of_measure` — sell by kg, litre, metre, pack (critical for wholesale)
- Category hierarchy (currently free-text string, not structured)
- Min/max stock levels (only reorder_point exists; max stock needed for over-stock alerts)
- Product tags / labels (flexible classification beyond single category)
- Price history — track when prices changed and by how much
- Discontinued status handling — products no longer ordered but still in inventory

**Chunk:** 1 (barcode, cost_price_cents), 2 (UOM, min/max stock, tags), 3 (category hierarchy, price history)

---

### Domain 4 — Supplier & Purchasing (gaps)

**What exists:** Supplier CRUD (name, status, contact_email, contact_phone, notes). Purchase order CRUD with line-level `quantity_received` and `unit_cost_cents`.

**What's missing:**
- Supplier address, payment terms, lead time fields on Supplier model
- Vendor price lists (standing cost per supplier per product — separate from PO line cost)
- PO receiving workflow — endpoint that marks received lines and triggers stock movements
- Partial receiving (receive some lines, leave rest open/backordered)
- PO status flow: draft → submitted → partially received → fully received → closed
- Auto-draft PO when stock hits reorder_point

**Chunk:** 1 (PO receiving workflow, supplier fields), 2 (vendor price lists, partial receiving, PO status flow), 3 (auto-draft PO)

---

### Domain 5 — Inventory Operations (gaps)

**What exists:** Stock adjustment creation, stock movement listing. Transfer order + lines model (but no admin endpoints).

**What's missing:**
- Transfer order admin endpoints (create, approve, ship, receive)
- Multi-location stock overview — stock at all shops in one dashboard view
- Cycle count / stocktake workflow (count all products in a shop, create adjustments from variances)
- Low-stock alerts (reorder_point field exists; nothing triggers a notification when crossed)
- Over-stock alerts (requires max stock level field)
- Shrinkage tracking as a distinct reason code category with reporting

**Chunk:** 1 (transfer order endpoints, multi-location stock view, low-stock alerts), 2 (cycle count, over-stock alerts, shrinkage reporting)

---

### Domain 6 — Discounts & Promotions

**What exists:** Nothing. No discount fields on `Transaction` or `TransactionLine`.

**What's missing:**
- Item-level discounts (percentage or fixed amount off a line)
- Cart-level discounts (percentage or fixed off total)
- Coupon / promo codes (single-use, multi-use, expiry date)
- Bulk / tiered pricing (buy 10+ units → get 10% off) — important for wholesale
- Time-limited promotions (date range)
- Manager override discounts (require a role with `discounts:approve` permission)

**Chunk:** 2 (item + cart discounts, coupon codes, manager override), 3 (tiered pricing, time-limited promos)

---

### Domain 7 — Loyalty & Rewards

**What exists:** Nothing.

**What's missing:**
- Points earning on purchase (configurable rate: e.g. 1 point per $1)
- Points redemption at checkout
- Store credit / customer wallet (balance, top-up, redemption)
- Loyalty tiers (bronze/silver/gold with threshold rules)
- Points expiry

**Chunk:** 3

---

### Domain 8 — Gift Cards & Vouchers

**What exists:** Nothing. No gift card tender type in `PaymentAllocation`.

**What's missing:**
- Issue gift cards (physical + digital)
- Redeem gift cards at POS as a tender type
- Gift card balance tracking
- Partial redemption + remaining balance carried forward
- Gift card expiry

**Chunk:** 3

---

### Domain 9 — Reporting (gaps)

**What exists:** One CSV export endpoint. Analytics: summary, sales series, category revenue, top products, hourly heatmap, payment methods, shop revenue.

**What's missing:**
- Profit & loss report (unlocked once `cost_price_cents` is added)
- COGS report (cost of goods sold per period)
- Inventory valuation report (stock on hand × cost price, per shop)
- Dead stock / slow-moving inventory report (products with no movement in N days)
- Purchase order history report (what we ordered, from whom, at what cost)
- Customer sales report (requires CRM)
- Shrinkage / loss report
- Scheduled reports (auto-email daily/weekly to manager)
- Comparison periods (this month vs. last month vs. same period last year)
- Stock forecasting (predict reorder needs based on sales velocity)

**Chunk:** 2 (P&L, COGS, inventory valuation, dead stock — all unlocked by cost_price), 3 (scheduled reports, comparison periods, forecasting)

---

### Domain 10 — Cash Management (gaps)

**What exists:** Shift closing with expected_cash_cents vs. reported_cash_cents and discrepancy tracking.

**What's missing:**
- Opening float recording (start-of-day cash amount per denomination)
- Cash denomination count at close (how many £50s, £20s, £10s, etc.)
- Petty cash / in-shift expense recording
- Cash drawer event log (open/close events per shift)

**Chunk:** 2 (denomination count, opening float), 3 (petty cash, drawer event log)

---

### Domain 11 — Notifications & Alerts (gaps)

**What exists:** In-app notifications model and endpoints. Tenant email config.

**What's missing:**
- Low-stock email alerts (trigger when stock drops below reorder_point)
- Over-stock alerts
- PO overdue alerts (expected delivery date passed, PO not received)
- Customer-facing email receipts (requires CRM)
- Shift summary email to manager
- Push notifications to admin mobile app
- Slack / Teams webhook alert integration

**Chunk:** 2 (low-stock + PO overdue alerts, shift summary email), 3 (customer receipts, push notifications, Slack integration)

---

### Domain 12 — Batch / Lot / Serial Tracking

**What exists:** Nothing. No batch or serial fields on products or stock movements.

**What's missing:**
- Lot/batch numbers on stock movements (for perishables with expiry dates)
- Serial number tracking (for high-value serialized goods)
- Expiry date tracking + expiry alerts
- FIFO/FEFO stock rotation enforcement

**Chunk:** 3

---

### Domain 13 — B2B Sales / Wholesale Orders

**What exists:** Nothing. Only POS cashier transactions (device-driven, offline-first).

**What's missing:**
- Sales order model — for wholesale customers ordering by phone, email, or portal
- Sales order lifecycle: draft → confirmed → picking → shipped → invoiced
- Back-order management (take order when stock = 0, fulfill when PO arrives)
- Minimum order quantities per product
- Order templates / standing orders (recurring orders from the same customer)
- Packing list generation (pick and pack document for fulfillment)

**Chunk:** 2 (basic sales order model + lifecycle), 3 (back-order, order templates, packing lists)

---

### Domain 14 — Invoicing & Credit Notes

**What exists:** Nothing for customer-facing documents. Billing invoices are SaaS subscription invoices only.

**What's missing:**
- Customer-facing invoice generation (tied to sales orders or B2B transactions)
- Credit note model (tied to returns or billing adjustments)
- Invoice PDF generation and email delivery
- Invoice payment tracking (paid / partially paid / overdue)
- Invoice numbering sequence (per tenant)

**Chunk:** 2 (credit notes — unlocked by returns), 3 (full invoice generation, PDF, payment tracking)

---

### Domain 15 — Accounts Receivable / Credit Terms

**What exists:** Nothing.

**What's missing:**
- Customer credit limits
- Net payment terms per customer (Net 30, Net 60, COD, prepaid)
- Outstanding balance tracking per customer
- Overdue invoice alerts

**Chunk:** 3 — builds on CRM + invoicing

---

### Domain 16 — Receipt & Document Customization

**What exists:** Nothing configurable. No receipt template settings.

**What's missing:**
- Receipt template configuration (logo, business name/address, footer message, custom fields)
- Digital receipt delivery to customer email after sale (requires CRM)
- QR code on receipt (for returns, warranty, or loyalty)
- Printable invoice layout for B2B

**Chunk:** 2 (receipt template config), 3 (digital receipts, QR codes)

---

### Domain 17 — POS Advanced Features

**What exists:** Multi-tender payment, offline-first sync, product variants.

**What's missing:**
- Hold / park transactions (pause a sale, start another, return to parked sale)
- Custom / ad-hoc line items (sell an unlisted item with a custom price and description)
- Item notes / special instructions on a transaction line
- Void transaction (cancel a posted transaction from admin)
- Tip / gratuity support (amount or percentage, split across tender)
- Customer-facing display screen mode (second screen at POS terminal)
- QR code / barcode product lookup at POS (requires barcode field on product)

**Chunk:** 2 (hold transactions, custom line items, item notes, void, barcode lookup), 3 (tip/gratuity, customer display)

---

### Domain 18 — Tax Management (gaps)

**What exists:** Per-product per-shop tax overrides (`ShopProductTax`). Default tax rate per shop.

**What's missing:**
- Named tax rate bands/categories (e.g., Standard 20%, Reduced 5%, Zero-rated 0%) — not just per-product overrides
- Tax-inclusive vs. tax-exclusive pricing toggle per tenant
- Multiple tax components per line (compound taxes — e.g., state + local)
- Tax period report / export (total tax collected per period, by rate band)

**Chunk:** 2 (tax bands, inclusive/exclusive toggle, tax period report), 3 (compound taxes)

---

### Domain 19 — Integration Ecosystem (gaps)

**What exists:** Webhooks, API tokens, CSV product import.

**What's missing:**
- CSV imports for customers, suppliers, stock levels (not just products)
- Bulk export: transactions, customers, products, stock
- Accounting integrations: Xero / QuickBooks (daily sales summary, invoice sync)
- E-commerce integrations: Shopify / WooCommerce (bi-directional stock sync)
- Payment gateway integrations: Stripe Terminal / Square (card payments via API)

**Chunk:** 2 (more CSV imports, bulk export), 3 (accounting, e-commerce, payment gateway integrations)

---

### Domain 20 — Product Bundles & Kits

**What exists:** Product groups exist for variant merchandising only. No bundle/kit concept.

**What's missing:**
- Bundle / kit definition (group of products sold as one unit with one price)
- Bundle stock deduction (selling a bundle deducts each component from stock)
- Composite products / assemblies (a product made from other products — manufacturing)
- Bundle pricing rules (bundle discount vs. sum of parts)

**Chunk:** 2 (basic bundles/kits), 3 (composite/assembly with BOM)

---

### Domain 21 — Auto-reorder & Smart Purchasing

**What exists:** `reorder_point` field on products. No automation built on it.

**What's missing:**
- Auto-draft PO when product stock crosses reorder_point (for configured products + suppliers)
- Suggested order quantity (based on lead time + sales velocity)
- Reorder report — list of all products currently below reorder_point
- Preferred supplier per product

**Chunk:** 2 (reorder report, preferred supplier), 3 (auto-draft PO, suggested quantities)

---

### Domain 22 — Staff Scheduling & Time Tracking

**What exists:** Staff model with invite/enroll. Shift closings track which device closed.

**What's missing:**
- Employee clock in / clock out (time tracking per shift)
- Staff scheduling (assign employees to shifts at specific shops)
- Sales per employee analytics (who sold what, in which shift)
- Commission rates and commission report per employee

**Chunk:** 3

---

### Domain 23 — Security & Compliance

**What exists:** JWT auth, RBAC, audit logs, API tokens with scopes.

**What's missing:**
- Two-factor authentication (2FA / TOTP) for admin/operator logins
- Active session management (see all active sessions, revoke a session)
- Password policies (complexity, expiry, history)
- IP allowlisting for API token access
- GDPR / data privacy: right-to-erasure for customer data, data export
- Data retention policies (auto-purge old audit logs / transactions after N years)

**Chunk:** 2 (2FA, session management), 3 (IP allowlist, GDPR tooling, retention policies)

---

### Domain 24 — Platform & Onboarding

**What exists:** Platform-managed multi-tenant currency. Billing plans. Deployment mode.

**What's missing:**
- Onboarding wizard for new tenants (guided setup: shops → products → staff → devices)
- Usage limits enforcement (product count, user count, shop count by plan tier)
- White-labeling (custom logo, brand colors per tenant — for reseller use cases)
- Feature flags per plan tier (some features only on higher plans)
- In-app changelog / "what's new" panel

**Chunk:** 2 (usage limits enforcement, onboarding wizard), 3 (white-labeling, feature flags, changelog)

---

## Prioritized Chunk Summary

### Chunk 1 — Ship-blocking (build before first paying customer)

| # | Feature | Domain |
|---|---|---|
| 1.1 | Customer profiles, purchase history, groups | CRM |
| 1.2 | Returns & refunds (full workflow, restock on return) | Returns |
| 1.3 | Barcode / UPC / EAN field on products | Catalog |
| 1.4 | Cost price (`cost_price_cents`) on products | Catalog |
| 1.5 | PO receiving workflow (mark received → stock movement) | Purchasing |
| 1.6 | Supplier model improvements (address, payment terms, lead time) | Purchasing |
| 1.7 | Transfer order admin endpoints (create, approve, ship, receive) | Inventory Ops |
| 1.8 | Multi-location stock overview dashboard | Inventory Ops |
| 1.9 | Low-stock alerts (email + in-app when stock crosses reorder_point) | Alerts |

### Chunk 2 — Competitive parity (build within first few months)

| # | Feature | Domain |
|---|---|---|
| 2.1 | Item-level and cart-level discounts, coupon codes, manager override | Discounts |
| 2.2 | Cycle count / stocktake workflow | Inventory Ops |
| 2.3 | Basic B2B sales order model + lifecycle | B2B Orders |
| 2.4 | Credit notes (tied to returns) | Invoicing |
| 2.5 | Receipt template configuration | Documents |
| 2.6 | Hold / park transactions, custom line items, void transaction | POS |
| 2.7 | Barcode product lookup at POS | POS |
| 2.8 | Tax rate bands (named rates), inclusive/exclusive toggle, tax report | Tax |
| 2.9 | P&L report, COGS report, inventory valuation report | Reporting |
| 2.10 | Dead stock / slow-moving inventory report | Reporting |
| 2.11 | Units of measure on products | Catalog |
| 2.12 | Product tags and max stock level | Catalog |
| 2.13 | Vendor price lists (per supplier per product) | Purchasing |
| 2.14 | Partial PO receiving, PO status flow | Purchasing |
| 2.15 | PO overdue alerts, shift summary email | Alerts |
| 2.16 | CSV imports for customers, suppliers, stock | Integrations |
| 2.17 | Bulk export (transactions, products, customers, stock) | Integrations |
| 2.18 | Basic product bundles / kits | Bundles |
| 2.19 | Reorder report, preferred supplier per product | Auto-reorder |
| 2.20 | Opening float + denomination count at shift close | Cash Mgmt |
| 2.21 | 2FA for admin/operator logins | Security |
| 2.22 | Active session management | Security |
| 2.23 | Onboarding wizard for new tenants | Platform |
| 2.24 | Usage limits enforcement by plan | Platform |
| 2.25 | Customer-specific pricing (price list per customer group) | CRM |

### Chunk 3 — Differentiating (build when core is solid)

| # | Feature | Domain |
|---|---|---|
| 3.1 | Loyalty & rewards (points, tiers, store credit wallet) | Loyalty |
| 3.2 | Gift cards & vouchers | Gift Cards |
| 3.3 | Tiered / bulk pricing (quantity discounts) | Discounts |
| 3.4 | Time-limited promotions | Discounts |
| 3.5 | Batch / lot / serial tracking with expiry dates | Inventory |
| 3.6 | Full invoice generation + PDF + payment tracking | Invoicing |
| 3.7 | Accounts receivable + credit terms (Net 30/60) | AR |
| 3.8 | Digital receipt delivery to customer email | Documents |
| 3.9 | Tip / gratuity at POS | POS |
| 3.10 | Customer-facing display screen mode | POS |
| 3.11 | Scheduled reports (auto-email daily/weekly) | Reporting |
| 3.12 | Comparison period analytics | Reporting |
| 3.13 | Stock demand forecasting | Reporting |
| 3.14 | Back-order management | B2B Orders |
| 3.15 | Order templates / standing orders | B2B Orders |
| 3.16 | Packing list generation | B2B Orders |
| 3.17 | Accounting integrations (Xero, QuickBooks) | Integrations |
| 3.18 | E-commerce integrations (Shopify, WooCommerce) | Integrations |
| 3.19 | Composite products / assemblies (BOM) | Bundles |
| 3.20 | Auto-draft PO on reorder trigger | Auto-reorder |
| 3.21 | Staff commission tracking + report | Staff |
| 3.22 | Employee clock in/out + scheduling | Staff |
| 3.23 | White-labeling + feature flags per plan | Platform |
| 3.24 | GDPR tooling (erasure, export, retention policies) | Security |
| 3.25 | Category hierarchy (structured, not free text) | Catalog |
| 3.26 | Price history tracking | Catalog |
| 3.27 | Shrinkage tracking + loss report | Inventory |
| 3.28 | Compound taxes (multi-component per line) | Tax |
| 3.29 | Push notifications to admin mobile | Alerts |
| 3.30 | Slack / Teams alert integrations | Alerts |

---

## Implementation Notes

- **Cost price is a keystone** — Domains 9 (reporting), 21 (auto-reorder), and parts of domain 6 (margin-based discounts) all unlock once `cost_price_cents` is on the Product model. This should be the first schema change in Chunk 1.
- **CRM is a keystone** — Domains 7 (loyalty), 11 (customer receipts), 14 (invoicing), and 15 (AR) all depend on a Customer model existing. Build CRM early in Chunk 1.
- **Returns depend on CRM** — A return should optionally be tied to a customer. Build returns after CRM.
- **B2B orders depend on both CRM and returns** — Don't start Chunk 2 B2B work without Chunk 1 CRM + returns in place.
- **Tax bands should be tackled before discount engine** — Tax-inclusive pricing interacts with how discounts are applied. Resolve tax model first.
- **Barcode field enables POS scanning** — Add to product schema in Chunk 1; the cashier scanning feature follows naturally once the field exists in the sync pull response.
