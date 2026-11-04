import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["VULTR_INFERENCE_API_KEY"] = ""
os.environ["VULTR_INFERENCE_MODEL"] = ""
os.environ["APPROVAL_REQUIRED_OVER_USD"] = "5000"
os.environ["INVOICE_PRICE_TOLERANCE_PCT"] = "2.0"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.db import Base, get_db
from app.main import app


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    engine.dispose()


@pytest.fixture()
def db(session_factory):
    s = session_factory()
    yield s
    s.close()


@pytest.fixture()
def client(session_factory, tmp_path, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path / "uploads"))

    def _get_db():
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def vendors(db):
    from app.models import Vendor

    rows = [
        Vendor(name="Alpha IT", category="it_hardware", rating=4.5, email="a@x.test"),
        Vendor(name="Beta IT", category="it_hardware", rating=3.0, email="b@x.test"),
        Vendor(name="Gamma Supply", category="general", rating=4.0, email="g@x.test"),
    ]
    db.add_all(rows)
    db.commit()
    return rows
