# Architecture Research

**Domain:** Personal budgeting web application (multi-currency CSV import, AI categorization, budget views)
**Researched:** 2026-06-23
**Confidence:** MEDIUM (cross-referenced web sources; no curated/official doc sources available for architecture patterns specific to this domain)

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     FRONTEND (React SPA)                         │
│  ┌───────────┐  ┌───────────────┐  ┌──────────────────┐         │
│  │ CSV Upload │  │ Transaction   │  │ Budget Summary   │         │
│  │ Component  │  │ List View     │  │ View (Grid)      │         │
│  └─────┬─────┘  └──────┬────────┘  └────────┬─────────┘         │
│        │               │                    │                   │
│        └───────────────┴────────────────────┘                   │
│                         │ HTTP/REST                             │
├─────────────────────────┼───────────────────────────────────────┤
│                     API LAYER (FastAPI)                          │
│  ┌───────────┐  ┌───────────────┐  ┌──────────────────┐         │
│  │ Upload    │  │ Transactions  │  │ Budget           │         │
│  │ Router    │  │ Router        │  │ Router           │         │
│  └─────┬─────┘  └──────┬────────┘  └────────┬─────────┘         │
│        │               │                    │                   │
├────────┴───────────────┴────────────────────┴───────────────────┤
│                   SERVICE LAYER (Business Logic)                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐    │
│  │ CSV      │  │ Category │  │ Currency │  │ Budget       │    │
│  │ Parser   │  │ Service  │  │ Service  │  │ Aggregation  │    │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬───────┘    │
│       │             │             │               │            │
│       │        ┌────┴─────┐       │               │            │
│       │        │ OpenAI   │       │               │            │
│       │        │ Client   │       │               │            │
│       │        └──────────┘       │               │            │
├───────┴─────────────┴─────────────┴───────────────┴────────────┤
│                   DATA LAYER (SQLAlchemy + PostgreSQL)           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ Transac- │  │ Category │  │ Exchange │  │ Budget   │       │
│  │ tions    │  │ Trees    │  │ Rates    │  │ Config   │       │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘       │
└─────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| CSV Upload Component | File selection, format auto-detection feedback, upload progress, import status | React dropzone + progress bar, POST multipart/form-data |
| Transaction List View | Chronological display, filtering by date/category/currency/bank, sorting | TanStack Table with server-side pagination |
| Budget Summary View | Monthly columns, category group rows, totals, % of net income | Custom grid component matching Excel layout |
| Upload Router | Accept CSV files, validate format, trigger ingestion pipeline | FastAPI UploadFile endpoint, returns job status |
| Transactions Router | CRUD for transactions, filtering/pagination, category overrides | REST endpoints with query params for filters |
| Budget Router | Aggregated budget data by month, category management | Computed views, no direct table CRUD |
| CSV Parser Service | Detect bank format, parse columns, normalize to common schema | Per-format parser classes with shared output type |
| Category Service | AI categorization via OpenAI, manual override, category CRUD | Batch OpenAI calls, caching, fallback to manual |
| Currency Service | Convert amounts to base currency using stored rates | Decimal arithmetic, rate lookup, no live API for MVP |
| Budget Aggregation | Roll up transactions into budget grid structure | SQL aggregation queries, grouped by month + category |
| OpenAI Client | Manage API calls for transaction categorization | Batched requests, structured JSON output, retry logic |

## Recommended Project Structure

```
budgeting-app/
├── docker-compose.yml          # PostgreSQL + app services
├── frontend/                   # React SPA
│   ├── src/
│   │   ├── components/         # Reusable UI components
│   │   │   ├── upload/         # CSV upload dropzone, progress
│   │   │   ├── transactions/   # Transaction table, filters
│   │   │   └── budget/         # Budget grid, category groups
│   │   ├── hooks/              # Custom React hooks (useTransactions, useBudget)
│   │   ├── api/                # API client functions (fetch wrappers)
│   │   ├── types/              # TypeScript interfaces
│   │   ├── utils/              # Formatting (currency, dates)
│   │   └── App.tsx             # Root layout + routing
│   └── package.json
├── backend/                    # FastAPI application
│   ├── app/
│   │   ├── main.py             # FastAPI app factory, CORS, lifespan
│   │   ├── routers/            # HTTP endpoint definitions
│   │   │   ├── upload.py       # CSV upload endpoints
│   │   │   ├── transactions.py # Transaction CRUD + filtering
│   │   │   ├── budget.py       # Budget aggregation endpoints
│   │   │   └── categories.py   # Category management
│   │   ├── services/           # Business logic (no HTTP concerns)
│   │   │   ├── csv_parser.py   # Bank-specific CSV parsing
│   │   │   ├── categorizer.py  # OpenAI categorization orchestration
│   │   │   ├── currency.py     # Currency conversion logic
│   │   │   └── budget.py       # Budget aggregation logic
│   │   ├── models/             # SQLAlchemy ORM models
│   │   │   ├── transaction.py
│   │   │   ├── category.py
│   │   │   └── exchange_rate.py
│   │   ├── schemas/            # Pydantic request/response models
│   │   │   ├── transaction.py
│   │   │   ├── upload.py
│   │   │   └── budget.py
│   │   ├── core/               # Configuration, database setup
│   │   │   ├── config.py       # Settings from env vars
│   │   │   └── database.py     # Async engine + session factory
│   │   └── parsers/            # Per-bank CSV format parsers
│   │       ├── base.py         # Abstract parser interface
│   │       ├── revolut_fr.py   # Revolut French format
│   │       ├── revolut_en.py   # Revolut English format
│   │       └── credit_agricole.py # CA semicolon-delimited format
│   ├── alembic/                # Database migrations
│   │   ├── versions/
│   │   └── env.py
│   ├── tests/
│   └── requirements.txt
└── sample_data/                # Example CSVs for development
```

### Structure Rationale

- **backend/app/routers/**: Separates HTTP concerns (request validation, response shaping) from business logic. Each router maps to a domain area, not a database table.
- **backend/app/services/**: Pure business logic with no knowledge of HTTP. Testable in isolation. Services call each other (e.g., upload service calls csv_parser then categorizer then currency converter).
- **backend/app/parsers/**: Dedicated directory because bank format parsing is the most complex and most likely to grow. Each bank format is a class implementing a common interface. Adding a new bank is adding one file.
- **backend/app/models/ vs schemas/**: Models are SQLAlchemy ORM (database shape). Schemas are Pydantic (API shape). They look similar but evolve independently. Never return ORM models directly from endpoints.
- **frontend/src/components/**: Organized by feature area (upload, transactions, budget) rather than by type (buttons, forms, tables). Each feature folder contains its specific components, keeping related code together.

## Architectural Patterns

### Pattern 1: Pipeline Pattern for CSV Ingestion

**What:** Process CSV uploads through a linear pipeline: Detect Format -> Parse -> Normalize -> Deduplicate -> Categorize -> Convert Currency -> Store
**When to use:** Whenever data flows through multiple transformation steps in sequence.
**Trade-offs:** Easy to understand and test each step independently. Rigid ordering; harder to parallelize. Good enough for this app's scale.

**Example:**
```python
# services/ingestion.py
async def process_upload(file_content: bytes, db: AsyncSession) -> ImportResult:
    # Step 1: Detect format
    bank_format = detect_bank_format(file_content)
    parser = get_parser(bank_format)  # Factory returns correct parser

    # Step 2: Parse to normalized schema
    raw_transactions = parser.parse(file_content)

    # Step 3: Deduplicate against existing data
    new_transactions = await deduplicate(raw_transactions, db)

    # Step 4: AI categorization (batched)
    categorized = await categorize_batch(new_transactions)

    # Step 5: Currency conversion
    converted = await convert_currencies(categorized, base_currency="ILS")

    # Step 6: Persist
    await store_transactions(converted, db)

    return ImportResult(
        total=len(raw_transactions),
        new=len(new_transactions),
        duplicates=len(raw_transactions) - len(new_transactions),
    )
```

### Pattern 2: Strategy Pattern for Bank Format Parsers

**What:** Each bank format implements a common parser interface. Format detection picks the right parser. New banks require only a new parser class, no changes to existing code.
**When to use:** When you have multiple input formats that must produce the same output structure.
**Trade-offs:** More files than a single parser with conditionals, but far easier to maintain and extend.

**Example:**
```python
# parsers/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from datetime import date

@dataclass
class NormalizedTransaction:
    date: date
    description: str
    amount: Decimal
    currency: str
    bank_source: str
    raw_description: str  # Keep original for dedup + audit

class BankParser(ABC):
    @abstractmethod
    def can_parse(self, header_row: list[str]) -> bool:
        """Return True if this parser handles the given CSV format."""

    @abstractmethod
    def parse(self, content: str) -> list[NormalizedTransaction]:
        """Parse CSV content into normalized transactions."""

# parsers/revolut_fr.py
class RevolutFRParser(BankParser):
    EXPECTED_HEADERS = ["Type", "Produit", "Date de debut", ...]

    def can_parse(self, header_row: list[str]) -> bool:
        return all(h in header_row for h in self.EXPECTED_HEADERS)

    def parse(self, content: str) -> list[NormalizedTransaction]:
        # French-specific parsing logic
        ...
```

### Pattern 3: Dual-Amount Storage for Multi-Currency

**What:** Store both the original transaction amount/currency AND the converted base-currency amount. Never discard the original data.
**When to use:** Any multi-currency financial application.
**Trade-offs:** Uses more storage per row (two amount columns + rate), but enables rate corrections without re-importing, auditing, and display in either currency.

**Example:**
```python
# models/transaction.py
class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    description = Column(String, nullable=False)

    # Original amount as received from bank
    original_amount = Column(Numeric(12, 2), nullable=False)
    original_currency = Column(String(3), nullable=False)  # ISO 4217

    # Converted to base currency
    base_amount = Column(Numeric(12, 2), nullable=False)
    base_currency = Column(String(3), nullable=False, default="ILS")
    exchange_rate = Column(Numeric(12, 6), nullable=False)  # Rate used

    # Categorization
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    ai_confidence = Column(Float, nullable=True)  # OpenAI confidence
    manually_categorized = Column(Boolean, default=False)

    # Source tracking
    bank_source = Column(String(50), nullable=False)  # "revolut_fr", "ca"
    import_hash = Column(String(64), unique=True)  # For dedup
    imported_at = Column(DateTime, server_default=func.now())
```

### Pattern 4: Request-Scoped Async Sessions

**What:** Create one AsyncSession per HTTP request via FastAPI dependency injection. Session lives for the request, commits or rolls back, then closes.
**When to use:** All database access in FastAPI.
**Trade-offs:** Simple mental model, automatic cleanup, no connection leaks. Slightly more boilerplate than a global session but dramatically safer.

**Example:**
```python
# core/database.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

engine = create_async_engine(
    settings.database_url,
    pool_size=5,       # Single user app, small pool
    max_overflow=5,
    pool_pre_ping=True,
)
async_session = async_sessionmaker(engine, expire_on_commit=False)

async def get_db():
    async with async_session() as session:
        async with session.begin():
            yield session
```

## Data Flow

### CSV Import Flow (Primary Data Path)

```
[User selects CSV file]
    |
    v
[Frontend] --POST multipart/form-data--> [Upload Router]
    |                                          |
    |                                    [Read file bytes]
    |                                          |
    |                                    [Detect encoding (chardet)]
    |                                          |
    |                                    [Detect bank format (header matching)]
    |                                          |
    |                                    [Parse via format-specific parser]
    |                                          |
    |                                    [Normalize to NormalizedTransaction]
    |                                          |
    |                                    [Generate import_hash per transaction]
    |                                          |
    |                                    [Query DB for existing hashes -> deduplicate]
    |                                          |
    |                                    [Batch new transactions -> OpenAI]
    |                                          |
    |                                    [Receive category assignments]
    |                                          |
    |                                    [Apply exchange rates -> base_amount]
    |                                          |
    |                                    [Bulk insert to PostgreSQL]
    |                                          |
    v                                          v
[Display import summary]  <---JSON---  [Return ImportResult]
```

### Budget View Data Flow (Read Path)

```
[User navigates to Budget view]
    |
    v
[Frontend] --GET /api/budget?year=2026--> [Budget Router]
    |                                          |
    |                                    [Budget Service]
    |                                          |
    |                                    [SQL: GROUP BY month, category_group]
    |                                    [SUM(base_amount) per cell]
    |                                    [Calculate % of net income]
    |                                          |
    v                                          v
[Render grid: months x categories]  <--  [BudgetGrid JSON]
```

### Key Data Flows

1. **Import flow (write-heavy):** CSV bytes -> parsed rows -> deduplicated -> AI-categorized -> currency-converted -> stored. This is the most complex flow and should be built first.
2. **Transaction view (read-heavy):** Query with filters (date range, category, bank, currency) -> paginated results. Server-side pagination because transaction count will grow over time.
3. **Budget view (aggregation-heavy):** SQL GROUP BY queries that compute monthly sums per category. No separate "budget" table -- this is a computed view over transactions. Budget structure (which categories exist, their groups) is stored; amounts come from transaction aggregation.
4. **Category override (point write):** User corrects a single transaction's category. Updates one row. Marks `manually_categorized = True` so future AI runs do not overwrite it.

## Database Schema Design

### Core Tables

```
transactions
├── id (PK)
├── date
├── description
├── original_amount (NUMERIC 12,2)
├── original_currency (VARCHAR 3)
├── base_amount (NUMERIC 12,2)
├── base_currency (VARCHAR 3)
├── exchange_rate (NUMERIC 12,6)
├── category_id (FK -> categories)
├── ai_confidence (FLOAT)
├── manually_categorized (BOOLEAN)
├── bank_source (VARCHAR 50)
├── import_hash (VARCHAR 64, UNIQUE)
└── imported_at (TIMESTAMP)

categories
├── id (PK)
├── name (VARCHAR, e.g., "Rent")
├── group_name (VARCHAR, e.g., "Home Expenses")
├── display_order (INTEGER)
└── is_income (BOOLEAN)

exchange_rates
├── id (PK)
├── from_currency (VARCHAR 3)
├── to_currency (VARCHAR 3)
├── rate (NUMERIC 12,6)
├── effective_date (DATE)
└── source (VARCHAR, e.g., "manual", "api")

import_logs
├── id (PK)
├── filename (VARCHAR)
├── bank_source (VARCHAR 50)
├── total_rows (INTEGER)
├── new_rows (INTEGER)
├── duplicate_rows (INTEGER)
└── imported_at (TIMESTAMP)
```

### Schema Design Decisions

- **NUMERIC(12,2) for amounts:** Exact decimal arithmetic, no floating-point drift. 12 digits total handles amounts up to 9,999,999,999.99.
- **NUMERIC(12,6) for exchange rates:** 6 decimal places for rate precision during conversion. Rates like 1 USD = 3.758432 ILS need this granularity.
- **import_hash for deduplication:** SHA-256 of (date + original_amount + original_currency + description + bank_source). UNIQUE constraint prevents DB-level duplicates. Cheaper than multi-column composite checks on every insert.
- **Two-level categories via group_name:** Flat table with group_name string rather than a separate category_groups table. Simpler for a two-level hierarchy. If hierarchy goes deeper, migrate to adjacency list or materialized path.
- **is_income flag on categories:** Distinguishes income categories from expense categories for NET calculation in budget view.
- **import_logs table:** Audit trail for every CSV import. Helps debug "where did this transaction come from?" questions.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Single user, <10k transactions | Current architecture is sufficient. All queries run fast. No caching needed. |
| Single user, 10k-100k transactions | Add database indexes on (date, category_id, bank_source). Server-side pagination becomes important. Consider materialized view for budget aggregation. |
| Multi-user (future milestone) | Add user_id FK to all tables. Add auth middleware. Connection pool sizing becomes relevant. |

### Scaling Priorities

1. **First bottleneck: OpenAI API latency.** Categorizing 500 transactions one-by-one takes minutes. Batch into groups of 20-50 transactions per API call using structured JSON output. This is a day-one optimization, not a later concern.
2. **Second bottleneck: Budget aggregation query.** GROUP BY across months and categories scans the entire transactions table. For <10k rows this is instant. Past 50k, add a composite index on (date, category_id, base_amount) or use a materialized view that refreshes on import.

## Anti-Patterns

### Anti-Pattern 1: Using Float for Money

**What people do:** Store amounts as Python `float` or PostgreSQL `REAL`/`DOUBLE PRECISION`.
**Why it is wrong:** 0.1 + 0.2 = 0.30000000000000004 in IEEE 754. Over thousands of transactions, rounding errors compound. Budget totals will not match individual transaction sums.
**Do this instead:** Use Python `Decimal` everywhere on the backend. Use PostgreSQL `NUMERIC(12,2)`. On the frontend, receive amounts as strings from the API and format for display only.

### Anti-Pattern 2: Converting Currency on the Fly

**What people do:** Store only original amounts and apply exchange rates at query time.
**Why it is wrong:** Rates change. Today's query gives different totals than yesterday's for the same data. Budget becomes non-deterministic. Debugging discrepancies is impossible.
**Do this instead:** Convert once at import time. Store both original and converted amounts. If rates need correction, update exchange_rates table and run a migration script to recalculate base_amounts.

### Anti-Pattern 3: Monolithic CSV Parser

**What people do:** Single `parse_csv()` function with if/elif branches for each bank format.
**Why it is wrong:** Each bank format has different encodings, delimiters, date formats, column names, and edge cases. A single function becomes unmaintainable after 3 formats.
**Do this instead:** Strategy pattern with one parser class per bank format. Format detection is a separate concern from parsing. Adding a new bank never touches existing parser code.

### Anti-Pattern 4: Returning ORM Models from API Endpoints

**What people do:** Pass SQLAlchemy model instances directly as FastAPI response.
**Why it is wrong:** Couples database schema to API contract. Adding a database column leaks it to clients. Lazy-loaded relationships trigger N+1 queries during serialization.
**Do this instead:** Define Pydantic response schemas explicitly. Map ORM model -> Pydantic schema in the service or router layer. This lets database and API evolve independently.

### Anti-Pattern 5: One OpenAI Call per Transaction

**What people do:** Send each transaction description to OpenAI individually.
**Why it is wrong:** 500 transactions = 500 API calls. Each call has network latency (~200ms) plus token overhead from system prompt repetition. Costs 10-20x more than batching.
**Do this instead:** Batch 20-50 transaction descriptions into a single prompt. Use structured JSON output to get all categories back in one response. Process uncategorized transactions in batch, not individually.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| OpenAI API | HTTP client with retry + exponential backoff | Use gpt-4o-mini for cost efficiency. Structured JSON output mode. Batch 20-50 transactions per call. Cache system prompt. |
| PostgreSQL | Async SQLAlchemy via asyncpg driver | Connection pool via create_async_engine. Alembic for migrations. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Frontend <-> Backend | REST/JSON over HTTP | CORS configured for local dev. Pydantic schemas define contract. |
| Routers <-> Services | Direct Python function calls | Routers handle HTTP; services handle logic. Services never import from routers. |
| Services <-> Models | SQLAlchemy async session passed as argument | Services receive session via dependency injection, never create their own. |
| Parsers <-> Services | Parser returns list[NormalizedTransaction] | Parsers know nothing about the database. Services orchestrate storage. |
| Services <-> OpenAI | Service calls an OpenAI client wrapper | Wrapper handles retries, rate limits, response parsing. Service only sees categories. |

## Build Order (Dependency Chain)

The components have clear dependencies that dictate build order:

```
Phase 1: Foundation
  Database schema + models + migrations
  Core config + database setup
  Basic project scaffolding (both frontend and backend)
      |
      v
Phase 2: Data Ingestion Pipeline
  CSV parsers (all 3 bank formats)
  Format detection
  Deduplication logic
  Upload endpoint
      |
      v
Phase 3: AI Categorization
  OpenAI client wrapper
  Batch categorization service
  Category CRUD
  Manual override endpoint
      |
      v
Phase 4: Currency Conversion
  Exchange rate storage + management
  Conversion service (applied during import)
  Rate management endpoint (manual entry for MVP)
      |
      v
Phase 5: Transaction View
  Transaction query service (filtering, pagination)
  Transaction list frontend component
  Filter controls
      |
      v
Phase 6: Budget View
  Budget aggregation queries
  Budget grid component (monthly columns, category groups)
  Totals + percentage calculations
```

**Build order rationale:**
- Database schema is the foundation everything else depends on.
- CSV parsing must work before anything else is useful -- without data, there is nothing to categorize, convert, or display.
- AI categorization depends on having parsed transactions to categorize.
- Currency conversion depends on having categorized transactions (though technically independent, doing it during import means it comes after parsing).
- Transaction view is the simplest read path -- good first frontend milestone.
- Budget view is the most complex aggregation -- build last, when the data pipeline is proven.

## Sources

- [FastAPI Best Practices - zhanymkanov](https://github.com/zhanymkanov/fastapi-best-practices) [web, LOW confidence]
- [FastAPI Bigger Applications - Official Docs](https://fastapi.tiangolo.com/tutorial/bigger-applications/) [web, LOW confidence]
- [Working with Money in Postgres - Crunchy Data](https://www.crunchydata.com/blog/working-with-money-in-postgres) [web, LOW confidence]
- [PostgreSQL Numeric Types - Official Docs](https://www.postgresql.org/docs/current/datatype-numeric.html) [web, LOW confidence]
- [SQLAlchemy 2.0 Async Patterns](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html) [web, LOW confidence]
- [Why You Should Never Use Floating Point for Money](https://sergiolema.dev/2026/06/01/why-you-should-never-use-floating-point-for-money/) [web, LOW confidence]
- [Currency Rounding in Finance Apps - AppMaster](https://appmaster.io/blog/currency-rounding-finance-apps) [web, LOW confidence]
- [OpenAI Cost Optimization Guide](https://developers.openai.com/api/docs/guides/cost-optimization) [web, LOW confidence]
- [RFC 4180 - CSV Format Standard](https://inventivehq.com/blog/handling-special-characters-in-csv-files) [web, LOW confidence]
- [Duplicate Transaction Detection - AI Accountant](https://www.aiaccountant.com/blog/detect-duplicate-bank-transactions) [web, LOW confidence]
- [TanStack Table for React](https://reactscript.com/best-data-table/) [web, LOW confidence]
- [FastAPI File Uploads Guide](https://plainenglish.io/python/file-uploads-and-downloads-in-fastapi-a-comprehensive-guide) [web, LOW confidence]

---
*Architecture research for: BudgetingApp - Personal budgeting web application*
*Researched: 2026-06-23*
