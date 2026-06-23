# Feature Research

**Domain:** Personal budgeting / multi-currency expense tracking
**Researched:** 2026-06-23
**Confidence:** MEDIUM (cross-verified across multiple industry sources, competitor documentation, and user forums)

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete or broken.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| CSV import with format auto-detection | Core data ingestion method; users bring bank exports | MEDIUM | Must handle Revolut FR/EN + Credit Agricole semicolon-delimited formats. Column mapping, delimiter detection, date format handling (DD/MM/YYYY vs MM/DD/YYYY). Save import config per bank so repeat imports skip setup. |
| Transaction list with chronological view | Users need to see what was imported and verify correctness | LOW | Scrollable list with date, description, amount, category, currency. Pagination or virtual scroll for large datasets. |
| Auto-categorization of transactions | Every modern budgeting app does this; manual-only categorization feels like 2010 | HIGH | OpenAI API for initial pass. Industry benchmark: 85-90% accuracy. Must handle merchant name normalization. Accuracy drops for ATM withdrawals, small merchants, peer-to-peer transfers. |
| Manual category correction / override | AI is never 100% accurate; users must be able to fix mistakes | LOW | Inline editing on transaction list. Single-click category reassignment. |
| Category-based budget summary view | The entire point of the app; this IS the core value proposition | MEDIUM | Must match the existing Excel layout: monthly columns (Jan-Dec), category groups (Home, Household, Insurance, Health, Discretionary), row totals, Annual Total column, % of Net Income column. |
| Multi-currency display with base currency conversion | User has accounts in ILS, EUR, USD, DKK; meaningless without conversion | MEDIUM | Store original currency + amount AND converted amount. Use exchange rate on transaction date for accuracy. Display both original and converted amounts. |
| Duplicate transaction detection | Users re-import overlapping date ranges constantly; double-counting destroys trust | MEDIUM | Match on date + amount + description combination. Flag potential duplicates for manual review rather than silently dropping. Critical for CSV-based workflows where no unique transaction ID exists. |
| Data persistence across sessions | Losing imported data is unacceptable | LOW | PostgreSQL storage. Every import persists permanently. No "session-only" state. |
| Filtering and search on transactions | Users need to find specific transactions or view subsets | LOW | Filter by date range, category, currency, bank/account. Text search on description. |
| Category management (add/edit/rename) | Budget categories must match user's mental model | LOW | Two-level hierarchy (General Category + Precise Description). Pre-populated with the defined categories but user-editable. |

### Differentiators (Competitive Advantage)

Features that set this product apart from YNAB, Monarch, Copilot, and spreadsheets. Not required for launch, but create genuine value.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Multi-bank CSV format support (Revolut FR, Revolut EN, Credit Agricole) | Most budgeting apps only support US/UK banks or require standardized formats. Supporting French banks and Revolut's locale-specific exports is a real differentiator for expats. | MEDIUM | Hardcoded parsers per bank format. Auto-detect which format based on header row. CA's semicolon delimiter and multiline descriptions need special handling. |
| AI categorization that learns from corrections | Copilot and Monarch do this with bank sync, but few CSV-import apps do. Corrections feed back so the same merchant is always categorized correctly on re-import. | HIGH | Store correction mappings (merchant description -> category). Apply learned rules before calling OpenAI on subsequent imports. Reduces API costs over time. |
| Excel-matching budget layout | Users migrating from Excel expect their familiar layout. Pixel-perfect match to their existing budget structure reduces adoption friction to near-zero. | MEDIUM | Monthly columns, category group subtotals, income/savings/expenses sections, NET row, % of net income. This is the existing user's mental model. |
| Batch import with smart merge | Import multiple CSVs at once (one per Revolut currency account + CA), deduplicate across files, and merge into a unified transaction set. | MEDIUM | Handles the common workflow: user downloads 4-5 CSVs at month end, uploads them all at once. Cross-file duplicate detection (same transaction appearing in different export date ranges). |
| Transaction-date exchange rates | Most multi-currency apps use current rates or daily snapshots. Using the rate from the actual transaction date provides historically accurate budget analysis. | MEDIUM | Requires historical exchange rate data. Can use free APIs (Frankfurter/ECB or similar) or store a rate table. Fallback to manual rate entry if API unavailable. |
| Export to CSV/Excel | Users want their data back. Proves the app doesn't hold data hostage. Also useful for tax purposes. | LOW | Export transactions and/or budget summary in CSV or Excel format. |
| Category rules engine | Beyond AI: let users define explicit rules ("any transaction containing 'CARREFOUR' = Groceries") that override AI categorization. | MEDIUM | Simple string-matching rules with priority over AI. Reduces API calls and ensures consistency. |
| Month-over-month comparison | Show spending trends across months for each category. "You spent 20% more on restaurants in March than February." | LOW | Computed from existing budget data. Simple percentage change calculation per category. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems for a personal single-user budgeting app.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Direct bank API connections (Plaid, open banking) | Eliminates manual CSV export step | Massive complexity: bank auth flows, token refresh, API costs ($0.30-$3/connection/month), regulatory compliance, breaks constantly. Most aggregators (Plaid, Tink) have limited EU/Israel support. Revolut and CA in France are poorly supported. | Stick with CSV import. Add a "quick import" flow that remembers per-bank settings to minimize friction. Re-evaluate in future milestone. |
| Real-time currency conversion rates | Feels more "accurate" | Unnecessary precision for personal budgeting. Exchange rates change by fractions of a percent intraday. Adds API dependency and cost for negligible benefit. | Use daily or weekly rate snapshots via Frankfurter/ECB API. Manual rate override for edge cases. Transaction-date rates are sufficient. |
| Multi-user / household support | Common feature in Monarch, YNAB | Requires authentication, authorization, data isolation, sharing permissions, conflict resolution. Enormous complexity for a personal project. Single-user solves the actual need. | Keep single-user. If needed later, add a second "view-only" role in a future milestone, not full multi-user. |
| Investment / portfolio tracking | "See everything in one place" | Completely different data model (holdings, prices, returns vs. transactions, categories, budgets). Doubles the scope. YNAB deliberately excludes this. | Out of scope. Use a dedicated tool for investments. Budget app tracks spending, not wealth. |
| Savings goals with gamification | Popular in consumer apps | Adds motivational UI complexity without solving the core problem (understanding spending). YNAB's approach works because of methodology, not badges. | The budget summary itself shows NET (income - expenses). That IS the savings visibility. |
| Push notifications / alerts | "Notify me when I overspend" | Requires mobile app or push infrastructure. Web-first app has limited notification capability. Customizable alerts add significant UX complexity. Users report alert fatigue as a top complaint. | Show clear visual indicators in the budget view when a category exceeds its budget. No push notifications for MVP. |
| Receipt scanning / OCR | "Snap a photo of receipts" | Unreliable OCR accuracy, mobile-first feature (camera access), requires separate ML pipeline, storage for images. Not needed when bank CSVs already contain the data. | CSV import captures all transaction data. Receipt scanning solves a problem this user doesn't have. |
| Recurring transaction prediction | Auto-detect subscriptions and predict future expenses | Complex pattern detection, high false positive rate, requires months of historical data. Over-engineered for a personal budgeting tool. | Let users manually mark transactions as recurring if needed in a future version. |
| Custom AI model fine-tuning | Train a model specifically on user's transactions | Fine-tuning OpenAI models is expensive and complex. Diminishing returns vs few-shot prompting with correction history. | Use few-shot examples from stored corrections in OpenAI prompts. Much cheaper and nearly as effective. |

## Feature Dependencies

```
CSV Import (parse + normalize)
    |-- requires --> Bank Format Parsers (Revolut FR, EN, CA)
    |-- requires --> Currency Detection (per transaction)

Auto-Categorization (OpenAI)
    |-- requires --> CSV Import (transactions must exist)
    |-- requires --> Category Hierarchy (categories must be defined)
    |-- enhanced-by --> Category Rules Engine (apply rules before AI)
    |-- enhanced-by --> Correction Learning (reduce API calls over time)

Manual Category Correction
    |-- requires --> Auto-Categorization (must have categories to correct)
    |-- enhances --> Correction Learning (corrections feed learning)

Currency Conversion
    |-- requires --> CSV Import (amounts + original currency)
    |-- requires --> Exchange Rate Data (manual or API)

Budget Summary View
    |-- requires --> CSV Import (transaction data)
    |-- requires --> Auto-Categorization (categorized transactions)
    |-- requires --> Currency Conversion (all amounts in base currency)
    |-- requires --> Category Hierarchy (budget structure)

Transaction List View
    |-- requires --> CSV Import (transaction data)

Duplicate Detection
    |-- requires --> CSV Import (runs during import)
    |-- requires --> Existing Transaction Data (compare against stored data)

Filtering and Search
    |-- requires --> Transaction List View

Export
    |-- requires --> Transaction Data + Budget Summary (data to export)

Month-over-Month Comparison
    |-- requires --> Budget Summary View (computed from budget data)
    |-- requires --> Multiple months of data
```

### Dependency Notes

- **Budget Summary View requires four upstream features:** This is the most dependent feature. It needs import, categorization, currency conversion, and category hierarchy all working before it can render. This means it comes last in the build order.
- **Auto-Categorization requires CSV Import:** You cannot categorize transactions that do not exist. Import must be built and tested first.
- **Currency Conversion is independent of categorization:** These can be built in parallel. Conversion happens at import time; categorization can happen after.
- **Duplicate Detection runs during import:** It is part of the import pipeline, not a standalone feature. Build it as part of the import flow.
- **Correction Learning enhances but does not block Auto-Categorization:** Can ship AI categorization without the learning loop, then add it.

## MVP Definition

### Launch With (v1)

Minimum viable product that replaces the manual Excel pipeline.

- [ ] **CSV Import with auto-format detection** -- The entry point for all data. Without this, nothing works. Support Revolut FR, Revolut EN, and Credit Agricole formats.
- [ ] **Transaction normalization and storage** -- Parse all formats into a unified schema with date, description, amount, original currency, bank source. Store in PostgreSQL.
- [ ] **Duplicate detection during import** -- Prevent double-counting on overlapping imports. Flag potential duplicates for user review.
- [ ] **Auto-categorization via OpenAI** -- Send transaction descriptions to OpenAI, receive category assignments from the defined hierarchy. 85-90% accuracy target.
- [ ] **Manual category correction** -- Let user fix wrong categories with inline editing. Store corrections.
- [ ] **Currency conversion to base currency** -- Convert all amounts to ILS using configurable exchange rates (manual entry for MVP, API later).
- [ ] **Chronological transaction list with filtering** -- View all transactions, filter by date/category/currency/bank.
- [ ] **Budget summary view matching Excel layout** -- Monthly columns, category groups, totals, % of net income, NET row. This is the core deliverable.
- [ ] **Category hierarchy management** -- Pre-populated with defined categories. Add/edit/rename support.

### Add After Validation (v1.x)

Features to add once core pipeline is working and the user is actively using the app.

- [ ] **Category rules engine** -- Add when the user notices the same merchants keep being miscategorized. Reduces OpenAI API costs.
- [ ] **Correction learning** -- Add when there are enough manual corrections to meaningfully improve accuracy. Store description-to-category mappings.
- [ ] **Transaction-date exchange rates via API** -- Add when manual rate entry becomes tedious. Integrate Frankfurter (ECB) free exchange rate API.
- [ ] **Batch multi-file import** -- Add when importing 4-5 CSVs individually feels slow. Upload all at once with cross-file dedup.
- [ ] **Export to CSV/Excel** -- Add when the user needs data portability or tax reporting.
- [ ] **Month-over-month spending comparison** -- Add once 2-3 months of data exist.

### Future Consideration (v2+)

Features to defer until the core product is stable and the user wants more.

- [ ] **Income tracking from payslips** -- Manual income entry works for MVP. Structured payslip parsing is a separate problem domain.
- [ ] **Savings goals** -- Only valuable after months of tracking. NET row already shows savings implicitly.
- [ ] **Multi-user/household** -- Only if the user's partner needs access. Authentication is a large scope increase.
- [ ] **Bank API integration** -- Only if CSV import becomes genuinely painful. EU open banking (PSD2) maturity for Revolut/CA needs evaluation.
- [ ] **Mobile app** -- Only if the user actively wants to check budgets on the go. Web-first is fine for monthly budget review.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| CSV import + format detection | HIGH | MEDIUM | P1 |
| Transaction storage + normalization | HIGH | LOW | P1 |
| Duplicate detection | HIGH | MEDIUM | P1 |
| Auto-categorization (OpenAI) | HIGH | HIGH | P1 |
| Manual category correction | HIGH | LOW | P1 |
| Currency conversion | HIGH | MEDIUM | P1 |
| Transaction list with filtering | MEDIUM | LOW | P1 |
| Budget summary view (Excel layout) | HIGH | MEDIUM | P1 |
| Category hierarchy management | MEDIUM | LOW | P1 |
| Category rules engine | MEDIUM | MEDIUM | P2 |
| Correction learning | MEDIUM | MEDIUM | P2 |
| Exchange rate API integration | MEDIUM | LOW | P2 |
| Batch multi-file import | MEDIUM | MEDIUM | P2 |
| Export to CSV/Excel | LOW | LOW | P2 |
| Month-over-month comparison | LOW | LOW | P2 |
| Income tracking (payslips) | LOW | HIGH | P3 |
| Savings goals | LOW | MEDIUM | P3 |
| Multi-user | LOW | HIGH | P3 |
| Bank API integration | MEDIUM | HIGH | P3 |
| Mobile app | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have for launch -- these are the features that replace the Excel pipeline
- P2: Should have, add when the core is working and validated
- P3: Nice to have, future milestone consideration

## Competitor Feature Analysis

| Feature | YNAB | Monarch Money | Copilot Money | Lunch Money | BudgetingApp (Ours) |
|---------|------|---------------|---------------|-------------|---------------------|
| Bank sync | Yes (Plaid) | Yes (Plaid) | Yes (Plaid) | Yes (Plaid) | No -- CSV import only |
| CSV import | Yes | Yes | No | Yes (with config saving) | Yes -- primary method |
| Multi-currency | Limited | Limited | No | Yes (native) | Yes -- core feature |
| AI categorization | No | Yes | Yes | No | Yes -- OpenAI powered |
| Manual categorization | Yes | Yes | Yes | Yes | Yes |
| Envelope/zero-based budgeting | Yes (core) | Optional | No | No | No -- category-based |
| Budget vs actual views | Yes | Yes | Yes | Yes | Yes -- Excel layout match |
| Net worth tracking | No | Yes | Yes | Yes | No (out of scope) |
| Investment tracking | No | Yes | Yes | No | No (out of scope) |
| Household/multi-user | Yes | Yes | No | No | No (single user) |
| Mobile app | Yes | Yes | Yes (Apple only) | No (web only) | No (web only) |
| Subscription tracking | No | Yes | Yes | No | No |
| Custom categories | Yes | Yes | Yes | Yes | Yes (two-level hierarchy) |
| Data export | Yes | Yes | Limited | Yes (API) | Yes (planned P2) |
| Free tier | No ($14.99/mo) | No ($9.99/mo) | No ($11.99/mo) | No ($8.33/mo) | Yes -- personal project |
| Self-hosted | No | No | No | No | Yes -- Docker Compose |

### Our Competitive Position

This app does not compete with YNAB or Monarch head-on. It occupies a niche:

1. **Multi-currency CSV import for EU/Israel banks** -- None of the major apps handle Revolut French exports or Credit Agricole well. Plaid support for these banks ranges from poor to nonexistent.
2. **AI categorization without bank sync** -- Most AI-powered apps require bank connections. This app applies AI to imported CSVs.
3. **Excel-familiar budget layout** -- Targets a user migrating from spreadsheets, not users new to budgeting. The layout IS the differentiator.
4. **Self-hosted, no subscription** -- Personal project with no recurring costs beyond OpenAI API usage.

The closest competitor is **Lunch Money** (web-only, multi-currency, CSV import, no bank sync required). However, Lunch Money lacks AI categorization and charges $8.33/month. This app is free, AI-powered, and specifically tuned for the user's bank formats and budget structure.

## Sources

- [Best budgeting apps for 2026 - Engadget](https://www.engadget.com/apps/best-budgeting-apps-120036303.html)
- [YNAB vs Copilot - MoneyPatrol](https://moneypatrol.com/moneytalk/budgeting/ynab-vs-copilot/)
- [Best Budget Management Apps Must-Have Features 2026 - MoneyPatrol](https://moneypatrol.com/moneytalk/budgeting/best-budget-management-apps-must-have-features-in-2026/)
- [Best budgeting apps 2026 - CNBC](https://www.cnbc.com/select/best-budgeting-apps/)
- [Best Budget Apps 2026 - NerdWallet](https://www.nerdwallet.com/finance/learn/best-budget-apps)
- [Multi-Currency Budget Tracker Guide - Pennies](https://getpennies.com/ultimate-multi-currency-budget-tracker/)
- [Multi-Currency Budgeting Apps 2026 - BorderlessBudget](https://borderlessbudget.com/compare/budgeting-apps-with-multi-currency)
- [Lunch Money Multi-Currency Features](https://lunchmoney.app/features/multicurrency/)
- [Lunch Money CSV Import](https://support.lunchmoney.app/guides/import-via-csv)
- [Actual Budget Duplicate Detection (GitHub issue)](https://github.com/actualbudget/actual/issues/4280)
- [Actual Budget Import Docs](https://actualbudget.org/docs/transactions/importing/)
- [HN: What frustrates you about personal finance apps?](https://news.ycombinator.com/item?id=46566663)
- [AI Budget Management Tools 2026 - Finny](https://getfinny.app/blog/ai-budget-management-tools-2026)
- [Top Personal Finance Apps with Custom Categories - Quicken](https://www.quicken.com/blog/top-personal-finance-apps-with-customizable-budget-categories/)
- [Why Users Abandon Financial Apps - Glance](https://thisisglance.com/learning-centre/why-do-users-abandon-financial-apps)

---
*Feature research for: Personal budgeting / multi-currency expense tracking*
*Researched: 2026-06-23*
