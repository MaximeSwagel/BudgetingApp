# Roadmap: BudgetingApp

## Overview

This roadmap transforms a manual Excel budgeting pipeline into an automated web app. The journey starts with database and project scaffolding, then builds the CSV import pipeline for all three bank formats, adds AI categorization and multi-currency conversion as data enrichment, surfaces imported data through a filterable transaction list, and culminates in the budget summary view that replaces the Excel spreadsheet. Each phase delivers a complete, verifiable capability that the next phase builds on.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation & Data Model** - Database schema, project scaffolding, Docker Compose setup
- [ ] **Phase 2: CSV Import Pipeline** - Bank format parsers, upload endpoint, duplicate detection
- [ ] **Phase 3: Categorization & Currency** - OpenAI auto-categorization, manual corrections, multi-currency conversion
- [ ] **Phase 4: Transaction View** - Chronological transaction list with filtering and details
- [ ] **Phase 5: Budget View** - Monthly budget grid matching Excel layout with totals and percentages

## Phase Details

### Phase 1: Foundation & Data Model
**Goal**: The application infrastructure is running and the data model correctly represents multi-currency, multi-bank transactions with proper money precision
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: STOR-01, STOR-02
**Success Criteria** (what must be TRUE):
  1. Docker Compose brings up the full stack (React frontend, FastAPI backend, PostgreSQL database) with a single command
  2. The database schema stores transactions with NUMERIC precision for money amounts, dual-amount fields (original + converted), and import batch tracking
  3. The API health endpoint responds and the frontend loads in the browser
**Plans**: TBD

### Phase 2: CSV Import Pipeline
**Goal**: Users can upload bank CSV exports and see their transactions parsed, validated, and stored correctly
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: IMPT-01, IMPT-02, IMPT-03, IMPT-04, IMPT-05, IMPT-06
**Success Criteria** (what must be TRUE):
  1. User can upload a Revolut CSV (French or English format) and see parsed transactions appear
  2. User can upload a Credit Agricole CSV (semicolon-delimited, multiline descriptions) and see parsed transactions appear
  3. App correctly auto-detects which bank and language a CSV came from without user intervention
  4. Incomplete or pending transactions are filtered out during import
  5. When uploading a CSV with overlapping date ranges, duplicate transactions are flagged rather than silently re-imported
**Plans**: TBD
**UI hint**: yes

### Phase 3: Categorization & Currency
**Goal**: Every imported transaction is automatically categorized into the budget hierarchy and converted to the user's base currency
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: CATG-01, CATG-02, CATG-03, CATG-04, CURR-01, CURR-02, CURR-03
**Success Criteria** (what must be TRUE):
  1. After import, transactions are auto-categorized by OpenAI into the two-level category hierarchy (General Category + Precise Description)
  2. User can manually correct the category on any transaction and see the change persist
  3. User can add, edit, or rename categories in the hierarchy
  4. All transaction amounts are converted to the configurable base currency (default ILS), with both original and converted amounts stored
  5. User can change the base display currency and see all amounts re-displayed accordingly
**Plans**: TBD
**UI hint**: yes

### Phase 4: Transaction View
**Goal**: Users can browse and explore all their imported transactions in a rich, filterable list
**Mode:** mvp
**Depends on**: Phase 3
**Requirements**: TRNV-01, TRNV-02, TRNV-03
**Success Criteria** (what must be TRUE):
  1. User can view all imported transactions in a chronological list showing original amount, currency, converted amount, category, and bank source
  2. User can filter the transaction list by date range, bank, currency, and category
  3. Filtering updates results immediately and the list handles hundreds of transactions without noticeable lag
**Plans**: TBD
**UI hint**: yes

### Phase 5: Budget View
**Goal**: Users can see their spending organized in a budget summary that matches their existing Excel layout, replacing the manual spreadsheet
**Mode:** mvp
**Depends on**: Phase 4
**Requirements**: BUDG-01, BUDG-02, BUDG-03, BUDG-04, BUDG-05
**Success Criteria** (what must be TRUE):
  1. User can view a budget grid with monthly columns and category group rows matching the Excel layout
  2. Budget view shows income (manual entry), savings, and expense sections grouped by category (Home, Household, Insurance/Tax/Fees, Health Care, Discretionary)
  3. Monthly totals, annual totals, and percentage of net income per category are calculated and displayed correctly
  4. User can set monthly budget targets per category and see comparison against actual spending
**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation & Data Model | 0/0 | Not started | - |
| 2. CSV Import Pipeline | 0/0 | Not started | - |
| 3. Categorization & Currency | 0/0 | Not started | - |
| 4. Transaction View | 0/0 | Not started | - |
| 5. Budget View | 0/0 | Not started | - |
