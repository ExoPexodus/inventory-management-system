# Feature Gap Analysis — Industry-Standard IMS (Multi-Market Retail)
**Date:** 2026-04-23  
**Author:** Rushil Rana  
**Status:** Approved  

## Context

This document maps all missing industry-standard features against what is already built in the IMS monorepo. It covers the API (`services/api`), admin web (`apps/admin-web`), and cashier POS (`apps/cashier`).

**Target market:** General retail (primary) — grocery, fashion, electronics, FMCG, specialty stores.  
**Target geographies:** India (primary launch), Indonesia and Canada (planned expansion). Each market has its own compliance requirements, payment rails, and localisation needs.  
**Target customer size:** Small (1–3 locations) to medium (3–20 locations). The product must scale from simple to complex without overwhelming small users.  
**Competitive context:** India — Vyapar, KhataBook, OkCredit, Gofrugal, Marg, Tally. See the Competitive Edge section at the bottom.

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
- Customer groups / segments (VIP, regular, loyalty member)
- Store credit / customer wallet balance (see also Domain 26 — Khata)

> Note: Differentiated pricing for customer groups (e.g. VIP discounts) is handled through Domain 6 (discount codes + manager overrides) and Domain 7 (loyalty tiers), not through dedicated per-customer price lists.

**Chunk:** 1 (profiles, purchase history, groups), 2 (store credit wallet)

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
- `barcode` / UPC / EAN field — critical for POS scanning; also needed for label printing (Domain 27)
- `cost_price_cents` — without it, margin and COGS calculations are impossible
- `hsn_code` — mandatory for GST invoices in India (Domain 23)
- `unit_of_measure` — sell by kg, litre, metre, piece, pack (grocery, fabric, hardware retail)
- Max stock level (only reorder_point exists; max needed for over-stock alerts)
- Product tags / labels (flexible classification beyond single category)
- Price history — track when prices changed and by how much
- Discontinued status handling — no longer ordered but still in stock
- `negative_inventory_allowed` flag per product — configurable whether a sale can proceed when stock = 0 (block, warn with override, or allow silently)
- Product availability per shop — enable or disable a product at specific shop locations without deleting it from the catalog
- See also Domain 43 for product enrichment (image upload, MRP, custom fields)

**Chunk:** 1 (barcode, cost_price_cents, hsn_code, negative_inventory_allowed), 2 (UOM, max stock, tags, product availability per shop), 3 (price history, discontinued handling)

---

### Domain 4 — Supplier & Purchasing (gaps)

**What exists:** Supplier CRUD (name, status, contact_email, contact_phone, notes). PO CRUD with line-level `quantity_received` and `unit_cost_cents`.

**What's missing:**
- Supplier address and GSTIN (needed for GST input tax credit)
- Supplier lead time (days to delivery — used for reorder timing)
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
- Promotional bundle pricing — "any 3 for ₹299" style (different from fixed kit bundles — customer picks any 3 items from a category)
- Minimum selling price / floor price per product — prevent cashiers from discounting below a set floor (franchise protection, margin protection)

**Chunk:** 2 (item + cart discounts, coupon codes, manager override, floor price), 3 (time-limited promotions, promotional bundle pricing)

---

### Domain 7 — Loyalty & Rewards

**What exists:** Nothing.

**What's missing:**
- Points earning on purchase (configurable rate: e.g. 1 point per ₹100)
- Points redemption at checkout
- Store credit / customer wallet (balance, top-up, redemption)
- Loyalty tiers (bronze/silver/gold with threshold rules)
- Points expiry
- Points deducted on return (reverse the points earned on a returned transaction)
- Loyalty multiplier events ("double points this weekend" promotions)
- Points expiry WhatsApp notifications (remind customer before points expire)

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
- Quick-access favourites grid — configurable pinned products on the cashier home screen for one-tap adding (avoids searching for top-selling items every time)
- Shift daily sales target — manager sets a revenue goal per shift; cashier sees live progress on their dashboard
- Quick product creation at POS — create a new product inline from the cashier screen without navigating to admin (useful when a new item arrives mid-shift)
- Manager remote approval — when a cashier requests a discount override or return approval, it appears on the manager's device for one-tap approval rather than requiring physical presence at the till

**Chunk:** 2 (hold transactions, custom line items, item notes, void, barcode lookup, favourites grid, shift target, manager remote approval), 3 (tip/gratuity, customer display, quick product creation)

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
- Tally export (see Domain 28)

**Chunk:** 2 (more CSV imports, bulk export), 3 (payment gateway, e-commerce integrations)

---

### Domain 18 — Product Bundles & Kits

**What exists:** Product groups exist for variant merchandising only.

**What's missing:**
- Bundle / kit definition (group of products sold as one unit at one price)
- Bundle stock deduction (auto-deduct each component on sale)
- Bundle pricing rules (bundle price vs. sum of parts)
- In-store assembly bundles (e.g. gift hampers, custom gift sets built from individual products at time of sale — stock deducted per component)

**Chunk:** 2 (basic bundles/kits), 3 (in-store assembly)

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

### Domain 43 — Product Enrichment

**What exists:** `image_url` is a stored URL string — no actual upload. One image per product. No MRP field. No custom metadata fields.

**What's missing:**
- **Product image upload** — upload images directly from phone/desktop rather than pasting a URL; stored in cloud object storage (S3 / equivalent)
- **Multi-image per product** — multiple angles, variant-specific images
- **MRP (Maximum Retail Price)** — legally mandated field for packaged goods in India; POS should alert if selling price exceeds MRP; shown on shelf labels and receipts
- **Price guard alerts** — warn cashier if selling price is below cost price (margin protection) or above MRP (legal protection)
- **Shelf / aisle location** — text field for where to find the product in the store (e.g., "Aisle 3, Shelf B") — useful during stocktakes and for staff helping customers
- **Bulk price update** — update selling price (or cost price) for all products in a category at once, or by percentage change; critical for seasonal repricing without editing hundreds of products one by one
- **Custom product fields** — configurable extra metadata per tenant (e.g. warranty period, country of origin, care instructions, material, brand)
- **Multi-language product names** — store product name in multiple languages (e.g. English + Hindi + Bahasa) for multilingual receipts and POS display
- **Product search by supplier** — filter catalog by which supplier provides each product

**Chunk:** 1 (MRP field, price guard), 2 (image upload, shelf location, bulk price update, product search by supplier), 3 (multi-image, custom fields, multi-language names)

---

### Domain 44 — Advanced POS Operations

**What exists:** Multi-tender, offline sync, variants, hold/park (being added).

**What's missing:**
- **Staff PIN / quick cashier login** — each staff member has a 4-digit PIN; they enter it at the start of their session on a shared device; sales are attributed to the active cashier; requires no full logout between cashiers
- **Cashier handover** — pass the device to the next cashier without closing the shift; active shift continues, cashier identity changes with a PIN entry
- **Layaway / deposit payment** — customer pays a deposit now, product is reserved, balance paid when they collect; generates a layaway record tied to the customer; critical for Indian retail (electronics, clothing, gold)
- **Price rounding rules** — configurable rounding for transaction totals: nearest ₹1 / ₹5 / ₹10 for India (paisa avoidance); nearest $0.05 for Canadian cash transactions (penny phased out); rounding applies to cash only, not card
- **Transaction-level notes** — free-text note on the whole transaction (delivery instructions, custom order reference, customer request)
- **Multi-unit selling** — configure a product to be sold in multiple pack sizes without duplicate SKUs (e.g. 1 piece = ₹50, 6-pack = ₹280, carton = ₹900); POS prompts for unit selection
- **Product modifiers at POS** — add customisations to a product line that change the price (e.g. size: S/M/L, filling choice, engraving text, gift wrapping add-on); relevant for tailors, bakeries, jewellery shops, gift stores
- **Tax exemption per customer** — flag certain customers as tax-exempt (registered charities, government bodies, diplomatic entities); tax lines are suppressed on their transactions

**Chunk:** 2 (staff PIN, cashier handover, layaway, price rounding, transaction notes, multi-unit selling, tax exemption per customer), 3 (product modifiers)

---

### Domain 45 — Returns & Exchange (depth)

The returns domain (Domain 2) covers the core workflow. These gaps only become visible once returns are live:

**What's missing:**
- **Return without receipt** — look up the original transaction by customer name/phone, product name, or approximate date range; common in retail where customers lose receipts
- **Configurable return policy per product category** — e.g. electronics: 7 days; clothing: 30 days; perishables: no returns; displayed to cashier at the point of initiating a return
- **Return window enforcement** — POS alerts cashier if customer is past the configured return window; requires manager PIN override to proceed
- **Exchange workflow** — return one item and immediately replace with another in a single transaction (price difference settled as charge or refund); currently would require two separate flows
- **Serial number verification on return** — for electronics, scan or enter the serial number at return and verify it matches what was originally sold before accepting
- **Partial refund amount** — refund a custom amount rather than the exact original line price (e.g. for goodwill refund or damaged-but-accepted return)

**Chunk:** 2 (return without receipt, return policy config, return window enforcement, partial refund), 3 (exchange workflow, serial number verification)

---

### Domain 46 — Customer Intelligence

CRM (Domain 1) covers profiles and history. These are the analytical and re-engagement layers on top:

**What's missing:**
- **Birthday field + birthday discount automation** — store customer date of birth; on their birthday automatically send a WhatsApp message with a discount voucher or loyalty bonus points
- **Visit frequency tracking** — track last visit date and total visit count per customer; display on customer profile
- **At-risk customer dashboard** — customers who haven't visited in X configurable days are flagged in a list; manager can see who's drifting away
- **WhatsApp re-engagement** — automatically send a "we miss you" message with a personalised promo to customers who haven't visited in X days (CASL opt-in required for Canadian tenants)
- **Customer lifetime value (CLV)** — total spend since first visit, visible on the customer profile and in a report; useful for identifying true VIPs beyond just last-visit recency
- **Average basket value per customer** — mean transaction value; helps distinguish high-value occasional buyers from frequent small buyers
- **Referral tracking** — "referred by" field on customer profile; track which customers bring in new customers; basis for referral incentive programmes

**Chunk:** 2 (birthday field, visit frequency, at-risk dashboard), 3 (birthday automation, WhatsApp re-engagement, CLV report, referral tracking)

---

### Domain 47 — Advanced Inventory Operations

Beyond the stocktake workflow already in Domain 5:

**What's missing:**
- **Mobile stocktake** — conduct a cycle count from the admin mobile app; staff walks the shop floor, scans barcodes or taps products, enters physical count; far more practical than doing it from a desktop admin panel
- **Blind count mode** — during a stocktake, hide the system's expected quantities so staff counts what they physically see, not what the system expects; reduces anchoring bias and catches real discrepancies
- **Inventory write-off** — formal process to write off stock that cannot be sold (expired, damaged beyond repair, stolen with police report); distinct from a stock adjustment because it carries an explicit P&L cost and appears in a dedicated write-off report
- **Inventory aging report** — for each product at each shop, how long has the current stock been sitting since it was received; highlights items at risk of becoming dead stock before the dead stock report catches them
- **GRN (Goods Received Note)** — a printable/downloadable document auto-generated when a PO is marked as received; lists what was ordered vs what arrived; signed by the receiving staff member as a paper audit trail

**Chunk:** 2 (mobile stocktake, blind count, inventory write-off), 3 (inventory aging report, GRN)

---

### Domain 48 — Supplier Depth

Beyond basic supplier CRUD (Domain 4):

**What's missing:**
- **Multiple contacts per supplier** — most suppliers have separate people for placing orders, tracking deliveries, and handling accounts/invoices; currently only one email and phone per supplier record
- **Supplier performance notes** — free-text log of interactions, quality issues, dispute history, and delivery reliability per supplier; visible to anyone creating a PO
- **Supplier invoice matching** — when a PO is received, attach the supplier's paper/digital invoice (PDF or photo), match the invoice total against the PO total, and flag any discrepancy before payment is made
- **Supplier product catalogue** — link which products each supplier carries, at what typical cost; used to auto-populate PO lines and drive the preferred-supplier-per-product feature (Domain 19)

**Chunk:** 2 (multiple contacts, performance notes, supplier product catalogue), 3 (invoice matching)

---

### Domain 49 — Device & POS Health

**What exists:** Device enrollment and refresh exist. No visibility into device health or sync status from admin.

**What's missing:**
- **Device last-sync dashboard** — admin view showing each enrolled device, its last sync timestamp, and how many transactions are sitting in the offline queue; immediately spot devices that are offline or stuck
- **Offline duration alerts** — notify the manager (in-app + email) if a device hasn't synced in a configurable number of hours; could indicate a broken device, connectivity problem, or forgotten open shift
- **Receipt printer assignment** — configure which network/bluetooth printer is associated with each device; currently no printer management exists at all
- **Per-device sales reporting** — revenue, transaction count, and average basket by device per shift; useful for understanding if one till is being underused or if a specific cashier is assigned to it

**Chunk:** 2 (device last-sync dashboard, offline duration alerts), 3 (printer assignment, per-device sales reporting)

---

### Domain 50 — Customer Feedback & NPS

**What exists:** Nothing.

**What's missing:**
- **Post-sale feedback QR code** — printed on the receipt; customer scans it and gets a simple 1–5 star rating form (optionally with a comment box); no app download required
- **NPS tracking** — Net Promoter Score calculated from ratings per shop, trended over time; visible in the analytics dashboard
- **Negative feedback alerts** — when a customer gives 1–2 stars, alert the shop manager immediately via in-app notification or WhatsApp so they can follow up
- **Feedback visible in admin** — review all customer ratings and comments; filter by shop, date, rating; flag for resolution

**Chunk:** 3

---

### Domain 51 — Advanced Analytics & Reporting

Beyond what's already in Domain 9:

**What's missing:**
- **Gross margin per product and category** — selling price minus cost price, expressed as % and absolute value; requires cost_price_cents from Domain 3; unlocks a full margin report once Chunk 1 is done
- **Inter-store performance comparison** — side-by-side analytics for two or more shops: revenue, basket size, top products, staff performance, conversion; critical for owners managing multiple locations
- **ABC product classification** — automatically classify products as A (top 20% of revenue), B (middle 30%), C (bottom 50%); standard retail inventory technique; drives purchasing priority and shelf-space decisions
- **Basket / affinity analysis** — what products are most commonly bought together; surfaces cross-sell opportunities and informs product placement decisions
- **Staff productivity report** — revenue per cashier, items per transaction per cashier, average transaction value per cashier, voids and discounts per cashier; requires staff PIN (Domain 44) to attribute sales
- **Cash flow summary** — daily cash in (sales) vs. cash out (purchases, petty cash, expenses) per shop

**Chunk:** 2 (gross margin report, inter-store comparison), 3 (ABC classification, basket analysis, staff productivity, cash flow summary)

---

### Domain 52 — Local Delivery Management

Relevant for grocery, pharmacy, electronics, and FMCG retail in urban India and Indonesia — home delivery from the store has become a baseline customer expectation.

**What exists:** Nothing. Transactions are all in-store.

**What's missing:**
- **Delivery order creation at POS** — mark a transaction as a delivery order with a customer delivery address and scheduled delivery time window
- **Delivery fee as a line item** — add a delivery charge to the transaction total (configurable per shop)
- **Delivery status tracking** — simple manual status updates: pending → out for delivery → delivered; no GPS required
- **Delivery person assignment** — assign a staff member or external rider to a delivery run; they see their assigned deliveries in the admin mobile app
- **Delivery confirmation** — mark delivery as complete with an OTP the customer receives, or a photo of the delivered goods
- **Delivery-integrated WhatsApp** — auto-send customer a WhatsApp message when order is out for delivery and again when delivered

**Chunk:** 3

---

### Domain 53 — Fraud Prevention & Anomaly Detection

**What exists:** Audit logs exist for admin actions. No fraud-specific monitoring.

**What's missing:**
- **Suspicious cashier pattern alerts** — flag unusual patterns automatically: excessive voids in a shift, excessive discounts by a single cashier, high volume of no-receipt returns, refunds to a different tender than the original payment
- **Void / discount rate thresholds** — configurable per-tenant thresholds; alert manager when a cashier exceeds X% discount rate or Y voids in a shift
- **Customer fraud flag** — mark a customer as flagged in CRM (e.g. history of fraudulent returns, chargebacks); POS warns cashier when a flagged customer is selected
- **Anomaly detection on stock movements** — flag unexpected stock movements (large adjustments made outside shift hours, movements by users without inventory permissions)
- **Cashier loss report** — report on discrepancies between expected and actual cash per cashier over time; identifies patterns of cash handling issues

**Chunk:** 2 (suspicious pattern alerts, void/discount thresholds, customer fraud flag), 3 (anomaly detection on stock, cashier loss report)

---

### Domain 54 — Warranty & After-sales Tracking

Relevant for electronics, appliance, and tool retailers:

**What exists:** Nothing.

**What's missing:**
- **Warranty period per product** — configurable warranty duration (e.g. 12 months) stored on the product; displayed on the receipt
- **Warranty record per sale** — when a product with a warranty is sold, a warranty record is created linking the sale, the customer, the product serial number (if tracked), and the expiry date
- **Warranty lookup** — admin or cashier looks up a customer's warranty status by customer name, phone, or receipt number; used when a customer brings an item in for service
- **Warranty expiry alerts** — notify customers via WhatsApp before their warranty expires (useful for upselling extended warranty or service plans)

**Chunk:** 3

---

### Domain 55 — Customer Self-service & Catalogue Sharing

**What exists:** Nothing customer-facing beyond the physical receipt.

**What's missing:**
- **Customer self-service portal** — a simple web page (no app) where customers enter their phone number, verify via OTP, and see their purchase history, loyalty points balance, active Khata balance, and outstanding Layaway payments
- **Digital product catalogue** — a shareable web link or PDF showing the store's products with prices and images; tenant configures which products appear; shared via WhatsApp or printed as a price list brochure
- **Price list WhatsApp broadcast** — send the catalogue or price list directly to a customer segment via WhatsApp Business API (e.g. "our new arrivals" or "this week's offers")

**Chunk:** 3

---

### Domain 56 — Advanced Promotions

Beyond basic discounts and coupons (Domain 6):

**What exists:** Nothing.

**What's missing:**
- **Promotional bundle pricing** — "any 3 items from this category for ₹299" (customer picks freely, not a fixed kit); different from Domain 18 bundles which are fixed product groupings
- **Loyalty multiplier events** — double or triple points on specific products, categories, or date ranges (e.g. "3× points on electronics this weekend")
- **Customer-segment-specific promotions** — a promotion that only applies to customers in a specific group (e.g. VIP members get 15% off, others don't)
- **Flash sale pricing** — a product's price drops to a sale price for a defined time window; reverts automatically; cashier sees the sale badge on the product
- **Spend-and-save thresholds** — "spend ₹2000, get ₹200 off" cart-level promotion tied to spend amount (different from a percentage discount)

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
- Overdue Khata aging report — list all customers with outstanding balances, bucketed by days overdue (0–30, 31–60, 60+ days); sorted by amount owed

**Chunk:** 1 (Udhar record, balance tracking, payment received, Khata statement)  
**Chunk:** 2 (WhatsApp reminders, credit limits, settlement workflow, overdue aging report)

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

---

## Internationalisation Foundation

These cross-cutting requirements must be in place before any country-specific work can land cleanly. They are shared infrastructure — not India, Indonesia, or Canada features specifically.

**What exists:** Datetimes are timezone-aware (stored as UTC timestamptz). Currency is configurable per tenant. `billing_country` and `billing_state` exist on Tenant but are billing-only — not operational. No timezone field on Tenant or Shop. No i18n framework anywhere in the stack. Everything is hardcoded English.

---

### Domain 30 — i18n Framework & Translation Infrastructure

**What's missing:**
- Translation layer for admin web (react-i18next or equivalent)
- Translation layer for cashier Flutter app (flutter_localizations + intl package)
- Translatable API error messages (currently all English strings)
- Language preference field on Tenant (drives default UI language for that tenant's staff)
- Language preference field on Device (cashier operator may override tenant default)

**Chunk:** 1 (framework scaffold + language fields on Tenant/Device), 2 (first translated languages per market)

---

### Domain 31 — Timezone per Tenant & Shop

**What's missing:**
- `timezone` field on Tenant (IANA timezone string, e.g. `Asia/Kolkata`, `Asia/Jakarta`, `America/Toronto`)
- `timezone` field on Shop (override tenant default — needed for Indonesia where a business may span WIB and WITA zones)
- All shift reports, daily analytics, and closing summaries displayed in the shop's local timezone
- Financial year boundary awareness per tenant (India: April–March; Canada: calendar year or custom; Indonesia: calendar year)

**Chunk:** 1

---

### Domain 32 — Country-aware Tax Engine

**What's missing:**
- Pluggable tax rule engine per tenant country (not hardcoded per country in app logic)
- Tax rule model: country + region + product category → rate(s) + component labels
- Support for compound taxes (multiple named components per line — e.g. GST 5% + PST 7%)
- Support for tax-inclusive pricing toggle (price already includes tax, back-calculate on invoice)
- Support for tax-exempt product categories per country/region
- Tax component labels configurable per tenant (CGST/SGST/IGST for India; GST/HST/PST/QST for Canada; PPN for Indonesia)

**Chunk:** 1 (tax engine foundation + compound tax model), 2 (tax-exempt categories, per-country component labels)

---

### Domain 33 — Country-aware Address & Phone Validation

**What's missing:**
- Country field on Shop (operational country, separate from billing_country on Tenant)
- Postal/pincode format validation per country (India: 6-digit; Indonesia: 5-digit kode pos; Canada: A1A 1A1)
- Province/state dropdown per country (India: 28 states + 8 UTs with GST codes; Canada: 10 provinces + 3 territories with tax rules; Indonesia: 34 provinsi)
- Phone number country-code prefix per tenant (for CRM — +91 India, +62 Indonesia, +1 Canada)
- Phone format validation per country

**Chunk:** 2

---

## Indonesia-Specific Domains

Indonesia is mobile-first and e-commerce-heavy. QRIS (Bank Indonesia's mandated unified QR standard) covers all digital wallets with a single code. WhatsApp is as dominant here as in India. The tax system (PPN) is simpler than India's GST — mostly one rate — but e-filing is mandatory for registered businesses.

---

### Domain 34 — QRIS & Indonesian Payment Methods

QRIS is mandated by Bank Indonesia — one QR code works for GoPay, OVO, Dana, ShopeePay, LinkAja, and all bank apps simultaneously. Every Indonesian retailer displays one. Treating it as anything other than a first-class tender is a dealbreaker.

**What exists:** Cash and card tender types only.

**What's missing:**
- QRIS as a first-class tender type (one code, all wallets)
- Static QRIS display at checkout (tenant's merchant QR)
- Dynamic QRIS (amount pre-filled for faster checkout)
- Named digital wallet tenders for split reporting (GoPay, OVO, Dana, ShopeePay, LinkAja)
- Virtual account payments (customer transfers to a unique VA number issued per transaction — very common in Indonesia)
- COD (cash on delivery for retail/delivery orders)
- BNPL tenders: Kredivo, Akulaku (growing rapidly in Indonesian retail)

**Chunk:** 1 (QRIS tender + static QR display), 2 (dynamic QRIS, named wallet tenders, VA payments, COD), 3 (BNPL tenders)

---

### Domain 35 — PPN Compliance (Indonesian VAT)

PPN (Pajak Pertambahan Nilai) is Indonesia's VAT — currently 11%, rising to 12%. Simpler than India's GST but still requires specific invoice formats and electronic filing for registered businesses.

**What exists:** Nothing Indonesia-specific. Generic tax overrides only.

**What's missing:**
- NPWP field on Tenant and Supplier (Nomor Pokok Wajib Pajak — Indonesian tax ID, equivalent to GSTIN)
- PPN rate as a configurable field (not hardcoded — rate changes require no code deploy)
- PPN-exempt product categories (basic food, medical services, education are exempt)
- Faktur Pajak format (Indonesian tax invoice — required for PKP-registered businesses)
- NIK field on Customer profile (national ID — used on invoices for non-business buyers)
- e-Faktur integration (mandatory electronic tax invoice system via DJP Online — equivalent to India's e-invoicing)
- Annual PPN return summary export

**Chunk:** 1 (NPWP field, PPN rate config, Faktur Pajak format), 2 (PPN-exempt categories, annual PPN return export), 3 (e-Faktur / DJP Online integration)

---

### Domain 36 — Indonesian E-commerce Integration

Most Indonesian retailers sell across marketplaces alongside their physical store. Tokopedia, Shopee, and TikTok Shop are the dominant platforms. Stock going out-of-sync between physical and online is the top pain point for multi-channel Indonesian retailers.

**What exists:** Nothing. Webhooks and API tokens exist for custom integrations only.

**What's missing:**
- Shopee Seller Centre API — bi-directional stock sync
- Tokopedia (GoTo) Seller API — bi-directional stock sync
- TikTok Shop API — stock sync (fastest-growing channel in Indonesia)
- Lazada / Bukalapak as lower-priority additions
- Unified online order inbox (orders from all platforms visible in admin)

**Chunk:** 3

---

### Domain 37 — Indonesian Localisation

**What exists:** Nothing Indonesia-specific.

**What's missing:**
- Bahasa Indonesia language for cashier POS UI (expected by retail staff; Indonesian labour law context makes English-only software uncomfortable)
- IDR number formatting — dot as thousands separator, no decimal places (Rp 50.000 not Rp 50,000.00)
- DD/MM/YYYY date format
- Indonesia timezone selector per shop: WIB (UTC+7, Java/Sumatra), WITA (UTC+8, Bali/Lombok/Kalimantan), WIT (UTC+9, Papua/Maluku) — a retailer with shops in Jakarta and Bali needs both
- Indonesian address format (5-digit kode pos, provinsi dropdown of 34 provinces)
- +62 country code prefix on CRM phone number fields

**Chunk:** 2 (IDR formatting, date format, timezone, address format, +62 phone), 3 (Bahasa Indonesia POS UI)

---

## Canada-specific Domains

Canada's defining challenge is its tax system — the most complex of the three markets, entirely driven by which province a shop operates in. Payment-wise, Interac Debit is the dominant domestic rail. Quebec adds a French language requirement that is legally enforced for consumer-facing software.

---

### Domain 38 — Province-aware Multi-tax (Canadian Tax System)

The tax applied to a Canadian transaction is entirely determined by which province the shop is in. The rules differ in every province and getting them wrong exposes merchants to CRA audit risk.

| Province / Territory | Tax Structure |
|---|---|
| Ontario, NB, NS, PEI, NL | HST only (13–15%) — replaces both GST and PST |
| British Columbia | GST (5%) + PST (7%) — two separate components |
| Saskatchewan | GST (5%) + PST (6%) — two separate components |
| Manitoba | GST (5%) + RST (7%) — two separate components |
| Quebec | GST (5%) + QST (9.975%) — both shown separately |
| Alberta, Yukon, NWT, Nunavut | GST only (5%) — no provincial component |

**What exists:** Generic tax overrides per product/shop. No province awareness.

**What's missing:**
- Province field on Shop (drives all tax calculation — mandatory before any Canadian tenant goes live)
- Province-to-tax-rule mapping (GST-only / HST / GST+PST / GST+QST)
- Compound tax display on receipts and invoices (e.g., GST $2.50 + PST $3.50 shown as separate lines)
- Tax-exempt product categories by province (basic groceries nationally GST-exempt; children's clothing PST-exempt in BC; etc.)
- GST/HST registration number on all receipts for transactions over $30 CAD (legal requirement in Canada)
- QST registration number field for Quebec tenants
- Annual GST/HST return summary report (structured for CRA filing)
- Quebec QST annual return summary

**Chunk:** 1 (province field on Shop, province-to-tax mapping, compound tax display on receipt, GST/HST registration number — legal requirement)  
**Chunk:** 2 (tax-exempt categories by province, annual GST/HST + QST return reports)

---

### Domain 39 — Canadian Payment Methods

Interac Debit is the dominant domestic payment network in Canada — most Canadians use it daily. It is not the same as Visa Debit and must be its own tender type for accurate reporting. Interac e-Transfer is also common for custom orders, deposits, and layaway settlements.

**What exists:** Cash and card tender types only.

**What's missing:**
- Interac Debit as a first-class tender type
- Interac e-Transfer as a tender type (bank-to-bank via email/phone — common for custom orders, deposits, and layaway settlements)
- Apple Pay / Google Pay (contactless tap — growing rapidly, especially post-pandemic)

**Chunk:** 1 (Interac Debit), 2 (Interac e-Transfer, Apple Pay / Google Pay)

---

### Domain 40 — Canadian Compliance & Privacy

**What exists:** JWT auth, RBAC, audit logs. No Canadian-specific compliance fields.

**What's missing:**
- Business Number (BN) field on Tenant (9-digit federal business identifier — used on all tax filings)
- GST/HST registration number display on receipts and invoices for sales over $30 CAD (legal requirement — CRA enforced)
- QST registration number (Quebec tenants only)
- CASL compliance (Canadian Anti-Spam Legislation) — explicit opt-in required before any marketing email or WhatsApp message; this directly gates the WhatsApp broadcast feature (Domain 25) for Canadian tenants
- PIPEDA / provincial privacy law compliance (stricter than GDPR in some aspects — governs how customer data is collected, stored, and deleted for Canadian residents)
- Annual GST/HST return export structured for CRA

**Chunk:** 1 (BN + GST/HST registration on receipts — legal requirement), 2 (CASL opt-in management, annual return export), 3 (full PIPEDA compliance tooling)

---

### Domain 41 — Canadian Localisation & Language

**What exists:** Nothing Canada-specific.

**What's missing:**
- French language support for cashier POS (legally required in Quebec — the Charter of the French Language mandates French availability in workplace software)
- Bilingual receipt option — English + French (expected by Quebec consumers, legally prudent)
- CAD dollar formatting ($X,XXX.XX — comma thousands separator, 2 decimal places, $ prefix)
- Canadian postal code format validation (A1A 1A1 — alternating letter/digit/letter space digit/letter/digit)
- Province dropdown on Shop address (10 provinces + 3 territories — also drives tax rules from Domain 38)
- +1 country code prefix on CRM phone number fields
- Canadian timezone selector per shop (PT, MT, CT, ET, AT, NT — Canada spans 6 time zones)

**Chunk:** 2 (CAD formatting, postal code validation, province dropdown, +1 phone, timezone), 3 (French language POS, bilingual receipts)

---

### Domain 42 — Canadian Accounting Integrations

QuickBooks is the dominant SMB accounting tool in Canada. Wave Accounting was founded in Canada and has massive free-tier adoption among micro-businesses.

**What exists:** Webhooks and API tokens for custom integration only.

**What's missing:**
- QuickBooks Canada integration (daily sales sync, GST/HST reporting)
- Wave Accounting export (popular with micro-businesses — free product)
- FreshBooks integration (Canadian SaaS, popular with service-oriented retailers)
- Sage 50 Canada export
- CRA-compatible GST/HST report format

**Chunk:** 3

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
| 1.17 | i18n framework scaffold (admin web + cashier Flutter) + language fields on Tenant/Device | i18n Foundation |
| 1.18 | Timezone field on Tenant + Shop (IANA timezone string) | i18n Foundation |
| 1.19 | Country-aware tax engine foundation + compound tax model | i18n Foundation |
| 1.20 | QRIS tender type + static QR display at checkout (Indonesia) | Indonesian Payments |
| 1.21 | NPWP field on Tenant/Supplier, PPN rate config, Faktur Pajak format (Indonesia) | PPN Compliance |
| 1.22 | Province field on Shop + province-to-tax mapping engine (Canada) | Canadian Tax |
| 1.23 | Compound tax display on receipt — GST + HST/PST/QST (Canada) | Canadian Tax |
| 1.24 | BN + GST/HST registration number on all receipts over $30 CAD (Canada — legal) | Canadian Compliance |
| 1.25 | Interac Debit as first-class tender type (Canada) | Canadian Payments |
| 1.26 | MRP field on products + price guard (above MRP / below cost alerts) | Product Enrichment |
| 1.27 | `negative_inventory_allowed` flag per product | Product Catalog |
| 1.28 | Product availability per shop (enable/disable per location) | Product Catalog |

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
| 2.24 | Dynamic UPI QR, named wallet tenders, COD tender | Indian Payments |
| 2.25 | WhatsApp receipts + Khata reminders | WhatsApp |
| 2.26 | Khata credit limits + WhatsApp reminders + settlement workflow | Khata |
| 2.27 | Barcode generation + single label print + basic label template | Labels |
| 2.28 | Indian number format, ₹ symbol, date format, state code / address fields | Localisation |
| 2.29 | Dynamic QRIS, named wallet tenders (GoPay/OVO/Dana), VA payments, COD (Indonesia) | Indonesian Payments |
| 2.30 | PPN-exempt product categories + annual PPN return export (Indonesia) | PPN Compliance |
| 2.31 | IDR formatting, date format, timezone (WIB/WITA/WIT), address + +62 phone (Indonesia) | Indonesian Localisation |
| 2.32 | Tax-exempt product categories by province + annual GST/HST + QST return reports (Canada) | Canadian Tax |
| 2.33 | Interac e-Transfer + Apple Pay / Google Pay tenders (Canada) | Canadian Payments |
| 2.34 | CASL-compliant opt-in management for marketing messages (Canada) | Canadian Compliance |
| 2.35 | CAD formatting, postal code validation, province dropdown, +1 phone, timezone (Canada) | Canadian Localisation |
| 2.36 | Country-aware address format + phone country-code validation (all markets) | i18n Foundation |
| 2.37 | Product image upload (cloud storage, not just URL) + shelf/aisle location | Product Enrichment |
| 2.38 | Bulk price update by category or percentage | Product Enrichment |
| 2.39 | Product search by supplier in catalog | Product Enrichment |
| 2.40 | Staff PIN / quick cashier login + cashier handover | POS Operations |
| 2.41 | Layaway / deposit payment — hold product with partial payment | POS Operations |
| 2.42 | Price rounding rules (₹1/₹5/₹10 India; $0.05 Canada cash) | POS Operations |
| 2.43 | Transaction-level notes + multi-unit selling | POS Operations |
| 2.44 | Quick-access favourites grid + shift daily sales target | POS Operations |
| 2.45 | Manager remote approval queue for discounts and returns | POS Operations |
| 2.46 | Tax exemption per customer | POS Operations |
| 2.47 | Floor price / minimum selling price per product | Discounts |
| 2.48 | Return without receipt + return policy config per category | Returns Depth |
| 2.49 | Return window enforcement at POS | Returns Depth |
| 2.50 | Partial refund amount | Returns Depth |
| 2.51 | Customer birthday field + visit frequency + at-risk dashboard | Customer Intelligence |
| 2.52 | Mobile stocktake (admin mobile app) + blind count mode | Inventory Ops |
| 2.53 | Inventory write-off (P&L-impacting, separate from adjustment) | Inventory Ops |
| 2.54 | Multiple supplier contacts + performance notes | Supplier Depth |
| 2.55 | Supplier product catalogue (which supplier carries which products) | Supplier Depth |
| 2.56 | Device last-sync dashboard + offline duration alerts | Device Health |
| 2.57 | Gross margin report per product and category | Reporting |
| 2.58 | Inter-store performance comparison analytics | Reporting |
| 2.59 | Suspicious pattern alerts + void/discount thresholds + customer fraud flag | Fraud Prevention |
| 2.60 | Overdue Khata aging report (0–30 / 31–60 / 60+ days buckets) | Khata |

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
| 3.15 | In-store assembly bundles (gift hampers, custom gift sets) | Bundles |
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
| 3.31 | e-Faktur / DJP Online integration for electronic tax invoices (Indonesia) | PPN Compliance |
| 3.32 | Tokopedia / Shopee / TikTok Shop stock sync (Indonesia) | Indonesian E-commerce |
| 3.33 | BNPL tenders — Kredivo, Akulaku (Indonesia) | Indonesian Payments |
| 3.34 | Bahasa Indonesia cashier POS UI | Indonesian Localisation |
| 3.35 | French language cashier POS + bilingual receipts (Quebec, Canada) | Canadian Localisation |
| 3.36 | PIPEDA privacy compliance tooling (Canada) | Canadian Compliance |
| 3.37 | QuickBooks Canada / Wave / FreshBooks / Sage 50 accounting integrations (Canada) | Canadian Accounting |
| 3.38 | Multi-image per product + multi-language product names | Product Enrichment |
| 3.39 | Custom product fields (warranty period, origin, care instructions, etc.) | Product Enrichment |
| 3.40 | Product modifiers at POS (size, add-ons, custom options affecting price) | POS Operations |
| 3.41 | Quick product creation from POS cashier screen | POS Operations |
| 3.42 | Exchange workflow (return + replacement in single transaction) | Returns Depth |
| 3.43 | Serial number verification on return | Returns Depth |
| 3.44 | Birthday discount automation + WhatsApp re-engagement for at-risk customers | Customer Intelligence |
| 3.45 | Customer lifetime value (CLV) report + referral tracking | Customer Intelligence |
| 3.46 | Inventory aging report + GRN (Goods Received Note) | Inventory Ops |
| 3.47 | Supplier invoice matching (attach invoice, flag discrepancy) | Supplier Depth |
| 3.48 | Receipt printer assignment + per-device sales reporting | Device Health |
| 3.49 | Customer feedback QR code + NPS tracking + negative feedback alerts | Customer Feedback |
| 3.50 | ABC product classification + basket/affinity analysis | Reporting |
| 3.51 | Staff productivity report + cash flow summary | Reporting |
| 3.52 | Local delivery management (order, fee, status, assignment, confirmation) | Delivery |
| 3.53 | Anomaly detection on stock movements + cashier loss report | Fraud Prevention |
| 3.54 | Warranty tracking per sale + warranty lookup + expiry alerts | Warranty |
| 3.55 | Customer self-service portal (purchase history, loyalty, Khata via web OTP) | Self-service |
| 3.56 | Digital product catalogue / price list — shareable link + WhatsApp broadcast | Self-service |
| 3.57 | Promotional bundle pricing ("any 3 for ₹299") | Advanced Promotions |
| 3.58 | Loyalty multiplier events + customer-segment-specific promotions | Advanced Promotions |
| 3.59 | Flash sale pricing + spend-and-save thresholds | Advanced Promotions |
| 3.60 | Loyalty points deducted on return + expiry WhatsApp notifications | Loyalty |

---

## Implementation Notes

### General
- **Cost price is a keystone.** Domains covering P&L, COGS, inventory valuation, and margin-based reporting all unlock the moment `cost_price_cents` is added to the Product model. Do it in Chunk 1.
- **CRM + Khata ship together.** Khata is built on top of the Customer model. Design the Customer model with Khata in mind from the start — don't retrofit credit tracking later.
- **Returns depend on CRM.** A return should optionally be tied to a customer record (for Khata credit, for history). Build returns after CRM.
- **Tax engine before discount engine.** Tax-inclusive pricing interacts with how discounts are applied. The country-aware tax engine must be in place before the discount schema is finalised.
- **Barcode field → barcode generation → POS scanning.** These are sequential. The schema field comes first (Chunk 1), label printing second (Chunk 2), POS scan UX third.

### India
- **GST and cost price both belong in Chunk 1.** GST touches invoices, transactions, and product schema simultaneously. Neither can wait.
- **UPI is Chunk 1, not Chunk 2.** In India, a POS without UPI support is a dealbreaker regardless of everything else it offers.
- **Indian address + GST state code determines CGST/IGST split.** The state of the seller vs. the state of the buyer determines whether a transaction is intra-state (CGST + SGST) or inter-state (IGST). Design the address and tax domains together.
- **WhatsApp receipts require CRM.** Receipts go to a customer's phone number — CRM must exist first.

### Indonesia
- **QRIS is Chunk 1.** Like UPI in India, QRIS is the dominant payment rail. No Indonesian retailer will adopt software that doesn't support it natively.
- **NPWP field is a prerequisite for Faktur Pajak.** The tax invoice format references the seller's and buyer's NPWP. Add the field before building the invoice format.
- **Indonesia has 3 timezones.** A tenant with shops across Java and Bali needs per-shop timezone. The i18n Foundation timezone work (Domain 31) must land before Indonesian tenants can have accurate shift reports.
- **e-Faktur (DJP Online) is a Chunk 3 external integration** — it requires a registered integration with Indonesia's tax authority and should not block the core PPN compliance work in Chunk 1.

### Canada
- **Province field on Shop is the single most critical Canadian schema change.** Without it, the entire provincial tax system cannot function. It must land in Chunk 1 before any Canadian tenant goes live.
- **GST/HST registration number on receipts is a legal requirement** in Canada for transactions over $30 CAD. This is not optional — ship it with Chunk 1.
- **CASL gates WhatsApp marketing in Canada.** The WhatsApp promotional broadcast feature (Domain 25, Chunk 3) requires explicit CASL opt-in from each customer before a Canadian tenant can use it. Build opt-in management before enabling broadcasts for Canadian tenants.
- **Quebec is a special case.** French language requirement (Charter of the French Language) and QST registration both apply only to Quebec tenants. Design the province field to carry this context through to both tax and localisation logic.
- **Canadian tax-exempt categories need province context.** Basic groceries are GST-exempt nationally, but PST exemption rules differ per province. The tax engine must evaluate both the product category and the shop's province together.

---

## Competitive Edge Summary

### India
| Edge | Why it matters | Who doesn't have it |
|---|---|---|
| **Offline-first POS** | Internet is unreliable in Tier 2/3 cities and markets | Vyapar (web), KhataBook (online-only), most SaaS tools |
| **Khata built into POS** | Every Indian retailer runs a credit book — owning this natively vs. a separate app is a durable moat | No POS does this; KhataBook/OkCredit are standalone and don't know what the customer bought |
| **WhatsApp receipts & reminders** | WhatsApp is the primary communication channel for Indian retailers and their customers | Nobody does this natively in a retail POS |
| **GST done right and simply** | Compliance is mandatory but every competitor makes it painful | Marg/Busy are overly complex; Vyapar is accounting-first and not POS-native |
| **UPI as first-class tender** | UPI is dominant in Indian retail — must feel native, not like an afterthought | Most POS treat it as "other" or require a separate app |
| **Multi-location from day 1** | Retail chains with 2–3 shops need this from the start | Most Indian retail software is single-store |
| **Clean modern UX** | #1 pain point cited by users of every Indian retail tool | Tally, Marg, Busy, Gofrugal all have complex, dated interfaces |
| **Barcode label printing** | Indian domestic goods rarely have pre-printed barcodes | Almost no Indian retail software generates and prints labels |

### Indonesia
| Edge | Why it matters | Who doesn't have it |
|---|---|---|
| **QRIS natively supported** | Bank Indonesia mandated — every retailer needs it; most foreign POS tools treat it as an afterthought | Most international POS tools don't support QRIS at all |
| **Offline-first in a mobile-first market** | Connectivity is inconsistent outside major cities; staff use Android devices | Most Indonesian retail tools are cloud-only web apps |
| **Tokopedia / Shopee / TikTok Shop sync** | Most Indonesian retailers sell on 2–3 platforms simultaneously; stock sync is a top pain point | No retail POS currently offers a unified multi-marketplace sync |
| **PPN compliance built in** | DJP Online e-Faktur is mandatory for PKP businesses; most small business tools don't handle it | Indonesian-market POS tools are scarce; most retailers use manual spreadsheets |
| **Multi-timezone support** | A business with shops in Jakarta (WIB) and Bali (WITA) needs correct per-shop reporting | Most tools assume a single timezone |

### Canada
| Edge | Why it matters | Who doesn't have it |
|---|---|---|
| **Province-aware tax from day 1** | Getting Canadian tax wrong exposes merchants to CRA risk; it's genuinely complex and most tools handle it poorly | Many international POS tools apply a flat rate rather than proper GST/HST/PST/QST |
| **Interac Debit as first-class tender** | Dominant Canadian payment rail — most Canadians pay with Interac daily | Many non-Canadian POS tools treat it as generic "debit" with no separate reporting |
| **French language POS (Quebec)** | Legally required under Quebec's Charter of the French Language for workplace software | Most international retail tools are English-only |
| **CASL-compliant marketing** | Canadian retailers need opt-in tools built in — not an afterthought — to avoid heavy CASL fines | Most marketing features in POS tools have no opt-in management |
| **QuickBooks / Wave integration** | Canadian SMBs are deeply embedded in these tools; their accountants expect exports to work | Most retail POS tools in Canada offer only generic CSV exports |

### Cross-market
| Edge | Why it matters across all three markets |
|---|---|
| **Single platform, three markets** | A retailer operating in India and Canada doesn't want two different systems — one product that handles both is a strong retention moat |
| **Proper i18n from the foundation** | Competitors who bolt on translations after the fact produce inconsistent UIs; building i18n first means every new language is a clean addition |
| **WhatsApp as a communication layer** | WhatsApp is dominant in India and Indonesia and well-used in Canada's South Asian and Southeast Asian immigrant communities — one integration serves all three |
