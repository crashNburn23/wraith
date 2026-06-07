# Wraith

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A self-hosted, single-user Cyber Threat Intelligence platform. It ingests RSS feeds, scrapes full article text, extracts structured intelligence via a local LLM, and surfaces it through a daily ranked bulletin that gets smarter from your feedback.

**The loop:** Ingest → Enrich → Score → Bulletin → Feedback → better Bulletin tomorrow.

No auth. No cloud dependencies by default. No embeddings. Runs entirely on localhost.

---

## Features

- **Daily Bulletin** — all enriched articles ranked by a two-axis recommended score (threat severity + personal relevance). Paginated, filterable, hideable.
- **Re-rank by prompt** — type a natural-language focus ("ransomware hitting healthcare") and the LLM reorders the bulletin around it without rebuilding.
- **Interest Profile** — declare your sectors, threat actors, categories, and keywords. The profile match component scores every article against your profile from day one, no ratings required.
- **Feedback loop** — 👍/👎 on any article feeds into the relevance score for future bulletins. The more you rate, the more personalised it gets.
- **LLM Enrichment** — extracts AI summary, threat category, severity score (0–100), sector targets, geo data, IOCs, MITRE ATT&CK TTPs, threat actors, and CVE mentions from every article.
- **Intel Hub** — searchable, filterable views across Articles, IOCs, CVEs, and Actors.
- **CVE tracking** — CVSS, EPSS, and CISA KEV data for every CVE mentioned in your articles.
- **RAG Chat** — ask questions about your intel database; retrieval is keyword-based over enriched articles, IOCs, CVEs, and actors.
- **Score transparency** — every bulletin card shows a full drill-down: threat axis (AI severity + KEV bonus) and relevance axis (profile match + feedback signal + recency), with per-component bars and contributing articles.
- **RSS management** — add feeds manually or import a CSV. Toggle active/inactive, see failure counts.
- **Data retention** — automated weekly pruning keeps the DB lean. `scraped_text` is held 30 days post-enrichment (enough for article text view), then nulled.

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12+, FastAPI, Uvicorn |
| ORM / DB | SQLAlchemy 2, Alembic, SQLite (default) / PostgreSQL |
| Scheduling | APScheduler (in-process cron, 5 jobs) |
| Feed ingestion | feedparser, trafilatura, httpx |
| LLM | Ollama (default, local) or Anthropic API |
| Frontend | React 19, Vite, Tailwind v3, TanStack Query, React Router v7 |

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Python 3.12+ | 3.14 works |
| Node 18+ | For the frontend |
| Ollama | [ollama.com](https://ollama.com) — for local LLM enrichment |
| An LLM model | `qwen2.5:7b` (default) or `qwen2.5:14b` (better quality, needs ~10 GB VRAM) |

> **No GPU required**, but enrichment will be slow on CPU (~30–90 s/article vs ~1–5 s with GPU). Reduce `ENRICH_BATCH_SIZE` to 1–2 if running CPU-only.

---

## Quick Start

```bash
# 1. Install and start Ollama, pull a model
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:7b          # ~4.7 GB — good quality
# ollama pull qwen2.5:14b       # ~9 GB — better quality, recommended with GPU

# 2. Clone and configure
git clone <repo-url> cti_two
cd cti_two
cp .env.example .env            # defaults work out of the box for Ollama

# 3. Install dependencies, run migrations, seed RSS sources
./start.sh setup

# 4. Start the platform
./start.sh dev
```

Open **http://localhost:5173** — no login required.

---

## First Run

After `./start.sh dev` the database is empty. Run the pipeline once manually:

1. **Settings → Pipeline → Ingest → Run Now** — fetches all 10 seeded RSS feeds (~50–150 articles)
2. **Settings → Pipeline → Enrich → Run Now** — runs LLM enrichment on every pending article *(takes a while — watch the progress bar)*
3. **Settings → Build Bulletin** — scores and ranks all enriched articles into today's bulletin
4. **Settings → Interest Profile** — add your sectors, threat actors, and keywords so the profile match component starts working immediately

After that, the scheduler takes over automatically (see [Scheduled Jobs](#scheduled-jobs)).

---

## Configuration

Copy `.env.example` to `.env` and edit as needed. All fields have working defaults for a local Ollama setup.

```ini
# Database — SQLite by default, switch to Postgres when ready
DATABASE_URL=sqlite:///./cti.db
# DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/cti

# LLM — Ollama (local) is the default
LLM_PROVIDER=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen2.5:7b

# Anthropic (optional — set LLM_PROVIDER=anthropic to use)
ANTHROPIC_API_KEY=

# NVD API key (optional — increases rate limit for CVE lookups)
NVD_API_KEY=

# Enrichment pipeline
ENRICH_BATCH_SIZE=5             # articles per enrichment run
ENRICH_DELAY_SECONDS=0          # pause between LLM calls (0 = as fast as possible)

# Scheduled jobs (UTC hours, 24h)
INGEST_HOUR=7
ENRICH_HOUR=8
CVE_SYNC_HOUR=9
BULLETIN_HOUR=10

LOG_LEVEL=INFO
```

### Switching to Anthropic

```ini
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
LLM_MODEL=claude-sonnet-4-5
```

### Switching to PostgreSQL

```ini
DATABASE_URL=postgresql+psycopg2://cti_user:changeme@localhost:5432/cti_platform
```

Then run `./start.sh migrate` to apply migrations to the new database.

---

## Scoring System

Every article gets a **recommended score** (0–1) composed of two axes:

```
recommended = threat_score + relevance_score

threat_score    = (weight_ai_severity × severity/100)
                + (weight_kev_bonus   × kev_bonus)

relevance_score = (weight_profile_match  × profile_match)
                + (weight_feedback_signal × feedback_signal)
                + (weight_recency         × recency_factor)
```

### Default weights

| Component | Default | Axis | What it measures |
|---|---|---|---|
| AI Severity | 35% | Threat | LLM-extracted severity 0–100, normalised |
| Profile Match | 25% | Relevance | Overlap with your interest profile |
| Feedback Signal | 20% | Relevance | Similarity to articles you've rated 👍/👎 |
| KEV Bonus | 10% | Threat | Article mentions a CISA KEV CVE |
| Recency | 10% | Relevance | Exponential decay, 3-day half-life |

All weights are editable in **Settings → Scoring Weights** and must sum to 100%.

### Interest Profile

The profile match component scores articles against four dimensions you define in **Settings → Interest Profile**:

| Dimension | Matched against |
|---|---|
| Sectors | Article's extracted sector targets |
| Threat Actors | Article's extracted threat actors |
| Categories | Article's threat category (ransomware, vulnerability, etc.) |
| Keywords | Article title + AI summary (substring match) |

Score per dimension = `overlapping items / profile items in that dimension`, averaged across populated dimensions. An empty profile scores 0 for profile match — the 25% weight is effectively reassigned to other factors.

### Feedback Signal

After you rate ≥3 articles within the lookback window (default 90 days), the feedback signal activates. It computes weighted overlap between each candidate article and your past-rated articles across category, TTPs, actors, and sectors. The full contributing article list is visible in the score breakdown drill-down.

---

## Scheduled Jobs

| Job | Default UTC | Env var |
|---|---|---|
| Ingest RSS feeds | 07:00 | `INGEST_HOUR` |
| Enrich new articles | 08:00 | `ENRICH_HOUR` |
| CVE sync (article-linked) | 09:00 | `CVE_SYNC_HOUR` |
| Build daily bulletin | 10:00 | `BULLETIN_HOUR` |
| Data pruning | Sunday 03:00 | (fixed) |

All pipeline jobs can also be triggered manually from **Settings → Pipeline**.

---

## Data Retention

The weekly pruning job (every Sunday 03:00) applies this policy:

| Data | Rule |
|---|---|
| `scraped_text` on enriched articles | Nulled after 30 days — summary kept in `ai_summary` |
| `error` / `no_text` articles | Deleted after 14 days |
| `pending` articles | Deleted after 30 days (feed churn) |
| Enriched articles not in any bulletin | Deleted after 90 days |
| Bulletins, feedback, CVE records, actors | Kept forever |

Run it manually any time via **Settings → Storage & Retention → Run Now**.

---

## RSS Feed Import (CSV)

In addition to adding feeds one at a time, you can bulk-import via **Settings → RSS Sources → Import CSV**.

Expected format (header row required):

```csv
name,url
Krebs on Security,https://krebsonsecurity.com/feed/
Bleeping Computer,https://www.bleepingcomputer.com/feed/
```

The `url` column also accepts `feed_url`. Duplicate URLs are skipped. The import result shows added/skipped/error counts.

---

## Directory Structure

```
cti_two/
├── .env.example
├── .gitignore
├── start.sh                        # setup / dev / migrate / stop / reset-db
│
├── backend/
│   ├── pyproject.toml
│   ├── alembic/
│   │   └── versions/
│   │       ├── 0001_initial_schema.py
│   │       └── 0002_profile_match.py
│   ├── scripts/
│   │   └── seed_sources.py         # seeds 10 CTI RSS feeds, idempotent
│   └── app/
│       ├── main.py                 # FastAPI app, lifespan, router registration
│       ├── core/
│       │   ├── config.py           # Pydantic Settings (reads .env)
│       │   └── logging.py
│       ├── db/
│       │   ├── session.py
│       │   └── base.py             # DeclarativeBase + TimestampMixin
│       ├── models/                 # SQLAlchemy models
│       ├── schemas/                # Pydantic request/response models
│       ├── api/
│       │   ├── deps.py             # get_db dependency
│       │   └── routers/            # 10 routers (all prefixed /api)
│       └── services/
│           ├── enrichment_prompt.py    # LLM call + Pydantic extraction
│           ├── enrichment_runner.py    # batch orchestration, pause/resume
│           ├── enrichment_schema.py    # EnrichmentResult model
│           ├── scoring.py              # two-axis recommended score
│           ├── bulletin.py             # daily bulletin build
│           ├── rag.py                  # keyword RAG + LLM streaming for chat
│           ├── ingest_runner.py        # fetch → scrape → dedup
│           ├── feed_fetcher.py
│           ├── scraper.py              # full-text via trafilatura
│           ├── dedup.py                # SHA-256 URL dedup
│           ├── cve_enrichment.py       # NVD + EPSS + KEV per article CVE
│           ├── pruning.py              # data retention policy
│           ├── llm_client.py           # unified Ollama/Anthropic client factory
│           ├── job_state.py            # in-process run state for pipeline jobs
│           └── scheduler.py            # APScheduler job definitions
│
└── frontend/
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── App.jsx                 # router (5 routes)
        ├── main.jsx
        ├── index.css
        ├── lib/
        │   ├── api.js              # Axios wrappers for all backend endpoints
        │   └── utils.js
        ├── components/
        │   ├── Shell.jsx           # nav sidebar
        │   ├── ScoreBreakdown.jsx  # two-axis score drill-down
        │   ├── EntityModal.jsx
        │   ├── HighlightedText.jsx
        │   └── ui.jsx              # Button, Input, Card, Spinner, etc.
        └── pages/
            ├── Bulletin.jsx        # daily bulletin, re-rank, pagination
            ├── ArticleDetail.jsx   # full article + inline-editable entities
            ├── IntelHub.jsx        # Articles / IOCs / CVEs / Actors tabs
            ├── Chat.jsx            # RAG chatbot
            └── Settings.jsx        # profile, sources, scoring, pipeline, storage
```

---

## API Reference

All routes are prefixed `/api`. No authentication required.

| Router | Key endpoints |
|---|---|
| `/health` | `GET /health` |
| `/sources` | CRUD + `POST /sources/import-csv` |
| `/ingest` | `POST /run`, `GET /status` |
| `/enrich` | `POST /run`, `POST /pause`, `POST /resume`, `GET /status`, `POST /articles/{id}` |
| `/articles` | `GET /` (paginated + filtered), `GET /{id}` |
| `/bulletin` | `GET /today`, `GET /{date}`, `GET /history`, `POST /build`, `POST /rerank` |
| `/feedback` | `POST /` (rate article), `PATCH /read-status/{id}` |
| `/search` | `GET /` (full-text), `GET /ioc`, `GET /actors`, `GET /tags` |
| `/cve` | `GET /`, `GET /stats`, `GET /{cve_id}`, `POST /sync` |
| `/chat` | `POST /` (SSE streaming), `GET /health` |
| `/settings` | `GET|PATCH /scoring`, `GET|PATCH /profile`, `GET /scheduler`, `GET /feedback-signal`, `POST /prune` |

---

## `start.sh` Commands

```bash
./start.sh setup      # create venv, install deps, migrate DB, seed sources, npm install
./start.sh dev        # start API (:8000) + frontend (:5173) in background
./start.sh api        # start API only
./start.sh ui         # start frontend only
./start.sh migrate    # run pending Alembic migrations
./start.sh stop       # kill running dev processes
./start.sh reset-db   # drop and recreate local SQLite DB (destructive)
```

---

## LLM Notes

### Model recommendations

| Model | Size | Notes |
|---|---|---|
| `qwen2.5:7b` | ~4.7 GB | Default. Good JSON reliability, reasonable speed. |
| `qwen2.5:14b` | ~9 GB | Better extraction accuracy, recommended with a GPU. |
| `llama3.1:8b` | ~4.7 GB | Good alternative if qwen isn't available. |

### JSON reliability

The enrichment prompt asks for structured JSON output. `qwen2.5` models handle this well. If you see frequent enrichment errors, try:

```ini
# In .env — slower but more reliable for weak models
ENRICH_BATCH_SIZE=1
ENRICH_DELAY_SECONDS=1
```

### Ollama concurrency

Ollama processes one inference at a time. The chat endpoint has a 120-second read timeout — if enrichment is running, chat requests queue behind it. Use the **Stop** button in the chat UI to cancel a waiting request.

---

## Database Schema

13 tables. Key relationships:

```
sources ──< articles ──< iocs
                    ──< ttp_tags
                    ──< article_actors >── threat_actors
                    ──< cve_mentions  >── cve_records
                    ──< bulletin_items >── bulletins
                    ──< feedback
                    ──< read_status

scoring_config   (single row — editable via Settings)
user_profile     (single row — your interest profile)
```

---

## License

MIT — see [LICENSE](LICENSE) for the full text.

---

## Contributing / Extending

This is a personal tool, but the codebase is intentionally minimal and modifiable:

- **Add a new scoring component** — add a column to `bulletin_items`, a function in `scoring.py`, a weight to `scoring_config`, and a weight slider in `Settings.jsx`.
- **Add a new RSS source type** — extend `feed_fetcher.py`; the ingestion pipeline is source-type agnostic.
- **Switch to PostgreSQL** — update `DATABASE_URL` in `.env` and run `./start.sh migrate`. No code changes needed.
- **Switch to Anthropic** — set `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` in `.env`. The `llm_client.py` factory handles both providers transparently.
