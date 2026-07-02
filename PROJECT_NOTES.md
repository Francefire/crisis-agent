# Datathon — Ultia × CNC — Project Notes

Operational notes so any session can pick up where we left off. Working dir: `/home/moto/Documents/datathon` (not a git repo).

## The challenge (short)
Nexa 2-day datathon: "Gérer une crise virale avec des agents IA" — the **Ultia × CNC** affair (mars–avril 2026).
Mission = (1) understand/explain the crisis, (2) imagine automatable responses, (3) build & orchestrate ≥1 AI agent, demo on the corpus.
It is **NOT fake news** — facts are real. Analyse the **dynamic** (who amplifies, how, how fast). Neutral tone.
5-axis grid: Acteurs · Narratifs · Propagation · Coordination · Sémantique.
Day-1 deliverable = slides (grid + timeline + key figures) + a simple agent on a sample. Day-2 = end-to-end agent demo + slides + 10-min pitch.

## Data
- `Dataset/data.xlsx` — 35 396 rows × 30 cols, all French, 2026-03-19 → 2026-05-01.
- `Dataset/dictionnaire_bdd.xlsx` — column dictionary.
- Key cols: Date, Author, Full Text, `message_normalizer` (cleaned), Likes/Comments/Shares/Impressions/Reach, X Followers/Following/Posts/Verified, `X Reply to`, `X Repost of` (holds the **original tweet URL** — extract handle via regex `twitter\.com/([^/]+)/status`), Engagement Type, Hashtags (mostly empty).
- Canonical numbers live in `analysis/out/key_figures.json` (regenerate with eda.py).

## Key findings (Day-1 analysis)
- 35 396 msgs / 10 437 accounts. **86 % retweets** (30 368); only 671 originals (1,9 %). It's an amplification cascade, not a debate.
- Timeline: 4-day deflagration. Peak **27 mars = 7 303 msgs** (then 26/29/28 mars). Collapses after ~30 mars.
- Amplified accounts (most retweeted, handle from `X Repost of`): @SirAfuera 1852, @LeDindonFiscal 1544, @ojim_france 1254, @jon_delorraine 1083, @anatolium 1065, @charlesvillaa 1000, @SirenesFR 856, @EugenieBastie 791; also fxbellamy, MarionMarechal, LeCNC. Only **9,1 % verified**.
- Narratives (keyword freq): money frame (cnc, argent, euros, fonds, subventions, millions, aides), political-camp frame (gauche/extrême/droite/français), who-gets-funded frame (talent, streameuse, créateurs, cinéma, film).
- Coordination: top messages retweeted **500–654× verbatim**; synchronized same-minute bursts; 5 688 accounts post exactly 1 msg.
- Sentiment: 66 % neutral / 31 % negative / 3 % positive; negativity tracks the volume spike.

## Environment / toolchain (the tweaks that made things work)
- **Python:** system `python3` is PEP-668 "externally managed" → `pip install` fails. Use the venv:
  - `.venv/` — created with `python3 -m venv .venv`; run everything as `.venv/bin/python`.
  - Installed: pandas 3.0.3, openpyxl, matplotlib, numpy, python-pptx 1.0.2, pillow.
- **Node:** v22; `pptxgenjs` 1.0.2 installed locally (`node_modules/`). Build decks with `node analysis/<script>.js`.
- **QA rendering:** LibreOffice `soffice` + poppler `pdftoppm` are available:
  - `soffice --headless --convert-to pdf <file>.pptx`
  - `pdftoppm -jpeg -r 120 <file>.pdf slide` → slide-1.jpg … (inspect visually; use `-f N -l N` for one page).
  - matplotlib uses DejaVu Sans (no accents issues); avoid odd glyphs.

## Deck build pipeline (final = v3)
1. `analysis/eda.py` → `analysis/figures/` + `analysis/out/key_figures.json` (all numbers).
2. `analysis/build_charts_v2.py` → `analysis/figures_v2/` : `timeline.png`, `amplified.png`, `terms.png` (transparent PNGs, dark labels → sit on white cards).
3. `analysis/build_assets_v3.py` → `analysis/figures_v3/` : `hero.png`, `hero_wide.png`, `sentiment_donut.png`, `engagement_donut.png`.
4. `analysis/build_deck_v3.js` (pptxgenjs) → `Datathon_Ultia_CNC_Jour1_v3.pptx` → export PDF for QA.
- Backups: `..._v1.pptx` (python-pptx, first draft), `..._v2.pptx` (pptxgenjs, no imagery), `..._v3.pptx`/`.pdf` (final, image-rich).

## Design system
- Layout `LAYOUT_WIDE` (13.333 × 7.5"). Dark "investigation" theme.
- Colors (hex, no `#`): INK `0B1020`, PANEL `1B2340`; accents VIOLET `7C3AED`, CYAN `22D3EE`, CORAL `FF5C5C` (reserve coral for negatives/alerts); text LIGHT `E5E7EB`, MUTED `94A3B8`.
- Fonts: **Georgia** headers (serif, editorial) + **Calibri** body. Every content slide carries a chart or image; no empty bands; single-color honest charts (no rank-based color coding implying false categories).
- pptxgenjs gotchas: no `#` in hex, no 8-char hex opacity, fresh shadow object per call, `bullet:true` (not unicode •).

## Getting the deck into Canva  → see memory [[canva-import-route]]
- Manual Canva PPTX import **errors** on this account. Working route:
  1. User uploads the file (sandbox blocks me): `! curl -F "reqtype=fileupload" -F "time=1h" -F "fileToUpload=@/home/moto/Documents/datathon/Datathon_Ultia_CNC_Jour1_v3.pptx" https://litterbox.catbox.moe/resources/internals/api.php` → direct `https://litter.catbox.moe/...` link (auto-deletes 1h).
  2. Plugin `import-design-from-url` with that URL → imports as **fully editable** native Canva elements, pixel-faithful.
- Avoid Canva `generate-design` for this data deck — it drops real figures, invents placeholder charts, makes text-only slides.
- **Final Canva design:** id `DAHOOoOFvsE` — edit https://www.canva.com/d/xvDVciAFQ-CC3PQ . (Stale designs to delete manually: `DAHOOSLsGB4`, `DAHOOh03Z54`.)

## Analyste agent (see memory [[analyste-agent-plan]])
- **Phase 1 DONE** — deterministic tool layer, no LLM key needed. Lives in `agent/`:
  - `config.yaml` — column-role schema (text/author/timestamp/engagement/repost/sentiment…) + French stopwords + repost-handle regex. Remap columns here to run on any tweet corpus.
  - `tools.py` — `Corpus` class loads config+xlsx once; tools: `profile(top)`, `timeline(freq,top)` [peaks + patient-zero + amplified-onset ignition order], `narratives(k,dedupe)` [TF-IDF+k-means; dedupe=True clusters DISTINCT texts, weights by volume → n_messages + n_distinct_texts + top_terms + real samples + sentiment mix], `sample(contains/author/amplified/engagement/sentiment/date/…, n, sort)` [verbatim grounding]. All return JSON-serialisable dicts. CLI: `.venv/bin/python agent/tools.py {profile|timeline|narratives|sample} …`.
  - `verify_tools.py` — asserts tool output == `key_figures.json`; **15/15 pass** (run: `cd agent && ../.venv/bin/python verify_tools.py`).
  - New venv pkgs: scikit-learn 1.9, pyyaml, python-dotenv.
  - Note: narratives has one dominant macro-cluster (~50% "CNC finances cinema/talent w/ public money") even at high k — genuine (retweets share vocab); LLM can raise k or drill via sample().
- **Phase 2 DONE** — LLM wired, working end-to-end on Gemini.
  - `agent/analyste.py` — single tool-using agent via `langchain.agents.create_agent` (LangChain **1.3.11**). Model = `ChatGoogleGenerativeAI` `gemini-2.5-flash`, temp 0. Key: `GEMINI_API_KEY` in `.env` (loaded via python-dotenv; `.env.example` provided). Swap provider = edit `build_model()`.
  - 4 tools = thin `@tool` wrappers over `Corpus` (docstrings in FR are the tool specs). `timeline` drops the raw `series` to stay compact.
  - Structured output via `response_format=RapportAnalyste` (Pydantic): synthese / faits_cles / narratifs[nom,resume,volume_pct,exemple] / dynamique / limites.
  - System prompt enforces: fait vs narratif vs dynamique, neutral tone, every number/@handle from a tool result, "preuve insuffisante" reserved for a single missing fact (never a whole section), always fill all sections from collected tool data, use `timeline` for propagation, raise k if a cluster >50%.
  - Verified: profile-type Q → all numbers match key_figures; narratives Q → 7 grounded narratives w/ real sample tweets + correct volume shares + rich timeline-based `dynamique`. CLI: `.venv/bin/python agent/analyste.py "<question>"`.
  - Packages added: langchain 1.3.11, langchain-google-genai, langgraph.
- **Phase 3a DONE** — Analyste now covers the FULL 5-axis grid.
  - Two new deterministic tools in `tools.py`: `coordination(min_dup,top)` (verbatim-dup messages + same-minute bursts + verbatim-duplication rate 82.4% + activity concentration) and `semantique(freq)` (sentiment mix + per-period + negative-share on peak vs overall + most-negative period). CLI subcommands added.
  - `verify_tools.py` extended → **20/20 pass** (dup counts 654…, burst 7/7/6…, sentiment all match key_figures).
  - Wired into `analyste.py` as `@tool`s; `RapportAnalyste` gained `coordination` + `sentiment` fields; system prompt now maps all 5 axes to their tools (Acteurs=profile, Narratifs=narratives, Propagation=timeline, Coordination=coordination, Sémantique=semantique). Tested: "organique ou coordonnée + sentiment?" → 4 tool calls, grounded coord+sentiment verdict, all figures correct.
- **Phase 3b DONE** — orchestration `agent/orchestrateur.py`: **Analyste → Stratège → Rédacteur**.
  - Analyste = tool-grounded diagnosis (reuses analyste.py). Stratège = structured LLM call → `PlanStrategie` (objectifs/audiences/axes_reponse[justifiés par un fait]/risques/kpis/posture). Rédacteur = structured LLM call → `LivrablesRedaction` (communiqué / fil_social ≤280 / faq / éléments de langage). Client configurable (default "le CNC").
  - Grounding contract: Stratège & Rédacteur have NO corpus access; they may only use facts in the Analyste's report (no new numbers/@handles). Only the Analyste touches data.
  - CLI: `.venv/bin/python agent/orchestrateur.py "<question>"` → prints diagnostic + plan + livrables. `run_pipeline(question, client)` returns the full dict.
  - **Gemini free-tier quota WALL (confirmed):** this project's free tier caps **every** model (2.5-flash AND 2.5-flash-lite) at **20 req/day** (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`). One Analyste run ≈ 5 calls, full pipeline ≈ 7 → exhausts in ~3 runs/day. Individual agents proven working earlier today; pipeline blocked only by quota.
  - **Multi-provider support added** (robustness + quota headroom): `analyste.build_model()` now dispatches on `LLM_PROVIDER` env = `gemini|groq|mistral` (lazy imports; keys `GEMINI_API_KEY`/`GROQ_API_KEY`/`MISTRAL_API_KEY`; model override `LLM_MODEL`). `langchain-groq` + `langchain-mistralai` installed. `.env.example` updated. **To run the full pipeline today: set `LLM_PROVIDER=groq` + `GROQ_API_KEY` in `.env`** (Groq free tier = thousands/day; default model llama-3.3-70b-versatile).
  - **Diagnosis caching:** orchestrator writes `agent/out/diagnostic.json` after stage 1 and `pipeline_result.json` at the end; `--cache` flag reuses the saved diagnostic (skip the 5-call Analyste when iterating on Stratège/Rédacteur). Import-verified end-to-end (no API).
- ⏭ **Phase 3c ideas** — run the pipeline for real (needs quota: Groq key or wait for Gemini daily reset); feed orchestrator output into a Day-2 deck; add a guardrail that Rédacteur text contains no @handle/number absent from the diagnostic. Minor: some nearest-centroid narrative samples are low-signal ("Cheh pour Ultia") — prompt tells agent to fall back to `sample(contains=…, sort=reach)`.
