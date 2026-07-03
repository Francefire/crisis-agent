# CLAUDE.md

Ultia × CNC datathon: analyse a viral X crisis (French corpus) **and** build an AI-agent
pipeline that tools the crisis response. Facts are real — analyse the *dynamic*, neutral tone.

## Read first (don't re-derive from code)
- **`README.md`** + **`PROJECT_NOTES.md`** — compact current state: findings, architecture,
  how to run, config. Read these by default.
- **`docs/dev-log.md`** (full history) and **`docs/superpowers/specs/`** (design specs) —
  **read on demand only**; they're large. Don't load them unless you need the *why* behind a
  past decision.

## Repo layout
- `agent/` — the pipeline: **Analyste → Relecteur → Stratège → Rédacteur** (only the Analyste
  touches data via deterministic tools; downstream stages reason only over its facts).
  - `tools.py` (Corpus + 12 pandas/NLP tools) · `providers.py` (LLM provider registry — add a
    provider = one dict entry) · `models.py` (selection policy) · `llm.py` (engine: key
    rotation, rate limit, fallback) · `analyste.py` (tools+schema+prompt, `--deep` mode) ·
    `reviewer.py` (grounding audit) · `orchestrateur.py` (declarative `Stage` pipeline —
    add an agent = one `Stage`) · `runlog.py`.
- `analysis/` — EDA + pptxgenjs deck builders. `out/key_figures.json` = canonical numbers.
- `docs/outputs/` — rendered decks. `Dataset/` — corpus.

## How to run
- **Always use `.venv/bin/python`** — system pip is PEP-668 locked; bare `python`/`pip` fail.
- `.venv/bin/python agent/verify_tools.py` — **60/60** deterministic tool checks, no API key.
  Run after any change to `tools.py`/`Corpus`; it's the fast, free correctness gate.
- `.venv/bin/python agent/orchestrateur.py "<q>" [--cache] [--deep]` — full pipeline.
- Decks: `node analysis/build_*_deck.js` (Node v22, local pptxgenjs).

## Conventions & gotchas
- **Files get edited concurrently** (user / other sessions) — re-read a file right before
  editing; don't trust a stale read.
- LLM provider/keys via `.env` (see `.env.example`): `LLM_PROVIDER` + keys `<PROVIDER>_API_KEY(S)`
  (many allowed; inline priority `key|N`). Default mistral + groq fallback.
- Keep dev notes discipline: append durable history to `docs/dev-log.md`, keep `PROJECT_NOTES.md`
  compact. Don't bloat this file — it loads every session.
- Commit only when asked; keep unrelated changes in separate commits; file moves as renames.
