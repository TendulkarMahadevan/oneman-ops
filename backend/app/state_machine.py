"""The single place where statuses change.

`transition()` validates the move against an explicit table and writes the AuditLog row in the same
unit of work, so no state change can happen without an audit entry.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditLog, Invoice, PurchaseOrder, PurchaseRequest

REQUEST_TRANSITIONS: dict[str, frozenset[str]] = {
    "open": frozenset({"quoted", "rejected"}),
    "quoted": frozenset({"quoted", "compared", "rejected"}),
    "compared": frozenset({"awaiting_approval", "approved", "rejected"}),
    "awaiting_approval": frozenset({"approved", "rejected"}),
    "approved": frozenset({"po_created"}),
    "po_created": frozenset(),
    "rejected": frozenset(),
}

INVOICE_TRANSITIONS: dict[str, frozenset[str]] = {
    "uploaded": frozenset({"extracted", "needs_review"}),
    "extracted": frozenset({"matched", "flagged"}),
    "needs_review": frozenset({"flagged", "rejected"}),
    "matched": frozenset({"approved", "rejected"}),
    "flagged": frozenset({"approved", "rejected"}),
    "approved": frozenset({"paid"}),
    "paid": frozenset(),
    "rejected": frozenset(),
}

_TABLES: dict[str, dict[str, frozenset[str]]] = {
    "request": REQUEST_TRANSITIONS,
    "invoice": INVOICE_TRANSITIONS,
}


class IllegalTransition(Exception):
    def __init__(self, kind: str, current: str, target: str) -> None:
        self.kind, self.current, self.target = kind, current, target
        super().__init__(f"Illegal {kind} transition: {current} -> {target}")


def can_transition(kind: str, current: str, target: str) -> bool:
    return target in _TABLES[kind].get(current, frozenset())


def _kind_of(entity: object) -> str:
    if isinstance(entity, PurchaseRequest):
        return "request"
    if isinstance(entity, Invoice):
        return "invoice"
    raise TypeError(f"No state machine for {type(entity).__name__}")


def write_audit(db: Session, entity_type: str, entity_id: int, actor: str, action: str, detail: str = "") -> AuditLog:
    row = AuditLog(entity_type=entity_type, entity_id=entity_id, actor=actor, action=action, detail=detail)
    db.add(row)
    return row


def transition(db: Session, entity: PurchaseRequest | Invoice, target: str, actor: str, action: str, detail: str = "") -> None:
    """Move `entity` to `target` or raise IllegalTransition. Always writes an audit row."""
    kind = _kind_of(entity)
    if not can_transition(kind, entity.status, target):
        raise IllegalTransition(kind, entity.status, target)
    previous = entity.status
    entity.status = target
    db.flush()
    suffix = f"[{previous} -> {target}]"
    write_audit(db, kind, entity.id, actor, action, f"{detail} {suffix}".strip())


def audit_po(db: Session, po: PurchaseOrder, actor: str, action: str, detail: str = "") -> None:
    """POs have no lifecycle yet (always `issued`); creation is audited here."""
    write_audit(db, "purchase_order", po.id, actor, action, detail)
