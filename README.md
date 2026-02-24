# Texas Worksheet Generator

Generate print-ready, Texas TEKS-aligned worksheets for any grade level, subject, topic, and complexity level.
Powered by FastAPI, Alpine.js, SQLite, and the OpenRouter LLM API.

**Live URL:** `https://lab.kudithipudi.org/worksheets/`

---

## Architecture

```
Browser
  └── HTTPS ──► Nginx (lab.kudithipudi.org, Let's Encrypt TLS)
                  └── /worksheets/ ──► Unix socket ──► Gunicorn (UvicornWorker)
                                         /var/www/worksheets/worksheets.sock
                                              └── FastAPI app (main.py)
                                                    ├── constants.py  (curriculum data)
                                                    ├── schemas.py    (request/response models)
                                                    ├── llm.py        (OpenRouter integration)
                                                    ├── routes.py     (API handlers)
                                                    ├── models.py     (SQLAlchemy ORM)
                                                    └── database.py   (engine, migrations)
                                                    └── SQLite (worksheets.db)
```

The Nginx server block lives alongside other apps at
`/etc/nginx/sites-enabled/lab.kudithipudi.org`. It strips the `/worksheets`
prefix before proxying, so FastAPI sees clean paths (`/`, `/api/generate`, etc.).

---

## Project Layout

```
/var/www/worksheets/
├── main.py              # App entry point — lifespan, CORS, static mount, router
├── constants.py         # VALID_* lists, TOPICS_BY_SUBJECT, FLAG_THRESHOLD
├── schemas.py           # Pydantic schemas — GenerateRequest, RateRequest, QuestionOut, WorksheetOut
├── llm.py               # LLM integration — prompt builder, response parser, _generate_from_llm()
├── routes.py            # All 7 API route handlers + DB helper functions
├── models.py            # SQLAlchemy Question model
├── database.py          # Engine, WAL pragmas, session factory, migrate_db()
├── gunicorn_config.py   # Gunicorn settings (socket, workers, timeouts)
├── requirements.txt     # Python dependencies
├── tests.py             # Test suite (71 tests, 7 skipped without LLM key)
├── start.sh             # Bootstrap + launch script
├── worksheets.service   # Systemd unit (reference copy)
├── nginx.conf           # Nginx snippet (reference copy)
├── .env                 # Secrets — never commit this
├── .env.example         # Template
├── worksheets.db        # SQLite database (created on first run)
├── worksheets.sock      # Unix socket (created by Gunicorn at runtime)
└── static/
    └── index.html       # Alpine.js + Tailwind SPA
```

---

## Configuration

Copy `.env.example` to `.env` and fill in values:

```ini
OPENROUTER_API_KEY=sk-or-...          # Required
LLM_MODEL=qwen/qwen3-vl-30b-a3b-thinking
SITE_URL=https://lab.kudithipudi.org/worksheets
DATABASE_URL=sqlite:///./worksheets.db
VETTED_THRESHOLD=1000
```

---

## Deployment

### 1 — Install dependencies

```bash
cd /var/www/worksheets
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

Or use the bootstrap script (also removes a stale socket):

```bash
sudo -u www-data bash start.sh
```

### 2 — Systemd service

The live service file is `/etc/systemd/system/worksheets.service`.

```bash
# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable --now worksheets

# Common management commands
sudo systemctl status   worksheets
sudo systemctl restart  worksheets
sudo journalctl -u worksheets -f       # live logs
```

The service runs as `www-data`, loads secrets from `/var/www/worksheets/.env`,
and writes the socket to `/var/www/worksheets/worksheets.sock`.

### 3 — Nginx

The app is configured inside the shared virtual host:

```
/etc/nginx/sites-enabled/lab.kudithipudi.org
```

Relevant block (already in place):

```nginx
location /worksheets/ {
    include proxy_params;
    proxy_set_header X-Script-Name /worksheets;
    proxy_set_header X-Forwarded-Prefix /worksheets;
    rewrite ^/worksheets(/.*)$ $1 break;
    proxy_pass http://unix:/var/www/worksheets/worksheets.sock;
}
```

After any Nginx config change:

```bash
sudo nginx -t && sudo systemctl reload nginx
```

---

## Gunicorn settings (`gunicorn_config.py`)

| Setting | Value | Notes |
|---|---|---|
| `bind` | `unix:/var/www/worksheets/worksheets.sock` | consumed by Nginx |
| `worker_class` | `uvicorn.workers.UvicornWorker` | required for FastAPI async |
| `workers` | `1` | single worker for this host |
| `timeout` | `120 s` | covers 90 s LLM API timeout |
| `max_requests` | `1000` | periodic worker recycle |

---

## Curriculum Structure

### Subjects and TEKS Topics

Topics are drawn from official **Texas Essential Knowledge and Skills (TEKS)** strand names:

| Subject | Topics |
|---|---|
| **Mathematics** | Number and Operations, Algebraic Reasoning, Geometry and Measurement, Data Analysis, Proportionality, Financial Literacy |
| **Reading & ELA** | Foundational Language Skills, Reading Comprehension, Author's Purpose and Craft, Vocabulary, Literary Analysis, Research and Inquiry |
| **Science** | Matter and Energy, Force, Motion, and Energy, Earth and Space, Organisms and Environments |
| **Social Studies** | History, Geography, Economics, Government and Citizenship, Culture and Society |
| **Writing** | Personal Narrative, Expository Writing, Persuasive / Argumentative Writing, Informational Writing, Research Writing |

### Difficulty Levels

| Level | Description |
|---|---|
| **Approaching** | Scaffolded questions with simplified language and single-step problems; supports ELL and SpEd students |
| **On-Level** | Grade-appropriate questions aligned to core TEKS expectations and procedural fluency |
| **Advanced** | Multi-step, STAAR-style problems at Bloom's apply/analyze level; challenges above-average learners |
| **GT/Enrichment** | Non-routine, open-ended problems requiring synthesis and original reasoning at Bloom's evaluate/create level |

### Question Types

`Multiple Choice`, `Short Answer`, `Fill-in-the-Blank`, `Matching`, `True/False`, `Mixed`

When `Mixed` is selected the LLM distributes formats freely. Any other selection restricts the LLM to only those formats.

---

## Application Logic

### Hybrid question sourcing

Every `/api/generate` call checks how many **vetted** questions exist in SQLite
for the requested `grade + subject + topic + level` combination (vetted =
`thumbs_up > thumbs_down` AND `is_flagged = false`).

| Vetted count | Behaviour |
|---|---|
| `< 1 000` | Call OpenRouter LLM, save returned questions to DB, return them |
| `≥ 1 000` | Randomly sample from the local DB — no LLM call |

### Rating & auto-flagging

- Users rate questions **Helpful / Needs Work** (thumbs up / down).
- A **Needs Work** rating optionally includes a structured reason (e.g. "Incorrect answer", "Unclear wording").
- A question is auto-flagged when `thumbs_down ≥ 5` **and**
  `thumbs_down > thumbs_up × 2`. Flagged questions are excluded from the
  vetted pool and from future DB draws.

### LLM prompt (`llm.py`)

`_build_teks_prompt()` constructs a detailed prompt that:

- References the specific **TEKS strand** and grade level
- Injects level-specific pedagogical guidance (scaffolding for Approaching, STAAR-style for Advanced, Bloom's evaluate/create for GT/Enrichment)
- Restricts or mixes question formats based on the `question_types` field
- Requests a `teks_code` field on every question (best-effort; left empty if unknown)
- Asks for age-appropriate language and Texas cultural context

`_parse_llm_response()` handles the full range of model output styles:

- Strips `<think>…</think>` and `<thinking>…</thinking>` reasoning blocks
- Extracts JSON from markdown code fences
- Accepts both `{"questions": [...]}` wrapper objects and bare `[...]` arrays

### Database schema

The `questions` table stores all generated and rated questions:

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER | Primary key |
| `grade` | VARCHAR(20) | e.g. `"Grade 3"` |
| `subject` | VARCHAR(50) | e.g. `"Mathematics"` |
| `topic` | VARCHAR(100) | TEKS strand name, e.g. `"Number and Operations"` |
| `level` | VARCHAR(20) | `"Approaching"`, `"On-Level"`, `"Advanced"`, or `"GT/Enrichment"` |
| `question_text` | TEXT | |
| `answer_text` | TEXT | |
| `source` | VARCHAR(10) | `"llm"` or `"db"` |
| `thumbs_up` | INTEGER | cumulative helpful votes |
| `thumbs_down` | INTEGER | cumulative needs-work votes |
| `is_flagged` | BOOLEAN | set by auto-flag logic |
| `teks_code` | VARCHAR(20) | LLM-tagged TEKS code, e.g. `"TEKS 3.4A"` (optional) |
| `flag_reason` | VARCHAR(100) | Reason provided with a Needs Work rating (optional) |
| `created_at` | DATETIME | server-side default |

#### Forward migration

`database.migrate_db()` is called at startup and safely adds any new columns
to existing databases. It wraps each `ALTER TABLE` in a `try/except` since
SQLite does not support `ADD COLUMN IF NOT EXISTS`.

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Serve SPA (`static/index.html`) |
| `GET` | `/api/topics` | Return all subjects with their TEKS topic lists |
| `GET` | `/api/question-types` | Return supported question type options |
| `POST` | `/api/generate` | Generate worksheet |
| `POST` | `/api/rate` | Rate a question |
| `GET` | `/api/stats` | Library statistics |
| `GET` | `/health` | Uptime probe |
| `GET` | `/docs` | Auto-generated Swagger UI |

### `POST /api/generate`

Request body:

```json
{
  "grade":          "Grade 3",
  "subject":        "Mathematics",
  "topic":          "Number and Operations",
  "level":          "On-Level",
  "count":          10,
  "question_types": ["Mixed"]
}
```

- `grade` — one of the 14 valid grades (`"Pre-K"`, `"Kindergarten"`, `"Grade 1"` … `"Grade 12"`)
- `subject` — one of the five supported subjects
- `topic` — must be a valid TEKS strand for the chosen subject (see Curriculum Structure above)
- `level` — `"Approaching"`, `"On-Level"` (default), `"Advanced"`, or `"GT/Enrichment"`
- `count` — number of questions, 1–30
- `question_types` — list of one or more question types; `["Mixed"]` (default) lets the LLM choose freely

### `GET /api/topics`

Returns the full subject → topic mapping:

```json
{
  "Mathematics": ["Number and Operations", "Algebraic Reasoning", ...],
  "Reading & ELA": ["Foundational Language Skills", ...],
  ...
}
```

### `GET /api/question-types`

Returns the list of valid question type strings:

```json
["Multiple Choice", "Short Answer", "Fill-in-the-Blank", "Matching", "True/False", "Mixed"]
```

---

## Development

```bash
# Run locally without Gunicorn
source venv/bin/activate
uvicorn main:app --reload --port 8000
# → http://localhost:8000
```

The app serves `static/index.html` at `/`, so the SPA works identically in
local dev and production.

---

## Testing

The test suite covers all major functionality with 71 tests across 11 test classes.
API tests run against the live service via the Unix socket; unit tests use an
isolated temporary SQLite database.

```bash
# Fast — no LLM calls (recommended for development)
SKIP_LLM=1 venv/bin/python tests.py -v

# Full suite including live LLM calls (slow, costs credits)
venv/bin/python tests.py -v

# Against live HTTPS instead of the local socket
BASE_URL=https://lab.kudithipudi.org/worksheets venv/bin/python tests.py
```

### Test classes

| Class | What it covers |
|---|---|
| `TestCurriculumConstants` | `VALID_GRADES`, `VALID_SUBJECTS`, `TOPICS_BY_SUBJECT`, `VALID_LEVELS`, `VALID_QUESTION_TYPES` completeness |
| `TestPromptBuilder` | Prompt content for each level, question-type format injection, TEKS mention |
| `TestLLMResponseParser` | JSON extraction, `<think>`/`<thinking>` tag stripping, code fence unwrapping, bare array format, malformed input handling |
| `TestDatabaseModel` | Column defaults, `is_vetted` property, `teks_code`/`flag_reason` columns, idempotent migration |
| `TestAPIHealth` | `/health` endpoint |
| `TestAPITopics` | `/api/topics` and `/api/question-types` endpoints |
| `TestAPIValidation` | Invalid grade/subject/topic/level/question_type/count rejected with 422 |
| `TestAPIGenerate` | End-to-end generate calls (skipped when `SKIP_LLM=1`) |
| `TestAPIRating` | Thumbs up/down increments, reason storage, auto-flag trigger and non-trigger |
| `TestAPIStats` | Stats endpoint keys and non-negative counts |
| `TestFrontend` | SPA HTML served at `/`, Alpine.js present, all subjects/levels/topics in HTML |
