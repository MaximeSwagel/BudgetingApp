# Requirements: BudgetingApp

**Defined:** 2026-06-23
**Core Value:** See all spending across all bank accounts and currencies in one place, automatically categorized and mapped to a personal budget structure

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Data Import

- [ ] **IMPT-01**: User can upload CSV files exported from Revolut (French format)
- [ ] **IMPT-02**: User can upload CSV files exported from Revolut (English format)
- [ ] **IMPT-03**: User can upload CSV files exported from Crédit Agricole (semicolon-delimited French format with multiline descriptions)
- [ ] **IMPT-04**: App auto-detects bank and language from uploaded CSV headers
- [ ] **IMPT-05**: App filters out incomplete/pending transactions (only imports completed ones)
- [ ] **IMPT-06**: App detects and flags potential duplicate transactions from overlapping imports

### Categorization

- [ ] **CATG-01**: App auto-categorizes transactions using OpenAI API into two-level hierarchy (General Category + Precise Description)
- [ ] **CATG-02**: User can manually correct the category assigned to any transaction
- [ ] **CATG-03**: App uses existing category set: Home Expenses, Household Expenses, Insurance/Tax/Bank Fees, Health Care, Discretionary (with subcategories)
- [ ] **CATG-04**: User can add, edit, or rename categories

### Currency

- [ ] **CURR-01**: App converts all transaction amounts to a configurable base currency (default ILS)
- [ ] **CURR-02**: App stores both original amount/currency and converted amount with exchange rate used
- [ ] **CURR-03**: User can set or change the base display currency

### Transaction View

- [ ] **TRNV-01**: User can view all imported transactions in a chronological list
- [ ] **TRNV-02**: User can filter transactions by date range, bank, currency, and category
- [ ] **TRNV-03**: User can see original amount, currency, converted amount, category, and bank for each transaction

### Budget View

- [ ] **BUDG-01**: User can view a budget summary matching the Excel layout — monthly columns with category group rows
- [ ] **BUDG-02**: Budget view shows income section (manual entry), savings section, and expense categories
- [ ] **BUDG-03**: Budget view calculates monthly totals, annual totals, and percentage of net income per category
- [ ] **BUDG-04**: Budget view groups expenses by category group (Home, Household, Insurance/Tax/Fees, Health Care, Discretionary)
- [ ] **BUDG-05**: User can set monthly budget targets per category for comparison against actual spending

### Storage

- [ ] **STOR-01**: All transaction data is stored persistently in PostgreSQL
- [ ] **STOR-02**: App tracks which import batch each transaction came from

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Savings & Goals

- **GOAL-01**: User can set savings goals with target amounts and timelines
- **GOAL-02**: User can track progress toward savings goals over time
- **GOAL-03**: App suggests monthly savings allocation based on income and expenses

### Investment Tracking

- **INVT-01**: User can track investment accounts and balances
- **INVT-02**: Unallocated savings automatically route to investment tracking

### Smart Features

- **SMRT-01**: App learns from manual corrections to improve future categorization
- **SMRT-02**: App creates recurring transaction rules from user corrections
- **SMRT-03**: App detects inter-account transfers and marks them as non-expense

### Bank Integration

- **BANK-01**: User can connect Revolut account directly via API
- **BANK-02**: User can connect CA account directly via API

### Authentication

- **AUTH-01**: User can log in with email and password
- **AUTH-02**: Multi-user support with separate data

## Out of Scope

| Feature | Reason |
|---------|--------|
| Real-time bank API connections | Complex auth flows, CSV upload works now — defer to v2 |
| Mobile app | Web-first, mobile later |
| Real-time currency conversion rates | Manual or periodic rate updates sufficient for monthly budgeting |
| Receipt scanning / OCR | High complexity, not core to budget tracking |
| Tax filing / export | Out of domain for personal budgeting MVP |
| Multi-user / authentication | Single user for MVP, no login needed |
| Investment portfolio analysis | Future scope after basic budgeting works |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| IMPT-01 | — | Pending |
| IMPT-02 | — | Pending |
| IMPT-03 | — | Pending |
| IMPT-04 | — | Pending |
| IMPT-05 | — | Pending |
| IMPT-06 | — | Pending |
| CATG-01 | — | Pending |
| CATG-02 | — | Pending |
| CATG-03 | — | Pending |
| CATG-04 | — | Pending |
| CURR-01 | — | Pending |
| CURR-02 | — | Pending |
| CURR-03 | — | Pending |
| TRNV-01 | — | Pending |
| TRNV-02 | — | Pending |
| TRNV-03 | — | Pending |
| BUDG-01 | — | Pending |
| BUDG-02 | — | Pending |
| BUDG-03 | — | Pending |
| BUDG-04 | — | Pending |
| BUDG-05 | — | Pending |
| STOR-01 | — | Pending |
| STOR-02 | — | Pending |

**Coverage:**
- v1 requirements: 23 total
- Mapped to phases: 0
- Unmapped: 23 ⚠️

---
*Requirements defined: 2026-06-23*
*Last updated: 2026-06-23 after initial definition*
