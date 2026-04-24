import os
import pytest
from sqlalchemy import text
from starlette.testclient import TestClient
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from app.main import app
from app.database import SessionLocal


@pytest.fixture(autouse=True)
def reset_db():
    db = SessionLocal()
    try:
        db.execute(text("TRUNCATE links RESTART IDENTITY CASCADE"))
        db.commit()
    finally:
        db.close()


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
