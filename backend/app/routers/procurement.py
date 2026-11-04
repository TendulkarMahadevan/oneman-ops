from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import PurchaseRequest, Vendor
from app.schemas import (ApproveIn, CompareOut, QuoteOut, QuotesCreate, RejectIn, RequestCreate,
                         RequestDetail, RequestSummary, VendorOut)
from app.services import procurement as svc
from app.services import views

router = APIRouter(tags=["procurement"])


@router.get("/vendors", response_model=list[VendorOut])
def list_vendors(db: Session = Depends(get_db)):
    return db.scalars(select(Vendor).order_by(Vendor.name)).all()


@router.get("/procurement/requests", response_model=list[RequestSummary])
def list_requests(status_: str | None = Query(default=None, alias="status"), db: Session = Depends(get_db)):
    stmt = select(PurchaseRequest).order_by(PurchaseRequest.created_at.desc(), PurchaseRequest.id.desc())
    if status_:
        stmt = stmt.where(PurchaseRequest.status == status_)
    return db.scalars(stmt).all()


@router.post("/procurement/requests", response_model=RequestDetail, status_code=status.HTTP_201_CREATED)
def create_request(body: RequestCreate, db: Session = Depends(get_db)):
    req = svc.create_request(db, body)
    return views.request_detail(db, svc.get_request(db, req.id))


@router.get("/procurement/requests/{request_id}", response_model=RequestDetail)
def get_request(request_id: int, db: Session = Depends(get_db)):
    return views.request_detail(db, svc.get_request(db, request_id))


@router.post("/procurement/requests/{request_id}/quotes", response_model=list[QuoteOut],
             status_code=status.HTTP_201_CREATED)
def add_quotes(request_id: int, body: QuotesCreate, db: Session = Depends(get_db)):
    req = svc.get_request(db, request_id)
    created = svc.add_quotes(db, req, body.quotes, body.simulate, actor="requester")
    req = svc.get_request(db, request_id)
    new_ids = {q.id for q in created}
    return [views.quote_out(req, q) for q in req.quotes if q.id in new_ids]


@router.post("/procurement/requests/{request_id}/compare", response_model=CompareOut)
def compare(request_id: int, db: Session = Depends(get_db)):
    svc.compare(db, svc.get_request(db, request_id))
    return views.compare_out(svc.get_request(db, request_id))


@router.post("/procurement/requests/{request_id}/approve", response_model=RequestDetail)
def approve(request_id: int, body: ApproveIn, db: Session = Depends(get_db)):
    svc.approve(db, svc.get_request(db, request_id), body.approver, body.quote_id, body.note)
    return views.request_detail(db, svc.get_request(db, request_id))


@router.post("/procurement/requests/{request_id}/reject", response_model=RequestDetail)
def reject(request_id: int, body: RejectIn, db: Session = Depends(get_db)):
    svc.reject(db, svc.get_request(db, request_id), body.actor, body.reason)
    return views.request_detail(db, svc.get_request(db, request_id))
