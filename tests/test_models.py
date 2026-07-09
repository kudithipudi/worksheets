"""Database model tests against the temp SQLite DB."""

from sqlalchemy import inspect

import app.db as db_module
from app.db import migrate_db
from app.models import Question


class TestDatabaseModel:

    def test_create_and_retrieve_question(self, db_session):
        q = Question(
            grade="Grade 1", subject="Science",
            topic="Earth and Space", level="On-Level",
            question_text="What is the sun?", answer_text="A star.",
            source="llm",
        )
        db_session.add(q)
        db_session.commit()
        fetched = db_session.query(Question).filter_by(id=q.id).first()
        assert fetched.topic == "Earth and Space"
        assert fetched.level == "On-Level"

    def test_default_rating_values(self, db_session):
        q = Question(
            grade="Grade 2", subject="Writing",
            topic="Personal Narrative", level="Approaching",
            question_text="Q", answer_text="A", source="llm",
        )
        db_session.add(q)
        db_session.commit()
        db_session.refresh(q)
        assert q.thumbs_up == 0
        assert q.thumbs_down == 0
        assert not q.is_flagged

    def test_is_vetted_property(self, db_session):
        q = Question(
            grade="Grade 3", subject="Mathematics",
            topic="Data Analysis", level="On-Level",
            question_text="Q", answer_text="A", source="llm",
            thumbs_up=3, thumbs_down=1,
        )
        db_session.add(q)
        db_session.commit()
        assert q.is_vetted

    def test_teks_code_and_flag_reason_columns_exist(self):
        cols = {c["name"] for c in inspect(db_module.engine).get_columns("questions")}
        assert "teks_code" in cols
        assert "flag_reason" in cols

    def test_teks_code_stored(self, db_session):
        q = Question(
            grade="Grade 5", subject="Mathematics",
            topic="Proportionality", level="Advanced",
            question_text="Q", answer_text="A", source="llm",
            teks_code="TEKS 5.4E",
        )
        db_session.add(q)
        db_session.commit()
        db_session.refresh(q)
        assert q.teks_code == "TEKS 5.4E"

    def test_flag_reason_stored(self, db_session):
        q = Question(
            grade="Grade 6", subject="Science",
            topic="Matter and Energy", level="On-Level",
            question_text="Q", answer_text="A", source="llm",
            flag_reason="Unclear wording",
        )
        db_session.add(q)
        db_session.commit()
        db_session.refresh(q)
        assert q.flag_reason == "Unclear wording"

    def test_migrate_db_idempotent(self):
        """Running migrate_db() twice must not raise."""
        migrate_db()
        migrate_db()
