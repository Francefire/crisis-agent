# Datathon — Ultia × CNC — Project Notes

Compact current-state summary so any session can pick up fast. Working dir:
`/home/moto/Documents/datathon` (git repo; remote `origin` = crisis-agent on GitHub).
**Full chronological history + rationale → [`docs/dev-log.md`](docs/dev-log.md)** (read
on demand only). Design specs → `docs/superpowers/specs/`. Rendered decks →
`docs/outputs/`.

## The challenge
Nexa 2-day datathon: "Gérer une crise virale avec des agents IA" — the **Ultia × CNC**
affair (mars–avril 2026). Mission = (1) understand/explain the crisis, (2) imagine
automatable responses, (3) build & orchestrate ≥1 AI agent, demo on the corpus.
**NOT fake news** — facts are real; analyse the *dynamic* (who amplifies, how, how
fast), neutral tone. 5-axis grid: Acteurs · Narratifs · Propagation · Coordination ·
Sémantique.

## Data
- `Dataset/data.xlsx` — 35 396 rows × 30 cols, French, 2026-03-19 → 2026-05-01.
- Key cols: Date, Author, Full Text, `message_normalizer` (cleaned), engagement metrics,
  follower proxies, `X Reply to`, `X Repost of` (original tweet URL — handle via regex
  `twitter\.com/([^/]+)/status`), Engagement Type. Column ROLES are mapped in
  `agent/config.yaml` (schema-driven → tools run on any tweet corpus).
- Canonical numbers: `analysis/out/key_figures.json` (from `analysis/eda.py`).

## Key findings (corrected)
- 35 396 msgs / 10 437 accounts. **86 % retweets** (30 368); 1.9 % originals → an
  amplification cascade, not a debate. Only **9.1 % verified**.
- Timeline: 4-day deflagration, peak **27 mars = 7 303 msgs**, collapses after ~30 mars.
  Ignition→peak ≈ **7 h**, **+28 %/h**, doubling ≈ 2.8 h; reach peaks **2 h before**
  volume (big sources fire before relays).
- Top amplified: @SirAfuera 1852, @LeDindonFiscal 1544, @ojim_france 1254, @jon_delorraine
  1083, @anatolium 1065, @charlesvillaa 1000, @SirenesFR 856, @EugenieBastie 791.
- Narratives: money frame · political-camp frame · who-gets-funded frame; framing drifts
  ("argent public/impôts" peaks 29 mars, days after the person/camp frames).
- **Coordination = synchronised RETWEET amplification, NOT copy-paste.** The ~82 %
  "verbatim duplication" counts retweets (identical by nature). True copy-paste
  (`copy_paste_rate_pct`, ORIGINAL/QUOTE only) ≈ **0.6 %**. What's real: 30.1 % of copies
  land <60 s from another, **×3.7 vs a uniform null** (`synchrony_lift_vs_uniform`) —
  suggestive, not proof. Network = broad mass-relay (one giant component), not tight
  cells. Neutral tone: "signals compatible with coordination," never "bots proven."
- Sentiment: 66 % neutral / 31 % negative / 3 % positive; negativity tracks the spike.

## Repo layout
- `agent/` — the AI-agent pipeline (see below).
- `analysis/` — EDA + deck builders (`eda.py`, `build_*_charts.py` → `figures*/`,
  `build_*_deck.js` via pptxgenjs). `out/key_figures.json` = canonical numbers.
- `docs/outputs/` — rendered decks (pptx/pdf). `docs/superpowers/specs/` — design specs.
  `docs/dev-log.md` — full history.
- `Dataset/` — the corpus.

## Agent architecture (`agent/`)
Pipeline: **Analyste → Relecteur → Stratège → Rédacteur**. Only the Analyste touches the
data (deterministic tools); downstream stages reason ONLY over its facts (grounding
contract: no new numbers/@handles).
- `tools.py` — `Corpus` class: loads config+xlsx once; 12 deterministic pandas/NLP tools
  (profile, timeline+velocity, narratives, narrative_timelines, coordination,
  coordination_network, semantique, breakdown, actor, engagement_quality, reply_network,
  sample). Every fact the LLM cites comes from here. No API key needed.
- `providers.py` — **single registry of LLM providers** (gemini/groq/mistral/deepseek):
  key env, lazy chat class, key kwarg, extra kwargs, live model-list fetcher, per-tier
  scored candidates, and an optional `thinking` capability. Adding a provider = one entry.
  Also the one key parser (`keys()`), supporting inline priority `key|N`.
- `models.py` — model *selection policy*: availability cache (24 h → `out/model_cache.json`),
  env-preferred override, best-first ordering. Reads candidates from `providers.py`.
- `llm.py` — the **LLM engine** (provider/model selection, per-provider rate limiter,
  key rotation on TOKEN-quota 429, provider+key fallback chain, `build_model/structured/
  agent`, `build_thinking_agent`). Provider priority: env `LLM_PROVIDER_PRIORITY` >
  config.yaml `llm.provider_priority` > `[LLM_PROVIDER, LLM_FALLBACK_PROVIDER]`.
- `analyste.py` — **domain layer**: the 12 `@tool` wrappers, `RapportAnalyste` schema,
  system prompt, per-run tool-call budget (`LLM_TOOL_BUDGET_TOTAL=16`/`_PER=3`; blocks
  over-exploration), `run_diagnostic()` core, and `--deep`/`--thinking` mode.
- `reviewer.py` — the Relecteur: (A) deterministic grounding auditor (every @handle must
  exist in corpus; every number must trace to a tool output; neutral-tone gate; substance
  floor) + (B) advisory LLM critic. Hard errors trigger ONE Analyste correction pass.
- `orchestrateur.py` — the pipeline runner. Downstream agents are **declarative `Stage`s**
  (`STAGES` list); adding an agent = one `Stage(key, name, schema, prompt, inputs, tier)`.
- `runlog.py` — run logging → `out/run.log` + stderr; `SERVED BY` tally proves which
  provider/model/key served each call.

## How to run
```bash
.venv/bin/python agent/verify_tools.py                 # 60/60 deterministic tool checks
.venv/bin/python agent/analyste.py "<question>"        # diagnosis only
.venv/bin/python agent/orchestrateur.py "<question>"   # full pipeline
.venv/bin/python agent/orchestrateur.py "<q>" --cache  # reuse last diagnostic
.venv/bin/python agent/orchestrateur.py "<q>" --deep   # wider budget; DeepSeek reasoning
node analysis/build_day2_deck.js                       # rebuild the master deck
```
`--deep`/`--thinking`: raises tool budget (30/5) + recursion (80) + a depth prompt suffix;
on DeepSeek it enables true reasoning (`deepseek-v4-flash`), else degrades to normal.

## Config / env (`.env`, see `.env.example`)
- `LLM_PROVIDER` (+ `LLM_FALLBACK_PROVIDER`) or `LLM_PROVIDER_PRIORITY=a,b,c`.
- Keys: `<PROVIDER>_API_KEY(S)` — one or many (comma/space/newline); inline priority `key|N`.
- Current default: `LLM_PROVIDER=mistral` + fallback `groq` (mistral-large has the context
  for the tool-heavy Analyste; Groq free tier 413s on it → falls back). DeepSeek off by
  default (paid, but 1M context + reasoning; use when `LLM_PROVIDER=deepseek` or `--deep`).
- Tunables: `LLM_RPS` (0.5), `LLM_MAX_RETRIES` (6), `LLM_TOOL_BUDGET_TOTAL/_PER`,
  `LLM_RECURSION_LIMIT`, `LLM_<PROVIDER>_<TIER>` model override.

## Toolchain gotchas
- **Python:** system pip is PEP-668 locked → always use `.venv/bin/python`. Pkgs: pandas 3,
  scikit-learn, langchain 1.3.11 + langgraph, langchain-{google-genai,groq,mistralai,openai},
  networkx, python-pptx, pyyaml, python-dotenv.
- **Node:** v22, `pptxgenjs` local. pptxgenjs: no `#`/8-char hex, fresh shadow per call,
  `bullet:true`.
- **QA:** `soffice --headless --convert-to pdf x.pptx` then `pdftoppm -jpeg -r 120 x.pdf s`.
- pandas 3.0 datetimes are µs → unix seconds via `.values.astype("datetime64[s]").astype("int64")`.

## Deck → Canva  → memory [[canva-import-route]]
Manual PPTX import errors on this account. Route: user uploads via litterbox
(`! curl -F ... https://litterbox.catbox.moe/.../api.php`) → plugin
`import-design-from-url` → fully editable native import. Avoid `generate-design` (drops
real figures). Latest master deck design: id `DAHOUyzCplc`
(edit https://www.canva.com/d/avHPYQwGPNNA3iu ).

## HTML-visualizer prompt emitter (`--emit-viz`, 2026-07-03)
`agent/viz_prompt.py` (pure, stdlib-only, no LLM): `build_analyste_md(report, tool_outputs)` →
a **data dashboard** prompt, `build_report_md(pipeline_result, tool_outputs)` → a
**report/action-plan** prompt; `emit()` writes the `.md` AND prints it. Wired as `--emit-viz`:
`analyste.py "<q>" --emit-viz` → `out/viz_analyste.md`; `orchestrateur.py "<q>" [--cache]
--emit-viz` → **both** `out/viz_analyste.md` + `out/viz_report.md` (with `--cache` = zero API
calls). Each `.md` = role brief + dark "investigation" design direction + the run's real data as
fenced JSON (the dashboard embeds `tool_outputs`, where the numbers live) + a section-by-section
build spec + Chart.js (CDN, `chartjs-plugin-annotation` optional) feature reminders + acceptance
checklist. Workflow: run with the flag → paste the `.md` into another AI → get a single-file HTML
you open locally. `ask()` now also returns `tool_outputs`. Doesn't touch `tools.py`;
`verify_tools.py` stays 60/60.
