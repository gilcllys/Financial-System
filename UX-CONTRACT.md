# UX Contract

## Product context

- Audience: people tracking personal, credit-card, and shared household spending.
- Primary jobs: record income and expenses, understand card invoices, review obligations, and reconcile shared amounts.
- Target market(s): Brazil is evidenced by pt-BR copy and BRL formatting; no other market is asserted.
- Active locales: pt-BR.
- Language/content register: concise, neutral, correctly accented Portuguese. Native review is by the product owner.
- Timezone/calendar policy: business dates use the user's local calendar; invoice closing dates move from weekend to the prior Friday.
- Accessibility target: WCAG 2.2 AA.

## Business-context sources

| Domain / scope | Authoritative source | Source type | Reviewed date |
|---|---|---|---|
| Invoice, installment, income, and shared-cost calculations | `docs/financial-rules.md` and user-approved decisions in the Codex conversation | Product decision record | 2026-11-02 |
| Original user findings | `Melhorias_Controle_Financeiro.pdf` supplied in the conversation | User-provided report | 2026-11-02 |
| Data lifecycle and compatibility | Existing Django models and API serializers | Application API | 2026-11-02 |
| Deletion and retention | Existing model/API behavior; destructive actions require a clear confirmation | Application behavior | 2026-11-02 |

## Visual contract

- Project `DESIGN.md`: root `DESIGN.md`.
- Token ownership model: `DESIGN.md` mirrors existing runtime tokens.
- Runtime design-system/token source: `frontend/src/styles/_tokens.scss`.
- Mapping/export/adapters: existing SCSS variables.
- Token drift gate: review changed token values against SCSS variables.
- Supported themes: light.
- Design-context owner/review policy: product owner approves new business semantics; preserve current visual identity.

## Canonical UI Map

| Capability | Canonical owner | Source of truth | Allowed variants | Verification |
|---|---|---|---|---|
| Table Selection | feature table | API query and selection state | page / all-results | keyboard + E2E |
| Select/Listbox | native `<select>` controls | Existing Angular form controls | native select; authored combobox where search is needed | keyboard + native popup |
| Date | native `<input type="date">` | Browser-local calendar control | native date input | locale + keyboard + E2E |
| Form | `ExpenseFormComponent` | Django serializer and `docs/financial-rules.md` | create / edit / shared | validation E2E |
| Scrollbar | global SCSS | `frontend/src/styles.scss` | shared scrollbar theme | computed style |
| Toast | `ToastService` and shared toast component | `frontend/src/app/core/services/toast.service.ts` | success / warning / info / error | live-region test |
| CRUD | feature components and shared confirmation dialog | operation-specific API behavior | return / stay | full-flow E2E |

## Component behavior

| Component | Default | Hover | Focus | Active | Disabled | Busy | Error |
|---|---|---|---|---|---|---|---|
| Button | existing primary/secondary | existing palette | visible ring | pressed | muted and non-actionable | stable label/size | inline/toast feedback |
| Input | labeled, existing surface | border accent | visible ring | n/a | native disabled | stable geometry | inline field message |
| Search | committed query after debounce | border accent | visible ring | n/a | n/a | stale requests suppressed | preserve query and explain failure |
| Table/list | semantic labels and headers | row highlight | keyboard reachable | selected state labeled | n/a | explicit loading state | retry or preserve filters |

## Dataset navigation

- Admin tables: not applicable.
- Exploratory lists: History, card invoices, installments.
- URL state: feature filter state should be committed and shareable where currently supported; do not put secrets in URLs.
- Page size: use API maximum and display result count/range.
- Empty/no-results/error/loading: distinguish empty data from no matches; show an action or retry where useful.
- Selection scope: bulk category changes display selected count and confirm the result.

## Flow ledger

| Operation | Trigger | Pending | Success destination | Success feedback | Failure recovery | Focus outcome | Source ref |
|---|---|---|---|---|---|---|---|
| Create expense | Save | disable duplicate submission | remain ready for next entry or return to list | toast | preserve entered values | focus next amount after save-and-add | expense form |
| Edit expense | Save | disable submit | history/list | toast | keep values | return to initiating row |
| Delete expense/group | explicit delete | app-owned confirmation then pending | same list | toast | retain record and show error | restore to initiating control | user PDF |
| Search/filter | apply or debounce | suppress stale results | same route | updated count | preserve filters | retain focus | history |

## Navigation and responsive behavior

- Route document title policy: route heading should identify the current page.
- Route error / 403 page behavior: show an explanatory state and preserve a safe return path.
- Breadcrumb/tab/route-state policy: retain filter context when navigating to an item and back.
- Sidebar/drawer: use the existing responsive navigation and keyboard controls.
- Responsive table strategy: retain semantic columns and allow horizontal overflow where necessary.
- Truncation/full-value access: labels remain available to assistive technology; don't truncate financial amounts.
- Focus restoration: dialogs restore focus to the trigger; route navigation focuses the page heading.

## Overlays and feedback

- Dialog primitive: shared app-owned alert dialog; no browser-native confirm/alert.
- Destructive confirmation: identify record and impact; cancel is the safe default.
- Toast placement/duration: shared toast service; errors remain long enough to read.
- Layer order: dialog > drawer > popover > toast.

## Async and resilience

- Mutation default: pessimistic for destructive operations.
- Idempotency: prevent duplicate submit while a request is pending; recurring generation is idempotent by template and month.
- Offline/read-stale/write: preserve form values on failure and allow retry.
- Stale-request handling: latest committed filters own the displayed results.
- Dialog/form recovery: failed mutations keep context available.

## Validation

- Schema/validation layer: Django serializers and Angular reactive forms.
- Trigger timing: inline errors after submit or field touch.
- Error summary: field-specific errors plus API message through shared toast.
- Duplicate-submit prevention: disable submit during request.

## Permission and clipboard

- Permission UI strategy: hide unavailable actions where possible; server remains authoritative.
- Clipboard: announce copy outcome without exposing sensitive values.

## Migration status

- Migration ledger: `docs/financial-rules.md` and Django migrations.
- Current risk-prioritized slices: financial correctness first, then history and accessibility behaviors.
- Rollout: additive migrations and backwards-compatible endpoints.

## Verification

- Required commands: Django tests, Angular unit tests, Angular production build, migration checks.
- Browser/device/locale/theme: desktop and responsive viewport, pt-BR, light theme.
- Accessibility: keyboard focus and automated axe scan on representative CRUD screens.
- Native-language/domain review: product owner review of Portuguese labels and financial formulas.
