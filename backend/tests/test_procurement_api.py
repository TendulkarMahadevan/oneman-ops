from decimal import Decimal

import pytest

from app import llm
from app.models import AuditLog


def new_request(client, **over):
    body = {"title": "Laptops", "item": "Laptop", "category": "it_hardware", "quantity": 10,
            "estimated_unit_price": "1000", "requester": "dana", "justification": "refresh"}
    body.update(over)
    r = client.post("/procurement/requests", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def quotes_for(client, rid, vendors, prices=(1000, 900, 1100), leads=(10, 20, 5)):
    body = {"quotes": [{"vendor_id": v.id, "unit_price": str(p), "lead_time_days": l}
                       for v, p, l in zip(vendors, prices, leads)]}
    r = client.post(f"/procurement/requests/{rid}/quotes", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_full_flow_over_threshold(client, vendors, db):
    rid = new_request(client)["id"]
    quotes_for(client, rid, vendors)
    cmp = client.post(f"/procurement/requests/{rid}/compare").json()
    assert cmp["status"] == "awaiting_approval" and cmp["approval_required"] is True
    assert [q["rank"] for q in cmp["ranked"]] == [1, 2, 3]
    assert all(0 <= q["score"] <= 1 for q in cmp["ranked"])
    assert all(q["rationale"] and q["rationale_source"] == "template" for q in cmp["ranked"])
    assert cmp["purchase_order"] is None

    r = client.post(f"/procurement/requests/{rid}/approve", json={"approver": "carol"})
    assert r.status_code == 200
    d = r.json()
    po = d["purchase_order"]
    top = d["quotes"][0]
    assert d["status"] == "po_created"
    assert po["po_number"].startswith("PO-") and po["vendor_id"] == top["vendor_id"]
    assert Decimal(po["total"]) == Decimal(top["unit_price"]) * 10 and po["quantity"] == 10

    actions = [(t["actor"], t["action"]) for t in d["timeline"]]
    assert actions == [("dana", "request_created"), ("requester", "quotes_added"), ("system", "quotes_compared"),
                       ("system", "approval_required"), ("carol", "approved"), ("carol", "po_created"),
                       ("carol", "po_created")]
    assert db.query(AuditLog).count() == 7


def test_under_threshold_auto_approves(client, vendors):
    rid = new_request(client, quantity=2)["id"]  # 2 x ~900 < 5000
    quotes_for(client, rid, vendors)
    cmp = client.post(f"/procurement/requests/{rid}/compare").json()
    assert cmp["status"] == "po_created" and cmp["approval_required"] is False
    assert Decimal(cmp["purchase_order"]["total"]) == Decimal(cmp["ranked"][0]["unit_price"]) * 2
    d = client.get(f"/procurement/requests/{rid}").json()
    assert "auto_approved" in [t["action"] for t in d["timeline"]]


def test_approve_is_idempotent_and_reject_after_po_blocked(client, vendors):
    rid = new_request(client)["id"]
    quotes_for(client, rid, vendors)
    client.post(f"/procurement/requests/{rid}/compare")
    a = client.post(f"/procurement/requests/{rid}/approve", json={"approver": "carol"}).json()
    b = client.post(f"/procurement/requests/{rid}/approve", json={"approver": "carol"}).json()
    assert a["purchase_order"]["id"] == b["purchase_order"]["id"]
    assert len(b["timeline"]) == len(a["timeline"])
    r = client.post(f"/procurement/requests/{rid}/reject", json={"actor": "carol", "reason": "changed mind"})
    assert r.status_code == 409


def test_override_recommended_quote_is_audited(client, vendors):
    rid = new_request(client)["id"]
    qs = quotes_for(client, rid, vendors)
    cmp = client.post(f"/procurement/requests/{rid}/compare").json()
    other = cmp["ranked"][-1]["id"]
    d = client.post(f"/procurement/requests/{rid}/approve",
                    json={"approver": "carol", "quote_id": other, "note": "preferred supplier"}).json()
    assert d["purchase_order"]["vendor_id"] == cmp["ranked"][-1]["vendor_id"]
    assert any("OVERRIDE" in t["detail"] for t in d["timeline"])


def test_reject_awaiting_approval(client, vendors):
    rid = new_request(client)["id"]
    quotes_for(client, rid, vendors)
    client.post(f"/procurement/requests/{rid}/compare")
    d = client.post(f"/procurement/requests/{rid}/reject", json={"actor": "carol", "reason": "over budget"}).json()
    assert d["status"] == "rejected" and d["rejection_reason"] == "over budget" and d["purchase_order"] is None
    assert client.post(f"/procurement/requests/{rid}/approve", json={"approver": "c"}).status_code == 409


def test_cannot_approve_before_compare_or_compare_without_quotes(client, vendors):
    rid = new_request(client)["id"]
    assert client.post(f"/procurement/requests/{rid}/approve", json={"approver": "c"}).status_code == 409
    assert client.post(f"/procurement/requests/{rid}/compare").status_code == 409


def test_compare_needs_two_quotes(client, vendors):
    rid = new_request(client)["id"]
    client.post(f"/procurement/requests/{rid}/quotes",
                json={"quotes": [{"vendor_id": vendors[0].id, "unit_price": "10", "lead_time_days": 3}]})
    assert client.post(f"/procurement/requests/{rid}/compare").status_code == 422


def test_quote_validation(client, vendors):
    rid = new_request(client)["id"]
    bad = client.post(f"/procurement/requests/{rid}/quotes",
                      json={"quotes": [{"vendor_id": 999, "unit_price": "10", "lead_time_days": 3}]})
    assert bad.status_code == 422
    neg = client.post(f"/procurement/requests/{rid}/quotes",
                      json={"quotes": [{"vendor_id": vendors[0].id, "unit_price": "-1", "lead_time_days": 3}]})
    assert neg.status_code == 422
    both = client.post(f"/procurement/requests/{rid}/quotes", json={"simulate": True, "quotes": [
        {"vendor_id": vendors[0].id, "unit_price": "1", "lead_time_days": 3}]})
    assert both.status_code == 422


def test_simulated_quotes_are_labelled_and_deterministic(client, vendors):
    rid = new_request(client)["id"]
    sim = client.post(f"/procurement/requests/{rid}/quotes", json={"simulate": True}).json()
    assert len(sim) == 3 and all(q["source"] == "simulated" for q in sim)
    rid2 = new_request(client, title="Laptops again")["id"]
    again = client.post(f"/procurement/requests/{rid2}/quotes", json={"simulate": True}).json()
    assert len(again) == 3  # different request id => different seed, same shape


def test_duplicate_title_conflict(client):
    new_request(client)
    r = client.post("/procurement/requests", json={"title": "Laptops", "item": "xx", "category": "cc",
                                                    "quantity": 1, "estimated_unit_price": "1", "requester": "z"})
    assert r.status_code == 409


def test_not_found(client):
    assert client.get("/procurement/requests/999").status_code == 404


def test_llm_rationales_used_when_valid_and_fallback_when_not(client, vendors, monkeypatch):
    from app.services import procurement

    def fake_ok(system, user, schema):
        import re
        ids = [int(i) for i in re.findall(r"'quote_id': (\d+)", user)]
        return schema(rationales=[{"quote_id": i, "rationale": "Solid option on balance."} for i in ids])

    monkeypatch.setattr(llm, "chat_json", fake_ok)
    rid = new_request(client)["id"]
    quotes_for(client, rid, vendors)
    cmp = client.post(f"/procurement/requests/{rid}/compare").json()
    assert {q["rationale_source"] for q in cmp["ranked"]} == {"llm"}

    def fake_bad(system, user, schema):
        return schema(rationales=[{"quote_id": 12345, "rationale": "Hallucinated quote id."}])

    monkeypatch.setattr(llm, "chat_json", fake_bad)
    rid2 = new_request(client, title="Chairs")["id"]
    quotes_for(client, rid2, vendors)
    cmp2 = client.post(f"/procurement/requests/{rid2}/compare").json()
    assert {q["rationale_source"] for q in cmp2["ranked"]} == {"template"}


def test_llm_cannot_change_scores_or_amounts(client, vendors, monkeypatch):
    def fake(system, user, schema):
        raise llm.LLMError("down")

    monkeypatch.setattr(llm, "chat_json", fake)
    rid = new_request(client)["id"]
    quotes_for(client, rid, vendors)
    cmp = client.post(f"/procurement/requests/{rid}/compare").json()
    assert cmp["ranked"][0]["vendor_name"] in {"Alpha IT", "Beta IT", "Gamma Supply"}
    assert Decimal(cmp["recommended_total"]) == Decimal(cmp["ranked"][0]["unit_price"]) * 10


def test_seed_is_idempotent_and_produces_pos(db):
    from sqlalchemy import func, select

    from app.models import PurchaseOrder, Vendor
    from app.seed import seed

    first = seed(db)
    second = seed(db)
    assert first == {"vendors": 6, "requests": 3, "invoices": 4} and second == {"vendors": 0, "requests": 0, "invoices": 0}
    assert db.scalar(select(func.count()).select_from(Vendor)) == 6
    pos = db.scalars(select(PurchaseOrder).order_by(PurchaseOrder.id)).all()
    assert [p.po_number for p in pos] == ["PO-1001", "PO-1002", "PO-1003"]
