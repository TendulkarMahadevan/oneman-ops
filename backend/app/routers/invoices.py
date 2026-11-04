from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.errors import Invalid
from app.models import Invoice
from app.schemas import AuditOut, DecisionIn, InvoiceDetail, InvoiceSummary, PaymentOut
from app.services import invoices as svc
from app.services.views import po_out

router = APIRouter(prefix="/invoices", tags=["invoices"])


def invoice_detail(db: Session, inv: Invoice) -> InvoiceDetail:
    return InvoiceDetail(
        **InvoiceSummary.model_validate(inv).model_dump(),
        invoice_date=inv.invoice_date, line_items=inv.line_items, extraction_error=inv.extraction_error,
        flag_details=inv.flag_details or [], exception_summary=inv.exception_summary,
        exception_summary_source=inv.exception_summary_source, decision_reason=inv.decision_reason,
        purchase_order=po_out(inv.purchase_order) if inv.purchase_order else None,
        payment=PaymentOut.model_validate(inv.payment) if inv.payment else None,
        raw_text=inv.raw_text, timeline=[AuditOut.model_validate(a) for a in svc.timeline(db, inv)],
    )


@router.get("", response_model=list[InvoiceSummary])
def list_invoices(status_: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Invoice).order_by(Invoice.created_at.desc(), Invoice.id.desc())
    if status_:
        stmt = stmt.where(Invoice.status == status_)
    return db.scalars(stmt).all()


@router.post("/upload", response_model=InvoiceDetail, status_code=status.HTTP_201_CREATED)
async def upload_invoice(file: UploadFile = File(...), actor: str = Form("uploader"), db: Session = Depends(get_db)):
    limit = get_settings().max_upload_bytes
    data = await file.read(limit + 1)  # never buffer more than limit+1 bytes
    if len(data) > limit:
        raise Invalid(f"File exceeds the {get_settings().max_upload_mb} MB limit")
    return invoice_detail(db, svc.upload(db, file.filename or "", data, actor=actor.strip()[:80] or "uploader"))


@router.get("/{invoice_id}", response_model=InvoiceDetail)
def get_invoice(invoice_id: int, db: Session = Depends(get_db)):
    return invoice_detail(db, svc.get_invoice(db, invoice_id))


@router.post("/{invoice_id}/match", response_model=InvoiceDetail)
def match_invoice(invoice_id: int, db: Session = Depends(get_db)):
    return invoice_detail(db, svc.match(db, svc.get_invoice(db, invoice_id)))


@router.post("/{invoice_id}/decision", response_model=InvoiceDetail)
def decide_invoice(invoice_id: int, body: DecisionIn, db: Session = Depends(get_db)):
    return invoice_detail(db, svc.decide(db, svc.get_invoice(db, invoice_id), body.decision, body.actor, body.reason))
