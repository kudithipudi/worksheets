"""
SQLAlchemy ORM models for the Texas Worksheet Generator.
"""

from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Index
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class Question(Base):
    """Persisted worksheet question with cumulative rating data."""

    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)

    # Classification
    grade = Column(String(20), nullable=False, index=True)
    subject = Column(String(50), nullable=False, index=True)
    topic = Column(String(100), nullable=False, default="General", index=True)
    level = Column(String(20), nullable=False, default="On-Level", index=True)

    # Content
    question_text = Column(Text, nullable=False)
    answer_text = Column(Text, nullable=False)

    # Provenance: "llm" when AI-generated, "db" when pulled from library
    source = Column(String(10), default="llm", nullable=False)

    # Rating counters
    thumbs_up = Column(Integer, default=0, nullable=False)
    thumbs_down = Column(Integer, default=0, nullable=False)

    # Flagged automatically when thumbs_down is disproportionate
    is_flagged = Column(Boolean, default=False, nullable=False)

    # TEKS code tagged by LLM (e.g. "TEKS 3.4A")
    teks_code = Column(String(50), nullable=True, default="")

    # Reason provided when a teacher rates a question as "Needs Work"
    flag_reason = Column(String(100), nullable=True, default="")

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # ── Derived helpers ────────────────────────────────────────────────────────

    @property
    def rating_score(self) -> int:
        return self.thumbs_up - self.thumbs_down

    @property
    def is_vetted(self) -> bool:
        """True when the question has a positive rating and is not flagged."""
        return (
            self.thumbs_up > self.thumbs_down
            and not self.is_flagged
        )

    def __repr__(self) -> str:
        return (
            f"<Question id={self.id} grade={self.grade!r} "
            f"subject={self.subject!r} source={self.source!r}>"
        )


class RateLimitHit(Base):
    """One row per hit against a rate-limited route (sliding-window log)."""

    __tablename__ = "rate_limit_hits"
    __table_args__ = (
        Index("idx_rate_limit_hits_route_ip_time", "route", "ip", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    ip = Column(String(64), nullable=False)
    route = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
