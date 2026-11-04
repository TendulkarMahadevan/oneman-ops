#!/usr/bin/env python3
"""End-to-end smoke test against a running deployment.

    python scripts/smoke_test.py https://ops.example.com      # public URL (goes through the /api proxy)
    python scripts/smoke_test.py http://localhost:8000 --direct # backend directly

Needs only httpx. Requires the demo seed (`python -m app.seed`) and a configured LLM, because it uploads
the sample invoices in samples/ which are extracted by the model. Creates new records on every run; it
never edits the database directly. Exit code 0 = every check passed.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
failures: list[str] = []


def check(ok: bool, msg: str) -> None:
    print(("  PASS  " if ok else "  FAIL  ") + msg)
    if not ok:
        failures.append(msg)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("base_url")
    ap.add_argument("--direct", action="store_true", help="talk to the backend without the /api prefix")
    args = ap.parse_args()
    base = args.base_url.rstrip("/") + ("" if args.direct else "/api")
    c = httpx.Client(base_url=base, timeout=120, follow_redirects=True)
    t0 = time.time()

    def call(method: str, path: str, **kw):
        r = c.request(method, path, **kw)
        if r.status_code >= 400:
            print(f"  HTTP {r.status_code} on {method} {path}: {r.text[:300]}")
        return r

    print("Health")
    h = call("GET", "/health").json()
    check(h["database"] == "ok", "database reachable")
    check(h["llm"] == "ok", f"Vultr inference reachable ({h['llm']})")

    print("Procurement: request -> quotes -> compare -> approve -> PO")
    title = f"Smoke test laptops {int(time.time())}"
    r = call("POST", "/procurement/requests", json={"title": title, "item": "Developer laptop", "category": "it_hardware",
                                                    "quantity": 10, "estimated_unit_price": "1400", "requester": "smoke-test"})
    check(r.status_code == 201, "request created")
    rid = r.json()["id"]
    q = call("POST", f"/procurement/requests/{rid}/quotes", json={"simulate": True})
    check(q.status_code == 201 and len(q.json()) >= 2, "simulated quotes added")
    cmp = call("POST", f"/procurement/requests/{rid}/compare").json()
    check(cmp["status"] == "awaiting_approval", "over-threshold order held for approval")
    check(all(x["rationale"] for x in cmp["ranked"]), "every quote has a rationale")
    d = call("POST", f"/procurement/requests/{rid}/approve", json={"approver": "smoke-test"}).json()
    check(d["status"] == "po_created" and d["purchase_order"] is not None, f"PO issued ({(d['purchase_order'] or {}).get('po_number')})")
    check(len(d["timeline"]) >= 6, "audit timeline recorded")

    print("Invoices: upload -> extract -> match")
    expectations = {
        "sample_clean_PO-1002.pdf": ("matched", []),
        "sample_price_mismatch_PO-1001.pdf": ("flagged", ["PRICE_VARIANCE"]),
        "sample_qty_mismatch_PO-1003.pdf": ("flagged", ["QTY_MISMATCH"]),
        "sample_prompt_injection_PO-1003.txt": ("flagged", ["SUSPICIOUS_CONTENT"]),
    }
    uploaded: dict[str, dict] = {}
    for name, (status, flags) in expectations.items():
        path = SAMPLES / name
        r = call("POST", "/invoices/upload", files={"file": (name, path.read_bytes())}, data={"actor": "smoke-test"})
        if r.status_code != 201:
            check(False, f"{name}: upload")
            continue
        inv = call("POST", f"/invoices/{r.json()['id']}/match").json()
        uploaded[name] = inv
        got = set(inv["flags"] or [])
        check(inv["status"] == status and set(flags) <= got and (name.startswith("sample_prompt") or got == set(flags)),
              f"{name}: {inv['status']} {sorted(got)}")
        if status == "flagged":
            check(bool(inv["exception_summary"]), f"{name}: exception summary present")

    print("Duplicate detection: re-upload the clean invoice")
    r = call("POST", "/invoices/upload", files={"file": ("sample_clean_PO-1002.pdf", (SAMPLES / "sample_clean_PO-1002.pdf").read_bytes())})
    dup = call("POST", f"/invoices/{r.json()['id']}/match").json()
    check("DUPLICATE_INVOICE" in (dup["flags"] or []), f"duplicate flagged {dup['flags']}")

    print("Human exception decision")
    pm = uploaded.get("sample_price_mismatch_PO-1001.pdf")
    if pm:
        bad = call("POST", f"/invoices/{pm['id']}/decision", json={"decision": "approve", "actor": "smoke-test"})
        check(bad.status_code == 422, "approving a flagged invoice without a reason is refused")
        ok = call("POST", f"/invoices/{pm['id']}/decision", json={"decision": "reject", "actor": "smoke-test", "reason": "Price differs from PO; requesting credit note"}).json()
        check(ok["status"] == "rejected", "flagged invoice rejected with reason")
    clean = uploaded.get("sample_clean_PO-1002.pdf")
    if clean and clean["status"] == "matched":
        paid = call("POST", f"/invoices/{clean['id']}/decision", json={"decision": "approve", "actor": "smoke-test"}).json()
        check(paid["status"] == "paid" and paid["payment"]["simulated"] is True, "clean invoice approved and paid (simulated)")

    print("Audit log + dashboard")
    audit = call("GET", "/audit?actor=smoke-test&limit=200").json()
    check(len(audit) >= 8, f"audit log contains the run ({len(audit)} rows by smoke-test)")
    check(call("GET", "/dashboard/summary").status_code == 200, "dashboard summary loads")
    check(call("GET", "/approvals").status_code == 200, "approvals queue loads")

    elapsed = time.time() - t0
    check(elapsed < 180, f"full flow finished in {elapsed:.0f}s (< 180s)")
    print(f"\n{'ALL CHECKS PASSED' if not failures else str(len(failures)) + ' CHECK(S) FAILED'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
