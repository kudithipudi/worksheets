"""
Texas Worksheet Generator – Test Suite
=======================================
Covers: DB models, schema validation, prompt builder, LLM parser, and live API routes.

Usage:
    # Default: Unix socket (service must be running)
    venv/bin/python tests.py

    # Verbose
    venv/bin/python tests.py -v

    # Against live HTTPS
    BASE_URL=https://lab.kudithipudi.org/worksheets venv/bin/python tests.py

    # Skip slow/costly LLM generate tests
    SKIP_LLM=1 venv/bin/python tests.py -v
"""

import os
import sys
import tempfile
import unittest

import httpx

# ── Point SQLAlchemy at a throw-away DB for direct-import tests ────────────────
_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP_DB.name}")
os.environ.setdefault("OPENROUTER_API_KEY", "test-key-not-real")
os.environ.setdefault("SITE_URL", "http://localhost")

import database as db_module
from database import SessionLocal, init_db, migrate_db
from constants import TOPICS_BY_SUBJECT, VALID_GRADES, VALID_LEVELS, VALID_QUESTION_TYPES, VALID_SUBJECTS
from llm import _build_teks_prompt, _parse_llm_response
from models import Question

# Re-initialise against the temp DB
db_module.engine = db_module.create_engine(
    os.environ["DATABASE_URL"],
    connect_args={"check_same_thread": False},
)
db_module.SessionLocal = db_module.sessionmaker(
    autocommit=False, autoflush=False, bind=db_module.engine
)
init_db()
migrate_db()

# ── HTTP client (Unix socket or BASE_URL) ──────────────────────────────────────
SOCKET = "/var/www/worksheets/worksheets.sock"
SERVICE_DB = "/var/www/worksheets/worksheets.db"
BASE_URL = os.getenv("BASE_URL", "http://worksheets")
_USE_SOCKET = os.path.exists(SOCKET) and not os.getenv("BASE_URL")

if _USE_SOCKET:
    transport = httpx.HTTPTransport(uds=SOCKET)
    client = httpx.Client(transport=transport, base_url=BASE_URL, timeout=120.0)
else:
    client = httpx.Client(
        base_url=os.getenv("BASE_URL", "https://lab.kudithipudi.org/worksheets"),
        timeout=120.0,
    )

SKIP_LLM = bool(os.getenv("SKIP_LLM"))

# ── Service-DB session (for seeding questions into the running service's DB) ──
# When testing against the local socket, seed into the production DB so that
# question IDs are valid for the live /api/rate endpoint.
if _USE_SOCKET and os.path.exists(SERVICE_DB):
    _svc_engine = db_module.create_engine(
        f"sqlite:///{SERVICE_DB}",
        connect_args={"check_same_thread": False},
    )
    _ServiceSession = db_module.sessionmaker(
        autocommit=False, autoflush=False, bind=_svc_engine
    )
else:
    _ServiceSession = SessionLocal  # fall back to temp DB


# ── Helpers ───────────────────────────────────────────────────────────────────

VALID_GENERATE_PAYLOAD = {
    "grade":   "Grade 3",
    "subject": "Mathematics",
    "topic":   "Number and Operations",
    "level":   "On-Level",
    "count":   3,
}


def _seed_question(grade="Grade 4", subject="Social Studies",
                   topic="History", level="On-Level",
                   thumbs_up=0, thumbs_down=0) -> int:
    """Insert a question into the service DB (or temp DB) and return its ID."""
    session = _ServiceSession()
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


# ══════════════════════════════════════════════════════════════════════════════
# 1. Curriculum constants
# ══════════════════════════════════════════════════════════════════════════════

class TestCurriculumConstants(unittest.TestCase):

    def test_grade_count(self):
        self.assertEqual(len(VALID_GRADES), 14)

    def test_grade_includes_boundaries(self):
        self.assertIn("Pre-K", VALID_GRADES)
        self.assertIn("Grade 12", VALID_GRADES)

    def test_subject_count(self):
        self.assertEqual(len(VALID_SUBJECTS), 5)

    def test_all_subjects_have_topics(self):
        for s in VALID_SUBJECTS:
            self.assertIn(s, TOPICS_BY_SUBJECT, f"Subject '{s}' missing from TOPICS_BY_SUBJECT")
            self.assertGreater(len(TOPICS_BY_SUBJECT[s]), 0, f"Subject '{s}' has no topics")

    def test_four_levels(self):
        self.assertEqual(VALID_LEVELS, ["Approaching", "On-Level", "Advanced", "GT/Enrichment"])

    def test_question_types_list(self):
        expected = ["Multiple Choice", "Short Answer", "Fill-in-the-Blank",
                    "Matching", "True/False", "Mixed"]
        self.assertEqual(VALID_QUESTION_TYPES, expected)

    def test_teks_strand_names(self):
        self.assertIn("Number and Operations", TOPICS_BY_SUBJECT["Mathematics"])
        self.assertIn("Algebraic Reasoning", TOPICS_BY_SUBJECT["Mathematics"])
        self.assertIn("Organisms and Environments", TOPICS_BY_SUBJECT["Science"])
        self.assertIn("Government and Citizenship", TOPICS_BY_SUBJECT["Social Studies"])
        self.assertIn("Foundational Language Skills", TOPICS_BY_SUBJECT["Reading & ELA"])

    def test_no_duplicate_topics_per_subject(self):
        for subj, topics in TOPICS_BY_SUBJECT.items():
            self.assertEqual(len(topics), len(set(topics)), f"Duplicate topics in {subj}")


# ══════════════════════════════════════════════════════════════════════════════
# 2. Prompt builder
# ══════════════════════════════════════════════════════════════════════════════

class TestPromptBuilder(unittest.TestCase):

    def _prompt(self, level="On-Level", question_types=None):
        return _build_teks_prompt(
            "Grade 5", "Mathematics", "Algebraic Reasoning", level, 5,
            question_types=question_types,
        )

    def test_contains_teks_mention(self):
        self.assertIn("TEKS", self._prompt())

    def test_contains_grade(self):
        self.assertIn("Grade 5", self._prompt())

    def test_contains_topic(self):
        self.assertIn("Algebraic Reasoning", self._prompt())

    def test_approaching_guidance(self):
        p = self._prompt("Approaching")
        self.assertIn("APPROACHING", p)
        self.assertIn("scaffolded", p.lower())

    def test_on_level_guidance(self):
        p = self._prompt("On-Level")
        self.assertIn("ON-LEVEL", p)

    def test_advanced_guidance(self):
        p = self._prompt("Advanced")
        self.assertIn("ADVANCED", p)
        self.assertIn("STAAR", p)

    def test_gt_guidance(self):
        p = self._prompt("GT/Enrichment")
        self.assertIn("GT/ENRICHMENT", p)
        self.assertIn("synthesis", p.lower())

    def test_count_in_prompt(self):
        p = _build_teks_prompt("Grade 1", "Science", "Earth and Space", "On-Level", 7)
        self.assertIn("7", p)

    def test_json_template_present(self):
        self.assertIn('"questions"', self._prompt())

    def test_teks_code_in_json_schema(self):
        self.assertIn("teks_code", self._prompt())

    def test_specific_question_types_in_prompt(self):
        p = self._prompt("On-Level", question_types=["Multiple Choice", "Short Answer"])
        self.assertIn("Multiple Choice", p)
        self.assertIn("Short Answer", p)

    def test_mixed_question_types_uses_all_formats(self):
        p = self._prompt("On-Level", question_types=["Mixed"])
        # Mixed should not list specific restricted types
        self.assertNotIn("Use ONLY these question formats", p)


# ══════════════════════════════════════════════════════════════════════════════
# 3. LLM response parser
# ══════════════════════════════════════════════════════════════════════════════

MOCK_LLM_QUESTIONS = [
    {"question": f"What is {i} + {i}?", "answer": str(i * 2),
     "type": "short_answer", "teks_code": f"TEKS 3.{i}A"}
    for i in range(1, 6)
]

import json as _json
MOCK_LLM_RESPONSE = _json.dumps({"questions": MOCK_LLM_QUESTIONS})


class TestLLMResponseParser(unittest.TestCase):

    def test_bare_json(self):
        result = _parse_llm_response(MOCK_LLM_RESPONSE)
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0]["question"], "What is 1 + 1?")

    def test_json_in_code_fence(self):
        wrapped = f"```json\n{MOCK_LLM_RESPONSE}\n```"
        result = _parse_llm_response(wrapped)
        self.assertEqual(len(result), 5)

    def test_strips_think_tags(self):
        content = f"<think>internal reasoning here</think>\n{MOCK_LLM_RESPONSE}"
        result = _parse_llm_response(content)
        self.assertEqual(len(result), 5)

    def test_strips_multiple_think_tags(self):
        content = f"<think>step 1</think><think>step 2</think>{MOCK_LLM_RESPONSE}"
        result = _parse_llm_response(content)
        self.assertEqual(len(result), 5)

    def test_raises_on_garbage(self):
        with self.assertRaises(ValueError):
            _parse_llm_response("this is not json at all")

    def test_raises_on_unparseable_content(self):
        with self.assertRaises(ValueError):
            _parse_llm_response('{"data": "not_a_list"}')

    def test_bare_array_format(self):
        """Model sometimes returns a bare [...] array instead of {"questions": [...]}"""
        bare = _json.dumps(MOCK_LLM_QUESTIONS)
        result = _parse_llm_response(bare)
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0]["question"], "What is 1 + 1?")

    def test_strips_thinking_tags(self):
        content = f"<thinking>internal reasoning</thinking>\n{MOCK_LLM_RESPONSE}"
        result = _parse_llm_response(content)
        self.assertEqual(len(result), 5)

    def test_teks_code_preserved(self):
        result = _parse_llm_response(MOCK_LLM_RESPONSE)
        self.assertEqual(result[0]["teks_code"], "TEKS 3.1A")


# ══════════════════════════════════════════════════════════════════════════════
# 4. Database model
# ══════════════════════════════════════════════════════════════════════════════

class TestDatabaseModel(unittest.TestCase):

    def setUp(self):
        self.session = SessionLocal()

    def tearDown(self):
        self.session.close()

    def test_create_and_retrieve_question(self):
        q = Question(
            grade="Grade 1", subject="Science",
            topic="Earth and Space", level="On-Level",
            question_text="What is the sun?", answer_text="A star.",
            source="llm",
        )
        self.session.add(q)
        self.session.commit()
        fetched = self.session.query(Question).filter_by(id=q.id).first()
        self.assertEqual(fetched.topic, "Earth and Space")
        self.assertEqual(fetched.level, "On-Level")

    def test_default_rating_values(self):
        q = Question(
            grade="Grade 2", subject="Writing",
            topic="Personal Narrative", level="Approaching",
            question_text="Q", answer_text="A", source="llm",
        )
        self.session.add(q)
        self.session.commit()
        self.session.refresh(q)
        self.assertEqual(q.thumbs_up, 0)
        self.assertEqual(q.thumbs_down, 0)
        self.assertFalse(q.is_flagged)

    def test_is_vetted_property(self):
        q = Question(
            grade="Grade 3", subject="Mathematics",
            topic="Data Analysis", level="On-Level",
            question_text="Q", answer_text="A", source="llm",
            thumbs_up=3, thumbs_down=1,
        )
        self.session.add(q)
        self.session.commit()
        self.assertTrue(q.is_vetted)

    def test_teks_code_and_flag_reason_columns_exist(self):
        from sqlalchemy import inspect
        cols = {c["name"] for c in inspect(db_module.engine).get_columns("questions")}
        self.assertIn("teks_code", cols)
        self.assertIn("flag_reason", cols)

    def test_teks_code_stored(self):
        q = Question(
            grade="Grade 5", subject="Mathematics",
            topic="Proportionality", level="Advanced",
            question_text="Q", answer_text="A", source="llm",
            teks_code="TEKS 5.4E",
        )
        self.session.add(q)
        self.session.commit()
        self.session.refresh(q)
        self.assertEqual(q.teks_code, "TEKS 5.4E")

    def test_flag_reason_stored(self):
        q = Question(
            grade="Grade 6", subject="Science",
            topic="Matter and Energy", level="On-Level",
            question_text="Q", answer_text="A", source="llm",
            flag_reason="Unclear wording",
        )
        self.session.add(q)
        self.session.commit()
        self.session.refresh(q)
        self.assertEqual(q.flag_reason, "Unclear wording")

    def test_migrate_db_idempotent(self):
        """Running migrate_db() twice must not raise."""
        migrate_db()
        migrate_db()


# ══════════════════════════════════════════════════════════════════════════════
# 5. API – Health
# ══════════════════════════════════════════════════════════════════════════════

class TestAPIHealth(unittest.TestCase):

    def test_health_returns_ok(self):
        r = client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")


# ══════════════════════════════════════════════════════════════════════════════
# 6. API – Topics / Question Types
# ══════════════════════════════════════════════════════════════════════════════

class TestAPITopics(unittest.TestCase):

    def test_topics_endpoint(self):
        r = client.get("/api/topics")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("Mathematics", data)
        self.assertIn("Science", data)

    def test_question_types_endpoint(self):
        r = client.get("/api/question-types")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIsInstance(data, list)
        self.assertIn("Multiple Choice", data)
        self.assertIn("Mixed", data)


# ══════════════════════════════════════════════════════════════════════════════
# 7. API – Input validation
# ══════════════════════════════════════════════════════════════════════════════

class TestAPIValidation(unittest.TestCase):

    def test_invalid_grade_rejected(self):
        payload = {**VALID_GENERATE_PAYLOAD, "grade": "Grade 99"}
        r = client.post("/api/generate", json=payload)
        self.assertEqual(r.status_code, 422)

    def test_invalid_subject_rejected(self):
        payload = {**VALID_GENERATE_PAYLOAD, "subject": "Art"}
        r = client.post("/api/generate", json=payload)
        self.assertEqual(r.status_code, 422)

    def test_invalid_topic_for_subject_rejected(self):
        payload = {**VALID_GENERATE_PAYLOAD, "topic": "Organisms and Environments"}
        r = client.post("/api/generate", json=payload)
        self.assertEqual(r.status_code, 422)

    def test_invalid_level_rejected(self):
        payload = {**VALID_GENERATE_PAYLOAD, "level": "Advanced Placement"}
        r = client.post("/api/generate", json=payload)
        self.assertEqual(r.status_code, 422)

    def test_invalid_question_type_rejected(self):
        payload = {**VALID_GENERATE_PAYLOAD, "question_types": ["Essay"]}
        r = client.post("/api/generate", json=payload)
        self.assertEqual(r.status_code, 422)

    def test_count_above_30_rejected(self):
        payload = {**VALID_GENERATE_PAYLOAD, "count": 31}
        r = client.post("/api/generate", json=payload)
        self.assertEqual(r.status_code, 422)

    def test_count_below_1_rejected(self):
        payload = {**VALID_GENERATE_PAYLOAD, "count": 0}
        r = client.post("/api/generate", json=payload)
        self.assertEqual(r.status_code, 422)

    def test_rate_invalid_direction_rejected(self):
        r = client.post("/api/rate", json={"question_id": 1, "rating": "sideways"})
        self.assertEqual(r.status_code, 422)

    def test_rate_nonexistent_question_404(self):
        r = client.post("/api/rate", json={"question_id": 99999999, "rating": "up"})
        self.assertEqual(r.status_code, 404)


# ══════════════════════════════════════════════════════════════════════════════
# 8. API – Generate (real LLM call, skippable)
# ══════════════════════════════════════════════════════════════════════════════

class TestAPIGenerate(unittest.TestCase):

    @unittest.skipIf(SKIP_LLM, "SKIP_LLM=1 set — skipping LLM call tests")
    def test_generate_returns_questions(self):
        r = client.post("/api/generate", json=VALID_GENERATE_PAYLOAD)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("questions", data)
        self.assertGreater(len(data["questions"]), 0)

    @unittest.skipIf(SKIP_LLM, "SKIP_LLM=1 set — skipping LLM call tests")
    def test_generate_response_shape(self):
        r = client.post("/api/generate", json=VALID_GENERATE_PAYLOAD)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        for key in ("source", "grade", "subject", "topic", "level", "questions", "generated_at"):
            self.assertIn(key, data)
        q = data["questions"][0]
        for key in ("id", "question", "answer", "grade", "subject", "topic", "level",
                    "thumbs_up", "thumbs_down", "teks_code"):
            self.assertIn(key, q, msg=f"Missing key '{key}' in question")

    @unittest.skipIf(SKIP_LLM, "SKIP_LLM=1 set — skipping LLM call tests")
    def test_generate_with_specific_question_types(self):
        payload = {**VALID_GENERATE_PAYLOAD,
                   "question_types": ["Multiple Choice", "Short Answer"]}
        r = client.post("/api/generate", json=payload)
        self.assertEqual(r.status_code, 200)

    @unittest.skipIf(SKIP_LLM, "SKIP_LLM=1 set — skipping LLM call tests")
    def test_generate_approaching_level(self):
        payload = {**VALID_GENERATE_PAYLOAD, "level": "Approaching"}
        r = client.post("/api/generate", json=payload)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["level"], "Approaching")

    @unittest.skipIf(SKIP_LLM, "SKIP_LLM=1 set — skipping LLM call tests")
    def test_generate_gt_level(self):
        payload = {**VALID_GENERATE_PAYLOAD, "level": "GT/Enrichment"}
        r = client.post("/api/generate", json=payload)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["level"], "GT/Enrichment")

    @unittest.skipIf(SKIP_LLM, "SKIP_LLM=1 set — skipping LLM call tests")
    def test_all_four_levels_accepted(self):
        """All 4 difficulty levels must pass validation and return non-422."""
        for level in ["Approaching", "On-Level", "Advanced", "GT/Enrichment"]:
            payload = {**VALID_GENERATE_PAYLOAD, "level": level}
            r = client.post("/api/generate", json=payload)
            self.assertNotEqual(r.status_code, 422,
                                msg=f"Level '{level}' was unexpectedly rejected with 422")

    @unittest.skipIf(SKIP_LLM, "SKIP_LLM=1 set — skipping LLM call tests")
    def test_count_30_accepted(self):
        """Count of 30 is the new maximum — must not be rejected with 422."""
        payload = {**VALID_GENERATE_PAYLOAD, "count": 30}
        r = client.post("/api/generate", json=payload)
        self.assertNotEqual(r.status_code, 422)


# ══════════════════════════════════════════════════════════════════════════════
# 9. API – Rating (seeded via direct SQLAlchemy)
# ══════════════════════════════════════════════════════════════════════════════

class TestAPIRating(unittest.TestCase):

    def test_thumbs_up_increments(self):
        qid = _seed_question()
        r = client.post("/api/rate", json={"question_id": qid, "rating": "up"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["thumbs_up"], 1)
        self.assertEqual(data["thumbs_down"], 0)

    def test_thumbs_down_increments(self):
        qid = _seed_question()
        r = client.post("/api/rate", json={"question_id": qid, "rating": "down"})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["thumbs_down"], 1)

    def test_thumbs_down_with_reason(self):
        qid = _seed_question()
        r = client.post("/api/rate", json={
            "question_id": qid, "rating": "down", "reason": "Unclear wording"
        })
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["thumbs_down"], 1)
        self.assertEqual(data.get("reason"), "Unclear wording")

    def test_auto_flag_triggers(self):
        """Question flagged after ≥5 down-votes that are 2× more than up-votes."""
        qid = _seed_question(thumbs_up=1, thumbs_down=4)
        r = client.post("/api/rate", json={"question_id": qid, "rating": "down"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["is_flagged"])

    def test_auto_flag_not_triggered_prematurely(self):
        """Should NOT flag when votes are balanced."""
        qid = _seed_question(thumbs_up=4, thumbs_down=4)
        r = client.post("/api/rate", json={"question_id": qid, "rating": "down"})
        self.assertFalse(r.json()["is_flagged"])

    def test_reason_in_response(self):
        """Rate response includes 'reason' key."""
        qid = _seed_question()
        r = client.post("/api/rate", json={"question_id": qid, "rating": "up"})
        self.assertIn("reason", r.json())


# ══════════════════════════════════════════════════════════════════════════════
# 10. API – Stats
# ══════════════════════════════════════════════════════════════════════════════

class TestAPIStats(unittest.TestCase):

    def test_stats_returns_expected_keys(self):
        r = client.get("/api/stats")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        for key in ("total_questions", "vetted_questions", "flagged_questions", "by_grade_subject"):
            self.assertIn(key, data)

    def test_stats_counts_are_non_negative(self):
        r = client.get("/api/stats")
        data = r.json()
        self.assertGreaterEqual(data["total_questions"], 0)
        self.assertGreaterEqual(data["vetted_questions"], 0)
        self.assertGreaterEqual(data["flagged_questions"], 0)


# ══════════════════════════════════════════════════════════════════════════════
# 11. Frontend – Static file served
# ══════════════════════════════════════════════════════════════════════════════

class TestFrontend(unittest.TestCase):

    def test_root_returns_html(self):
        r = client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r.headers["content-type"])

    def test_html_contains_alpine(self):
        r = client.get("/")
        self.assertIn("alpinejs", r.text)

    def test_html_contains_all_subjects(self):
        r = client.get("/")
        for s in VALID_SUBJECTS:
            self.assertIn(s, r.text)

    def test_html_contains_four_levels(self):
        r = client.get("/")
        for level in ["Approaching", "On-Level", "Advanced", "GT/Enrichment"]:
            self.assertIn(level, r.text, msg=f"Level '{level}' not found in HTML")

    def test_html_contains_teks_topics(self):
        r = client.get("/")
        self.assertIn("Number and Operations", r.text)
        self.assertIn("Organisms and Environments", r.text)

    def test_html_contains_question_bank(self):
        r = client.get("/")
        self.assertIn("Question Bank", r.text)

    def test_html_contains_noscript(self):
        r = client.get("/")
        self.assertIn("<noscript>", r.text)

    def test_html_contains_question_types(self):
        r = client.get("/")
        self.assertIn("Multiple Choice", r.text)
        self.assertIn("Mixed", r.text)


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite  = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2 if "-v" in sys.argv else 1)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
