from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, model_validator


def _utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


UTCDateTime = Annotated[datetime, PlainSerializer(_utc_iso, return_type=str)]
Money = Annotated[Decimal, PlainSerializer(lambda d: format(d, "f"), return_type=str)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class VendorOut(ORM):
    id: int
    name: str
    category: str
    rating: float
    email: str


# ---- procurement -----------------------------------------------------------
class RequestCreate(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    item: str = Field(min_length=2, max_length=160)
    category: str = Field(min_length=2, max_length=40)
    quantity: int = Field(gt=0, le=100_000)
    estimated_unit_price: Decimal = Field(gt=0, le=Decimal("10000000"))
    justification: str = Field(default="", max_length=2000)
    requester: str = Field(min_length=1, max_length=80)


class QuoteIn(BaseModel):
    vendor_id: int
    unit_price: Decimal = Field(gt=0, le=Decimal("10000000"))
    lead_time_days: int = Field(ge=0, le=730)


class QuotesCreate(BaseModel):
    quotes: list[QuoteIn] = Field(default_factory=list, max_length=20)
    simulate: bool = False

    @model_validator(mode="after")
    def _one_mode(self) -> "QuotesCreate":
        if self.simulate == bool(self.quotes):
            raise ValueError("Provide either `quotes` or `simulate: true`, not both and not neither")
        return self


class ApproveIn(BaseModel):
    approver: str = Field(min_length=1, max_length=80)
    quote_id: int | None = None
    note: str = Field(default="", max_length=1000)


class RejectIn(BaseModel):
    actor: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=3, max_length=1000)


class QuoteOut(ORM):
    id: int
    vendor_id: int
    vendor_name: str
    vendor_rating: float
    unit_price: Money
    lead_time_days: int
    total: Money
    source: str
    score: float | None
    score_breakdown: dict | None
    rank: int | None
    rationale: str | None
    rationale_source: str | None


class PurchaseOrderOut(ORM):
    id: int
    po_number: str
    request_id: int
    vendor_id: int
    vendor_name: str
    item: str
    quantity: int
    unit_price: Money
    total: Money
    currency: str
    status: str
    created_at: UTCDateTime


class AuditOut(ORM):
    id: int
    entity_type: str
    entity_id: int
    actor: str
    action: str
    detail: str
    created_at: UTCDateTime


class RequestSummary(ORM):
    id: int
    title: str
    item: str
    category: str
    quantity: int
    estimated_unit_price: Money
    requester: str
    status: str
    created_at: UTCDateTime


class RequestDetail(RequestSummary):
    justification: str
    recommended_quote_id: int | None
    rejection_reason: str | None
    approval_threshold_usd: Money
    score_weights: dict[str, float]
    quotes: list[QuoteOut]
    purchase_order: PurchaseOrderOut | None
    timeline: list[AuditOut]


class CompareOut(BaseModel):
    request_id: int
    status: str
    ranked: list[QuoteOut]
    recommended_quote_id: int
    recommended_total: Money
    approval_required: bool
    purchase_order: PurchaseOrderOut | None


# ---- invoices --------------------------------------------------------------
class FlagOut(BaseModel):
    code: str
    message: str


class PaymentOut(ORM):
    reference: str
    amount: Money
    currency: str
    simulated: bool
    created_at: UTCDateTime


class InvoiceSummary(ORM):
    id: int
    status: str
    filename: str | None
    vendor_name: str | None
    invoice_number: str | None
    po_number: str | None
    total: Money | None
    currency: str | None
    confidence: float | None
    flags: list[str] | None
    created_at: UTCDateTime


class InvoiceDetail(InvoiceSummary):
    invoice_date: str | None
    line_items: list[dict] | None
    extraction_error: str | None
    flag_details: list[FlagOut]
    exception_summary: str | None
    exception_summary_source: str | None
    decision_reason: str | None
    purchase_order: PurchaseOrderOut | None
    payment: PaymentOut | None
    raw_text: str | None
    timeline: list[AuditOut]


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    actor: str = Field(min_length=1, max_length=80)
    reason: str = Field(default="", max_length=1000)


# ---- dashboard / approvals -------------------------------------------------
class DashboardOut(BaseModel):
    open_requests: int
    awaiting_approval: int
    flagged_invoices: int
    spend_this_month_usd: Money
    avg_cycle_time_hours: float | None
    invoices_total: int
    touchless_invoices: int
    recent_activity: list[AuditOut]


class ApprovalItem(BaseModel):
    kind: str  # request | invoice
    id: int
    title: str
    amount_usd: Money | None
    reason: str
    flags: list[str]
    created_at: UTCDateTime


class HealthOut(BaseModel):
    status: str
    database: str
    llm: str
    llm_configured: bool
