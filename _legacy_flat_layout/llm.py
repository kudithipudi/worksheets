"""
LLM integration for the Texas Worksheet Generator.
Handles prompt building, response parsing, and the async generate call.
"""

import json
import logging
import os
import re

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()

OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen/qwen3-vl-30b-a3b-thinking")
SITE_URL: str = os.getenv("SITE_URL", "http://localhost")

logger = logging.getLogger("worksheets")


def _build_teks_prompt(
    grade: str, subject: str, topic: str, level: str, count: int,
    question_types: list[str] | None = None,
) -> str:
    if level == "Approaching":
        level_guidance = (
            "APPROACHING level: questions must be scaffolded with simplified language, "
            "single-step problems, and clear visual or contextual supports. Designed to "
            "support ELL and SpEd students while still addressing the TEKS strand. "
            "Use familiar vocabulary and concrete examples."
        )
    elif level == "Advanced":
        level_guidance = (
            "ADVANCED level: questions must be multi-step, requiring Bloom's Taxonomy "
            "apply/analyze levels. Include STAAR-style problem structures with real-world "
            "contexts. Complexity should challenge students beyond standard TEKS benchmarks "
            "while remaining accessible to on-grade advanced learners."
        )
    elif level == "GT/Enrichment":
        level_guidance = (
            "GT/ENRICHMENT level: questions must involve novel application, synthesis of "
            "multiple concepts, creative extension, and open-ended exploration. Encourage "
            "higher-order thinking (Bloom's evaluate/create). Problems should be non-routine "
            "and may require original reasoning or justification."
        )
    else:
        level_guidance = (
            "ON-LEVEL: questions must assess core TEKS knowledge and procedural fluency "
            "at standard grade-level expectations. Straightforward application of concepts "
            "taught in class."
        )

    if question_types and question_types != ["Mixed"]:
        formats = ", ".join(question_types)
        format_instruction = (
            f"3. Use ONLY these question formats: {formats}. "
            "Each question must match one of these formats exactly."
        )
    else:
        format_instruction = (
            "3. Mix formats across: multiple-choice, short-answer, fill-in-the-blank, "
            "matching, and true/false."
        )

    return f"""\
You are an expert Texas educator writing worksheet questions aligned with the \
Texas Essential Knowledge and Skills (TEKS).

Create exactly {count} questions for:
  Grade   : {grade}
  Subject : {subject}
  Topic   : {topic}  (official TEKS strand)
  Level   : {level}

Level guidance — {level_guidance}

Additional requirements:
1. Every question MUST be directly tied to the TEKS strand "{topic}" for {grade} {subject}.
2. Vary difficulty within the level: roughly 1/3 easy, 1/3 medium, 1/3 challenging.
{format_instruction}
4. Language and context must be age-appropriate for {grade} students.
5. Where relevant, incorporate Texas geography, history, flora, and culture.
6. Each answer must be clear, complete, and unambiguous.
7. For teks_code, provide the most specific TEKS code that applies (e.g. "TEKS 3.4A") if known; otherwise leave empty.

IMPORTANT: Respond with ONLY valid JSON — no markdown fences, no explanation, no preamble.

{{
  "questions": [
    {{
      "question": "Full question text",
      "answer": "Full answer text",
      "type": "short_answer",
      "teks_code": "e.g. TEKS 3.4A (optional)"
    }}
  ]
}}"""


def _parse_llm_response(content: str) -> list[dict]:
    """
    Extract the questions JSON from the LLM reply.
    Handles:
    - <think>…</think> and <thinking>…</thinking> reasoning blocks
    - Markdown code fences (```json … ```)
    - {"questions": [...]} wrapper object
    - Bare JSON array [...]
    """
    # Strip all known thinking/reasoning block formats
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    content = re.sub(r"<thinking>.*?</thinking>", "", content, flags=re.DOTALL)
    content = content.strip()

    def _extract_questions(data) -> list[dict] | None:
        """Return the questions list from parsed JSON, regardless of wrapper."""
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            if isinstance(data.get("questions"), list):
                return data["questions"]
        return None

    # Try explicit code fences first (most reliable)
    for pattern in (
        r"```json\s*([\s\S]*?)\s*```",
        r"```\s*([\s\S]*?)\s*```",
    ):
        m = re.search(pattern, content, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1).strip())
                result = _extract_questions(data)
                if result is not None:
                    return result
            except json.JSONDecodeError:
                pass

    # Try parsing the content as a bare array (model sometimes returns [...] directly)
    bracket_start = content.find("[")
    if bracket_start != -1:
        depth = 0
        for i, ch in enumerate(content[bracket_start:], bracket_start):
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(content[bracket_start : i + 1])
                        result = _extract_questions(data)
                        if result is not None:
                            return result
                    except json.JSONDecodeError:
                        break

    # Fall back to finding outermost JSON object
    brace_start = content.find("{")
    if brace_start != -1:
        depth = 0
        for i, ch in enumerate(content[brace_start:], brace_start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(content[brace_start : i + 1])
                        result = _extract_questions(data)
                        if result is not None:
                            return result
                    except json.JSONDecodeError:
                        break

    raise ValueError("Could not locate valid JSON in LLM response")


async def _generate_from_llm(
    grade: str, subject: str, topic: str, level: str, count: int,
    question_types: list[str] | None = None,
) -> list[dict]:
    if not OPENROUTER_API_KEY:
        raise HTTPException(
            status_code=503,
            detail=(
                "OpenRouter API key not configured. "
                "Set OPENROUTER_API_KEY in your .env file."
            ),
        )

    prompt = _build_teks_prompt(grade, subject, topic, level, count, question_types)

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": SITE_URL,
        "X-Title": "Texas Worksheet Generator",
        "Content-Type": "application/json",
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 4096,
    }

    try:
        async with httpx.AsyncClient(timeout=110.0) as client:
            resp = await client.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
    except httpx.TimeoutException:
        logger.error("OpenRouter request timed out")
        raise HTTPException(
            status_code=504,
            detail="The AI took too long to respond. Please try again.",
        )
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        logger.error("OpenRouter HTTP error %s: %s", status, exc.response.text[:400])
        if status == 402:
            raise HTTPException(
                status_code=402,
                detail=(
                    "OpenRouter account has insufficient credits. "
                    "Add credits at openrouter.ai/credits or switch LLM_MODEL "
                    "to a free model (e.g. append ':free' to the model slug)."
                ),
            )
        if status == 429:
            raise HTTPException(
                status_code=429,
                detail="OpenRouter rate limit reached. Please wait a moment and try again.",
            )
        raise HTTPException(
            status_code=502,
            detail=f"AI API returned an error ({status}). Please try again.",
        )

    try:
        body = resp.json()
        content = body["choices"][0]["message"]["content"]
        questions = _parse_llm_response(content)
    except (KeyError, IndexError) as exc:
        logger.error("Unexpected OpenRouter response structure: %s", exc)
        raise HTTPException(status_code=502, detail="Unexpected response from AI API.")
    except ValueError as exc:
        logger.error("JSON parse failure: %s", exc)
        # Log the raw content (truncated) to help diagnose what the model returned
        try:
            raw_content = body["choices"][0]["message"]["content"]
            logger.error("Raw LLM content (first 1000 chars): %r", raw_content[:1000])
        except Exception:
            pass
        raise HTTPException(status_code=502, detail="Could not parse questions from AI response.")

    if not questions:
        raise HTTPException(status_code=502, detail="AI returned no questions. Please try again.")

    if len(questions) < count:
        logger.warning("LLM returned %d questions, expected %d", len(questions), count)

    return questions[:count]
