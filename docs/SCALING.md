# Scaling roadmap — transaction processing pipeline

**Status: future project, deliberately not built.** This documents when and how the
transaction-ingestion/categorization path would scale up, so the decision is recorded
and doesn't get re-litigated every time throughput comes up.

## Where we are today (and why it's enough)

Current volume: one user, a few CSV uploads per month, a few hundred rows each.
Processing happens synchronously inside the upload request:

```
CSV upload → parse → categorize (OpenAI, batches of 30) → convert currency → insert
```

End-to-end this is seconds per upload, and the bulk auto-categorize endpoint is
capped at 300 transactions per run (~10 OpenAI calls) to stay under HTTP/proxy
timeouts. At this scale, any queueing infrastructure would cost more to run than
the entire rest of the stack and add failure modes without removing any.

## The escalation ladder

Each step is only justified when the previous one actually hurts:

| Stage | Trigger | Change |
|---|---|---|
| 1. **Now** — synchronous in-request | works up to ~1–2k rows per upload | none |
| 2. **FastAPI BackgroundTasks** | uploads feel slow (>10s), user shouldn't wait for categorization | return the import immediately, categorize in-process in the background, UI polls the uncategorized count |
| 3. **Managed queue (SQS + worker)** | multiple users / uploads overlapping, retries needed, work must survive an app restart | upload enqueues a job; a separate worker container consumes, categorizes, writes back. SQS free tier: 1M requests/month |
| 4. **Kafka pipeline** | see below | full streaming architecture |

## Stage 4: the Kafka project (the "someday" design)

Kafka earns its keep when transaction events become a *stream* that multiple
consumers need independently and replayably — realistically: many users, bank-API
(PSD2/open-banking) live feeds instead of manual CSVs, and several downstream
systems reacting to the same events.

Sketch:

```
bank feeds / uploads
        │
        ▼
  producer (ingest API)
        │
        ▼
  Kafka topic: transactions.raw          (partitioned by user_id)
        │
        ├─→ consumer: categorizer        → OpenAI batch → topic: transactions.categorized
        ├─→ consumer: fx-converter       → Frankfurter rates → enrich
        └─→ consumer: db-writer          → PostgreSQL (the query/serving store)
                                            │
  topic: transactions.categorized ────────┴─→ consumer: alerting/budget-watchdog
                                              (e.g. "you crossed your monthly budget")
```

Key properties that justify the complexity *at that scale*:
- **Replay**: reprocess history through an improved categorizer by resetting consumer offsets, no re-upload needed.
- **Decoupling**: categorization latency (or an OpenAI outage) never blocks ingestion.
- **Fan-out**: new consumers (analytics, alerts, exports) attach without touching ingestion.

Cost/operational reality check: a minimal managed Kafka (MSK/Confluent) starts at
~$75–200/month — more than 10× everything else in this project combined. On AWS,
the honest first version of stage 4 is **Kinesis or SQS+SNS fan-out**, which gets
80% of the value serverless. Self-managing Kafka on the t3.micro is not viable
(the broker alone wants more RAM than the instance has).

## Non-goals

- Real-time dashboards (daily granularity is inherent to the data — bank exports)
- Multi-region, HA — this is a personal tool; RDS backups cover disaster recovery
