---
version: 1
name: Financial App
description: Controle financeiro pessoal com foco em leitura rápida de faturas, gastos e compromissos compartilhados.
colors:
  primary: "#0052ff"
  primary-active: "#003ecc"
  danger: "#cf202f"
  success: "#05b169"
  background: "#ffffff"
  surface: "#f7f7f7"
  surface-strong: "#eef0f3"
  text: "#0a0b0d"
  text-muted: "#5b616e"
  border: "#dee1e6"
typography:
  sans:
    fontFamily: "Inter, -apple-system, system-ui, sans-serif"
  mono:
    fontFamily: "JetBrains Mono, Courier New, monospace"
rounded:
  sm: "8px"
  md: "12px"
  lg: "16px"
spacing:
  base: "16px"
  page-max: "72rem"
components:
  button: {}
  card: {}
  dialog: {}
  table: {}
---

# Financial App Design System

## Overview

### Creative North Star

A clear monthly ledger: familiar, compact financial software where the amount and its period are always easy to identify. Preserve the existing blue accent and white canvas; hierarchy comes from spacing, typography, and restrained semantic color.

### Product context and register

- **Audience and primary job:** people tracking personal expenses, credit card invoices, and shared household spending.
- **Target market(s) and evidence:** Brazilian Portuguese UI and BRL formatting in the product; this does not establish additional markets.
- **Locale(s) and language policy:** pt-BR for interface copy, dates, and currency; use accents and sentence case.
- **Usage scene:** frequent desktop use with dense tables and monthly summaries; responsive layout supports smaller screens.
- **Register:** practical personal finance product.
- **Memorable signature:** pair every card amount with its invoice cycle and separate gross bank charges from the user's personal cost.
- **Restraint:** keep charts subordinate to totals; use color as a supplement to labels.
- **Anti-references:** avoid neon dashboards, emoji-only status indicators, and color-only financial meaning.
- **Token ownership/runtime mapping:** this file mirrors [frontend/src/styles/_tokens.scss](/home/gilcllys/Documentos/projetos/financial_app/frontend/src/styles/_tokens.scss); SCSS remains canonical.

## Colors

Blue `#0052ff` is the primary action and focus accent; red `#cf202f` and green `#05b169` communicate negative and positive values only when accompanied by text or a sign. White and soft gray form the canvas and cards, with `#dee1e6` borders. Maintain visible focus rings and do not rely on color alone for chart or status meaning. The current runtime supports the light theme.

## Typography

Use Inter for interface text and JetBrains Mono for aligned numeric values. Use pt-BR accents and sentence case. Currency is formatted in BRL; positive and negative values retain explicit signs where direction matters.

## Layout

Use the existing 240px desktop sidebar, 64px navigation geometry, 16px base spacing, and responsive feature layouts. Keep dense lists readable and reserve full-width regions for summaries and tables. Preserve existing route-specific structure unless a task requires a behavior change.

## Elevation & Depth

Use white cards, subtle gray surfaces, hairline borders, and existing soft shadows. Reserve overlays for dialogs and menus; avoid decorative blur.

## Shapes

Use the existing 8px, 12px, and 16px radius tokens for controls, cards, and larger panels. Keep table geometry square enough for clear row scanning.

## Components

### Foundational visual states

Interactive controls need visible hover, active, disabled, busy, error, and `:focus-visible` states. Async work uses the shared spinner and toast service. Empty states explain the next useful action.

### Buttons and actions

Use the existing primary blue for the main action, secondary styling for supporting actions, and a clearly labeled destructive treatment for deletion. Keep pending geometry stable.

### Navigation and data display

Use semantic labels for sidebar items, status badges with text, BRL values with explicit signs where needed, and accessible text summaries for charts. Tables retain headers and readable row labels.

### Forms and overlays

Use visible labels, inline field errors, and clear keyboard order. Destructive confirmation uses an app-owned accessible dialog. Toasts provide operation feedback.

### Iconography

Use the existing inline SVG line icons; retain adjacent text labels for important actions and statuses.

### Motion

Keep transitions short and state-related. Respect reduced-motion preferences.

### Content and data visualization

Use concise pt-BR language, BRL values, and explicit period names. Distinguish invoice-cycle analytics from purchase-month analytics. Pair chart colors with labels and textual summaries.

## Do's and Don'ts

- **Do:** show the period and meaning beside financial totals.
- **Do:** use stable category keys and one invoice-cycle rule.
- **Don't:** show a generic “Saldo” label for a value that mixes different financial concepts.
- **Don't:** communicate status only through color or emoji.
