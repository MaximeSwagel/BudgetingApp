# BudgetingApp

## What This Is

A personal budgeting web app that ingests bank CSV exports from multiple banks (Revolut, Crédit Agricole) across multiple currencies (ILS, EUR, USD, DKK), auto-categorizes transactions using OpenAI, converts everything to a configurable base currency, and presents spending data in two views: raw chronological transactions and a structured budget view matching the user's existing Excel budget layout with monthly columns, category totals, and percentage breakdowns.

## Core Value

See all spending across all bank accounts and currencies in one place, automatically categorized and mapped to a personal budget structure — replacing the manual Excel pipeline.

## Context

The user currently manages budgeting through a manual Excel pipeline:
1. Export CSVs from Revolut (per-currency accounts: ILS, EUR, USD, DKK) and Crédit Agricole (French bank, EUR only)
2. Merge and clean CSVs — remove incomplete transactions, standardize columns
3. Send to GPT for categorization into General Category + Precise Description
4. Add currency conversion (fixed rates to ILS)
5. Merge into a Spendings.xlsx with all transactions
6. Roll up into a Budget spreadsheet with monthly columns showing income, savings, expenses by category, and NET

This process is incomplete, manual, and fragile. The app automates the entire pipeline.

**Bank export formats:**
- **Revolut (French):** CSV with columns: Type, Produit, Date de début, Date de fin, Description, Montant, Frais, Devise, État, Solde
- **Revolut (English):** CSV with columns: Type, Product, Started Date, Completed Date, Description, Amount, Fee, Currency, State, Balance
- **Crédit Agricole:** Semicolon-delimited CSV with columns: Date, Libellé, Débit euros, Crédit euros (multiline descriptions, French date format DD/MM/YYYY)

**Budget categories (two-level hierarchy):**
- **Home Expenses:** Rent, Utilities (Gas/Electric/Water), Internet/TV
- **Household Expenses:** Groceries, ATM Withdrawals, Clothing, Furniture & Equipment, Laundry & Dry Cleaning, Cell Phone
- **Insurance/Tax/Bank Fees:** Renters Insurance, Other Insurance, Income Tax, Bank Fees
- **Health Care:** Health Insurance, Dental Insurance, Doctor & Dentist
- **Discretionary:** Restaurants & Coffee Shops, Classes, Subscriptions, Concerts & Shows, Gym/Sports, Travel/Vacation

**Budget structure (Excel layout):**
- Currency: configurable base currency (default ILS)
- Row sections: Employment (income, deductions, taxes) → Net Income → Savings & Investment → Expenses (by category group) → NET
- Column layout: Months (Jan–Dec) + Annual Total + % of Net Income

The user lives in Israel, uses ILS as primary currency, has a French bank account (CA, EUR), and Revolut accounts in ILS, EUR, USD, DKK. Starting employment in June 2026 at 17,500 ILS/month.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Upload bank CSVs (Revolut FR, Revolut EN, CA) and auto-detect format
- [ ] Parse and normalize transactions from all supported formats
- [ ] Auto-categorize transactions using OpenAI API into the defined category hierarchy
- [ ] Allow manual category correction after AI categorization
- [ ] Convert all amounts to configurable base currency (default ILS)
- [ ] View all transactions chronologically with filtering
- [ ] View budget summary matching Excel layout — monthly columns, category groups, totals, % of net
- [ ] Manage budget categories (add/edit/rename)
- [ ] Store all transaction data persistently in Postgres
- [ ] Handle duplicate detection when importing overlapping date ranges

### Out of Scope

- Authentication / multi-user — single user, no login for MVP
- Direct bank API connections (Revolut/CA APIs) — CSV upload only for now
- Real-time currency conversion rates — manual or periodic rate updates sufficient
- Savings goals and investment tracking — future milestone
- Income tracking from payslips — manual income entry in budget for now
- Mobile app — web-first

## Constraints

- **Stack**: React (frontend), Python + FastAPI (backend), PostgreSQL (database)
- **AI Provider**: OpenAI API for transaction categorization
- **Deployment**: Local development for MVP (Docker Compose)
- **Budget**: Personal project, minimize infrastructure costs

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| OpenAI over Claude for categorization | User already has GPT workflow for this, familiarity | — Pending |
| No auth for MVP | Single user, faster to ship | — Pending |
| CSV upload over bank APIs | Bank APIs require complex auth flows, CSV works now | — Pending |
| ILS as default base currency | User lives in Israel, primary spending currency | — Pending |
| Two-level category hierarchy | Matches existing Excel structure (General Category + Precise Description) | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-23 after initialization*
