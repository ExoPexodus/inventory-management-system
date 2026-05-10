# Autonomous Completion Roadmap

**Date:** 2026-05-10
**Mode:** Autonomous (decisions made at my discretion; stop only for blockers)
**Workflow:** Full brainstorm → spec → plan → implement per feature

---

## Locked design decisions

### RMA flow (Phase 3-tier)
- **Refund types:** all three — refund-only, return+refund, exchange
- **Inventory restock:** merchant decides per approval; tenant-level default setting; clear pathway when no restock
- **Return shipping:** configurable per request (Shiprocket return-AWB optional)
- **POS + Ecommerce coexistence:** unified RMA inbox wraps both flows
- **Refund execution:** auto-execute on approval (Stripe/Razorpay reverse charge)

### Multi-carrier
- Shiprocket only (already shipped) — polish + add "More carriers coming soon" page
- Q-tier scope, not a multi-day backend effort

### Other locked decisions (from earlier in this session)
- L5 command palette: search + actions both in scope
- Advanced RBAC: full custom roles via UI
- Transfer orders: with approval workflow
- Magic-link auth: coexists with OTP
- Platform-side plan-feature UI: in scope, includes fixing the three tenant-creation gaps

### Tenant-creation gaps (folded into platform-side feature)
1. Storage mode never forwarded by `services/platform/app/services/tenant_provision.py`
2. No `TenantLicenseCache` seeded at provision time
3. No initial subscription created on platform side

---

## Execution order

Smallest → largest, building momentum and minimising risk.

### Tier 0 — Quick wins (½ day each)
1. **Q6** — Type-ahead supplier search on Purchase Orders
2. **Q8** — Inline shop creation modal (replaces `/shops/new` page)
3. **Multi-carrier polish** — Shiprocket flow polish + "More carriers coming soon" placeholder

### Tier 1 — Small (1-2 days each)
4. **Q5** — Date-range picker on Orders + E-comm Orders
5. **Q4** — Inventory journal filters (date, shop, product)
6. **Q7** — Bulk approve reconciliations
7. **M1** — Integrations sub-tabs (Webhooks / API Tokens / Connected Stores)
8. **M2** — Merge Analytics + Reports → unified "Insights" page

### Tier 2 — Medium UX (3-7 days each)
9. **M3** — Standardise create UI pattern across list pages
10. **M4** — Row-selection + bulk actions toolbar
11. **L5** — Cmd+K command palette (search + actions)

### Tier 3 — Backend features (5-10 days each)
12. **Magic-link auth** — alternative login alongside OTP
13. **Transfer orders** — cross-shop inventory moves with approval
14. **Advanced RBAC** — custom roles via UI
15. **Platform-side plan-feature UI** — plans/limits/overrides + tenant gap fixes
16. **RMA flow** — full unified return-merchandise-authorisation system

---

## Per-feature workflow

Each feature follows the established pattern:
1. Brainstorm — explore context, design (autonomous decisions documented in spec)
2. Spec doc → `docs/superpowers/specs/`
3. Plan doc → `docs/superpowers/plans/`
4. Implement via subagent-driven development
5. Backend tests + frontend rebuild + push
6. Continue to next feature

## Stop conditions

- Genuine blocker (API doesn't exist, design needs human judgment, breaking change risk)
- Request from user

Otherwise, continuous execution.

---

## Progress

Updated as features ship.

| # | Feature | Status |
|---|---|---|
| 1 | Q6 — PO supplier search | ✅ shipped |
| 2 | Q8 — Inline shop creation | ✅ shipped |
| 3 | Multi-carrier polish | ✅ shipped |
| 4 | Q5 — Date-range picker | ✅ shipped |
| 5 | Q4 — Inventory filters | ✅ shipped |
| 6 | Q7 — Bulk reconciliation approve | ✅ shipped |
| 7 | M1 — Integrations sub-tabs | ✅ already in place (no-op) |
| 8 | M2 — Insights merge | ✅ shipped |
| 9 | M3 — Create UI standardisation | ✅ shipped (scoped to primitive + Suppliers exemplar) |
| 10 | M4 — Bulk actions toolbar | ✅ shipped (scoped to primitive + Products archive) |
| 11 | L5 — Command palette | ✅ shipped |
| 12 | Magic-link auth | _pending_ |
| 13 | Transfer orders | _pending_ |
| 14 | Advanced RBAC | _pending_ |
| 15 | Platform-side plan-feature UI | _pending_ |
| 16 | RMA flow | _pending_ |
