"""Idempotent demo seed: `python -m app.seed`.

Creates vendors, three purchase requests driven through the real workflow (quotes -> compare ->
approval gate -> PO), so every seeded record has a genuine audit trail. Safe to run repeatedly.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal, init_db
from app.models import PurchaseRequest, Vendor
from app.schemas import QuoteIn, RequestCreate
from app.services import procurement as svc

VENDORS = [
    ("Northwind Tech Supply", "it_hardware", 4.6, "sales@northwind-tech.example"),
    ("Apex Computing Ltd", "it_hardware", 4.2, "quotes@apex-computing.example"),
    ("Meridian Office Furnishings", "furniture", 4.4, "orders@meridian-office.example"),
    ("Summit Workspace Co", "furniture", 3.9, "sales@summit-workspace.example"),
    ("Cobalt Cloud Licensing", "software", 4.5, "partners@cobalt-cloud.example"),
    ("Brightline Distribution", "general", 3.8, "support@brightline-dist.example"),
]

# title, item, category, qty, est. unit price, justification, requester, [(vendor, unit price, lead days)]
REQUESTS = [
    ("Developer laptop refresh Q4", "14-inch developer laptop, 32GB RAM", "it_hardware", 12, "1450",
     "Replace 12 laptops past their 4-year lifecycle.", "priya.nair",
     [("Northwind Tech Supply", "1425.00", 9), ("Apex Computing Ltd", "1380.00", 21),
      ("Brightline Distribution", "1490.00", 5)]),
    ("Ergonomic chairs for new floor", "Ergonomic mesh office chair", "furniture", 30, "320",
     "Fit out the 4th floor ahead of the January hires.", "marcus.lee",
     [("Meridian Office Furnishings", "312.50", 14), ("Summit Workspace Co", "289.00", 30),
      ("Brightline Distribution", "335.00", 7)]),
    ("Observability platform seats", "Observability SaaS seat, annual", "software", 40, "95",
     "Consolidate three monitoring tools onto one platform.", "sofia.alvarez",
     [("Cobalt Cloud Licensing", "92.00", 2), ("Brightline Distribution", "99.00", 3)]),
]


def seed(db: Session) -> dict[str, int]:
    created = {"vendors": 0, "requests": 0}
    for name, category, rating, email in VENDORS:
        if not db.scalar(select(Vendor).where(Vendor.name == name)):
            db.add(Vendor(name=name, category=category, rating=rating, email=email))
            created["vendors"] += 1
    db.commit()
    by_name = {v.name: v for v in db.scalars(select(Vendor))}

    for title, item, category, qty, est, why, requester, quotes in REQUESTS:
        if db.scalar(select(PurchaseRequest).where(PurchaseRequest.title == title)):
            continue
        req = svc.create_request(db, RequestCreate(
            title=title, item=item, category=category, quantity=qty, estimated_unit_price=Decimal(est),
            justification=why, requester=requester))
        svc.add_quotes(db, req, [QuoteIn(vendor_id=by_name[v].id, unit_price=Decimal(p), lead_time_days=d)
                                 for v, p, d in quotes], simulated=False, actor=requester)
        req = svc.compare(db, svc.get_request(db, req.id))
        if req.status == "awaiting_approval":
            svc.approve(db, req, "seed-approver", None, "Seeded demo approval")
        created["requests"] += 1
    return created


def main() -> None:
    init_db()
    with SessionLocal() as db:
        print("Seeded:", seed(db))


if __name__ == "__main__":
    main()
