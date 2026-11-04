from app.seed import seed


def test_dashboard_and_approvals_after_seed(db, client):
    seed(db)
    d = client.get("/dashboard/summary").json()
    assert d["flagged_invoices"] == 3 and d["awaiting_approval"] == 0 and d["open_requests"] == 0
    assert d["invoices_total"] == 4 and d["touchless_invoices"] == 1
    assert float(d["spend_this_month_usd"]) == 17100 + 8670 + 3680
    assert d["avg_cycle_time_hours"] is not None and len(d["recent_activity"]) == 12
    items = client.get("/approvals").json()
    assert {(i["kind"], tuple(i["flags"])) for i in items} == {
        ("invoice", ("PRICE_VARIANCE",)), ("invoice", ("QTY_MISMATCH",)), ("invoice", ("DUPLICATE_INVOICE",))}


def test_approvals_includes_requests_over_threshold(client, vendors):
    body = {"title": "Big order", "item": "Laptop", "category": "it_hardware", "quantity": 10,
            "estimated_unit_price": "1000", "requester": "dana"}
    rid = client.post("/procurement/requests", json=body).json()["id"]
    client.post(f"/procurement/requests/{rid}/quotes", json={"simulate": True})
    client.post(f"/procurement/requests/{rid}/compare")
    items = client.get("/approvals").json()
    assert [(i["kind"], i["id"]) for i in items] == [("request", rid)]
    assert client.get("/dashboard/summary").json()["awaiting_approval"] == 1


def test_audit_filters(db, client):
    seed(db)
    all_rows = client.get("/audit?limit=500").json()
    assert all_rows == sorted(all_rows, key=lambda r: (r["created_at"], r["id"]), reverse=True)
    inv = client.get("/audit?entity_type=invoice").json()
    assert inv and {r["entity_type"] for r in inv} == {"invoice"}
    assert {r["action"] for r in client.get("/audit?action=match_flagged").json()} == {"match_flagged"}
    assert all("PRICE_VARIANCE" in r["detail"] for r in client.get("/audit?q=PRICE_VARIANCE").json())
    assert client.get("/audit?limit=2&offset=1").json() == all_rows[1:3]
    facets = client.get("/audit/facets").json()
    assert "seed-approver" in facets["actors"] and "system" in facets["actors"]


def test_health_reports_degraded_without_llm(client):
    h = client.get("/health").json()
    assert h["database"] == "ok" and h["llm"] == "not_configured" and h["status"] == "degraded"
    assert h["llm_configured"] is False
