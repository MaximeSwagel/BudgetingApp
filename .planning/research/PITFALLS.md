# Pitfalls Research

**Domain:** Personal budgeting app with multi-bank CSV import, AI categorization, multi-currency conversion
**Researched:** 2026-06-23
**Confidence:** MEDIUM (findings corroborated across multiple web sources; core claims like floating-point imprecision and CSV encoding issues are well-established engineering facts)

## Critical Pitfalls

### Pitfall 1: Floating-Point Arithmetic for Money

**What goes wrong:**
Using Python `float` or JavaScript `Number` for monetary values introduces silent rounding errors. `0.1 + 0.2` produces `0.30000000000000004`, not `0.3`. These errors compound across thousands of transactions, causing budget totals to disagree with the user's Excel calculations by unpredictable amounts. The user will notice when their app shows a NET of 1,247.03 ILS but Excel shows 1,247.00 ILS, and they will lose trust in the entire system.

**Why it happens:**
IEEE 754 binary floating-point cannot exactly represent most decimal fractions. Developers use `float` by default because it is the native numeric type in both Python and JavaScript.

**How to avoid:**
- Backend: Use Python's `decimal.Decimal` for all monetary arithmetic. Set context with `decimal.getcontext().rounding = decimal.ROUND_HALF_EVEN` (Banker's Rounding).
- Frontend: Use a library like `dinero.js` or `currency.js`, or represent all money as integer cents/agorot and divide only for display.
- Database: Use PostgreSQL `NUMERIC(12,2)` for amounts in base currency, `NUMERIC(12,4)` for exchange rates. Never use `FLOAT`, `REAL`, or the PostgreSQL `MONEY` type (locale-dependent, no sub-cent fractions).
- Conversion: When converting currencies, multiply amount by rate using Decimal, then round to target currency's minor unit count.

**Warning signs:**
- Budget totals off by fractions of a cent that grow over time
- Sum of category subtotals does not equal the grand total
- Tests comparing monetary values with `==` that pass sometimes and fail sometimes

**Phase to address:**
Database schema design and backend model layer (Phase 1 / data model). This must be decided before any transaction storage code is written. Retrofitting Decimal onto a float-based codebase requires touching every calculation.

---

### Pitfall 2: CSV Encoding and Format Detection Failures

**What goes wrong:**
Bank CSVs arrive in different encodings (UTF-8 with BOM from Revolut, Windows-1252 or ISO-8859-1 from Credit Agricole), different delimiters (comma vs semicolon), different date formats (YYYY-MM-DD vs DD/MM/YYYY), and with multiline quoted fields in the description column. A parser that assumes UTF-8 comma-delimited will silently corrupt French characters (accents in "Prevoyance" becoming garbled), split semicolon-delimited rows into wrong columns, or choke on multiline Credit Agricole descriptions.

**Why it happens:**
Developers test with one bank's format, get it working, and assume other banks are similar. French banks commonly use semicolon delimiters and Windows-1252 encoding. The BOM (Byte Order Mark, `EF BB BF`) prepended by some exports becomes a phantom character in the first column header if not handled.

**How to avoid:**
- Use `chardet` or `charset-normalizer` to detect encoding before parsing, with a confidence threshold (reject below 70% and ask user to specify).
- Open files with `encoding='utf-8-sig'` as the first attempt (handles BOM transparently), fall back to detected encoding.
- Implement per-bank parser classes with a registry pattern: `RevolutFRParser`, `RevolutENParser`, `CreditAgricoleParser`. Each knows its delimiter, date format, column mapping, and encoding expectations.
- For Credit Agricole specifically: use `delimiter=';'`, handle multiline descriptions by reading with `quoting=csv.QUOTE_ALL` and `newline=''`, parse dates as DD/MM/YYYY.
- Auto-detection heuristic: sniff first 3-5 lines to detect delimiter (count commas vs semicolons in non-quoted regions), check for BOM, validate expected column headers against known bank schemas.

**Warning signs:**
- First column header has invisible characters (BOM corruption)
- French accented characters appear as `Ã©` or `?` (encoding mismatch)
- Row count differs from expected (multiline fields splitting into extra rows)
- Amount column contains text or description column contains amounts (delimiter mismatch)

**Phase to address:**
CSV parsing and import phase. Build a comprehensive test suite with real sample files from each bank format before writing the parser. Include edge cases: empty rows, trailing commas, files with mixed line endings.

---

### Pitfall 3: Duplicate Transaction Detection That Is Either Too Aggressive or Too Lenient

**What goes wrong:**
When importing overlapping date ranges (common when re-exporting a month's data), naive duplicate detection either: (a) marks legitimate transactions as duplicates (two 5.90 EUR coffees on the same day at the same shop) and silently drops them, or (b) fails to catch actual duplicates (same transaction with slightly different description text across exports) and double-counts spending.

**Why it happens:**
Transaction descriptions are not stable identifiers. Revolut may export "Carrefour City" in one export and "CARREFOUR CITY PARIS" in another. Same-day, same-amount transactions are common for recurring purchases. There is no universal transaction ID in CSV exports (unlike bank API feeds that include unique IDs).

**How to avoid:**
- Use a composite key for matching: `(date, amount, currency, normalized_description_prefix)`. Normalize by: lowercase, strip whitespace, remove punctuation, take first 20 characters.
- Add a date proximity window of +/- 1 day to catch timezone-related date shifts between exports.
- When a potential duplicate is detected, flag it for user review rather than auto-removing. Present a "review duplicates" UI step after import.
- Store a hash of the raw CSV row as an import fingerprint. Exact row matches (byte-for-byte) are definite duplicates; fuzzy matches need human confirmation.
- Track import batches: record which file each transaction came from, so the user can undo an entire import if it went wrong.

**Warning signs:**
- Total spending drops after a re-import (false positive duplicates removed)
- Transaction count is lower than expected after importing a full month
- User reports "missing transactions" that were actually de-duplicated

**Phase to address:**
Import pipeline phase, after CSV parsing is solid. Requires a "pending review" state for transactions and a UI for confirming/rejecting duplicate candidates.

---

### Pitfall 4: AI Categorization Costs Spiraling Out of Control

**What goes wrong:**
Sending each transaction individually to OpenAI with a full category list and few-shot examples in the prompt burns through tokens rapidly. A month of 200 transactions across 4 Revolut accounts + CA could cost $2-5 per import if using GPT-4-class models with verbose prompts. Over a year of monthly imports, this adds up to $25-60 for a personal project. Worse, re-categorization of historical data (e.g., after adding a new category) multiplies costs.

**Why it happens:**
The system prompt containing the full category hierarchy + few-shot examples + instructions is repeated for every single API call. Developers use the most capable model for everything rather than matching model capability to task difficulty.

**How to avoid:**
- Batch transactions: send 20-50 transactions per API call using structured output (JSON array), not one-at-a-time.
- Use OpenAI's Batch API for non-urgent imports (50% cost reduction, 24-hour turnaround).
- Use `gpt-4o-mini` or even `gpt-4.1-nano` for categorization (simple classification task, not complex reasoning). Reserve larger models for ambiguous cases only.
- Cache category mappings: if "Carrefour City" was categorized as "Groceries" once, store that mapping and reuse it without calling the API again. Only call AI for genuinely new merchant descriptions.
- Implement prompt caching by placing static content (category list, instructions, few-shot examples) at the start of the prompt so OpenAI's automatic prompt caching can reduce input costs by up to 90%.
- Set `max_tokens` limit on responses to prevent runaway output.

**Warning signs:**
- OpenAI API bill exceeds $5/month for a personal budgeting app
- Import of 200 transactions takes more than 60 seconds (too many sequential API calls)
- Re-categorization of existing transactions re-calls the API for already-known merchants

**Phase to address:**
AI categorization phase. Design the caching layer and batching strategy before building the categorization pipeline. The merchant-to-category cache should be a first-class database entity, not an afterthought.

---

### Pitfall 5: Currency Conversion Rate Timing and Storage

**What goes wrong:**
Converting 150 EUR to ILS using today's rate when the transaction happened 3 weeks ago produces incorrect ILS amounts. Exchange rates fluctuate daily; EUR/ILS can move 2-3% in a month. Using a single fixed rate for all historical transactions (like the user currently does in Excel) is intentional but the app must make this explicit, not silently mix historical and current rates.

**Why it happens:**
Developers grab "the exchange rate" without specifying which date's rate. Free exchange rate APIs return current rates only, not historical. Storing converted amounts without the rate used makes it impossible to audit or recalculate later.

**How to avoid:**
- Store transactions in their original currency AND amount. Never discard the original.
- Store the exchange rate used alongside each conversion: `original_amount`, `original_currency`, `converted_amount`, `conversion_rate`, `conversion_date`.
- Let the user choose the conversion strategy: fixed rate per currency (matching their Excel approach), daily historical rate, or monthly average rate.
- For the MVP, fixed manual rates are fine (matches current workflow). But the data model must support per-transaction rates from day one so historical rates can be added later.
- When a rate is updated, offer to recalculate affected transactions (with user confirmation).

**Warning signs:**
- Converted amounts change when the app is restarted or rates are refreshed
- User cannot explain why the ILS equivalent differs from their manual calculation
- No way to audit which rate was used for a specific transaction

**Phase to address:**
Data model design and currency conversion phase. The schema must store both original and converted values from the beginning. Retrofitting dual-amount storage is a migration nightmare.

---

### Pitfall 6: Budget View Calculation Mismatch with Excel

**What goes wrong:**
The user's existing Excel budget has specific formulas: monthly column totals, category group subtotals, percentage of net income, and a NET row (Net Income - Savings - Expenses). If the app's budget view produces numbers that do not exactly match what their Excel would show for the same data, the user will not trust the app. Even 1 ILS off in a monthly total destroys confidence.

**Why it happens:**
Excel and the app may use different rounding at different stages. Excel rounds display values to 2 decimal places but keeps full precision internally. If the app rounds intermediate calculations, or if it rounds at a different stage than Excel, totals diverge. Additionally, category grouping logic (which transactions belong to "Home Expenses" vs "Household Expenses") may differ between AI categorization and the user's manual Excel assignments.

**How to avoid:**
- Define the exact calculation order: (1) sum raw amounts per category per month, (2) round each cell to 2 decimal places, (3) sum cells for group totals, (4) compute percentages from rounded totals. Document this and verify it matches Excel's behavior.
- Build a test suite with the user's actual Excel data: export their current Excel budget, import the same transactions into the app, and verify every cell matches.
- Use Python `Decimal` with explicit `quantize(Decimal('0.01'))` at each aggregation step.
- Display the calculation methodology in the UI ("totals are rounded per-cell before summing") so discrepancies can be diagnosed.

**Warning signs:**
- Monthly totals are off by 1-2 ILS compared to Excel
- Annual total does not equal sum of monthly columns
- Percentage of net income column does not sum to 100% (rounding)

**Phase to address:**
Budget view / reporting phase. Requires the user's actual Excel file as a test fixture. Cannot be properly verified without real data comparison.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Storing only converted ILS amounts, not originals | Simpler schema, one amount column | Cannot re-convert when rates change, cannot audit conversions, cannot add multi-currency views later | Never — always store both |
| Hardcoding bank format detection | Faster to ship two parsers | Every new bank or format change requires code changes, no user extensibility | MVP only, with clear abstraction layer ready |
| Skipping merchant-to-category cache | Simpler categorization flow | Every import re-calls OpenAI for known merchants, costs compound | Never — cache is essential for cost control |
| Using JavaScript native numbers for money on frontend | No extra library needed | Rounding errors in budget totals, display inconsistencies | Never for calculations; acceptable for display-only if backend sends pre-formatted strings |
| Single-table transaction storage | Simpler queries | Cannot track import batches, cannot undo imports, cannot store per-bank metadata | Never — import batch tracking is essential for the duplicate detection requirement |
| Storing AI category as free text | Quick to implement | Category renames break historical data, no foreign key integrity, typos create phantom categories | Never — use category ID foreign key |

## Integration Gotchas

Common mistakes when connecting to external services.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| OpenAI API | Sending one transaction per API call, no retry logic | Batch 20-50 transactions per call, implement exponential backoff with jitter, handle rate limits (429) gracefully |
| OpenAI API | Not validating structured output | Use `response_format` with JSON schema to enforce valid category IDs; validate response against known categories before saving |
| OpenAI API | No fallback when API is down | Queue failed categorizations for retry; allow manual categorization as fallback; show "uncategorized" rather than blocking import |
| Exchange rate API | Calling API per-transaction | Fetch rates once per day/import, cache in database, allow manual rate override |
| PostgreSQL | Using ORM default float types for money columns | Explicitly declare `NUMERIC(12,2)` in SQLAlchemy column definitions with `Numeric(precision=12, scale=2)` |

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Loading all transactions into React state for filtering | Slow page load, browser tab crashes | Server-side filtering with pagination; load max 100 transactions per page | 2,000+ transactions (roughly 6 months of data across all accounts) |
| Re-running AI categorization on every page load | Slow dashboard, high API costs | Cache categories in database, only categorize on import | Immediately — even 1 unnecessary API call is wasted money |
| Synchronous CSV parsing blocking the API server | Upload endpoint times out for large files | Use background task (Celery/ARQ) or async processing; return import job ID immediately | Files with 1,000+ rows or multiple simultaneous uploads |
| Computing budget aggregations in the frontend | Browser becomes unresponsive with a year of data | Pre-compute monthly aggregations in PostgreSQL with materialized views or summary tables | 12+ months of data across 5 accounts |
| N+1 queries when loading transactions with categories | Dashboard load time grows linearly with transaction count | Use SQLAlchemy `joinedload` or `selectinload` for category relationships | 500+ transactions |

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Storing OpenAI API key in frontend code or git repository | Key exposure, unauthorized API usage, unexpected billing | Store in environment variable, load server-side only, add `.env` to `.gitignore`, use Docker secrets in production |
| Logging full transaction data including amounts and descriptions | Financial data exposure in log files | Log transaction IDs and operation status only, never amounts or descriptions; sanitize error messages |
| No rate limiting on CSV upload endpoint | Denial of service, storage exhaustion | Limit file size (10MB), limit uploads per hour, validate file type server-side |
| Storing bank CSV files permanently on disk after parsing | Sensitive financial data at rest in unencrypted files | Parse CSV into database, delete the file after successful import, or encrypt at rest if retained for audit |

## UX Pitfalls

Common user experience mistakes in this domain.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| No feedback during CSV import + AI categorization | User thinks the app is frozen, clicks upload again, creates duplicates | Show progress: "Parsing CSV... Categorizing 47/200 transactions... Done" with a progress bar |
| AI miscategorization with no easy correction path | User sees "Gym/Sports" for a restaurant charge, cannot fix it without editing database | Inline category dropdown on each transaction; batch re-categorization for a merchant ("always categorize X as Y") |
| Budget view does not match Excel layout | User cannot cross-reference with their existing workflow | Mirror the exact Excel structure: same row order, same column headers (months), same section breaks (Income / Savings / Expenses / NET) |
| Showing raw imported data before categorization | User sees a wall of uncategorized transactions and feels overwhelmed | Show import summary first: "Imported 47 transactions. 42 auto-categorized, 5 need review." Link to review queue. |
| No way to undo an import | User imports wrong file or wrong date range, transactions are permanently mixed in | Track import batches with a "delete import" button that removes all transactions from that batch |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **CSV Parser:** Often missing handling for empty rows, trailing delimiters, and files with no transactions (header-only) -- verify with edge-case test files
- [ ] **Duplicate Detection:** Often missing handling for legitimate same-amount same-day transactions (two grocery runs) -- verify with user confirmation flow
- [ ] **Currency Conversion:** Often missing storage of the rate used -- verify that `conversion_rate` column exists and is populated for every converted transaction
- [ ] **Budget View:** Often missing the NET calculation row and percentage-of-income column -- verify all sections from the Excel layout are present
- [ ] **AI Categorization:** Often missing fallback for when OpenAI returns an invalid or unknown category -- verify error handling returns "Uncategorized" rather than crashing
- [ ] **Transaction List:** Often missing the original currency amount alongside the converted amount -- verify both are displayed
- [ ] **Import Flow:** Often missing the ability to undo/rollback a bad import -- verify import batch deletion works

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Float-based money storage discovered after data exists | HIGH | Write migration to convert float columns to NUMERIC, recalculate all converted amounts from stored original amounts and rates, verify totals against known-good source |
| CSV parser corruption (wrong encoding) | MEDIUM | Delete corrupted import batch, fix parser encoding detection, re-import from original CSV file (user still has it) |
| Duplicate transactions in database | MEDIUM | Query for candidate duplicates (same date + amount + similar description), present to user for review, bulk-delete confirmed duplicates, recompute budget aggregations |
| AI categorization costs too high | LOW | Implement merchant-to-category cache retroactively, backfill cache from existing categorized transactions, future imports use cache first |
| Currency conversion with wrong rates | MEDIUM | If original amounts and rates are stored: update rates, recalculate. If only converted amounts stored: HIGH cost, must re-import from CSV files |
| Budget totals do not match Excel | LOW | Adjust rounding strategy, re-aggregate from raw transactions. Low cost if calculation logic is centralized; high if scattered |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Floating-point money | Data model / schema design | Unit test: sum 1000 transactions, compare Decimal vs float result. They must differ, and the Decimal result must match manual calculation. |
| CSV encoding failures | CSV parsing / import | Integration test: parse one real sample file from each bank format. Verify row count, column values, accented characters, and amounts. |
| Duplicate detection | Import pipeline | Test: import same file twice, verify no duplicates. Import overlapping ranges, verify flagged candidates. Import two same-day same-amount transactions, verify both kept. |
| AI cost spiral | AI categorization | Monitor: log token usage and cost per import. Alert if cost per transaction exceeds $0.001. Verify cache hit rate after second import of similar transactions. |
| Currency rate timing | Data model + conversion | Schema test: verify `original_amount`, `original_currency`, `conversion_rate`, `converted_amount` columns exist. Query: verify no transaction has NULL conversion_rate. |
| Budget Excel mismatch | Budget view / reporting | Acceptance test: import user's real Excel data, compare every cell in budget view against Excel. Zero tolerance for discrepancies. |
| No import undo | Import pipeline | Test: import a batch, delete the batch, verify all transactions from that batch are removed and budget totals update. |

## Sources

- [Common Pitfalls in CSV and How to Avoid Them](https://www.companysconnects.com/post/common-pitfalls-in-csv-and-how-to-avoid-them)
- [How to Read UTF-8 with BOM CSV Files in Python](https://www.w3reference.com/blog/reading-utf-8-with-bom-using-python-csv-module-causes-unwanted-extra-characters/)
- [Python csv module documentation](https://docs.python.org/3/library/csv.html)
- [OpenAI Cost Optimization Guide](https://developers.openai.com/api/docs/guides/cost-optimization)
- [OpenAI Batch API](https://developers.openai.com/api/docs/guides/batch)
- [OpenAI Prompt Caching](https://developers.openai.com/api/docs/guides/prompt-caching)
- [Why You Should Never Use Floating Point for Money](https://sergiolema.dev/2026/06/01/why-you-should-never-use-floating-point-for-money/)
- [JavaScript Rounding Errors in Financial Applications](https://www.robinwieruch.de/javascript-rounding-errors/)
- [Avoid Common Pitfalls: Currency Data in Fintech](https://bitcat.dev/avoid-common-pitfalls-fintech-currency-handling/)
- [Detect Duplicate Bank Transactions Before They Derail Your Books](https://www.aiaccountant.com/blog/detect-duplicate-bank-transactions)
- [Working with Money in Postgres (Crunchy Data)](https://www.crunchydata.com/blog/working-with-money-in-postgres)
- [PostgreSQL Monetary Types Documentation](https://www.postgresql.org/docs/current/datatype-money.html)
- [How We Built AI-Powered Expense Categorization with RAG](https://medium.com/relay-financial/how-we-built-ai-powered-expense-categorization-with-rag-23a640fa3e78)
- [Building High-Performance Financial Dashboards with React](https://olivertriunfo.com/react-financial-dashboards/)
- [How to Handle Monetary Values in Python](https://shakuro.com/blog/how-to-handle-monetary-values)

---
*Pitfalls research for: Personal budgeting app with multi-bank CSV import, AI categorization, multi-currency*
*Researched: 2026-06-23*
