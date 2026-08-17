"""API route tests, in-process via httpx ASGITransport."""

import os

import pytest

from app.config import settings
from app.models.orm import RateLimitHit
from app.routers import worksheets as worksheets_router

SKIP_LLM = bool(os.getenv("SKIP_LLM"))
skip_llm_mark = pytest.mark.skipif(SKIP_LLM, reason="SKIP_LLM=1 set — skipping LLM call tests")


# ══════════════════════════════════════════════════════════════════════════════
# Health
# ══════════════════════════════════════════════════════════════════════════════

class TestAPIHealth:

    async def test_health_returns_ok(self, client):
        r = await client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


# ══════════════════════════════════════════════════════════════════════════════
# Topics / Question Types
# ══════════════════════════════════════════════════════════════════════════════

class TestAPITopics:

    async def test_topics_endpoint(self, client):
        r = await client.get("/api/topics")
        assert r.status_code == 200
        data = r.json()
        assert "Mathematics" in data
        assert "Science" in data

    async def test_question_types_endpoint(self, client):
        r = await client.get("/api/question-types")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert "Multiple Choice" in data
        assert "Mixed" in data


# ══════════════════════════════════════════════════════════════════════════════
# Input validation
# ══════════════════════════════════════════════════════════════════════════════

class TestAPIValidation:

    async def test_invalid_grade_rejected(self, client, valid_generate_payload):
        payload = {**valid_generate_payload, "grade": "Grade 99"}
        r = await client.post("/api/generate", json=payload)
        assert r.status_code == 422

    async def test_invalid_subject_rejected(self, client, valid_generate_payload):
        payload = {**valid_generate_payload, "subject": "Art"}
        r = await client.post("/api/generate", json=payload)
        assert r.status_code == 422

    async def test_invalid_topic_for_subject_rejected(self, client, valid_generate_payload):
        payload = {**valid_generate_payload, "topic": "Organisms and Environments"}
        r = await client.post("/api/generate", json=payload)
        assert r.status_code == 422

    async def test_invalid_level_rejected(self, client, valid_generate_payload):
        payload = {**valid_generate_payload, "level": "Advanced Placement"}
        r = await client.post("/api/generate", json=payload)
        assert r.status_code == 422

    async def test_invalid_question_type_rejected(self, client, valid_generate_payload):
        payload = {**valid_generate_payload, "question_types": ["Essay"]}
        r = await client.post("/api/generate", json=payload)
        assert r.status_code == 422

    async def test_count_above_30_rejected(self, client, valid_generate_payload):
        payload = {**valid_generate_payload, "count": 31}
        r = await client.post("/api/generate", json=payload)
        assert r.status_code == 422

    async def test_count_below_1_rejected(self, client, valid_generate_payload):
        payload = {**valid_generate_payload, "count": 0}
        r = await client.post("/api/generate", json=payload)
        assert r.status_code == 422

    async def test_rate_invalid_direction_rejected(self, client):
        r = await client.post("/api/rate", json={"question_id": 1, "rating": "sideways"})
        assert r.status_code == 422

    async def test_rate_nonexistent_question_404(self, client):
        r = await client.post("/api/rate", json={"question_id": 99999999, "rating": "up"})
        assert r.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# Generate (real LLM call, skippable via SKIP_LLM=1)
# ══════════════════════════════════════════════════════════════════════════════

@skip_llm_mark
class TestAPIGenerate:

    async def test_generate_returns_questions(self, client, valid_generate_payload):
        r = await client.post("/api/generate", json=valid_generate_payload)
        assert r.status_code == 200
        data = r.json()
        assert "questions" in data
        assert len(data["questions"]) > 0

    async def test_generate_response_shape(self, client, valid_generate_payload):
        r = await client.post("/api/generate", json=valid_generate_payload)
        assert r.status_code == 200
        data = r.json()
        for key in ("source", "grade", "subject", "topic", "level", "questions", "generated_at"):
            assert key in data
        q = data["questions"][0]
        for key in ("id", "question", "answer", "grade", "subject", "topic", "level",
                    "thumbs_up", "thumbs_down", "teks_code"):
            assert key in q, f"Missing key '{key}' in question"

    async def test_generate_with_specific_question_types(self, client, valid_generate_payload):
        payload = {**valid_generate_payload,
                   "question_types": ["Multiple Choice", "Short Answer"]}
        r = await client.post("/api/generate", json=payload)
        assert r.status_code == 200

    async def test_generate_approaching_level(self, client, valid_generate_payload):
        payload = {**valid_generate_payload, "level": "Approaching"}
        r = await client.post("/api/generate", json=payload)
        assert r.status_code == 200
        assert r.json()["level"] == "Approaching"

    async def test_generate_gt_level(self, client, valid_generate_payload):
        payload = {**valid_generate_payload, "level": "GT/Enrichment"}
        r = await client.post("/api/generate", json=payload)
        assert r.status_code == 200
        assert r.json()["level"] == "GT/Enrichment"

    async def test_all_four_levels_accepted(self, client, valid_generate_payload):
        """All 4 difficulty levels must pass validation and return non-422."""
        for level in ["Approaching", "On-Level", "Advanced", "GT/Enrichment"]:
            payload = {**valid_generate_payload, "level": level}
            r = await client.post("/api/generate", json=payload)
            assert r.status_code != 422, f"Level '{level}' was unexpectedly rejected with 422"

    async def test_count_30_accepted(self, client, valid_generate_payload):
        """Count of 30 is the maximum — must not be rejected with 422."""
        payload = {**valid_generate_payload, "count": 30}
        r = await client.post("/api/generate", json=payload)
        assert r.status_code != 422


# ══════════════════════════════════════════════════════════════════════════════
# Rating (seeded via direct SQLAlchemy)
# ══════════════════════════════════════════════════════════════════════════════

class TestAPIRating:

    async def test_thumbs_up_increments(self, client, seed_question):
        qid = seed_question()
        r = await client.post("/api/rate", json={"question_id": qid, "rating": "up"})
        assert r.status_code == 200
        data = r.json()
        assert data["thumbs_up"] == 1
        assert data["thumbs_down"] == 0

    async def test_thumbs_down_increments(self, client, seed_question):
        qid = seed_question()
        r = await client.post("/api/rate", json={"question_id": qid, "rating": "down"})
        assert r.status_code == 200
        assert r.json()["thumbs_down"] == 1

    async def test_thumbs_down_with_reason(self, client, seed_question):
        qid = seed_question()
        r = await client.post("/api/rate", json={
            "question_id": qid, "rating": "down", "reason": "Unclear wording"
        })
        assert r.status_code == 200
        data = r.json()
        assert data["thumbs_down"] == 1
        assert data.get("reason") == "Unclear wording"

    async def test_auto_flag_triggers(self, client, seed_question):
        """Question flagged after >=5 down-votes that are 2x more than up-votes."""
        qid = seed_question(thumbs_up=1, thumbs_down=4)
        r = await client.post("/api/rate", json={"question_id": qid, "rating": "down"})
        assert r.status_code == 200
        assert r.json()["is_flagged"]

    async def test_auto_flag_not_triggered_prematurely(self, client, seed_question):
        """Should NOT flag when votes are balanced."""
        qid = seed_question(thumbs_up=4, thumbs_down=4)
        r = await client.post("/api/rate", json={"question_id": qid, "rating": "down"})
        assert not r.json()["is_flagged"]

    async def test_reason_in_response(self, client, seed_question):
        """Rate response includes 'reason' key."""
        qid = seed_question()
        r = await client.post("/api/rate", json={"question_id": qid, "rating": "up"})
        assert "reason" in r.json()


# ══════════════════════════════════════════════════════════════════════════════
# Stats
# ══════════════════════════════════════════════════════════════════════════════

class TestAPIStats:

    async def test_stats_returns_expected_keys(self, client):
        r = await client.get("/api/stats")
        assert r.status_code == 200
        data = r.json()
        for key in ("total_questions", "vetted_questions", "flagged_questions", "by_grade_subject"):
            assert key in data

    async def test_stats_counts_are_non_negative(self, client):
        r = await client.get("/api/stats")
        data = r.json()
        assert data["total_questions"] >= 0
        assert data["vetted_questions"] >= 0
        assert data["flagged_questions"] >= 0


# ══════════════════════════════════════════════════════════════════════════════
# Rate limiting on POST /api/generate
# ══════════════════════════════════════════════════════════════════════════════

class TestAPIRateLimit:

    async def test_generate_rate_limited(
        self, client, db_session, seed_question, valid_generate_payload, monkeypatch
    ):
        # Start from a clean slate regardless of hits accumulated by earlier tests.
        db_session.query(RateLimitHit).delete()
        db_session.commit()

        # Force the cheap DB-sourcing path so this test never hits the paid LLM.
        monkeypatch.setattr(worksheets_router, "VETTED_THRESHOLD", 0)
        seed_question(
            grade=valid_generate_payload["grade"],
            subject=valid_generate_payload["subject"],
            topic=valid_generate_payload["topic"],
            level=valid_generate_payload["level"],
            thumbs_up=1,
        )

        monkeypatch.setattr(settings, "rate_limit_per_minute", 2)

        for _ in range(2):
            r = await client.post("/api/generate", json=valid_generate_payload)
            assert r.status_code == 200

        r = await client.post("/api/generate", json=valid_generate_payload)
        assert r.status_code == 429
        assert r.json()["detail"] == (
            "Too many requests — please slow down and try again in a minute."
        )
