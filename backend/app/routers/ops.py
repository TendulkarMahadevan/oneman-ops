from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import llm
from app.config import get_settings
from app.db import get_db
from app.models import AuditLog, Invoice, PurchaseOrder, PurchaseRequest
from app.money import line_total
from app.schemas import ApprovalItem, AuditOut, DashboardOut, HealthOut

router = APIRouter(tags=["ops"])
CLOSED_REQUEST = ("po_created", "rejected")


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@router.get("/health", response_model=HealthOut)
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception as exc:  # noqa: BLE001 - report any DB failure as unhealthy
        database = f"error: {type(exc).__name__}"
    llm_ok, llm_detail = llm.ping()
    ok = database == "ok" and llm_ok
    return HealthOut(status="ok" if ok else "degraded", database=database,
                     llm="ok" if llm_ok else llm_detail, llm_configured=get_settings().llm_configured)


@router.get("/dashboard/summary", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    pos = db.scalars(select(PurchaseOrder)).all()
    spend = sum((p.total for p in pos if _aware(p.created_at) >= month_start), Decimal(0))
    cycle_hours = [
        (_aware(p.created_at) - _aware(p.request.created_at)).total_seconds() / 3600 for p in pos
    ]
    invoices_total = db.scalar(select(func.count()).select_from(Invoice)) or 0
    touchless = db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "auto_approved",
                                                                          AuditLog.entity_type == "invoice")) or 0
    recent = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(12)).all()
    return DashboardOut(
        open_requests=db.scalar(select(func.count()).select_from(PurchaseRequest)
                                .where(PurchaseRequest.status.not_in(CLOSED_REQUEST))) or 0,
        awaiting_approval=db.scalar(select(func.count()).select_from(PurchaseRequest)
                                    .where(PurchaseRequest.status == "awaiting_approval")) or 0,
        flagged_invoices=db.scalar(select(func.count()).select_from(Invoice).where(Invoice.status == "flagged")) or 0,
        spend_this_month_usd=spend,
        avg_cycle_time_hours=round(sum(cycle_hours) / len(cycle_hours), 2) if cycle_hours else None,
        invoices_total=invoices_total, touchless_invoices=touchless,
        recent_activity=[AuditOut.model_validate(a) for a in recent],
    )


@router.get("/approvals", response_model=list[ApprovalItem])
def approvals(db: Session = Depends(get_db)):
    """Everything waiting on a human: requests over threshold, flagged invoices, big clean invoices."""
    threshold = get_settings().approval_required_over_usd
    items: list[ApprovalItem] = []
    for r in db.scalars(select(PurchaseRequest).where(PurchaseRequest.status == "awaiting_approval")):
        best = next((q for q in r.quotes if q.id == r.recommended_quote_id), None)
        items.append(ApprovalItem(
            kind="request", id=r.id, title=r.title, flags=[], created_at=r.created_at,
            amount_usd=line_total(r.quantity, best.unit_price) if best else None,
            reason=f"Order total exceeds the {threshold:,.0f} USD approval threshold"))
    for i in db.scalars(select(Invoice).where(Invoice.status.in_(("flagged", "matched", "needs_review")))):
        reason = ("Extraction failed; fields need manual review" if i.status == "needs_review"
                  else "Flagged by the three-way match" if i.status == "flagged"
                  else f"Clean match, but over the {threshold:,.0f} USD auto-approval limit")
        items.append(ApprovalItem(
            kind="invoice", id=i.id, title=f"{i.vendor_name or 'Unreadable invoice'} {i.invoice_number or ''}".strip(),
            amount_usd=i.total, reason=reason, flags=i.flags or [], created_at=i.created_at))
    return sorted(items, key=lambda x: _aware(x.created_at))


@router.get("/audit", response_model=list[AuditOut])
def audit(entity_type: str | None = None, actor: str | None = None, action: str | None = None,
          q: str | None = Query(default=None, max_length=100), limit: int = Query(default=100, ge=1, le=500),
          offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)):
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if actor:
        stmt = stmt.where(AuditLog.actor == actor)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if q:
        stmt = stmt.where(AuditLog.detail.ilike(f"%{q}%"))
    return db.scalars(stmt.limit(limit).offset(offset)).all()


@router.get("/audit/facets")
def audit_facets(db: Session = Depends(get_db)):
    return {
        "actors": sorted(db.scalars(select(AuditLog.actor).distinct())),
        "actions": sorted(db.scalars(select(AuditLog.action).distinct())),
        "entity_types": sorted(db.scalars(select(AuditLog.entity_type).distinct())),
    }
