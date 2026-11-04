"""SQLAlchemy models. Money is Numeric/Decimal, never float."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    category: Mapped[str] = mapped_column(String(40))
    rating: Mapped[float] = mapped_column(Float)  # 0-5
    email: Mapped[str] = mapped_column(String(120))


class PurchaseRequest(Base):
    __tablename__ = "purchase_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(160), unique=True)
    item: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(40))
    quantity: Mapped[int] = mapped_column(Integer)
    estimated_unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    justification: Mapped[str] = mapped_column(Text, default="")
    requester: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    recommended_quote_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    quotes: Mapped[list["Quote"]] = relationship(
        back_populates="request", order_by="Quote.rank", cascade="all, delete-orphan"
    )
    purchase_order: Mapped["PurchaseOrder | None"] = relationship(back_populates="request", uselist=False)


class Quote(Base):
    __tablename__ = "quotes"
    __table_args__ = (UniqueConstraint("request_id", "vendor_id", name="uq_quote_request_vendor"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("purchase_requests.id"), index=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    lead_time_days: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(12), default="manual")  # manual | simulated
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_breakdown: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale_source: Mapped[str | None] = mapped_column(String(12), nullable=True)  # llm | template

    request: Mapped[PurchaseRequest] = relationship(back_populates="quotes")
    vendor: Mapped[Vendor] = relationship()


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    po_number: Mapped[str] = mapped_column(String(24), unique=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("purchase_requests.id"), unique=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"))
    item: Mapped[str] = mapped_column(String(160))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 4))
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    status: Mapped[str] = mapped_column(String(16), default="issued")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    request: Mapped[PurchaseRequest] = relationship(back_populates="purchase_order")
    vendor: Mapped[Vendor] = relationship()


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default="uploaded", index=True)
    filename: Mapped[str | None] = mapped_column(String(200), nullable=True)
    stored_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Extracted fields (LLM output, schema-validated). All nullable: extraction can fail.
    vendor_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(60), nullable=True)
    invoice_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    po_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    line_items: Mapped[list | None] = mapped_column(JSON, nullable=True)
    total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    extraction_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Matching result (deterministic) + explanation (LLM or template).
    po_id: Mapped[int | None] = mapped_column(ForeignKey("purchase_orders.id"), nullable=True)
    flags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    flag_details: Mapped[list | None] = mapped_column(JSON, nullable=True)
    exception_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    exception_summary_source: Mapped[str | None] = mapped_column(String(12), nullable=True)

    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    purchase_order: Mapped[PurchaseOrder | None] = relationship()
    payment: Mapped["Payment | None"] = relationship(back_populates="invoice", uselist=False)


class Payment(Base):
    """Simulated payment record. No money moves; `simulated` is always True."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id"), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    currency: Mapped[str] = mapped_column(String(3))
    reference: Mapped[str] = mapped_column(String(40))
    simulated: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    invoice: Mapped[Invoice] = relationship(back_populates="payment")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(20), index=True)  # request | purchase_order | invoice
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    actor: Mapped[str] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(40))
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
