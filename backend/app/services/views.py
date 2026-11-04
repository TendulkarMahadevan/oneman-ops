"""Map ORM objects to API response models."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import PurchaseOrder, PurchaseRequest, Quote
from app.money import line_total
from app.schemas import AuditOut, CompareOut, PurchaseOrderOut, QuoteOut, RequestDetail
from app.services import procurement


def quote_out(req: PurchaseRequest, q: Quote) -> QuoteOut:
    return QuoteOut(
        id=q.id, vendor_id=q.vendor_id, vendor_name=q.vendor.name, vendor_rating=q.vendor.rating,
        unit_price=q.unit_price, lead_time_days=q.lead_time_days, total=line_total(req.quantity, q.unit_price),
        source=q.source, score=q.score, score_breakdown=q.score_breakdown, rank=q.rank,
        rationale=q.rationale, rationale_source=q.rationale_source,
    )


def po_out(po: PurchaseOrder) -> PurchaseOrderOut:
    return PurchaseOrderOut(
        id=po.id, po_number=po.po_number, request_id=po.request_id, vendor_id=po.vendor_id,
        vendor_name=po.vendor.name, item=po.item, quantity=po.quantity, unit_price=po.unit_price,
        total=po.total, currency=po.currency, status=po.status, created_at=po.created_at,
    )


def _sorted_quotes(req: PurchaseRequest) -> list[Quote]:
    return sorted(req.quotes, key=lambda q: (q.rank is None, q.rank or 0, q.id))


def request_detail(db: Session, req: PurchaseRequest) -> RequestDetail:
    return RequestDetail(
        id=req.id, title=req.title, item=req.item, category=req.category, quantity=req.quantity,
        estimated_unit_price=req.estimated_unit_price, requester=req.requester, status=req.status,
        created_at=req.created_at, justification=req.justification,
        recommended_quote_id=req.recommended_quote_id, rejection_reason=req.rejection_reason,
        approval_threshold_usd=get_settings().approval_required_over_usd,
        score_weights={"price": get_settings().score_weight_price, "lead_time": get_settings().score_weight_lead_time,
                       "rating": get_settings().score_weight_rating},
        quotes=[quote_out(req, q) for q in _sorted_quotes(req)],
        purchase_order=po_out(req.purchase_order) if req.purchase_order else None,
        timeline=[AuditOut.model_validate(a) for a in procurement.timeline(db, req)],
    )


def compare_out(req: PurchaseRequest) -> CompareOut:
    best = next(q for q in req.quotes if q.id == req.recommended_quote_id)
    return CompareOut(
        request_id=req.id, status=req.status, ranked=[quote_out(req, q) for q in _sorted_quotes(req)],
        recommended_quote_id=best.id, recommended_total=line_total(req.quantity, best.unit_price),
        approval_required=req.status == "awaiting_approval",
        purchase_order=po_out(req.purchase_order) if req.purchase_order else None,
    )
