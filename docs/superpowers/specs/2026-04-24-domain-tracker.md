# IMS Domain Feature Tracker
**Last Updated:** 2026-04-24
**Source:** [Feature Gap Analysis](./2026-04-23-feature-gap-analysis-design.md)

This is the live status tracker for all 56 feature domains. Update status and checkboxes as work is completed.

**Status values:** `Not Started` → `In Progress` → `Done`

---

## Summary Overview

| Domain | Name | Category | Chunks | Status |
|--------|------|----------|--------|--------|
| 1 | Customer Management (CRM) | General Retail | 1, 2 | Not Started |
| 2 | Returns & Refunds | General Retail | 1 | Not Started |
| 3 | Product Catalog (gaps) | General Retail | 1, 2, 3 | In Progress |
| 4 | Supplier & Purchasing (gaps) | General Retail | 1, 2 | Not Started |
| 5 | Inventory Operations (gaps) | General Retail | 1, 2 | Not Started |
| 6 | Discounts & Promotions | General Retail | 2, 3 | Not Started |
| 7 | Loyalty & Rewards | General Retail | 3 | Not Started |
| 8 | Gift Cards & Vouchers | General Retail | 3 | Not Started |
| 9 | Reporting (gaps) | General Retail | 2, 3 | Not Started |
| 10 | Cash Management (gaps) | General Retail | 2, 3 | Not Started |
| 11 | Notifications & Alerts (gaps) | General Retail | 2, 3 | Not Started |
| 12 | Batch / Lot / Expiry Tracking | General Retail | 3 | Not Started |
| 13 | Invoicing & Credit Notes | General Retail | 2, 3 | Not Started |
| 14 | Receipt & Document Customization | General Retail | 2, 3 | Not Started |
| 15 | POS Advanced Features | General Retail | 2, 3 | Not Started |
| 16 | Tax Management (gaps) | General Retail | 2 | Not Started |
| 17 | Integration Ecosystem (gaps) | General Retail | 2, 3 | Not Started |
| 18 | Product Bundles & Kits | General Retail | 2, 3 | Not Started |
| 19 | Auto-reorder & Smart Purchasing | General Retail | 2, 3 | Not Started |
| 20 | Security & Compliance | General Retail | 2, 3 | Not Started |
| 21 | Platform & Onboarding | General Retail | 2, 3 | Not Started |
| 22 | Staff Scheduling & Time Tracking | General Retail | 3 | Not Started |
| 23 | GST Compliance | India | 1, 2, 3 | Not Started |
| 24 | Indian Payment Methods | India | 1, 2, 3 | Not Started |
| 25 | WhatsApp Integration | India | 2, 3 | Not Started |
| 26 | Khata / Udhar | India | 1, 2 | Not Started |
| 27 | Barcode Generation & Label Printing | India | 2, 3 | Not Started |
| 28 | Tally & Accounting Export | India | 3 | Not Started |
| 29 | Indian Localisation | India | 2, 3 | Not Started |
| 30 | i18n Framework & Translation Infrastructure | i18n Foundation | 1, 2 | Not Started |
| 31 | Timezone per Tenant & Shop | i18n Foundation | 1 | Done |
| 32 | Country-aware Tax Engine | i18n Foundation | 1, 2 | Not Started |
| 33 | Country-aware Address & Phone Validation | i18n Foundation | 2 | Not Started |
| 34 | QRIS & Indonesian Payment Methods | Indonesia | 1, 2, 3 | Not Started |
| 35 | PPN Compliance (Indonesian VAT) | Indonesia | 1, 2, 3 | Not Started |
| 36 | Indonesian E-commerce Integration | Indonesia | 3 | Not Started |
| 37 | Indonesian Localisation | Indonesia | 2, 3 | Not Started |
| 38 | Province-aware Multi-tax (Canadian Tax) | Canada | 1, 2 | Not Started |
| 39 | Canadian Payment Methods | Canada | 1, 2 | Not Started |
| 40 | Canadian Compliance & Privacy | Canada | 1, 2, 3 | Not Started |
| 41 | Canadian Localisation & Language | Canada | 2, 3 | Not Started |
| 42 | Canadian Accounting Integrations | Canada | 3 | Not Started |
| 43 | Product Enrichment | General Retail | 1, 2, 3 | In Progress |
| 44 | Advanced POS Operations | General Retail | 2, 3 | Not Started |
| 45 | Returns & Exchange (depth) | General Retail | 2, 3 | Not Started |
| 46 | Customer Intelligence | General Retail | 2, 3 | Not Started |
| 47 | Advanced Inventory Operations | General Retail | 2, 3 | Not Started |
| 48 | Supplier Depth | General Retail | 2, 3 | Not Started |
| 49 | Device & POS Health | General Retail | 2, 3 | Not Started |
| 50 | Customer Feedback & NPS | General Retail | 3 | Not Started |
| 51 | Advanced Analytics & Reporting | General Retail | 2, 3 | Not Started |
| 52 | Local Delivery Management | General Retail | 3 | Not Started |
| 53 | Fraud Prevention & Anomaly Detection | General Retail | 2, 3 | Not Started |
| 54 | Warranty & After-sales Tracking | General Retail | 3 | Not Started |
| 55 | Customer Self-service & Catalogue Sharing | General Retail | 3 | Not Started |
| 56 | Advanced Promotions | General Retail | 3 | Not Started |

---

## General Retail Domains

---

### Domain 1 — Customer Management (CRM)
**Chunks:** 1, 2 | **Status:** Not Started

#### Chunk 1
- [ ] Customer profiles (name, phone, email, address, notes)
- [ ] Customer purchase history
- [ ] Customer groups / segments (VIP, regular, loyalty member)

#### Chunk 2
- [ ] Store credit / customer wallet balance

---

### Domain 2 — Returns & Refunds
**Chunks:** 1 | **Status:** Not Started

#### Chunk 1
- [ ] Return transactions linked to original sale
- [ ] Partial returns (some items from an order)
- [ ] Refund tender choice (back to cash, back to store credit/Khata, exchange)
- [ ] Auto-restock on return (creates a stock movement)
- [ ] Return reason codes (wrong item, damaged, changed mind)
- [ ] Admin return approval workflow

---

### Domain 3 — Product Catalog (gaps)
**Chunks:** 1, 2, 3 | **Status:** In Progress

#### Chunk 1
- [x] `barcode` / UPC / EAN field on products
- [x] `cost_price_cents` on products
- [x] `hsn_code` on products
- [x] `negative_inventory_allowed` flag per product

#### Chunk 2
- [ ] Unit of measure (kg, litre, metre, piece, pack)
- [ ] Max stock level field
- [ ] Product tags / labels
- [ ] Product availability per shop (enable/disable per location)

#### Chunk 3
- [ ] Price history tracking
- [ ] Discontinued status handling

---

### Domain 4 — Supplier & Purchasing (gaps)
**Chunks:** 1, 2 | **Status:** Not Started

#### Chunk 1
- [ ] PO receiving workflow (mark received → creates stock movement)
- [ ] Supplier address + GSTIN fields

#### Chunk 2
- [ ] Supplier lead time field (days to delivery)
- [ ] Partial PO receiving (receive some lines, leave rest open)
- [ ] PO status flow (draft → submitted → partially received → fully received → closed)
- [ ] Purchase return to supplier (negative stock movement)

---

### Domain 5 — Inventory Operations (gaps)
**Chunks:** 1, 2 | **Status:** Not Started

#### Chunk 1
- [ ] Transfer order admin endpoints (create, approve, ship, receive)
- [ ] Multi-location stock overview dashboard
- [ ] Low-stock alerts (in-app + email when stock crosses reorder_point)

#### Chunk 2
- [ ] Cycle count / stocktake workflow
- [ ] Over-stock alerts (requires max stock level from Domain 3)
- [ ] Shrinkage tracking with dedicated reason code and report

---

### Domain 6 — Discounts & Promotions
**Chunks:** 2, 3 | **Status:** Not Started

#### Chunk 2
- [ ] Item-level discounts (percentage or fixed amount off a line)
- [ ] Cart-level discounts (percentage or fixed off total)
- [ ] Coupon / promo codes (single-use, multi-use, expiry date)
- [ ] Manager override discounts (`discounts:approve` permission)
- [ ] Floor price / minimum selling price per product

#### Chunk 3
- [ ] Time-limited promotions (date range, e.g. Diwali sale)
- [ ] Promotional bundle pricing ("any 3 for ₹299")

---

### Domain 7 — Loyalty & Rewards
**Chunks:** 3 | **Status:** Not Started

#### Chunk 3
- [ ] Points earning on purchase (configurable rate, e.g. 1 point per ₹100)
- [ ] Points redemption at checkout
- [ ] Store credit / customer wallet (balance, top-up, redemption)
- [ ] Loyalty tiers (bronze/silver/gold with threshold rules)
- [ ] Points expiry
- [ ] Points deducted on return
- [ ] Loyalty multiplier events ("double points this weekend")
- [ ] Points expiry WhatsApp notifications

---

### Domain 8 — Gift Cards & Vouchers
**Chunks:** 3 | **Status:** Not Started

#### Chunk 3
- [ ] Issue gift cards (physical + digital)
- [ ] Redeem gift cards at POS as a tender type
- [ ] Gift card balance tracking
- [ ] Partial redemption + remaining balance carried forward
- [ ] Gift card expiry

---

### Domain 9 — Reporting (gaps)
**Chunks:** 2, 3 | **Status:** Not Started

#### Chunk 2
- [ ] Profit & loss report (unlocked once `cost_price_cents` exists)
- [ ] COGS report (cost of goods sold per period)
- [ ] Inventory valuation report (stock on hand × cost price, per shop)
- [ ] Dead stock / slow-moving inventory report (no movement in N days)

#### Chunk 3
- [ ] Scheduled reports (auto daily/weekly summary to owner)
- [ ] Comparison period analytics (this month vs last month vs same period last year)
- [ ] Stock demand forecasting

---

### Domain 10 — Cash Management (gaps)
**Chunks:** 2, 3 | **Status:** Not Started

#### Chunk 2
- [ ] Opening float recording (start-of-day cash amount)
- [ ] Cash denomination count at close (₹2000, ₹500, ₹200, ₹100 notes)

#### Chunk 3
- [ ] Petty cash / in-shift expense recording
- [ ] Cash drawer event log (open/close events per shift)

---

### Domain 11 — Notifications & Alerts (gaps)
**Chunks:** 2, 3 | **Status:** Not Started

#### Chunk 2
- [ ] Low-stock email + WhatsApp alerts (triggers from Domain 5)
- [ ] PO overdue alerts (expected delivery date passed, PO not received)
- [ ] Shift summary to manager (daily closing summary via email or WhatsApp)

#### Chunk 3
- [ ] Customer-facing digital receipts (email + WhatsApp — requires CRM)
- [ ] Push notifications to admin mobile app

---

### Domain 12 — Batch / Lot / Expiry Tracking
**Chunks:** 3 | **Status:** Not Started

#### Chunk 3
- [ ] Batch / lot numbers on stock movements
- [ ] Expiry date tracking per batch
- [ ] Expiry alerts (N days before expiry)
- [ ] FEFO (first-expiry-first-out) enforcement at POS

---

### Domain 13 — Invoicing & Credit Notes
**Chunks:** 2, 3 | **Status:** Not Started

#### Chunk 2
- [ ] Credit note linked to a return
- [ ] GST-compliant tax invoice generation tied to POS transactions

#### Chunk 3
- [ ] Invoice PDF generation
- [ ] WhatsApp / email invoice delivery
- [ ] Invoice numbering sequence (per tenant, per financial year)

---

### Domain 14 — Receipt & Document Customization
**Chunks:** 2, 3 | **Status:** Not Started

#### Chunk 2
- [ ] Receipt template configuration (logo, business name, GSTIN, footer message)
- [ ] Thermal printer-optimised layout (58mm / 80mm paper)

#### Chunk 3
- [ ] Digital receipt delivery via WhatsApp or email after sale
- [ ] QR code on receipt (returns, warranty, loyalty lookup)

---

### Domain 15 — POS Advanced Features
**Chunks:** 2, 3 | **Status:** Not Started

#### Chunk 2
- [ ] Hold / park transactions (pause a sale, serve another customer)
- [ ] Custom / ad-hoc line items (sell unlisted item with custom price)
- [ ] Item notes / special instructions on a transaction line
- [ ] Void transaction (cancel a posted transaction from admin)
- [ ] Barcode / QR product lookup at POS (requires barcode field — Domain 3)
- [ ] Quick-access favourites grid (pinned products on cashier home screen)
- [ ] Shift daily sales target (manager sets revenue goal; cashier sees live progress)
- [ ] Manager remote approval queue for discounts and returns

#### Chunk 3
- [ ] Tip / gratuity support
- [ ] Customer-facing display screen mode (second screen at POS terminal)
- [ ] Quick product creation from POS cashier screen

---

### Domain 16 — Tax Management (gaps)
**Chunks:** 2 | **Status:** Not Started

#### Chunk 2
- [ ] Named tax rate bands (0%, 5%, 12%, 18%, 28% GST slabs)
- [ ] Tax-inclusive vs. tax-exclusive pricing toggle per tenant
- [ ] CGST + SGST split display (intra-state) vs. IGST (inter-state)
- [ ] Tax period report (total collected per GST slab per period)

---

### Domain 17 — Integration Ecosystem (gaps)
**Chunks:** 2, 3 | **Status:** Not Started

#### Chunk 2
- [ ] CSV imports for customers, suppliers, stock levels
- [ ] Bulk export (transactions, customers, products, stock)

#### Chunk 3
- [ ] Razorpay / PayU payment gateway integration
- [ ] Shopify / WooCommerce stock sync

---

### Domain 18 — Product Bundles & Kits
**Chunks:** 2, 3 | **Status:** Not Started

#### Chunk 2
- [ ] Bundle / kit definition (group of products sold as one unit at one price)
- [ ] Bundle stock deduction (auto-deduct each component on sale)
- [ ] Bundle pricing rules (bundle price vs. sum of parts)

#### Chunk 3
- [ ] In-store assembly bundles (gift hampers, custom gift sets built at time of sale)

---

### Domain 19 — Auto-reorder & Smart Purchasing
**Chunks:** 2, 3 | **Status:** Not Started

#### Chunk 2
- [ ] Reorder report (all products currently below reorder_point)
- [ ] Preferred supplier per product

#### Chunk 3
- [ ] Auto-draft PO when stock crosses reorder_point
- [ ] Suggested order quantity (based on lead time + sales velocity)

---

### Domain 20 — Security & Compliance
**Chunks:** 2, 3 | **Status:** Not Started

#### Chunk 2
- [ ] Two-factor authentication (2FA / TOTP) for operator logins
- [ ] Active session management (view + revoke active sessions)

#### Chunk 3
- [ ] Password policies (complexity, expiry, history)
- [ ] IP allowlisting for API token access
- [ ] GDPR / data privacy tooling (right-to-erasure, customer data export)

---

### Domain 21 — Platform & Onboarding
**Chunks:** 2, 3 | **Status:** Not Started

#### Chunk 2
- [ ] Onboarding wizard for new tenants (shops → products → staff → devices)
- [ ] Usage limits enforcement by plan tier (product count, user count, shop count)

#### Chunk 3
- [ ] White-labeling (custom logo + brand colors per tenant)
- [ ] Feature flags per plan tier
- [ ] In-app changelog / "what's new" panel

---

### Domain 22 — Staff Scheduling & Time Tracking
**Chunks:** 3 | **Status:** Not Started

#### Chunk 3
- [ ] Employee clock in / clock out per shift
- [ ] Staff scheduling (assign employees to shifts at specific shops)
- [ ] Sales per employee analytics
- [ ] Commission rates and commission report

---

### Domain 43 — Product Enrichment
**Chunks:** 1, 2, 3 | **Status:** In Progress

#### Chunk 1
- [x] MRP (Maximum Retail Price) field on products
- [x] Price guard alerts (warn cashier if price is below cost or above MRP)

#### Chunk 2
- [ ] Product image upload (cloud storage, not just a URL)
- [ ] Shelf / aisle location field
- [ ] Bulk price update by category or percentage
- [ ] Product search by supplier in catalog

#### Chunk 3
- [ ] Multi-image per product (multiple angles, variant-specific images)
- [ ] Custom product fields (configurable extra metadata per tenant)
- [ ] Multi-language product names

---

### Domain 44 — Advanced POS Operations
**Chunks:** 2, 3 | **Status:** Not Started

#### Chunk 2
- [ ] Staff PIN / quick cashier login (4-digit PIN, sales attributed to active cashier)
- [ ] Cashier handover (pass device to next cashier without closing shift)
- [ ] Layaway / deposit payment (reserve product with partial payment)
- [ ] Price rounding rules (₹1/₹5/₹10 for India; $0.05 for Canadian cash)
- [ ] Transaction-level notes (free-text note on whole transaction)
- [ ] Multi-unit selling (same product in multiple pack sizes without duplicate SKUs)
- [ ] Tax exemption per customer

#### Chunk 3
- [ ] Product modifiers at POS (size, add-ons, options affecting price)

---

### Domain 45 — Returns & Exchange (depth)
**Chunks:** 2, 3 | **Status:** Not Started

#### Chunk 2
- [ ] Return without receipt (look up by customer name/phone/date range)
- [ ] Configurable return policy per product category (e.g. 7 days electronics, 30 days clothing)
- [ ] Return window enforcement at POS (alert + manager override to proceed)
- [ ] Partial refund amount (custom amount rather than exact line price)

#### Chunk 3
- [ ] Exchange workflow (return + replacement in a single transaction)
- [ ] Serial number verification on return

---

### Domain 46 — Customer Intelligence
**Chunks:** 2, 3 | **Status:** Not Started

#### Chunk 2
- [ ] Birthday field on customer profile
- [ ] Visit frequency tracking (last visit date, total visit count)
- [ ] At-risk customer dashboard (customers who haven't visited in X days)

#### Chunk 3
- [ ] Birthday discount automation via WhatsApp
- [ ] WhatsApp re-engagement for at-risk customers (CASL opt-in required for Canada)
- [ ] Customer lifetime value (CLV) report
- [ ] Average basket value per customer
- [ ] Referral tracking ("referred by" field on customer profile)

---

### Domain 47 — Advanced Inventory Operations
**Chunks:** 2, 3 | **Status:** Not Started

#### Chunk 2
- [ ] Mobile stocktake from admin mobile app (scan/tap products, enter physical count)
- [ ] Blind count mode (hide expected quantities during stocktake)
- [ ] Inventory write-off (P&L-impacting, separate from a stock adjustment)

#### Chunk 3
- [ ] Inventory aging report (how long current stock has been sitting since received)
- [ ] GRN (Goods Received Note) auto-generated when a PO is marked received

---

### Domain 48 — Supplier Depth
**Chunks:** 2, 3 | **Status:** Not Started

#### Chunk 2
- [ ] Multiple contacts per supplier (separate order, delivery, accounts contacts)
- [ ] Supplier performance notes (log of interactions, quality issues, disputes)
- [ ] Supplier product catalogue (which supplier carries which products at what cost)

#### Chunk 3
- [ ] Supplier invoice matching (attach invoice PDF, flag discrepancy vs PO total)

---

### Domain 49 — Device & POS Health
**Chunks:** 2, 3 | **Status:** Not Started

#### Chunk 2
- [ ] Device last-sync dashboard (last sync timestamp, offline queue size per device)
- [ ] Offline duration alerts (notify manager if device unsynced for X hours)

#### Chunk 3
- [ ] Receipt printer assignment per device
- [ ] Per-device sales reporting (revenue, transaction count, average basket by device)

---

### Domain 50 — Customer Feedback & NPS
**Chunks:** 3 | **Status:** Not Started

#### Chunk 3
- [ ] Post-sale feedback QR code on receipt (1–5 star rating, no app required)
- [ ] NPS tracking per shop, trended over time in analytics
- [ ] Negative feedback alerts (1–2 stars triggers immediate manager notification)
- [ ] Feedback review in admin (filter by shop, date, rating; flag for resolution)

---

### Domain 51 — Advanced Analytics & Reporting
**Chunks:** 2, 3 | **Status:** Not Started

#### Chunk 2
- [ ] Gross margin report per product and category (requires cost_price_cents)
- [ ] Inter-store performance comparison (side-by-side analytics for 2+ shops)

#### Chunk 3
- [ ] ABC product classification (A = top 20% revenue, B = middle 30%, C = bottom 50%)
- [ ] Basket / affinity analysis (products most commonly bought together)
- [ ] Staff productivity report (requires staff PIN from Domain 44)
- [ ] Cash flow summary (daily cash in vs. cash out per shop)

---

### Domain 52 — Local Delivery Management
**Chunks:** 3 | **Status:** Not Started

#### Chunk 3
- [ ] Delivery order creation at POS (customer address + scheduled delivery window)
- [ ] Delivery fee as a line item (configurable per shop)
- [ ] Delivery status tracking (pending → out for delivery → delivered)
- [ ] Delivery person assignment (staff member or external rider)
- [ ] Delivery confirmation (OTP or photo of delivered goods)
- [ ] WhatsApp delivery status notifications to customer

---

### Domain 53 — Fraud Prevention & Anomaly Detection
**Chunks:** 2, 3 | **Status:** Not Started

#### Chunk 2
- [ ] Suspicious cashier pattern alerts (excessive voids, discounts, no-receipt returns)
- [ ] Void / discount rate threshold alerts (configurable per tenant)
- [ ] Customer fraud flag in CRM (POS warns cashier when flagged customer is selected)

#### Chunk 3
- [ ] Anomaly detection on stock movements (large adjustments outside shift hours)
- [ ] Cashier loss report (expected vs actual cash per cashier over time)

---

### Domain 54 — Warranty & After-sales Tracking
**Chunks:** 3 | **Status:** Not Started

#### Chunk 3
- [ ] Warranty period per product (configurable duration, displayed on receipt)
- [ ] Warranty record per sale (links sale, customer, serial number, expiry date)
- [ ] Warranty lookup (by customer name, phone, or receipt number)
- [ ] Warranty expiry WhatsApp alerts to customer

---

### Domain 55 — Customer Self-service & Catalogue Sharing
**Chunks:** 3 | **Status:** Not Started

#### Chunk 3
- [ ] Customer self-service portal (purchase history, loyalty, Khata via OTP login)
- [ ] Digital product catalogue (shareable web link or PDF)
- [ ] Price list WhatsApp broadcast to customer segments

---

### Domain 56 — Advanced Promotions
**Chunks:** 3 | **Status:** Not Started

#### Chunk 3
- [ ] Promotional bundle pricing ("any 3 items from category for ₹299")
- [ ] Loyalty multiplier events (double/triple points on products, categories, or date ranges)
- [ ] Customer-segment-specific promotions (VIP-only discounts)
- [ ] Flash sale pricing (time-window price drop, auto-reverts)
- [ ] Spend-and-save thresholds ("spend ₹2000, get ₹200 off")

---

## India-Specific Domains

---

### Domain 23 — GST Compliance
**Chunks:** 1, 2, 3 | **Status:** Not Started

#### Chunk 1
- [ ] GSTIN field on Tenant profile
- [ ] GSTIN field on Supplier profile
- [ ] HSN / SAC code on products
- [ ] GST rate slab per product (0% / 5% / 12% / 18% / 28%)
- [ ] Intra-state split: CGST + SGST
- [ ] Inter-state: IGST
- [ ] GST-compliant tax invoice format

#### Chunk 2
- [ ] Bill of supply (for GST-exempt transactions)
- [ ] Composition scheme flag per tenant (flat-rate GST under ₹1.5cr)
- [ ] GSTR-1 export (outward supplies)
- [ ] GSTR-3B summary export
- [ ] Financial year awareness (April–March) for reports and invoice numbering

#### Chunk 3
- [ ] E-invoicing / IRN integration via IRP portal

---

### Domain 24 — Indian Payment Methods
**Chunks:** 1, 2, 3 | **Status:** Not Started

#### Chunk 1
- [ ] UPI as a first-class tender type
- [ ] Static UPI QR code display at checkout

#### Chunk 2
- [ ] Dynamic UPI QR code (amount pre-filled for faster checkout)
- [ ] Named digital wallet tenders (Paytm, PhonePe, Google Pay)
- [ ] UPI payment confirmation tracking
- [ ] Cash on delivery (COD) tender type

#### Chunk 3
- [ ] Razorpay / PayU gateway integration (online card + UPI confirmation)

---

### Domain 25 — WhatsApp Integration
**Chunks:** 2, 3 | **Status:** Not Started

#### Chunk 2
- [ ] Digital receipt via WhatsApp after sale (requires CRM — Domain 1)
- [ ] Khata / credit balance reminder via WhatsApp for overdue customers

#### Chunk 3
- [ ] Low-stock alert to owner / manager via WhatsApp
- [ ] Promotional message broadcast to customer segments via WhatsApp Business API
- [ ] WhatsApp opt-in / opt-out management per customer
- [ ] Daily sales summary to owner via WhatsApp

---

### Domain 26 — Khata / Udhar (Informal Credit Book)
**Chunks:** 1, 2 | **Status:** Not Started

#### Chunk 1
- [ ] Udhar / credit given to customer tied to a transaction
- [ ] Payment received against outstanding Khata balance
- [ ] Outstanding balance per customer with full chronological history
- [ ] Khata statement per customer (printable or WhatsApp-able)

#### Chunk 2
- [ ] Credit limit per customer (soft limit with override)
- [ ] WhatsApp reminder for overdue balance
- [ ] Khata settlement (mark customer balance as fully settled)
- [ ] Overdue Khata aging report (0–30 / 31–60 / 60+ days buckets)

---

### Domain 27 — Barcode Generation & Label Printing
**Chunks:** 2, 3 | **Status:** Not Started

#### Chunk 2
- [ ] Auto-generate EAN-13 barcode for products without one
- [ ] Single product label print from product detail page
- [ ] Basic label template configuration (paper size, fields: name, price, barcode, MRP)

#### Chunk 3
- [ ] Batch label printing (selected products or all below stock threshold)
- [ ] Advanced label templates
- [ ] QR code generation as alternative to barcode
- [ ] Thermal label printer support (Zebra, TSC, Bixolon)

---

### Domain 28 — Tally & Accounting Export
**Chunks:** 3 | **Status:** Not Started

#### Chunk 3
- [ ] Daily sales summary export in Tally XML / CSV format
- [ ] Purchase entry export (supplier bills) for Tally import
- [ ] GSTR-compatible export
- [ ] Bank reconciliation helper (match UPI / card settlements against bank CSV)

---

### Domain 29 — Indian Localisation
**Chunks:** 2, 3 | **Status:** Not Started

#### Chunk 2
- [ ] Indian number format (1,00,000 not 100,000; lakh/crore labels on charts)
- [ ] ₹ symbol as default display for INR tenants
- [ ] DD/MM/YYYY date format as default for Indian tenants
- [ ] Indian address format (pincode, GST state code dropdown)
- [ ] State code lookup (GST state codes 01–37 for CGST/IGST determination)

#### Chunk 3
- [ ] Hindi language option for cashier POS UI

---

## i18n Foundation Domains

---

### Domain 30 — i18n Framework & Translation Infrastructure
**Chunks:** 1, 2 | **Status:** Not Started

#### Chunk 1
- [ ] Translation layer for admin web (react-i18next or equivalent)
- [ ] Translation layer for cashier Flutter app (flutter_localizations + intl package)
- [ ] Language preference field on Tenant
- [ ] Language preference field on Device

#### Chunk 2
- [ ] Translatable API error messages
- [ ] First translated languages per market (Hindi, Bahasa Indonesia, French)

---

### Domain 31 — Timezone per Tenant & Shop
**Chunks:** 1 | **Status:** Done

#### Chunk 1
- [x] `timezone` field on Tenant (IANA timezone string, e.g. `Asia/Kolkata`)
- [x] `timezone` field on Shop (override tenant default — needed for multi-timezone countries)
- [x] All shift reports and daily analytics displayed in the shop's local timezone
- [x] Financial year boundary awareness per tenant (India: Apr–Mar; others: calendar year)

---

### Domain 32 — Country-aware Tax Engine
**Chunks:** 1, 2 | **Status:** Not Started

#### Chunk 1
- [ ] Pluggable tax rule engine per tenant country (not hardcoded per country)
- [ ] Tax rule model (country + region + product category → rate(s) + component labels)
- [ ] Support for compound taxes (multiple named components per line)

#### Chunk 2
- [ ] Support for tax-inclusive pricing toggle
- [ ] Support for tax-exempt product categories per country/region
- [ ] Tax component labels configurable per tenant (CGST/SGST/IGST, GST/HST/PST/QST, PPN)

---

### Domain 33 — Country-aware Address & Phone Validation
**Chunks:** 2 | **Status:** Not Started

#### Chunk 2
- [ ] Country field on Shop (operational country, separate from billing_country on Tenant)
- [ ] Postal/pincode format validation per country (India: 6-digit; Indonesia: 5-digit; Canada: A1A 1A1)
- [ ] Province/state dropdown per country
- [ ] Phone number country-code prefix per tenant (+91, +62, +1)
- [ ] Phone format validation per country

---

## Indonesia-Specific Domains

---

### Domain 34 — QRIS & Indonesian Payment Methods
**Chunks:** 1, 2, 3 | **Status:** Not Started

#### Chunk 1
- [ ] QRIS as a first-class tender type (one code, all wallets)
- [ ] Static QRIS display at checkout (tenant's merchant QR)

#### Chunk 2
- [ ] Dynamic QRIS (amount pre-filled for faster checkout)
- [ ] Named digital wallet tenders (GoPay, OVO, Dana, ShopeePay, LinkAja)
- [ ] Virtual account payments (unique VA number per transaction)
- [ ] Cash on delivery (COD) tender

#### Chunk 3
- [ ] BNPL tenders (Kredivo, Akulaku)

---

### Domain 35 — PPN Compliance (Indonesian VAT)
**Chunks:** 1, 2, 3 | **Status:** Not Started

#### Chunk 1
- [ ] NPWP field on Tenant and Supplier (Indonesian tax ID)
- [ ] PPN rate as a configurable field (not hardcoded — rate changes require no code deploy)
- [ ] Faktur Pajak format for PKP-registered businesses

#### Chunk 2
- [ ] PPN-exempt product categories (basic food, medical services, education)
- [ ] Annual PPN return summary export

#### Chunk 3
- [ ] e-Faktur / DJP Online integration (mandatory electronic tax invoicing)

---

### Domain 36 — Indonesian E-commerce Integration
**Chunks:** 3 | **Status:** Not Started

#### Chunk 3
- [ ] Shopee Seller Centre API — bi-directional stock sync
- [ ] Tokopedia (GoTo) Seller API — bi-directional stock sync
- [ ] TikTok Shop API — stock sync
- [ ] Lazada / Bukalapak (lower priority)
- [ ] Unified online order inbox (orders from all platforms in admin)

---

### Domain 37 — Indonesian Localisation
**Chunks:** 2, 3 | **Status:** Not Started

#### Chunk 2
- [ ] IDR number formatting (dot as thousands separator, no decimals — Rp 50.000)
- [ ] DD/MM/YYYY date format
- [ ] Indonesia timezone selector per shop (WIB / WITA / WIT)
- [ ] Indonesian address format (5-digit kode pos, 34-provinsi dropdown)
- [ ] +62 country code prefix on CRM phone number fields

#### Chunk 3
- [ ] Bahasa Indonesia language for cashier POS UI

---

## Canada-Specific Domains

---

### Domain 38 — Province-aware Multi-tax (Canadian Tax System)
**Chunks:** 1, 2 | **Status:** Not Started

#### Chunk 1
- [ ] Province field on Shop (drives all tax calculation — mandatory before any Canadian tenant goes live)
- [ ] Province-to-tax-rule mapping (GST-only / HST / GST+PST / GST+QST)
- [ ] Compound tax display on receipts and invoices (separate lines: GST $2.50 + PST $3.50)
- [ ] GST/HST registration number on all receipts over $30 CAD (legal requirement)
- [ ] QST registration number field for Quebec tenants

#### Chunk 2
- [ ] Tax-exempt product categories by province
- [ ] Annual GST/HST return summary report (structured for CRA filing)
- [ ] Quebec QST annual return summary

---

### Domain 39 — Canadian Payment Methods
**Chunks:** 1, 2 | **Status:** Not Started

#### Chunk 1
- [ ] Interac Debit as a first-class tender type

#### Chunk 2
- [ ] Interac e-Transfer as a tender type (bank-to-bank via email/phone)
- [ ] Apple Pay / Google Pay (contactless tap)

---

### Domain 40 — Canadian Compliance & Privacy
**Chunks:** 1, 2, 3 | **Status:** Not Started

#### Chunk 1
- [ ] Business Number (BN) field on Tenant (9-digit federal business identifier)
- [ ] GST/HST registration number display on receipts and invoices over $30 CAD

#### Chunk 2
- [ ] CASL-compliant opt-in management for marketing messages (gates WhatsApp broadcasts)
- [ ] Annual GST/HST return export structured for CRA

#### Chunk 3
- [ ] Full PIPEDA / provincial privacy law compliance tooling

---

### Domain 41 — Canadian Localisation & Language
**Chunks:** 2, 3 | **Status:** Not Started

#### Chunk 2
- [ ] CAD dollar formatting ($X,XXX.XX — comma thousands separator, 2 decimal places)
- [ ] Canadian postal code format validation (A1A 1A1)
- [ ] Province dropdown on Shop address (10 provinces + 3 territories)
- [ ] +1 country code prefix on CRM phone number fields
- [ ] Canadian timezone selector per shop (PT / MT / CT / ET / AT / NT)

#### Chunk 3
- [ ] French language support for cashier POS (legally required in Quebec)
- [ ] Bilingual receipt option (English + French)

---

### Domain 42 — Canadian Accounting Integrations
**Chunks:** 3 | **Status:** Not Started

#### Chunk 3
- [ ] QuickBooks Canada integration (daily sales sync, GST/HST reporting)
- [ ] Wave Accounting export
- [ ] FreshBooks integration
- [ ] Sage 50 Canada export
- [ ] CRA-compatible GST/HST report format
