import pytest

from app.models import AuditLog, Invoice, PurchaseRequest
from app.state_machine import IllegalTransition, can_transition, transition


def make_request(db, status="open"):
    r = PurchaseRequest(title="t1", item="x", category="c", quantity=1, estimated_unit_price=1,
                        requester="me", status=status)
    db.add(r)
    db.flush()
    return r


def test_legal_transition_updates_status_and_writes_audit(db):
    r = make_request(db)
    transition(db, r, "quoted", "alice", "quotes_added", "2 quotes")
    db.commit()
    assert r.status == "quoted"
    log = db.query(AuditLog).one()
    assert (log.entity_type, log.actor, log.action) == ("request", "alice", "quotes_added")
    assert "open -> quoted" in log.detail


@pytest.mark.parametrize("start,target", [
    ("open", "po_created"), ("open", "approved"), ("po_created", "rejected"),
    ("rejected", "open"), ("awaiting_approval", "po_created"), ("approved", "rejected"),
])
def test_illegal_request_transitions(db, start, target):
    r = make_request(db, start)
    with pytest.raises(IllegalTransition):
        transition(db, r, target, "x", "y")
    assert r.status == start
    assert db.query(AuditLog).count() == 0


def test_invoice_machine_blocks_pay_before_approval(db):
    inv = Invoice(status="flagged")
    db.add(inv)
    db.flush()
    with pytest.raises(IllegalTransition):
        transition(db, inv, "paid", "x", "pay")
    transition(db, inv, "approved", "x", "approve")
    transition(db, inv, "paid", "x", "pay")


def test_terminal_states_have_no_exits():
    for kind, states in (("request", ["po_created", "rejected"]), ("invoice", ["paid", "rejected"])):
        for s in states:
            for t in ("open", "quoted", "approved", "paid", "rejected", "matched"):
                assert not can_transition(kind, s, t)


def test_unsupported_entity_rejected(db):
    with pytest.raises(TypeError):
        transition(db, object(), "x", "a", "b")
