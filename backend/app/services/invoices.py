"""Invoice workflow: upload -> extract -> three-way match -> human decision -> simulated payment."""
from __future__ import annotations

import logging
import re
import uuid
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import extraction, llm, matching
from app.config import get_settings
from app.errors import Conflict, Invalid, NotFound
from app.models import AuditLog, Invoice, Payment, PurchaseOrder
from app.state_machine import transition, write_audit

log = logging.getLogger(__name__)
SYSTEM_ACTOR = "system"
ALLOWED = {".pdf": "pdf", ".txt": "text"}


# ---- upload ----------------------------------------------------------------
def sanitize_filename(name: str) -> str:
    base = Path(name or "upload").name  # drop any directory components
    stem, ext = Path(base).stem, Path(base).suffix.lower()
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")[:60] or "invoice"
    return f"{stem}{ext}"


def validate_upload(filename: str, data: bytes) -> str:
    """Return the document kind ('pdf' | 'text') or raise Invalid."""
    s = get_settings()
    ext = Path(filename or "").suffix.lower()
    kind = ALLOWED.get(ext)
    if kind is None:
        raise Invalid("Only .pdf and .txt invoices are accepted")
    if not data:
        raise Invalid("Uploaded file is empty")
    if len(data) > s.max_upload_bytes:
        raise Invalid(f"File exceeds the {s.max_upload_mb} MB limit")
    if kind == "pdf" and not data.lstrip()[:5] == b"%PDF-":
        raise Invalid("File content is not a PDF")
    if kind == "text" and b"\x00" in data:
        raise Invalid("File content is not plain text")
    return kind


def _store(data: bytes, safe_name: str) -> str:
    folder = Path(get_settings().upload_dir)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{uuid.uuid4().hex}_{safe_name}"
    path.write_bytes(data)
    return str(path)


def _apply_extraction(inv: Invoice, ex: extraction.ExtractedInvoice) -> None:
    inv.vendor_name, inv.invoice_number, inv.invoice_date = ex.vendor, ex.invoice_number, ex.date
    inv.po_number, inv.total, inv.currency, inv.confidence = ex.po_number, ex.total, ex.currency, ex.confidence
    inv.line_items = [{"description": li.description, "qty": str(li.qty), "unit_price": str(li.unit_price)}
                      for li in ex.line_items]


def upload(db: Session, filename: str, data: bytes, actor: str = "uploader") -> Invoice:
    kind = validate_upload(filename, data)
    safe = sanitize_filename(filename)
    inv = Invoice(status="uploaded", filename=safe, stored_path=_store(data, safe))
    db.add(inv)
    db.flush()
    write_audit(db, "invoice", inv.id, actor, "invoice_uploaded", f"{safe} ({len(data)} bytes, {kind})")
    try:
        inv.raw_text = extraction.extract_text(data, kind)
        _apply_extraction(inv, extraction.structure_invoice(inv.raw_text))
    except extraction.ExtractionError as exc:
        inv.extraction_error = str(exc)[:500]
        transition(db, inv, "needs_review", SYSTEM_ACTOR, "extraction_failed", inv.extraction_error)
    else:
        transition(db, inv, "extracted", SYSTEM_ACTOR, "extraction_succeeded",
                   f"invoice {inv.invoice_number} from {inv.vendor_name}, total {inv.total} {inv.currency}, "
                   f"confidence {inv.confidence:.2f}")
    db.commit()
    return inv


def register_extracted(db: Session, ex: extraction.ExtractedInvoice, raw_text: str, filename: str, actor: str) -> Invoice:
    """Insert an invoice whose fields were already extracted (used by the seed; bypasses the LLM, and says so)."""
    inv = Invoice(status="uploaded", filename=filename, raw_text=raw_text)
    db.add(inv)
    db.flush()
    _apply_extraction(inv, ex)
    write_audit(db, "invoice", inv.id, actor, "invoice_seeded", "Fields supplied directly; LLM extraction bypassed")
    transition(db, inv, "extracted", actor, "extraction_succeeded", "seeded fields")
    db.commit()
    return inv


# ---- lookup ----------------------------------------------------------------
def get_invoice(db: Session, invoice_id: int) -> Invoice:
    inv = db.get(Invoice, invoice_id)
    if inv is None:
        raise NotFound(f"Invoice {invoice_id} not found")
    return inv


def _find_po(db: Session, po_number: str | None) -> PurchaseOrder | None:
    wanted = matching.normalize_ref(po_number)
    if not wanted:
        return None
    return next((p for p in db.scalars(select(PurchaseOrder)) if matching.normalize_ref(p.po_number) == wanted), None)


def _is_duplicate(db: Session, inv: Invoice) -> bool:
    ref, vendor = matching.normalize_ref(inv.invoice_number), matching.normalize_vendor(inv.vendor_name or "")
    if not ref:
        return False
    earlier = db.scalars(select(Invoice).where(Invoice.id < inv.id, Invoice.invoice_number.is_not(None),
                                               Invoice.status != "rejected"))
    return any(matching.normalize_ref(o.invoice_number) == ref
               and matching.normalize_vendor(o.vendor_name or "") == vendor for o in earlier)


# ---- exception summary -----------------------------------------------------
class _ExceptionSummary(BaseModel):
    summary: str = Field(min_length=20, max_length=700)
    suggested_action: str = Field(min_length=5, max_length=300)


SUMMARY_SYSTEM = (
    "You are an accounts-payable analyst. A deterministic rule engine has flagged an invoice. Explain to a "
    "finance approver, in plain English, what is wrong (2-3 sentences) and give one suggested action. Use only "
    "the facts provided; do not invent numbers and do not alter the flags. "
    'Return ONLY JSON: {"summary":str,"suggested_action":str}'
)


def _exception_summary(po: PurchaseOrder | None, flags: list[matching.Flag], total: Decimal | None) -> tuple[str, str]:
    actions = " ".join(dict.fromkeys(matching.SUGGESTED_ACTIONS[f.code] for f in flags))
    template = " ".join(f.message for f in flags) + f" Suggested action: {actions}"
    facts = {"po_number": po.po_number if po else None, "po_vendor": po.vendor.name if po else None,
             "invoice_total": str(total) if total is not None else None,
             "flags": [{"code": f.code, "finding": f.message} for f in flags]}
    try:
        res = llm.chat_json(SUMMARY_SYSTEM, f"Flagged invoice facts (JSON):\n{facts}", _ExceptionSummary)
        return f"{res.summary.strip()} Suggested action: {res.suggested_action.strip()}", "llm"
    except llm.LLMError as exc:
        log.warning("Using template exception summary: %s", exc)
        return template, "template"


# ---- match -----------------------------------------------------------------
def _facts(inv: Invoice) -> matching.InvoiceFacts:
    return matching.InvoiceFacts(
        vendor_name=inv.vendor_name or "", currency=inv.currency or "",
        lines=[matching.Line(Decimal(li["qty"]), Decimal(li["unit_price"])) for li in inv.line_items or []],
        total=Decimal(inv.total), confidence=inv.confidence or 0.0,
        suspicious=matching.looks_like_prompt_injection(inv.raw_text or ""),
    )


def match(db: Session, inv: Invoice) -> Invoice:
    if inv.status not in ("extracted", "needs_review"):
        if inv.status in ("matched", "flagged", "approved", "paid", "rejected"):
            return inv  # idempotent: already matched
        raise Conflict(f"Invoice is '{inv.status}' and cannot be matched")
    s = get_settings()
    po = _find_po(db, inv.po_number)
    if inv.status == "needs_review":
        flags = [matching.Flag(matching.FLAG_LOW_CONFIDENCE,
                               f"Automatic extraction failed ({inv.extraction_error}); fields need manual entry.")]
        if matching.looks_like_prompt_injection(inv.raw_text or ""):
            flags.append(matching.Flag(matching.FLAG_SUSPICIOUS, "The document contains text that looks like AI instructions."))
    else:
        po_facts = (matching.PoFacts(po.po_number, po.vendor.name, po.quantity, po.unit_price, po.currency)
                    if po else None)
        flags = matching.match(_facts(inv), po_facts, _is_duplicate(db, inv),
                               s.invoice_price_tolerance_pct, s.low_confidence_threshold)

    inv.po_id = po.id if po else None
    inv.flags = [f.code for f in flags]
    inv.flag_details = [{"code": f.code, "message": f.message} for f in flags]
    if flags:
        inv.exception_summary, inv.exception_summary_source = _exception_summary(po, flags, inv.total)
        transition(db, inv, "flagged", SYSTEM_ACTOR, "match_flagged",
                   f"Flags: {', '.join(inv.flags)}. Summary source: {inv.exception_summary_source}")
    else:
        transition(db, inv, "matched", SYSTEM_ACTOR, "match_clean",
                   f"Three-way match passed against {po.po_number if po else 'n/a'}")
        if inv.total <= s.approval_required_over_usd:
            _approve_and_pay(db, inv, SYSTEM_ACTOR, "auto_approved",
                             f"Clean match and total {inv.total} within threshold {s.approval_required_over_usd}")
    db.commit()
    return inv


# ---- decision --------------------------------------------------------------
def _approve_and_pay(db: Session, inv: Invoice, actor: str, action: str, detail: str) -> None:
    transition(db, inv, "approved", actor, action, detail)
    payment = Payment(invoice_id=inv.id, amount=inv.total, currency=inv.currency or "USD",
                      reference=f"SIM-PAY-{inv.id:06d}", simulated=True)
    db.add(payment)
    db.flush()
    transition(db, inv, "paid", SYSTEM_ACTOR, "payment_simulated",
               f"SIMULATED payment {payment.reference} of {payment.amount} {payment.currency}; no funds moved")


def decide(db: Session, inv: Invoice, decision: str, actor: str, reason: str) -> Invoice:
    if decision not in ("approve", "reject"):
        raise Invalid("decision must be 'approve' or 'reject'")
    done_approve, done_reject = inv.status in ("approved", "paid"), inv.status == "rejected"
    if (decision == "approve" and done_approve) or (decision == "reject" and done_reject):
        return inv  # idempotent
    if done_approve or done_reject:
        raise Conflict(f"Invoice already {inv.status}; it cannot be {decision}d")
    if inv.status not in ("matched", "flagged", "needs_review"):
        raise Conflict(f"Invoice is '{inv.status}'; run the match before deciding")
    reason = (reason or "").strip()
    if decision == "reject":
        if len(reason) < 3:
            raise Invalid("A reason is required to reject an invoice")
        inv.decision_reason = reason
        transition(db, inv, "rejected", actor, "rejected", f"Reason: {reason}")
    else:
        if inv.status == "needs_review" or inv.total is None:
            raise Invalid("Cannot approve an invoice whose fields could not be extracted; reject it and ask for a clean copy")
        if inv.status == "flagged" and len(reason) < 3:
            raise Invalid("A reason is required to approve a flagged invoice")
        inv.decision_reason = reason or None
        override = f" Overriding flags: {', '.join(inv.flags)}." if inv.flags else ""
        _approve_and_pay(db, inv, actor, "approved", f"{actor} approved.{override} Reason: {reason or 'n/a'}")
    db.commit()
    return inv


def timeline(db: Session, inv: Invoice) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).where(AuditLog.entity_type == "invoice", AuditLog.entity_id == inv.id)
                           .order_by(AuditLog.created_at, AuditLog.id)))
