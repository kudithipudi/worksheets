"""
Pydantic schemas for the Texas Worksheet Generator API.
"""

from typing import List

from pydantic import BaseModel, Field, field_validator

from app.constants import (
    TOPICS_BY_SUBJECT,
    VALID_GRADES,
    VALID_LEVELS,
    VALID_QUESTION_TYPES,
    VALID_SUBJECTS,
)


class GenerateRequest(BaseModel):
    grade: str
    subject: str
    topic: str
    level: str = "On-Level"
    count: int = Field(default=10, ge=1, le=30)
    question_types: list[str] = Field(default=["Mixed"])

    @field_validator("grade")
    @classmethod
    def validate_grade(cls, v: str) -> str:
        if v not in VALID_GRADES:
            raise ValueError(f"grade must be one of: {', '.join(VALID_GRADES)}")
        return v

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, v: str) -> str:
        if v not in VALID_SUBJECTS:
            raise ValueError(f"subject must be one of: {', '.join(VALID_SUBJECTS)}")
        return v

    @field_validator("topic")
    @classmethod
    def validate_topic(cls, v: str, info) -> str:
        subject = info.data.get("subject")
        valid = TOPICS_BY_SUBJECT.get(subject, [])
        if valid and v not in valid:
            raise ValueError(f"topic must be one of: {', '.join(valid)}")
        return v

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        if v not in VALID_LEVELS:
            raise ValueError(f"level must be one of: {', '.join(VALID_LEVELS)}")
        return v

    @field_validator("question_types")
    @classmethod
    def validate_question_types(cls, v: list[str]) -> list[str]:
        for qt in v:
            if qt not in VALID_QUESTION_TYPES:
                raise ValueError(f"question_type must be one of: {', '.join(VALID_QUESTION_TYPES)}")
        return v


class RateRequest(BaseModel):
    question_id: int
    rating: str  # "up" | "down"
    reason: str = ""  # optional, for "down" ratings

    @field_validator("rating")
    @classmethod
    def validate_rating(cls, v: str) -> str:
        if v not in ("up", "down"):
            raise ValueError("rating must be 'up' or 'down'")
        return v


class QuestionOut(BaseModel):
    id: int
    question: str
    answer: str
    grade: str
    subject: str
    topic: str
    level: str
    thumbs_up: int
    thumbs_down: int
    teks_code: str = ""


class WorksheetOut(BaseModel):
    source: str         # "llm" | "database"
    grade: str
    subject: str
    topic: str
    level: str
    questions: List[QuestionOut]
    generated_at: str
