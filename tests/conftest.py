"""
Shared test fixtures for the Texas Worksheet Generator.

A throw-away SQLite database is created per test session and the app is
exercised in-process via httpx ASGITransport (no running service needed).
"""

import os
import tempfile

# ── Point SQLAlchemy at a throw-away DB BEFORE importing the app ──────────────
_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB.name}"
os.environ.setdefault("SITE_URL", "http://localhost")
os.environ.setdefault("ROOT_PATH", "")

import httpx
import pytest
import pytest_asyncio

from app.db import SessionLocal, init_db, migrate_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Question  # noqa: E402

# Create schema in the temp DB (lifespan is not run by ASGITransport)
init_db()
migrate_db()

SKIP_LLM = bool(os.getenv("SKIP_LLM"))


@pytest.fixture(scope="session")
def skip_llm() -> bool:
    return SKIP_LLM


@pytest.fixture()
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest_asyncio.fixture()
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", timeout=120.0
    ) as ac:
        yield ac


@pytest.fixture()
def seed_question():
    """Factory: insert a question into the temp DB and return its ID."""

    def _seed(grade="Grade 4", subject="Social Studies",
              topic="History", level="On-Level",
              thumbs_up=0, thumbs_down=0) -> int:
        session = SessionLocal()
        q = Question(
            grade=grade, subject=subject, topic=topic, level=level,
            question_text="Who was the first president of Texas?",
            answer_text="David G. Burnet (provisional) / Sam Houston (elected)",
            source="llm", thumbs_up=thumbs_up, thumbs_down=thumbs_down,
        )
        session.add(q)
        session.commit()
        qid = q.id
        session.close()
        return qid

    return _seed


VALID_GENERATE_PAYLOAD = {
    "grade":   "Grade 3",
    "subject": "Mathematics",
    "topic":   "Number and Operations",
    "level":   "On-Level",
    "count":   3,
}


@pytest.fixture()
def valid_generate_payload() -> dict:
    return dict(VALID_GENERATE_PAYLOAD)
