from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db import init_db
from app.errors import DomainError
from app.routers import invoices, ops, procurement
from app.state_machine import IllegalTransition

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_settings()  # fail fast on invalid configuration
    init_db()
    yield


app = FastAPI(title="OneManOps", version="0.1.0", lifespan=lifespan)

_origins = [o.strip() for o in get_settings().cors_origins.split(",") if o.strip()]
if _origins:
    app.add_middleware(CORSMiddleware, allow_origins=_origins, allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(DomainError)
async def _domain_error(_: Request, exc: DomainError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(IllegalTransition)
async def _illegal(_: Request, exc: IllegalTransition):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


app.include_router(procurement.router)
app.include_router(invoices.router)
app.include_router(ops.router)
