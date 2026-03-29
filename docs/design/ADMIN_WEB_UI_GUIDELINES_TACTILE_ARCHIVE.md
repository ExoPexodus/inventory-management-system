# Admin Web UI Guidelines: The Tactile Archive

This document defines the required visual and interaction rules for the admin web UI. It translates the "Digital Vellum" direction into practical implementation guidance for designers and engineers.

## 1) Design Intent

Build a cashier-fast interface with editorial character.

- The UI should feel like layered paper, not boxed software.
- Favor tonal layering over hard separators.
- Use intentional asymmetry in composition to avoid template-like layouts.
- Preserve speed and clarity for high-frequency cashier/admin tasks.

## 2) Core Principles

### 2.1 The Digital Vellum

- Think in surfaces and stacks: base sheet, work surface, active sheet, overlay.
- Use offsets and uneven panel weights for curated rhythm.
- Keep visual noise low; hierarchy should come from type, space, and tone.

### 2.2 No-Line Rule

- Do not use 1px borders to divide major sections.
- Define boundaries using background token shifts.
- If an accessibility boundary is needed, use a whisper-level outline only (see Section 5).

### 2.3 Luxury of Space

- Prefer breathing room over density.
- Increase spacing before adding visual separators.
- Avoid crowded controls, especially in list-heavy workflows.

## 3) Color and Surface Tokens

Use the following palette consistently.

### 3.1 Surface hierarchy

- `surface`: `#fbf9f4` (base canvas)
- `surface-container`: `#f0eee9` (secondary workspace)
- `surface-container-low`: `#f5f3ee` (general content background)
- `surface-container-lowest`: `#ffffff` (interactive cards/active input areas)
- `surface-bright`: overlay base for priority sheets
- `surface-tint`: `#455f88` at 5% opacity over bright surfaces for coated-paper sheen

### 3.2 Brand and semantic

- `primary`: `#06274d`
- `primary_container`: `#223d64`
- `secondary_container`: `#fed65b`
- `on_secondary_container`: `#745c00`
- `tertiary_fixed` (low-stock marker): `#ffdf99`
- `error_container` (out-of-stock marker): `#ffdad6`

### 3.3 Text color rules

- Never use pure black (`#000000`).
- Primary text: `on_surface` `#1b1c19`
- Secondary text: `on_surface_variant` `#43474c`

## 4) Typography System

### 4.1 Font roles

- Display/headlines: `Manrope`
- Body/labels/data UI: `Public Sans`

### 4.2 Hierarchy rules

- Use size and color contrast first; reserve bold weight for true emphasis.
- Keep dense data labels legible in fast-scanning contexts (stock/SKU/price fields).
- Right-align all currency and ledger-like numeric fields.

### 4.3 Suggested type usage

- Major totals and page-level highlights: display scale (`display-md` equivalent)
- Section headers: strong but not oversized editorial headers
- Table/cell labels: label scale (`label-md` equivalent) with high readability

## 5) Elevation and Depth

Use ambient depth, not heavy drop shadows.

- Lift elements by placing lighter surfaces on dimmer surfaces.
- Shadow only for floating, high-priority affordances.
- Preferred ambient shadow: blur `24px`, y-offset `8px`, color `on_surface` at `4%` opacity.
- Input ghost boundary: `outline-variant` `#c4c6cd` at `20%` opacity.

## 6) Components

### 6.1 Buttons

- **Primary ("Ink Well")**
  - Background: 45-degree gradient from `primary` to `primary_container`
  - Text: `on_primary` `#ffffff`
  - Radius: `lg` (`0.5rem`)
- **Secondary ("Pencil")**
  - Background: `secondary_container`
  - Text: `on_secondary_container`
  - Radius: `lg` (`0.5rem`)
- **Sizing**
  - Minimum tap target height in POS flows: `4rem`

### 6.2 Inputs ("Ledger")

- No boxed fields for standard text entry.
- Use bottom-only boundary with `outline-variant` at `40%` opacity.
- On focus:
  - Shift field background toward `surface-container-lowest`
  - Keep a subtle primary ink accent for focus/caret clarity.

### 6.3 Inventory cards and lists

- No divider lines between list items.
- Separate rows using whitespace (`spacing-4` rhythm).
- Stock status markers:
  - Low stock: small circular dot in `tertiary_fixed`
  - Out of stock: small circular dot in `error_container`

### 6.4 POS/cart drawer behavior

- Use glass treatment:
  - Surface at `85%` opacity
  - `backdrop-filter: blur(20px)`
- Preserve contextual visibility of inventory beneath overlays.

## 7) Layout, Rhythm, and Spacing

All layout decisions should align to a 1.4rem rhythm.

- `spacing-2`: `0.7rem` (inner element rhythm)
- `spacing-4`: `1.4rem` (core vertical rhythm)
- `spacing-6`: `2rem` (default major section gap)
- `spacing-8`: `2.75rem` (page gutters/thumb-safe edges)

Implementation rules:

- Default major section separation: `spacing-6`.
- Card/content internals: `spacing-2` or multiples.
- Avoid visual crowding; increase spacing before adding new UI chrome.

## 8) Composition Rules

- Break perfect symmetry intentionally in key screens (checkout, ledger, analytics).
- Avoid centered "single card in a sea of whitespace" unless the task is singular.
- Keep one dominant region and one supporting region per viewport where possible.
- Use tonal contrast to create focal points, not line-based boxes.

## 9) Accessibility and UX Guardrails

- Maintain WCAG-compliant contrast when applying subtle surfaces.
- Ensure all touch targets are comfortably tappable in high-speed contexts.
- Do not encode meaning by color alone; pair dots/badges with text labels where needed.
- Keep keyboard focus states visible and consistent, even when using minimal outlines.

## 10) Do and Don't Checklist

### Do

- Use tonal layers (`surface*`) to define structure.
- Keep numeric values right-aligned.
- Apply `secondary` yellow sparingly for warnings/special signals.
- Preserve calm editorial hierarchy with clear type contrast.

### Don't

- Don't use pure black text.
- Don't apply fully rounded "pill everything" corners.
- Don't separate sections with hard 1px borders.
- Don't compress density to fit more data at the cost of scan speed.

## 11) QA Review Checklist (Per Screen)

Before shipping a UI screen, verify:

- [ ] No major sectioning relies on hard border lines.
- [ ] Surface layering follows base -> workspace -> interactive -> overlay logic.
- [ ] Typography uses Manrope/Public Sans roles correctly.
- [ ] Primary actions use the ink gradient treatment.
- [ ] Inputs follow ledger style with minimal boundary treatment.
- [ ] List/table rows rely on spacing, not divider clutter.
- [ ] Numeric ledger fields are right-aligned.
- [ ] Visual density feels premium and uncrowded at cashier pace.

## 12) Implementation Note for Existing Code

When implementing in `apps/admin-web`:

- Keep shared design primitives in one place (tokens + reusable components).
- Prefer updating shared primitives over per-page one-off styles.
- If a page needs exception styling, document the exception in the page component and keep it minimal.

