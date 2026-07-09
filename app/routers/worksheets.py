"""
API route handlers for the Texas Worksheet Generator.
"""

import logging
import random
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.constants import FLAG_THRESHOLD, TOPICS_BY_SUBJECT, VALID_QUESTION_TYPES
from app.db import get_db
from app.services.llm import LLM_MODEL, _generate_from_llm
from app.models import Question, GenerateRequest, QuestionOut, RateRequest, WorksheetOut

logger = logging.getLogger("worksheets")

VETTED_THRESHOLD: int = settings.vetted_threshold

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ── Database helpers ───────────────────────────────────────────────────────────

def _count_vetted(db: Session, grade: str, subject: str, topic: str, level: str) -> int:
    return (
        db.query(Question)
        .filter(
            Question.grade == grade,
            Question.subject == subject,
            Question.topic == topic,
            Question.level == level,
            Question.thumbs_up > Question.thumbs_down,
            Question.is_flagged.is_(False),
        )
        .count()
    )


def _fetch_db_questions(
    db: Session, grade: str, subject: str, topic: str, level: str, count: int
) -> list[Question]:
    pool = (
        db.query(Question)
        .filter(
            Question.grade == grade,
            Question.subject == subject,
            Question.topic == topic,
            Question.level == level,
            Question.thumbs_up > Question.thumbs_down,
            Question.is_flagged.is_(False),
        )
        .all()
    )
    if len(pool) <= count:
        return pool
    return random.sample(pool, count)


def _save_questions(
    db: Session,
    grade: str,
    subject: str,
    topic: str,
    level: str,
    raw_questions: list[dict],
    source: str = "llm",
) -> list[Question]:
    saved: list[Question] = []
    for item in raw_questions:
        q_text = (item.get("question") or "").strip()
        a_text = (item.get("answer") or "").strip()
        if not q_text or not a_text:
            continue
        obj = Question(
            grade=grade,
            subject=subject,
            topic=topic,
            level=level,
            question_text=q_text,
            answer_text=a_text,
            source=source,
            teks_code=(item.get("teks_code") or "").strip(),
        )
        db.add(obj)
        saved.append(obj)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    for obj in saved:
        db.refresh(obj)
    return saved


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/", include_in_schema=False)
async def serve_frontend(request: Request):
    return templates.TemplateResponse(request, "index.html")


@router.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@router.get("/api/topics")
async def get_topics():
    """Return the full subject → topics mapping so the frontend can stay in sync."""
    return TOPICS_BY_SUBJECT


@router.get("/api/question-types")
async def get_question_types():
    """Return supported question type options."""
    return VALID_QUESTION_TYPES


@router.post("/api/generate", response_model=WorksheetOut)
async def generate_worksheet(
    req: GenerateRequest,
    db: Session = Depends(get_db),
):
    """
    Hybrid worksheet generation:
      • vetted DB questions >= VETTED_THRESHOLD  → pull from library
      • vetted DB questions <  VETTED_THRESHOLD  → generate via LLM
    """
    grade, subject, topic, level, count, question_types = (
        req.grade, req.subject, req.topic, req.level, req.count, req.question_types
    )
    vetted = _count_vetted(db, grade, subject, topic, level)
    logger.info(
        "Vetted for %s / %s / %s / %s: %d (threshold %d)",
        grade, subject, topic, level, vetted, VETTED_THRESHOLD,
    )

    if vetted >= VETTED_THRESHOLD:
        logger.info("Sourcing from database")
        db_qs = _fetch_db_questions(db, grade, subject, topic, level, count)
        source = "database"
        questions_out = [
            QuestionOut(
                id=q.id, question=q.question_text, answer=q.answer_text,
                grade=q.grade, subject=q.subject, topic=q.topic, level=q.level,
                thumbs_up=q.thumbs_up, thumbs_down=q.thumbs_down,
                teks_code=q.teks_code or "",
            )
            for q in db_qs
        ]
    else:
        logger.info("Sourcing from LLM (%s)", LLM_MODEL)
        raw = await _generate_from_llm(grade, subject, topic, level, count, question_types)
        saved = _save_questions(db, grade, subject, topic, level, raw, "llm")
        source = "llm"
        questions_out = [
            QuestionOut(
                id=q.id, question=q.question_text, answer=q.answer_text,
                grade=q.grade, subject=q.subject, topic=q.topic, level=q.level,
                thumbs_up=q.thumbs_up, thumbs_down=q.thumbs_down,
                teks_code=q.teks_code or "",
            )
            for q in saved
        ]

    return WorksheetOut(
        source=source,
        grade=grade,
        subject=subject,
        topic=topic,
        level=level,
        questions=questions_out,
        generated_at=datetime.utcnow().isoformat(),
    )


@router.post("/api/rate")
async def rate_question(req: RateRequest, db: Session = Depends(get_db)):
    """Apply a thumbs-up or thumbs-down rating. Auto-flag heavily negative questions."""
    q = db.query(Question).filter(Question.id == req.question_id).first()
    if q is None:
        raise HTTPException(status_code=404, detail="Question not found.")

    if req.rating == "up":
        q.thumbs_up += 1
    else:
        q.thumbs_down += 1
        if req.reason:
            q.flag_reason = req.reason[:100]
        if q.thumbs_down >= FLAG_THRESHOLD and q.thumbs_down > q.thumbs_up * 2:
            q.is_flagged = True
            logger.info(
                "Question %d auto-flagged (down=%d, up=%d)",
                q.id, q.thumbs_down, q.thumbs_up,
            )

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Database write failed.")

    return {
        "status": "ok",
        "question_id": q.id,
        "thumbs_up": q.thumbs_up,
        "thumbs_down": q.thumbs_down,
        "is_flagged": q.is_flagged,
        "reason": q.flag_reason or "",
    }


@router.get("/api/stats")
async def get_stats(db: Session = Depends(get_db)):
    """Return question library statistics."""
    total = db.query(Question).count()
    vetted = (
        db.query(Question)
        .filter(
            Question.thumbs_up > Question.thumbs_down,
            Question.is_flagged.is_(False),
        )
        .count()
    )
    flagged = db.query(Question).filter(Question.is_flagged.is_(True)).count()

    by_grade_subject: dict[str, int] = {}
    for q in db.query(Question).all():
        key = f"{q.grade} — {q.subject}"
        by_grade_subject[key] = by_grade_subject.get(key, 0) + 1

    return {
        "total_questions": total,
        "vetted_questions": vetted,
        "flagged_questions": flagged,
        "by_grade_subject": by_grade_subject,
    }
