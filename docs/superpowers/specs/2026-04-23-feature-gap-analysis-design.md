# Feature Gap Analysis — Industry-Standard IMS (India Retail Focus)
**Date:** 2026-04-23  
**Author:** Rushil Rana  
**Status:** Approved  

## Context

This document maps all missing industry-standard features against what is already built in the IMS monorepo. It covers the API (`services/api`), admin web (`apps/admin-web`), and cashier POS (`apps/cashier`).

**Target market:** General retail (primary) — grocery, fashion, electronics, FMCG, specialty stores.  
**Target geography:** India — GST compliance, UPI payments, WhatsApp communication, and Indian market conventions are first-class requirements, not afterthoughts.  
**Target customer size:** Small (1–3 locations) to medium (3–20 locations). The product must scale from simple to complex without overwhelming small users.  
**Competitive context:** Vyapar, KhataBook, OkCredit, Gofrugal, Marg, Tally. See the Competitive Edge section at the bottom.

> **Scope note:** Wholesale/distribution-specific features (B2B sales orders, accounts receivable, vendor price lists, packing lists, back-order management) are explicitly out of scope. This is a retail POS + inventory product.

---

## Shippable Chunk Legend

| Chunk | Label | Description |
|---|---|---|
| **1** | Ship-blocking | Must exist before first paying customer. Losing deals without it. |
| **2** | Competitive parity | Expected within first few months. Disadvantage without it. |
| **3** | Differentiating | Edge over competitors. Build once the core is solid. |

---

## What Is Already Built

| Area | Status |
|---|---|
| Multi-tenant SaaS, multi-location (shops) | ✅ Built |
| RBAC — roles, permissions, operators, staff | ✅ Built |
| SaaS billing (plans, invoices, usage, cancel/renew) | ✅ Built |
| Product catalog (SKU, name, category, description, image, reorder_point, variants, product groups) | ✅ Built |
| Immutable stock ledger (movements, adjustments pending→approved) | ✅ Built |
| Transfer orders (shop-to-shop model + partial line tracking) | ✅ Model built, ❌ admin endpoints missing |
| Purchase orders + lines (CRUD, line-level quantity_received) | ✅ Built |
| Suppliers (basic CRUD — name, email, phone, notes) | ✅ Basic built |
| Stock adjustment creation + movement listing | ✅ Built |
| Sales transactions, multi-tender (cash + card) | ✅ Built |
| Tax — per-product per-shop overrides, default shop rate | ✅ Built (not GST-aware) |
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
- Customer groups / segments (VIP, regular, wholesale account)
- Customer-specific pricing (price list per group)
- Store credit / customer wallet balance (see also Domain 28 — Khata)

**Chunk:** 1 (profiles, purchase history, groups), 2 (customer-specific pricing, store credit wallet)

---

### Domain 2 — Returns & Refunds

**What exists:** Nothing. `Transaction.kind = "sale"` only. No return kind, no credit note, no restock logic. Flagged in ADR as "next candidate."

**What's missing:**
- Return transactions linked to original sale
- Partial returns (some items from an order)
- Refund tender choice (back to cash, back to store credit/Khata, exchange)
- Auto-restock on return (creates a stock movement)
- Return reason codes (wrong item, damaged, changed mind)
- Admin return approval workflow (optional, for controlled returns)

**Chunk:** 1

---

### Domain 3 — Product Catalog (gaps)

**What exists:** SKU, name, category (free text), description, image_url, reorder_point, unit_price_cents, variants, product groups.

**What's missing:**
- `barcode` / UPC / EAN field — critical for POS scanning; also needed for label printing (Domain 29)
- `cost_price_cents` — without it, margin and COGS calculations are impossible
- `hsn_code` — mandatory for GST invoices in India (Domain 25)
- `unit_of_measure` — sell by kg, litre, metre, piece, pack (grocery, fabric, hardware retail)
- Max stock level (only reorder_point exists; max needed for over-stock alerts)
- Product tags / labels (flexible classification beyond single category)
- Price history — track when prices changed and by how much
- Discontinued status handling — no longer ordered but still in stock

**Chunk:** 1 (barcode, cost_price_cents, hsn_code), 2 (UOM, max stock, tags), 3 (price history, discontinued handling)

---

### Domain 4 — Supplier & Purchasing (gaps)

**What exists:** Supplier CRUD (name, status, contact_email, contact_phone, notes). PO CRUD with line-level `quantity_received` and `unit_cost_cents`.

**What's missing:**
- Supplier address and GSTIN (needed for GST input tax credit)
- Supplier payment terms and lead time
- PO receiving workflow — endpoint that marks received lines and creates stock movements
- Partial receiving (receive some lines, leave rest open)
- PO status flow: draft → submitted → partially received → fully received → closed
- Purchase return (return goods to supplier — generates negative stock movement)

**Chunk:** 1 (PO receiving workflow, supplier GSTIN + address), 2 (partial receiving, PO status flow, purchase return)

---

### Domain 5 — Inventory Operations (gaps)

**What exists:** Stock adjustment creation, stock movement listing. Transfer order + lines model exists but no admin endpoints.

**What's missing:**
- Transfer order admin endpoints (create, approve, ship, receive)
- Multi-location stock overview — stock across all shops in one dashboard view
- Cycle count / stocktake workflow (count products in a shop, auto-create adjustments from variances)
- Low-stock alerts (reorder_point field exists; nothing triggers a notification when stock crosses it)
- Over-stock alerts (requires max stock level field)
- Shrinkage tracking as a distinct reason code with its own report

**Chunk:** 1 (transfer order endpoints, multi-location stock view, low-stock alerts), 2 (cycle count, over-stock alerts, shrinkage report)

---

### Domain 6 — Discounts & Promotions

**What exists:** Nothing. No discount fields on `Transaction` or `TransactionLine`.

**What's missing:**
- Item-level discounts (percentage or fixed amount off a line)
- Cart-level discounts (percentage or fixed off total)
- Coupon / promo codes (single-use, multi-use, expiry date)
- Manager override discounts (requires a role with `discounts:approve` permission)
- Time-limited promotions (date range, e.g. Diwali sale)

**Chunk:** 2 (item + cart discounts, coupon codes, manager override), 3 (time-limited promotions)

---

### Domain 7 — Loyalty & Rewards

**What exists:** Nothing.

**What's missing:**
- Points earning on purchase (configurable rate: e.g. 1 point per ₹100)
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
- Profit & loss report (unlocked once `cost_price_cents` exists)
- COGS report (cost of goods sold per period)
- Inventory valuation report (stock on hand × cost price, per shop)
- Dead stock / slow-moving inventory report (no movement in N days)
- Shrinkage / loss report
- GST tax period report (GSTR-1 / GSTR-3B exports — see Domain 25)
- Scheduled reports (auto-email or WhatsApp daily/weekly summary to owner)
- Comparison period analytics (this month vs. last month vs. same period last year)
- Stock demand forecasting (predict reorder needs from sales velocity)

**Chunk:** 2 (P&L, COGS, inventory valuation, dead stock — all unlocked by cost_price), 3 (scheduled reports, comparison periods, forecasting)

---

### Domain 10 — Cash Management (gaps)

**What exists:** Shift closing with expected_cash_cents vs. reported_cash_cents and discrepancy tracking.

**What's missing:**
- Opening float recording (start-of-day cash amount)
- Cash denomination count at close (₹2000, ₹500, ₹200, ₹100 notes etc.)
- Petty cash / in-shift expense recording
- Cash drawer event log (open/close events per shift)

**Chunk:** 2 (denomination count, opening float), 3 (petty cash, drawer event log)

---

### Domain 11 — Notifications & Alerts (gaps)

**What exists:** In-app notifications model and endpoints. Tenant email config.

**What's missing:**
- Low-stock email + WhatsApp alerts (trigger when stock drops below reorder_point)
- PO overdue alerts (expected delivery date passed, PO not received)
- Shift summary to manager (daily closing summary via email or WhatsApp)
- Customer-facing digital receipts (email + WhatsApp — requires CRM)
- Push notifications to admin mobile app

**Chunk:** 2 (low-stock + PO overdue alerts, shift summary), 3 (customer receipts, push notifications)

---

### Domain 12 — Batch / Lot / Expiry Tracking

**What exists:** Nothing.

**What's missing:**
- Batch / lot numbers on stock movements (for FMCG, pharma, food retail)
- Expiry date tracking per batch
- Expiry alerts (N days before expiry)
- FEFO (first-expiry-first-out) enforcement at POS

**Chunk:** 3 — relevant for grocery, pharmacy, and FMCG retail

---

### Domain 13 — Invoicing & Credit Notes

**What exists:** Nothing for customer-facing documents.

**What's missing:**
- GST-compliant tax invoice generation (tied to POS transactions — mandatory in India for GST-registered businesses)
- Bill of supply (for GST-exempt transactions)
- Credit note linked to a return
- Invoice PDF generation and WhatsApp / email delivery
- Invoice numbering sequence (per tenant, per financial year)

**Chunk:** 2 (credit notes, GST invoice generation), 3 (PDF + WhatsApp delivery, invoice numbering)

---

### Domain 14 — Receipt & Document Customization

**What exists:** Nothing configurable.

**What's missing:**
- Receipt template configuration (logo, business name/address, GSTIN, footer message)
- Digital receipt delivery to customer via WhatsApp or email after sale
- QR code on receipt (for returns, warranty, loyalty lookup)
- Thermal printer-optimised layout (58mm / 80mm paper)

**Chunk:** 2 (receipt template config, thermal printer layout), 3 (digital receipts, QR codes)

---

### Domain 15 — POS Advanced Features

**What exists:** Multi-tender payment, offline-first sync, product variants.

**What's missing:**
- Hold / park transactions (pause a sale, serve another customer, return to parked sale)
- Custom / ad-hoc line items (sell an unlisted item with a custom price and description)
- Item notes / special instructions on a transaction line
- Void transaction (cancel a posted transaction from admin)
- Tip / gratuity support
- Customer-facing display screen mode (second screen at POS terminal)
- Barcode / QR product lookup at POS (requires barcode field — Domain 3)

**Chunk:** 2 (hold transactions, custom line items, item notes, void, barcode lookup), 3 (tip/gratuity, customer display)

---

### Domain 16 — Tax Management (gaps)

**What exists:** Per-product per-shop tax overrides. Default tax rate per shop. Not GST-aware.

**What's missing:**
- Named tax rate bands (0%, 5%, 12%, 18%, 28% GST slabs) replacing generic rate overrides
- Tax-inclusive vs. tax-exclusive pricing toggle per tenant
- CGST + SGST split display (intra-state) vs. IGST (inter-state)
- Tax period report — total collected per GST slab per period

**Chunk:** 2 (GST slabs, inclusive/exclusive toggle, tax report) — superseded by Domain 25 for India specifics

---

### Domain 17 — Integration Ecosystem (gaps)

**What exists:** Webhooks, API tokens, CSV product import.

**What's missing:**
- CSV imports for customers, suppliers, stock levels (not just products)
- Bulk export: transactions, customers, products, stock
- Razorpay / PayU integration (card + UPI payments via payment gateway)
- Shopify / WooCommerce stock sync (for retailers with an online store)
- Tally export (see Domain 25)

**Chunk:** 2 (more CSV imports, bulk export), 3 (payment gateway, e-commerce integrations)

---

### Domain 18 — Product Bundles & Kits

**What exists:** Product groups exist for variant merchandising only.

**What's missing:**
- Bundle / kit definition (group of products sold as one unit at one price)
- Bundle stock deduction (auto-deduct each component on sale)
- Bundle pricing rules (bundle price vs. sum of parts)
- Composite products / assemblies (product made from other products)

**Chunk:** 2 (basic bundles/kits), 3 (composite/assembly)

---

### Domain 19 — Auto-reorder & Smart Purchasing

**What exists:** `reorder_point` field on products. Nothing acts on it.

**What's missing:**
- Reorder report — all products currently below reorder_point
- Preferred supplier per product
- Auto-draft PO when stock crosses reorder_point
- Suggested order quantity (based on lead time + sales velocity)

**Chunk:** 2 (reorder report, preferred supplier), 3 (auto-draft PO, suggested quantities)

---

### Domain 20 — Security & Compliance

**What exists:** JWT auth, RBAC, audit logs, scoped API tokens.

**What's missing:**
- Two-factor authentication (2FA / TOTP) for operator logins
- Active session management (view + revoke active sessions)
- Password policies (complexity, expiry, history)
- IP allowlisting for API token access
- GDPR / data privacy: right-to-erasure, customer data export

**Chunk:** 2 (2FA, session management), 3 (IP allowlist, GDPR tooling)

---

### Domain 21 — Platform & Onboarding

**What exists:** Platform-managed currency, billing plans, deployment mode.

**What's missing:**
- Onboarding wizard for new tenants (guided: shops → products → staff → devices)
- Usage limits enforcement by plan tier (product count, user count, shop count)
- White-labeling (custom logo + brand colors per tenant — reseller use case)
- Feature flags per plan tier
- In-app changelog / "what's new" panel

**Chunk:** 2 (onboarding wizard, usage limits enforcement), 3 (white-labeling, feature flags, changelog)

---

### Domain 22 — Staff Scheduling & Time Tracking

**What exists:** Staff model (invite, enroll, reset credentials). Shift closings track device.

**What's missing:**
- Employee clock in / clock out per shift
- Staff scheduling (assign employees to shifts at specific shops)
- Sales per employee analytics
- Commission rates and commission report

**Chunk:** 3

---

---

## India-Specific Domains

These are the domains that directly address the Indian retail market. They are what will differentiate this product from every competitor in the space.

---

### Domain 23 — GST Compliance

This is non-negotiable for any Indian retail product. Competitors either bolt it on poorly (Vyapar) or make it too complex (Tally, Marg). The opportunity is to get it right and keep it simple.

**What exists:** Generic tax overrides. No GST-specific structure at all.

**What's missing:**
- GSTIN field on Tenant profile (their GST registration number)
- GSTIN field on Supplier profile (for input tax credit)
- HSN / SAC code on products (mandatory on GST invoices above ₹50,000; best practice always)
- GST rate slab per product (0% / 5% / 12% / 18% / 28%) replacing generic tax rates
- Intra-state split: CGST + SGST (each half of the GST rate)
- Inter-state: IGST (full GST rate, single line)
- Bill of supply (issued when seller is GST-registered but goods/services are exempt)
- Composition scheme flag per tenant (flat-rate GST for businesses under ₹1.5cr — no input credit)
- GSTR-1 export (outward supplies — what your CA asks for every quarter)
- GSTR-3B summary export (monthly GST return summary)
- E-invoicing / IRN (Invoice Reference Number via IRP portal — mandatory above ₹5cr turnover, growing requirement)
- Financial year awareness (Indian FY: April–March) for all reports and invoice numbering

**Chunk:** 1 (GSTIN fields, HSN codes, GST slabs, CGST/SGST/IGST split, proper tax invoice format)  
**Chunk:** 2 (Bill of supply, composition scheme, GSTR-1/3B export, FY-aware invoice numbering)  
**Chunk:** 3 (E-invoicing / IRN integration)

---

### Domain 24 — Indian Payment Methods

UPI is the dominant payment rail in India — over 50% of retail payments. Treating it as an "other" tender is a dealbreaker.

**What exists:** Cash and card tender types in `PaymentAllocation`.

**What's missing:**
- UPI as a first-class tender type (alongside cash and card)
- Static UPI QR code display at checkout (tenant's VPA / UPI ID)
- Dynamic UPI QR code (amount pre-filled, for faster checkout)
- Named digital wallet tenders (Paytm, PhonePe, Google Pay) as distinct tender types for reporting
- UPI payment confirmation tracking (mark as confirmed after checking app)
- Razorpay / PayU gateway integration for card + UPI (online confirmation)
- Cash on delivery as a tender type (for home delivery orders)

**Chunk:** 1 (UPI tender type, static QR code display at checkout)  
**Chunk:** 2 (dynamic QR, named wallet tenders, payment confirmation, COD)  
**Chunk:** 3 (Razorpay / PayU gateway integration)

---

### Domain 25 — WhatsApp Integration

No Indian retail POS does WhatsApp natively. KhataBook sends basic SMS. This is the single biggest UX differentiation available in the Indian market — retailers already live in WhatsApp.

**What exists:** Tenant email config. In-app notifications. No WhatsApp at all.

**What's missing:**
- Send digital receipt via WhatsApp after sale (customer phone number from CRM)
- Send Khata / credit balance reminder via WhatsApp for overdue customers
- Send low-stock alert to owner / manager via WhatsApp
- Promotional message broadcast to customer segments via WhatsApp Business API
- WhatsApp opt-in / opt-out management per customer
- Daily sales summary to owner via WhatsApp (morning message: yesterday's sales, top product)

**Chunk:** 2 (receipts + Khata reminders via WhatsApp)  
**Chunk:** 3 (promotional broadcasts, low-stock alerts, daily summary)

---

### Domain 26 — Khata / Udhar (Informal Credit Book)

KhataBook and OkCredit built ₹1000cr+ businesses purely on this concept. Every Indian retailer runs a credit book — either mental, physical, or in a notebook. Integrating Khata natively into the POS, tied to real transaction history, is a durable moat. Standalone Khata apps lose the moment they can't show you what the customer actually bought.

**What exists:** Nothing. No credit or Udhar concept in the codebase.

**What's missing:**
- Udhar / credit given to customer tied to a transaction (or as a standalone credit entry)
- Payment received against outstanding Khata balance
- Outstanding balance per customer with full chronological history
- Khata statement per customer (printable or WhatsApp-able)
- Credit limit per customer (soft limit with override)
- WhatsApp reminder for overdue balance (ties into Domain 25)
- Khata settlement (mark a customer's balance as fully settled)

**Chunk:** 1 (Udhar record, balance tracking, payment received, Khata statement)  
**Chunk:** 2 (WhatsApp reminders, credit limits, settlement workflow)

---

### Domain 27 — Barcode Generation & Label Printing

Most domestic Indian goods — local brands, kiranas, regional manufacturers — don't come with barcodes. Retailers who want to use barcode scanning at POS need to generate and print their own labels. Most Indian software ignores this entirely.

**What exists:** Barcode field will be added (Domain 3). No generation or printing capability.

**What's missing:**
- Auto-generate EAN-13 barcode for products that don't have one
- Label template configuration (paper size, fields: name, price, barcode, MRP, expiry)
- Single product label print from product detail page
- Batch label print (selected products or all products below stock threshold)
- QR code generation as alternative to barcode (links to product info or POS lookup)
- Thermal label printer support (Zebra, TSC, Bixolon — common in Indian retail)

**Chunk:** 2 (barcode generation, single label print, basic template)  
**Chunk:** 3 (batch print, advanced templates, QR codes, thermal printer profiles)

---

### Domain 28 — Tally & Accounting Export

Indian accountants and CAs live in Tally. Even if you build a full P&L report, customers will ask "can my CA import this into Tally?" Being able to say yes removes a major sales objection. This is not about replacing Tally — it's about playing well with it.

**What exists:** Nothing.

**What's missing:**
- Daily sales summary export in Tally XML / CSV format
- Purchase entry export (supplier bills) for Tally import
- GSTR-compatible export (overlaps with Domain 23)
- Bank reconciliation helper (match UPI / card settlements against bank statement CSV)

**Chunk:** 3 — important but not day-one; build after GST compliance is solid

---

### Domain 29 — Indian Localisation

Small details that every Indian user notices immediately when they're wrong.

**What exists:** Generic currency formatting. INR is supported via platform currency config.

**What's missing:**
- Indian number format (1,00,000 not 100,000; lakh/crore labels on analytics charts)
- ₹ symbol as default display for INR tenants (currently generic currency symbol)
- DD/MM/YYYY date format as default for Indian tenants
- Indian address format (pincode, state dropdown matching GST state codes for CGST/IGST determination)
- State code lookup (GST state codes 01–37 determine intra vs. inter-state tax split)
- Hindi language option for cashier POS UI (most used language in Tier 2/3 cities)

**Chunk:** 2 (number formatting, ₹ symbol, date format, address + state code fields)  
**Chunk:** 3 (Hindi language POS UI)

---

## Prioritized Chunk Summary

### Chunk 1 — Ship-blocking

| # | Feature | Domain |
|---|---|---|
| 1.1 | Customer profiles, purchase history, groups | CRM |
| 1.2 | Returns & refunds (full workflow, restock on return) | Returns |
| 1.3 | Barcode / UPC / EAN field on products | Catalog |
| 1.4 | Cost price (`cost_price_cents`) on products | Catalog |
| 1.5 | HSN code on products | Catalog + GST |
| 1.6 | GSTIN on tenant + supplier profiles | GST |
| 1.7 | GST rate slab per product (0/5/12/18/28%) | GST |
| 1.8 | CGST + SGST / IGST split on transactions | GST |
| 1.9 | GST-compliant tax invoice format | GST |
| 1.10 | PO receiving workflow (mark received → stock movement) | Purchasing |
| 1.11 | Supplier address + GSTIN fields | Purchasing |
| 1.12 | Transfer order admin endpoints (create, approve, ship, receive) | Inventory Ops |
| 1.13 | Multi-location stock overview dashboard | Inventory Ops |
| 1.14 | Low-stock alerts (in-app + email when stock crosses reorder_point) | Alerts |
| 1.15 | UPI as first-class tender type + static QR code at checkout | Indian Payments |
| 1.16 | Khata / Udhar — credit record, balance tracking, payment received, statement | Khata |

### Chunk 2 — Competitive parity

| # | Feature | Domain |
|---|---|---|
| 2.1 | Item-level and cart-level discounts, coupon codes, manager override | Discounts |
| 2.2 | Cycle count / stocktake workflow | Inventory Ops |
| 2.3 | Credit notes (tied to returns) | Invoicing |
| 2.4 | GST invoice generation, bill of supply, GSTR-1/3B export | GST |
| 2.5 | Composition scheme support | GST |
| 2.6 | FY-aware invoice numbering | GST |
| 2.7 | Receipt template config (logo, GSTIN, address, thermal layout) | Documents |
| 2.8 | Hold / park transactions, custom line items, void, barcode lookup | POS |
| 2.9 | GST slab bands + tax-inclusive/exclusive toggle + tax period report | Tax |
| 2.10 | P&L report, COGS report, inventory valuation report | Reporting |
| 2.11 | Dead stock / slow-moving inventory report | Reporting |
| 2.12 | Units of measure on products | Catalog |
| 2.13 | Max stock level + product tags | Catalog |
| 2.14 | Partial PO receiving + PO status flow | Purchasing |
| 2.15 | Purchase return to supplier | Purchasing |
| 2.16 | PO overdue alerts + shift summary notification | Alerts |
| 2.17 | CSV imports for customers, suppliers, stock | Integrations |
| 2.18 | Bulk export (transactions, products, customers, stock) | Integrations |
| 2.19 | Basic product bundles / kits | Bundles |
| 2.20 | Reorder report + preferred supplier per product | Auto-reorder |
| 2.21 | Opening float + denomination count at shift close (Indian notes) | Cash Mgmt |
| 2.22 | 2FA for operator logins + session management | Security |
| 2.23 | Onboarding wizard + usage limits enforcement by plan | Platform |
| 2.24 | Customer-specific pricing per group | CRM |
| 2.25 | Dynamic UPI QR, named wallet tenders, COD tender | Indian Payments |
| 2.26 | WhatsApp receipts + Khata reminders | WhatsApp |
| 2.27 | Khata credit limits + WhatsApp reminders + settlement workflow | Khata |
| 2.28 | Barcode generation + single label print + basic label template | Labels |
| 2.29 | Indian number format, ₹ symbol, date format, state code / address fields | Localisation |

### Chunk 3 — Differentiating

| # | Feature | Domain |
|---|---|---|
| 3.1 | Loyalty & rewards (points, tiers, store credit wallet) | Loyalty |
| 3.2 | Gift cards & vouchers | Gift Cards |
| 3.3 | Time-limited promotions (Diwali sale etc.) | Discounts |
| 3.4 | Batch / lot / expiry tracking (FMCG, pharmacy) | Inventory |
| 3.5 | Invoice PDF + WhatsApp / email delivery | Invoicing |
| 3.6 | Digital receipt delivery via WhatsApp / email | Documents |
| 3.7 | Tip / gratuity at POS | POS |
| 3.8 | Customer-facing display screen mode | POS |
| 3.9 | Scheduled reports (auto daily/weekly to owner) | Reporting |
| 3.10 | Comparison period analytics | Reporting |
| 3.11 | Stock demand forecasting | Reporting |
| 3.12 | Accounting integrations (Xero, QuickBooks) | Integrations |
| 3.13 | Shopify / WooCommerce stock sync | Integrations |
| 3.14 | Razorpay / PayU gateway integration | Indian Payments |
| 3.15 | Composite products / assemblies | Bundles |
| 3.16 | Auto-draft PO on reorder trigger | Auto-reorder |
| 3.17 | Staff commission tracking + report | Staff |
| 3.18 | Employee clock in/out + scheduling | Staff |
| 3.19 | White-labeling + feature flags per plan | Platform |
| 3.20 | GDPR / data privacy tooling | Security |
| 3.21 | Category hierarchy (structured, not free text) | Catalog |
| 3.22 | Price history tracking | Catalog |
| 3.23 | Shrinkage tracking + loss report | Inventory |
| 3.24 | Compound taxes (multi-component per line) | Tax |
| 3.25 | WhatsApp promotional broadcasts + daily sales summary | WhatsApp |
| 3.26 | Batch label printing + advanced templates + QR codes | Labels |
| 3.27 | Tally export + bank reconciliation helper | Accounting |
| 3.28 | E-invoicing / IRN integration | GST |
| 3.29 | Hindi language POS UI | Localisation |
| 3.30 | Push notifications to admin mobile | Alerts |

---

## Implementation Notes

- **GST and cost price are both keystones in Chunk 1.** GST touches invoices, transactions, and product schema. Cost price unlocks all margin and COGS reporting. Neither should be deferred — do both in Chunk 1.
- **CRM + Khata ship together.** Khata is built on top of the Customer model. Don't split them across different sprints — design the Customer model with Khata in mind from the start.
- **Returns depend on CRM.** A return should optionally be tied to a customer record (for Khata credit, for history). Build returns after CRM.
- **Tax bands (GST slabs) before discount engine.** Tax-inclusive pricing interacts with how discounts are applied — the GST slab model should be locked before the discount schema is designed.
- **UPI is Chunk 1, not Chunk 2.** In India, asking a retailer to use software that doesn't support UPI is a dealbreaker. This must ship alongside cash and card.
- **WhatsApp receipts require CRM.** Receipts go to a customer's phone number. The CRM must exist before WhatsApp delivery is possible.
- **Barcode field (Domain 3) enables barcode generation (Domain 27) enables POS scanning.** These three steps are sequential — the schema field comes first.
- **Indian address + state code field (Domain 29) determines CGST/IGST split (Domain 23).** The state of the buyer vs. the state of the seller determines whether a transaction is intra-state (CGST + SGST) or inter-state (IGST). Both domains must be designed together.

---

## Competitive Edge Summary

| Edge | Why it matters in India | Who doesn't have it |
|---|---|---|
| **Offline-first POS** | Internet is unreliable in Tier 2/3 cities and markets | Vyapar (web), KhataBook (mobile but online-only), most SaaS tools |
| **Khata built into POS** | Every Indian retailer runs a credit book — owning this natively vs. a separate app is a durable moat | No POS does this; KhataBook/OkCredit are standalone and don't know what the customer bought |
| **WhatsApp receipts & reminders** | WhatsApp is the primary communication channel for Indian retailers and their customers | Nobody does this natively in a retail POS |
| **GST done right and simply** | GST compliance is mandatory but every competitor makes it painful | Marg/Busy are overly complex; Vyapar is accounting-first and not POS-native |
| **UPI as first-class tender** | UPI is dominant in Indian retail — it must feel native, not like an afterthought | Most POS treat it as "other" or require a separate app |
| **Multi-location from day 1** | Retail chains and small businesses with 2–3 shops need this immediately | Most Indian retail software is single-store |
| **Clean modern UX** | Cited as the #1 pain point by users of every Indian retail tool | Tally, Marg, Busy, Gofrugal all have complex, dated interfaces |
| **Barcode label printing** | Indian domestic goods rarely have pre-printed barcodes | Almost no Indian retail software generates and prints labels |
