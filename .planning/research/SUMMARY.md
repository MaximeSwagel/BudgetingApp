# Research Summary: BudgetingApp

**Domain:** Personal budgeting web app (multi-bank CSV import, AI categorization, multi-currency)
**Researched:** 2026-06-23
**Overall confidence:** MEDIUM

## Executive Summary

The BudgetingApp replaces a manual Excel pipeline for tracking personal spending across multiple bank accounts (Revolut FR/EN, Credit Agricole) and currencies (ILS, EUR, USD, DKK). The standard stack for this type of application in 2026 is React 19 + Vite + TypeScript on the frontend, FastAPI + SQLAlchemy 2.0 + PostgreSQL on the backend, with OpenAI for transaction categorization and Frankfurter API for exchange rates.

The ecosystem is mature and well-documented. Every library in the recommended stack is actively maintained, widely adopted, and compatible with the others. The main technical risks are not in the technology choices but in domain-specific pitfalls: floating-point arithmetic for money (must use Decimal/NUMERIC throughout), CSV encoding and format detection across French and English bank exports, duplicate transaction detection that balances false positives and false negatives, and AI categorization cost control.

The architecture follows a standard three-tier SPA pattern with clear boundaries: React handles presentation, FastAPI handles business logic and external API orchestration, PostgreSQL stores everything. The CSV import pipeline is the most complex component -- it chains format detection, encoding handling, parsing, deduplication, AI categorization, and currency conversion. This pipeline should be built incrementally with thorough testing at each step.

The budget summary view -- monthly columns, category groups, totals, percentages -- is the product's core value and must match the user's existing Excel layout exactly. Any discrepancy in totals (even 1 ILS) will destroy user trust. This view should be built last, after the data pipeline is proven, using the user's actual Excel data as the acceptance test fixture.

## Key Findings

**Stack:** React 19 + Vite + TypeScript | FastAPI 0.138.0 + SQLAlchemy 2.0.51 + asyncpg | PostgreSQL 16 | OpenAI SDK 2.43.0 | shadcn/ui + TanStack Table/Query + Recharts
**Architecture:** Three-tier SPA with pipeline pattern for CSV import; strategy pattern for bank parsers; dual-amount storage (original + converted) for multi-currency
**Critical pitfall:** Floating-point money arithmetic -- must use Python Decimal + PostgreSQL NUMERIC(12,2) from day one; retrofitting is expensive

## Implications for Roadmap

Based on research, suggested phase structure:

1. **Foundation & Data Model** - Database schema, project scaffolding, Docker Compose
   - Addresses: Persistent storage, money precision, multi-currency schema
   - Avoids: Float-for-money pitfall (NUMERIC from day one), single-amount storage pitfall (dual amounts from day one)

2. **CSV Import Pipeline** - Bank format parsers, encoding detection, upload endpoint
   - Addresses: CSV upload with format auto-detection, parsing all 3 formats
   - Avoids: Encoding corruption pitfall, monolithic parser pitfall
   - Needs: Real sample CSV files from each bank as test fixtures

3. **AI Categorization** - OpenAI integration, batch processing, merchant cache
   - Addresses: Auto-categorization, manual correction
   - Avoids: One-call-per-transaction cost spiral, missing fallback for API failures
   - Needs deeper research: Optimal batch size, prompt engineering for French transaction descriptions

4. **Currency Conversion** - Frankfurter integration, rate storage, conversion logic
   - Addresses: Multi-currency conversion, exchange rate tracking
   - Avoids: On-the-fly conversion pitfall (convert once at import, store result)

5. **Transaction View** - Frontend list with filtering, sorting, pagination
   - Addresses: Chronological transaction list, filter by date/category/bank/currency
   - Avoids: Loading all transactions client-side (server-side pagination)

6. **Budget View** - Monthly grid, category aggregation, totals, percentages
   - Addresses: Budget summary matching Excel layout
   - Avoids: Frontend aggregation pitfall, rounding mismatch with Excel
   - Needs: User's actual Excel file as acceptance test fixture

**Phase ordering rationale:**
- Database schema must come first because every other component depends on the data model; getting money storage wrong early is the most expensive mistake to fix later
- CSV parsing before AI categorization because you need parsed transactions to categorize
- AI categorization before currency conversion because categorization is the higher-risk integration (external API, cost management, prompt engineering)
- Transaction view before budget view because it is simpler and provides immediate user feedback
- Budget view last because it is the most complex aggregation and depends on all preceding data being correct

**Research flags for phases:**
- Phase 2 (CSV Import): Likely needs deeper research on Credit Agricole multiline description handling and edge cases in French date parsing
- Phase 3 (AI Categorization): Likely needs deeper research on prompt engineering for French transaction descriptions and optimal batch sizes for cost/accuracy tradeoff
- Phase 6 (Budget View): Needs the user's actual Excel budget file to verify calculation accuracy; standard patterns otherwise
- Phase 1, 4, 5: Standard patterns, unlikely to need additional research

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM | All versions verified against PyPI/npm on 2026-06-23; library choices cross-referenced across multiple web sources; no Context7/curated docs available for version-specific feature verification |
| Features | MEDIUM | Feature landscape derived from PROJECT.md requirements + domain analysis; table stakes validated against common personal finance app patterns |
| Architecture | MEDIUM | Standard three-tier SPA; patterns (pipeline, strategy, dual-amount) well-established in fintech domain; specific implementation details based on web sources |
| Pitfalls | MEDIUM | Critical pitfalls (float money, CSV encoding, dedup) are well-documented engineering facts; cost optimization strategies verified against OpenAI official docs; domain-specific pitfalls (Excel mismatch) based on domain analysis |

## Gaps to Address

- **Credit Agricole CSV format edge cases**: Multiline descriptions, semicolon delimiter interactions, actual encoding of real exports need testing with real files
- **OpenAI prompt engineering**: Optimal prompt structure for categorizing French transaction descriptions into the specific category hierarchy needs experimentation
- **Optimal AI batch size**: Trade-off between batch size (cost efficiency) and categorization accuracy needs empirical testing (20 vs 50 transactions per call)
- **Excel budget calculation parity**: Exact rounding and aggregation order to match Excel requires the user's actual budget file for comparison
- **Frankfurter API ILS support**: ECB reference rates cover major currencies but ILS support and update frequency should be verified with a test call
- **React Router v7 vs v8 decision**: v8 is available but requires newer React/Vite versions; decision can be deferred to project scaffolding phase
