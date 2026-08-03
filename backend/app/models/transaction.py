from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class CategoryGroup(Base):
    __tablename__ = "category_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0)

    categories: Mapped[list["Category"]] = relationship(back_populates="group", cascade="all, delete-orphan")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    group_id: Mapped[int] = mapped_column(ForeignKey("category_groups.id"), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0)

    group: Mapped["CategoryGroup"] = relationship(back_populates="categories")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="category")

    __table_args__ = (UniqueConstraint("name", "group_id", name="uq_category_name_group"),)


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    bank: Mapped[str] = mapped_column(String(50), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    transaction_count: Mapped[int] = mapped_column(Integer, default=0)

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="import_batch")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    original_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    original_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    converted_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    exchange_rate: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    base_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    bank: Mapped[str] = mapped_column(String(50), nullable=False)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    import_batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"), nullable=False)
    is_duplicate: Mapped[bool] = mapped_column(default=False)
    is_expense: Mapped[bool] = mapped_column(default=True)

    category: Mapped["Category | None"] = relationship(back_populates="transactions")
    import_batch: Mapped["ImportBatch"] = relationship(back_populates="transactions")

    __table_args__ = (
        UniqueConstraint("date", "original_amount", "original_currency", "bank", "description", name="uq_transaction_dedup"),
    )


class CategoryGroupTarget(Base):
    """A single monthly spending ceiling for one main category
    (CategoryGroup) -- phase 1 of Budget Targets. Sub-category targets are
    deliberately out of scope (deferred to a later phase).

    Targets are absolute: whichever row was most recently written for a
    group is its current target, and that value applies to every month
    shown -- past, present, and future -- until changed or cleared. There
    is no per-month/date-gated lookup.

    `amount` is nullable: a NULL row means the target was explicitly
    cleared, rather than absent -- deleting a row would resurrect whatever
    target preceded it, which is the opposite of what "clear" means here.

    `effective_month` is always the first day of a month and records which
    month the row was written against -- it is retained as storage
    groundwork for a possible future per-month/versioned read mode, but is
    not consulted when resolving which target currently applies.
    """

    __tablename__ = "category_group_targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("category_groups.id"), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    effective_month: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("group_id", "effective_month", name="uq_group_target_month"),
    )


class UserSettings(Base):
    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)


class CategoryCorrection(Base):
    """Learned merchant-to-category correction.

    Recorded when the user flags a transaction as miscategorized on the
    Transactions page, optionally naming the right category. Keyed by a
    normalized `merchant_key` derived from the transaction description (see
    `app.services.corrections.normalize_merchant`). Both categorization entry
    points (CSV import and the Auto-categorize backlog run) consult this
    table before calling the AI provider, so a merchant the user has already
    taught is never sent to the provider again. No schema change was made to
    `transactions` itself (see D-01 in the plan) -- all correction state
    lives here, and a row's flag/learned status is derived at read time by
    matching its description against this table.
    """

    __tablename__ = "category_corrections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    merchant_key: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    description_sample: Mapped[str] = mapped_column(Text, nullable=False)
    # NULL category_id means "flagged as wrong but the user did not say what
    # it should be" -- a UI indicator only, never used to categorize.
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    # What the transaction was categorized as at flag time, kept for audit
    # and never overwritten on subsequent upserts of the same merchant_key.
    original_category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    # Plain Integer with NO ForeignKey: ImportBatchRepository.delete_with_transactions
    # deletes transactions wholesale on undo-import, so a real FK here would
    # either block that delete or leave a dangling reference. This column is
    # informational only (which transaction we originally learned from).
    source_transaction_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Two FKs to `categories.id` (category_id, original_category_id) require
    # `foreign_keys` to disambiguate which one this relationship follows.
    category: Mapped["Category | None"] = relationship(foreign_keys=[category_id])


class InternalTransferMatch(Base):
    """A detected pair of transactions that are two legs of the same
    inter-account movement between the user's own bank accounts.

    Plain Integer transaction-id columns with NO ForeignKey:
    `ImportBatchRepository.delete_with_transactions` and
    `POST /api/admin/reset` bulk-DELETE transactions, so a real FK here
    would either block that delete or dangle. Same reasoning and shape as
    `CategoryCorrection.source_transaction_id` (D-02).

    No derived monetary value (e.g. the transfer fee) is persisted here --
    it is computed at read time from the two legs so it can never drift
    from them.

    `status` is a tombstone, not a soft-delete convenience: "rejected" rows
    are kept forever so a re-scan never resurrects a pair the user already
    dismissed (D-06). The uniqueness constraint below is on the PAIR, not
    on the individual columns, so a transaction rejected in one pairing can
    still legitimately match a different transaction later.
    """

    __tablename__ = "internal_transfer_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    outgoing_transaction_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    incoming_transaction_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    confidence: Mapped[str] = mapped_column(String(10), nullable=False)  # high | medium | low
    status: Mapped[str] = mapped_column(String(10), nullable=False)  # confirmed | suggested | rejected
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            "outgoing_transaction_id", "incoming_transaction_id", name="uq_transfer_pair"
        ),
    )


class UploadLog(Base):
    """Append-only audit trail of every CSV upload attempt, success or
    failure. Unlike ImportBatch (deleted on undo/reset), this table has no FK
    to import_batches and is never deleted, so it survives undo/reset."""

    __tablename__ = "upload_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    bank: Mapped[str | None] = mapped_column(String(50), nullable=True)
    format_detected: Mapped[str | None] = mapped_column(String(50), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    rows_parsed: Mapped[int] = mapped_column(Integer, default=0)
    rows_imported: Mapped[int] = mapped_column(Integer, default=0)
    rows_skipped: Mapped[int] = mapped_column(Integer, default=0)
    rows_failed: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
