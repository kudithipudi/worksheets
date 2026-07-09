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
                                              └── FastAPI app (app/main.py)
                                                    ├── app/config.py         (pydantic-settings)
                                                    ├── app/constants.py      (curriculum data)
                                                    ├── app/models/schemas.py (request/response models)
                                                    ├── app/models/orm.py     (SQLAlchemy ORM)
                                                    ├── app/services/llm.py   (OpenRouter integration)
                                                    ├── app/routers/worksheets.py (API + page handlers)
                                                    ├── app/db.py             (engine, migrations)
                                                    ├── app/templates/        (Jinja2: base.html, index.html)
                                                    └── app/static/           (built Tailwind CSS, Alpine.js)
                                              └── SQLite (data/worksheets.db)
```

The Nginx server block lives alongside other apps at
`/etc/nginx/sites-enabled/lab.kudithipudi.org` (not part of this repo — shared
across all lab apps). It strips the `/worksheets` prefix before proxying via
`rewrite ^/worksheets(/.*)$ $1 break;`, so FastAPI sees clean, unprefixed paths
(`/`, `/api/generate`, `/static/...`, etc.). Because of that rewrite, the app
intentionally does **not** pass `ROOT_PATH` into FastAPI's `root_path=`
constructor arg (see the comment in `app/config.py`) — doing so makes
Starlette expect the prefix to still be present on incoming requests, which
breaks the `/static` mount. Templates instead use plain relative asset URLs
(`./static/css/app.css`).

---

## Project Layout

```
/var/www/worksheets/
├── app/
│   ├── main.py                 # App entry point — lifespan, CORS, static mount, router
│   ├── config.py                # pydantic-settings Settings (.env)
│   ├── db.py                    # Engine, WAL pragmas, session factory, migrate_db()
│   ├── constants.py              # VALID_* lists, TOPICS_BY_SUBJECT, FLAG_THRESHOLD
│   ├── models/
│   │   ├── orm.py                # SQLAlchemy Question model
│   │   └── schemas.py            # Pydantic schemas — GenerateRequest, RateRequest, QuestionOut, WorksheetOut
│   ├── routers/
│   │   └── worksheets.py         # All API route handlers + page route + DB helper functions
│   ├── services/
│   │   └── llm.py                # LLM integration — prompt builder, response parser, _generate_from_llm()
│   ├── templates/
│   │   ├── base.html             # Shared chrome — header/footer, lab link, Tailwind/Alpine includes
│   │   └── index.html            # SPA content (extends base.html)
│   └── static/
│       ├── css/
│       │   ├── input.css         # Tailwind source (custom styles + print CSS)
│       │   └── app.css           # Built, minified Tailwind output (committed)
│       └── js/
│           └── alpinejs-3.14.1.min.js  # Pinned, vendored Alpine.js build
├── data/                         # SQLite db (gitignored, www-data writable)
├── tests/                        # pytest suite
├── gunicorn.conf.py              # Gunicorn settings (socket, workers, timeouts)
├── tailwind.config.js            # Tailwind content globs + tx-navy/tx-gold theme
├── requirements.txt              # Python dependencies (fully pinned)
├── pytest.ini
├── worksheets.service            # Systemd unit (reference copy — also installed at /etc/systemd/system/)
├── nginx.conf                    # Standalone Nginx snippet reference (NOT the live config; see Architecture)
├── .env                          # Secrets — never commit this
├── .env.example                  # Template
└── _legacy_flat_layout/          # Archived pre-restructure files, kept for reference; safe to delete
```

---

## Configuration

All configuration is loaded via `app/config.py` (`pydantic-settings`), which
reads process environment variables first and falls back to `.env`. Copy
`.env.example` to `.env` and fill in values:

```ini
OPENROUTER_API_KEY=sk-or-...          # Required
LLM_MODEL=qwen/qwen3-vl-30b-a3b-thinking
SITE_URL=https://lab.kudithipudi.org/worksheets
DATABASE_URL=sqlite:///./data/worksheets.db
VETTED_THRESHOLD=1000
ROOT_PATH=/worksheets                 # documentation only — see Architecture note above
```

---

## Deployment

### 1 — Install dependencies

```bash
cd /var/www/worksheets
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

### 2 — Rebuild the Tailwind CSS (only after editing templates or `tailwind.config.js`)

```bash
# Standalone Tailwind CLI v3.4.17 (no Node/npm required at runtime)
curl -sL -o /tmp/tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.17/tailwindcss-linux-x64
chmod +x /tmp/tailwindcss
cd /var/www/worksheets
/tmp/tailwindcss -c tailwind.config.js -i app/static/css/input.css -o app/static/css/app.css --minify
```

### 3 — Systemd service

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

The service runs as `www-data`. The app itself reads secrets from
`/var/www/worksheets/.env` via `pydantic-settings` (not `EnvironmentFile=` in
the unit), and writes the socket to `/var/www/worksheets/worksheets.sock`.

### 4 — Nginx

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

## Gunicorn settings (`gunicorn.conf.py`)

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

### LLM prompt (`app/services/llm.py`)

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

`db.migrate_db()` is called at startup and safely adds any new columns
to existing databases. It wraps each `ALTER TABLE` in a `try/except` since
SQLite does not support `ADD COLUMN IF NOT EXISTS`.

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Serve the Jinja2-rendered SPA (`app/templates/index.html`) |
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
uvicorn app.main:app --reload --port 8000
# → http://localhost:8000
```

The app renders `app/templates/index.html` (extending `base.html`) at `/`, so
the SPA works identically in local dev and production. Nginx strips the
`/worksheets` prefix in production, so all routes and asset links are relative
(`./static/...`) and require no special local configuration.

---

## Testing

The suite is `pytest` + `pytest-asyncio`, using `httpx.ASGITransport` to drive
the app in-process (no running service required) against an isolated temp
SQLite database created in `tests/conftest.py`.

```bash
# Fast — no LLM calls (recommended for development)
SKIP_LLM=1 venv/bin/python -m pytest -v

# Full suite including live LLM calls (slow, costs OpenRouter credits)
venv/bin/python -m pytest -v
```

### Test modules

| Module | What it covers |
|---|---|
| `tests/test_constants.py` | `VALID_GRADES`, `VALID_SUBJECTS`, `TOPICS_BY_SUBJECT`, `VALID_LEVELS`, `VALID_QUESTION_TYPES` completeness |
| `tests/test_llm.py` | Prompt content for each level, question-type format injection, TEKS mention, JSON parsing incl. `<think>`/`<thinking>` stripping, code fences, bare arrays, malformed input |
| `tests/test_models.py` | Column defaults, `is_vetted` property, `teks_code`/`flag_reason` columns, idempotent migration |
| `tests/test_api.py` | `/health`, `/api/topics`, `/api/question-types`, validation (422s), `/api/generate` (skipped when `SKIP_LLM=1`), `/api/rate` incl. auto-flag, `/api/stats` |
| `tests/test_frontend.py` | SPA HTML served at `/`, Alpine.js present, all subjects/levels/topics in HTML, shared lab chrome, built CSS keeps print rules |
