"""Prompt builder and LLM response parser."""

import json

import pytest

from app.services.llm import _build_teks_prompt, _parse_llm_response


class TestPromptBuilder:

    def _prompt(self, level="On-Level", question_types=None):
        return _build_teks_prompt(
            "Grade 5", "Mathematics", "Algebraic Reasoning", level, 5,
            question_types=question_types,
        )

    def test_contains_teks_mention(self):
        assert "TEKS" in self._prompt()

    def test_contains_grade(self):
        assert "Grade 5" in self._prompt()

    def test_contains_topic(self):
        assert "Algebraic Reasoning" in self._prompt()

    def test_approaching_guidance(self):
        p = self._prompt("Approaching")
        assert "APPROACHING" in p
        assert "scaffolded" in p.lower()

    def test_on_level_guidance(self):
        p = self._prompt("On-Level")
        assert "ON-LEVEL" in p

    def test_advanced_guidance(self):
        p = self._prompt("Advanced")
        assert "ADVANCED" in p
        assert "STAAR" in p

    def test_gt_guidance(self):
        p = self._prompt("GT/Enrichment")
        assert "GT/ENRICHMENT" in p
        assert "synthesis" in p.lower()

    def test_count_in_prompt(self):
        p = _build_teks_prompt("Grade 1", "Science", "Earth and Space", "On-Level", 7)
        assert "7" in p

    def test_json_template_present(self):
        assert '"questions"' in self._prompt()

    def test_teks_code_in_json_schema(self):
        assert "teks_code" in self._prompt()

    def test_specific_question_types_in_prompt(self):
        p = self._prompt("On-Level", question_types=["Multiple Choice", "Short Answer"])
        assert "Multiple Choice" in p
        assert "Short Answer" in p

    def test_mixed_question_types_uses_all_formats(self):
        p = self._prompt("On-Level", question_types=["Mixed"])
        # Mixed should not list specific restricted types
        assert "Use ONLY these question formats" not in p


MOCK_LLM_QUESTIONS = [
    {"question": f"What is {i} + {i}?", "answer": str(i * 2),
     "type": "short_answer", "teks_code": f"TEKS 3.{i}A"}
    for i in range(1, 6)
]

MOCK_LLM_RESPONSE = json.dumps({"questions": MOCK_LLM_QUESTIONS})


class TestLLMResponseParser:

    def test_bare_json(self):
        result = _parse_llm_response(MOCK_LLM_RESPONSE)
        assert len(result) == 5
        assert result[0]["question"] == "What is 1 + 1?"

    def test_json_in_code_fence(self):
        wrapped = f"```json\n{MOCK_LLM_RESPONSE}\n```"
        result = _parse_llm_response(wrapped)
        assert len(result) == 5

    def test_strips_think_tags(self):
        content = f"<think>internal reasoning here</think>\n{MOCK_LLM_RESPONSE}"
        result = _parse_llm_response(content)
        assert len(result) == 5

    def test_strips_multiple_think_tags(self):
        content = f"<think>step 1</think><think>step 2</think>{MOCK_LLM_RESPONSE}"
        result = _parse_llm_response(content)
        assert len(result) == 5

    def test_raises_on_garbage(self):
        with pytest.raises(ValueError):
            _parse_llm_response("this is not json at all")

    def test_raises_on_unparseable_content(self):
        with pytest.raises(ValueError):
            _parse_llm_response('{"data": "not_a_list"}')

    def test_bare_array_format(self):
        """Model sometimes returns a bare [...] array instead of {"questions": [...]}"""
        bare = json.dumps(MOCK_LLM_QUESTIONS)
        result = _parse_llm_response(bare)
        assert len(result) == 5
        assert result[0]["question"] == "What is 1 + 1?"

    def test_strips_thinking_tags(self):
        content = f"<thinking>internal reasoning</thinking>\n{MOCK_LLM_RESPONSE}"
        result = _parse_llm_response(content)
        assert len(result) == 5

    def test_teks_code_preserved(self):
        result = _parse_llm_response(MOCK_LLM_RESPONSE)
        assert result[0]["teks_code"] == "TEKS 3.1A"
