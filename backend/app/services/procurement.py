"""Procurement workflow: request -> quotes -> compare -> approval gate -> PO.

Rules decide (scoring, gate, PO amounts); the LLM only writes the per-quote rationale text.
"""
from __future__ import annotations

import logging
import random
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import llm
from app.config import Settings, get_settings
from app.errors import Conflict, Invalid, NotFound
from app.models import AuditLog, PurchaseOrder, PurchaseRequest, Quote, Vendor
from app.money import line_total
from app.scoring import QuoteInput, Weights, score_quotes
from app.schemas import QuoteIn, RequestCreate
from app.state_machine import audit_po, transition, write_audit

log = logging.getLogger(__name__)
SYSTEM_ACTOR = "system"
MAX_SIMULATED_QUOTES = 4


# ---- helpers ---------------------------------------------------------------
def get_request(db: Session, request_id: int) -> PurchaseRequest:
    req = db.scalar(
        select(PurchaseRequest)
        .where(PurchaseRequest.id == request_id)
        .options(selectinload(PurchaseRequest.quotes).selectinload(Quote.vendor))
    )
    if req is None:
        raise NotFound(f"Purchase request {request_id} not found")
    return req


def _weights(s: Settings) -> Weights:
    return Weights(s.score_weight_price, s.score_weight_lead_time, s.score_weight_rating)


def request_total(req: PurchaseRequest, quote: Quote) -> Decimal:
    return line_total(req.quantity, quote.unit_price)


# ---- create ----------------------------------------------------------------
def create_request(db: Session, data: RequestCreate, actor: str | None = None) -> PurchaseRequest:
    if db.scalar(select(PurchaseRequest).where(PurchaseRequest.title == data.title)):
        raise Conflict(f"A purchase request titled '{data.title}' already exists")
    req = PurchaseRequest(**data.model_dump(), status="open")
    db.add(req)
    db.flush()
    write_audit(db, "request", req.id, actor or data.requester, "request_created",
                f"{data.quantity} x {data.item} @ est. {data.estimated_unit_price}")
    db.commit()
    return req


# ---- quotes ----------------------------------------------------------------
def _simulated_quotes(db: Session, req: PurchaseRequest) -> list[QuoteIn]:
    """Deterministic, clearly-labelled simulated vendor responses around the requester's estimate."""
    vendors = db.scalars(
        select(Vendor).where(Vendor.category.in_([req.category, "general"])).order_by(Vendor.id)
    ).all()
    if not vendors:
        raise Invalid(f"No vendors available for category '{req.category}'")
    out = []
    for v in vendors[:MAX_SIMULATED_QUOTES]:
        rng = random.Random(f"{req.id}:{v.id}")
        factor = Decimal(str(round(rng.uniform(0.86, 1.18), 3)))
        price = (req.estimated_unit_price * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        out.append(QuoteIn(vendor_id=v.id, unit_price=price, lead_time_days=rng.randint(3, 28)))
    return out


def add_quotes(db: Session, req: PurchaseRequest, items: list[QuoteIn], simulated: bool, actor: str) -> list[Quote]:
    if req.status not in ("open", "quoted"):
        raise Conflict(f"Cannot add quotes to a request in status '{req.status}'")
    if simulated:
        items = _simulated_quotes(db, req)
    existing = {q.vendor_id for q in req.quotes}
    vendor_ids = [i.vendor_id for i in items]
    if len(set(vendor_ids)) != len(vendor_ids):
        raise Invalid("Duplicate vendor in submitted quotes")
    known = {v.id for v in db.scalars(select(Vendor).where(Vendor.id.in_(vendor_ids)))}
    missing = set(vendor_ids) - known
    if missing:
        raise Invalid(f"Unknown vendor ids: {sorted(missing)}")
    dupes = existing & set(vendor_ids)
    if dupes:
        raise Conflict(f"Quotes already exist for vendor ids: {sorted(dupes)}")

    created = []
    for item in items:
        q = Quote(request=req, vendor_id=item.vendor_id, unit_price=item.unit_price,
                  lead_time_days=item.lead_time_days, source="simulated" if simulated else "manual")
        db.add(q)
        created.append(q)
    db.flush()
    db.refresh(req, attribute_names=["quotes"])
    for q in created:
        db.refresh(q, attribute_names=["vendor"])
    transition(db, req, "quoted", actor, "quotes_added",
               f"{len(created)} {'simulated' if simulated else 'manual'} quote(s)")
    db.commit()
    return created


# ---- compare ---------------------------------------------------------------
class _RationaleItem(BaseModel):
    quote_id: int
    rationale: str = Field(min_length=10, max_length=700)


class _RationaleSet(BaseModel):
    rationales: list[_RationaleItem]


RATIONALE_SYSTEM = (
    "You are a procurement analyst. You are given vendor quotes that have ALREADY been scored and ranked by "
    "a deterministic rule engine. Do not change scores, ranks or numbers. For each quote write 2-3 plain "
    "sentences explaining its strengths and weaknesses relative to the others, using only the numbers given. "
    'Return ONLY JSON: {"rationales":[{"quote_id":int,"rationale":str}]} with exactly one entry per quote.'
)


def _template_rationale(q: Quote, req: PurchaseRequest, n: int, cheapest: Quote, fastest: Quote) -> str:
    bits = [f"Ranked {q.rank} of {n} with a weighted score of {q.score:.2f}."]
    bits.append(
        f"Unit price {q.unit_price:.2f}" + (" is the lowest quoted." if q.id == cheapest.id
        else f" is {((q.unit_price / cheapest.unit_price) - 1) * 100:.1f}% above the lowest quote.")
    )
    bits.append(
        f"Lead time is {q.lead_time_days} days" + (" (fastest)." if q.id == fastest.id else ".")
        + f" Vendor rating {q.vendor.rating:.1f}/5."
    )
    return " ".join(bits)


def _rationales(req: PurchaseRequest, ranked: list[Quote]) -> tuple[dict[int, str], str]:
    payload = [
        {"quote_id": q.id, "vendor": q.vendor.name, "rank": q.rank, "score": q.score,
         "unit_price_usd": str(q.unit_price), "lead_time_days": q.lead_time_days,
         "vendor_rating_out_of_5": q.vendor.rating, "score_breakdown": q.score_breakdown}
        for q in ranked
    ]
    user = (f"Request: {req.quantity} x {req.item}. Weights: price/lead-time/rating as configured.\n"
            f"Quotes (JSON):\n{payload}")
    try:
        result = llm.chat_json(RATIONALE_SYSTEM, user, _RationaleSet)
        by_id = {r.quote_id: r.rationale.strip() for r in result.rationales}
        if set(by_id) != {q.id for q in ranked}:
            raise llm.LLMError("Rationale set does not cover exactly the submitted quotes")
        return by_id, "llm"
    except llm.LLMError as exc:
        log.warning("Using template rationales: %s", exc)
        cheapest = min(ranked, key=lambda q: q.unit_price)
        fastest = min(ranked, key=lambda q: q.lead_time_days)
        return {q.id: _template_rationale(q, req, len(ranked), cheapest, fastest) for q in ranked}, "template"


def compare(db: Session, req: PurchaseRequest, actor: str = SYSTEM_ACTOR) -> PurchaseRequest:
    """Score, rank, explain, then apply the approval gate. Idempotent once a decision path was entered."""
    if req.status != "quoted":
        if req.status in ("awaiting_approval", "approved", "po_created") and req.recommended_quote_id:
            return req  # already compared; return stored result
        raise Conflict(f"Cannot compare a request in status '{req.status}' (needs quotes first)")
    s = get_settings()
    quotes = list(req.quotes)
    if len(quotes) < 2:
        raise Invalid("At least two quotes are required to compare")

    scored = score_quotes(
        [QuoteInput(q.id, q.vendor_id, q.unit_price, q.lead_time_days, q.vendor.rating) for q in quotes],
        _weights(s),
    )
    by_id = {q.id: q for q in quotes}
    for sc in scored:
        q = by_id[sc.quote_id]
        q.score, q.rank = sc.score, sc.rank
        q.score_breakdown = {"price": sc.price_score, "lead_time": sc.lead_time_score, "rating": sc.rating_score}
    db.flush()
    ranked = sorted(quotes, key=lambda q: q.rank)
    texts, source = _rationales(req, ranked)
    for q in ranked:
        q.rationale, q.rationale_source = texts[q.id], source

    best = ranked[0]
    req.recommended_quote_id = best.id
    total = request_total(req, best)
    transition(db, req, "compared", actor, "quotes_compared",
               f"{len(ranked)} quotes ranked; recommended {best.vendor.name} (score {best.score:.2f}, total {total}); "
               f"rationale source: {source}")

    if total > s.approval_required_over_usd:
        transition(db, req, "awaiting_approval", SYSTEM_ACTOR, "approval_required",
                   f"Total {total} exceeds threshold {s.approval_required_over_usd}")
    else:
        transition(db, req, "approved", SYSTEM_ACTOR, "auto_approved",
                   f"Total {total} within threshold {s.approval_required_over_usd}")
        _issue_po(db, req, best, SYSTEM_ACTOR)
    db.commit()
    return req


# ---- approve / reject ------------------------------------------------------
def _next_po_number(po_id: int) -> str:
    return f"PO-{1000 + po_id}"


def _issue_po(db: Session, req: PurchaseRequest, quote: Quote, actor: str) -> PurchaseOrder:
    po = PurchaseOrder(
        po_number=f"TMP-{req.id}", request_id=req.id, vendor_id=quote.vendor_id, item=req.item,
        quantity=req.quantity, unit_price=quote.unit_price, total=request_total(req, quote), currency="USD",
    )
    db.add(po)
    db.flush()
    po.po_number = _next_po_number(po.id)
    audit_po(db, po, actor, "po_issued",
             f"{po.po_number}: {po.quantity} x {po.item} @ {po.unit_price} = {po.total} USD with {quote.vendor.name}")
    transition(db, req, "po_created", actor, "po_created", f"{po.po_number} issued to {quote.vendor.name}")
    return po


def approve(db: Session, req: PurchaseRequest, approver: str, quote_id: int | None, note: str) -> PurchaseRequest:
    if req.status == "po_created":
        return req  # idempotent: already approved and PO issued
    if req.status != "awaiting_approval":
        raise Conflict(f"Request is '{req.status}', not awaiting approval")
    chosen_id = quote_id or req.recommended_quote_id
    quote = next((q for q in req.quotes if q.id == chosen_id), None)
    if quote is None:
        raise Invalid(f"Quote {chosen_id} does not belong to request {req.id}")
    override = quote.id != req.recommended_quote_id
    total = request_total(req, quote)
    detail = f"{approver} approved {quote.vendor.name} total {total}"
    if override:
        detail += " (OVERRIDE of the recommended quote)"
    if note:
        detail += f". Note: {note}"
    transition(db, req, "approved", approver, "approved", detail)
    _issue_po(db, req, quote, approver)
    db.commit()
    return req


def reject(db: Session, req: PurchaseRequest, actor: str, reason: str) -> PurchaseRequest:
    if req.status == "rejected":
        return req
    if req.status in ("approved", "po_created"):
        raise Conflict(f"Request is '{req.status}' and can no longer be rejected")
    req.rejection_reason = reason
    transition(db, req, "rejected", actor, "rejected", f"Reason: {reason}")
    db.commit()
    return req


# ---- read models -----------------------------------------------------------
def timeline(db: Session, req: PurchaseRequest) -> list[AuditLog]:
    po_ids = [req.purchase_order.id] if req.purchase_order else []
    stmt = select(AuditLog).where(
        ((AuditLog.entity_type == "request") & (AuditLog.entity_id == req.id))
        | ((AuditLog.entity_type == "purchase_order") & (AuditLog.entity_id.in_(po_ids)))
    ).order_by(AuditLog.created_at, AuditLog.id)
    return list(db.scalars(stmt))
