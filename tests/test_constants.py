"""Curriculum constants."""

from app.constants import (
    TOPICS_BY_SUBJECT,
    VALID_GRADES,
    VALID_LEVELS,
    VALID_QUESTION_TYPES,
    VALID_SUBJECTS,
)


class TestCurriculumConstants:

    def test_grade_count(self):
        assert len(VALID_GRADES) == 14

    def test_grade_includes_boundaries(self):
        assert "Pre-K" in VALID_GRADES
        assert "Grade 12" in VALID_GRADES

    def test_subject_count(self):
        assert len(VALID_SUBJECTS) == 5

    def test_all_subjects_have_topics(self):
        for s in VALID_SUBJECTS:
            assert s in TOPICS_BY_SUBJECT, f"Subject '{s}' missing from TOPICS_BY_SUBJECT"
            assert len(TOPICS_BY_SUBJECT[s]) > 0, f"Subject '{s}' has no topics"

    def test_four_levels(self):
        assert VALID_LEVELS == ["Approaching", "On-Level", "Advanced", "GT/Enrichment"]

    def test_question_types_list(self):
        expected = ["Multiple Choice", "Short Answer", "Fill-in-the-Blank",
                    "Matching", "True/False", "Mixed"]
        assert VALID_QUESTION_TYPES == expected

    def test_teks_strand_names(self):
        assert "Number and Operations" in TOPICS_BY_SUBJECT["Mathematics"]
        assert "Algebraic Reasoning" in TOPICS_BY_SUBJECT["Mathematics"]
        assert "Organisms and Environments" in TOPICS_BY_SUBJECT["Science"]
        assert "Government and Citizenship" in TOPICS_BY_SUBJECT["Social Studies"]
        assert "Foundational Language Skills" in TOPICS_BY_SUBJECT["Reading & ELA"]

    def test_no_duplicate_topics_per_subject(self):
        for subj, topics in TOPICS_BY_SUBJECT.items():
            assert len(topics) == len(set(topics)), f"Duplicate topics in {subj}"
