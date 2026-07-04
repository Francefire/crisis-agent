# Viz-prompt emitter — design

**Date:** 2026-07-03
**Status:** approved (pending spec review)

## Goal

Add a launch argument `--emit-viz` to the agent CLIs that emits a **ready-to-paste Markdown prompt** instructing a downstream AI to build a single-file **HTML visualizer** of the crisis analysis. The Markdown bundles (1) a role/task brief, (2) an opinionated design direction, (3) the run's data as fenced JSON, (4) a concrete build spec, (5) technical constraints, and (6) an acceptance checklist.

Two visualizer flavours, matching the two output surfaces:

- **Data dashboard** — numbers-dense "control room" from the Analyste diagnostic **+ the run's `tool_outputs`** (where the real figures live). Emitted as `out/viz_analyste.md`.
- **Report / action-plan** — briefing-document from the full orchestrator pipeline (diagnostic → stratège plan → rédacteur livrables → reviewer verdict). Emitted as `out/viz_report.md`.

We do **not** build any HTML ourselves in this feature. We only generate the prompt+data the *other* AI consumes.

## Non-goals (YAGNI)

- No config knobs, theming options, or templating engine — two hard-coded string builders.
- No new LLM calls: emission is pure formatting over data already in memory / on disk.
- No changes to the tool layer, the agents' prompts, or `verify_tools.py`.

## Invocation & wiring

| Command | Emits |
|---|---|
| `analyste.py "<q>" --emit-viz` | `out/viz_analyste.md` (data dashboard) |
| `orchestrateur.py "<q>" --emit-viz` | **both** `out/viz_analyste.md` and `out/viz_report.md` |
| `orchestrateur.py --cache --emit-viz` | both, from cached `out/pipeline_result.json` + `out/tool_outputs.json` — **no API call** |

- Orchestrator emits both because it already runs the Analyste and caches `tool_outputs.json`.
- Output form (per user): **write the `.md` file AND print it to stdout.**
- `out/` is the existing `agent/out/` directory used by the other caches.

## Module: `agent/viz_prompt.py` (new)

Pure, LLM-free. Public surface:

```python
DESIGN_SYSTEM: str          # shared theme/brand block (dark "investigation" theme)

def build_analyste_md(report: dict, tool_outputs: list[str]) -> str
def build_report_md(pipeline_result: dict, tool_outputs: list[str] | None = None) -> str
def emit(md: str, path: str) -> None    # write file + print to stdout + print "wrote <path> (<size>)"
```

- `report` = `RapportAnalyste.model_dump()` (keys: `synthese`, `faits_cles`, `narratifs`, `dynamique`, `coordination`, `sentiment`, `limites`).
- `tool_outputs` = list of raw JSON **strings** (each a tool result). The builder parses each with `json.loads` (skipping non-JSON / budget-signal strings), tags it by an inferred tool name where possible (via distinctive keys, e.g. `velocity`→timeline, `synchrony`→coordination, `sentiment_share_pct`→profile/semantique), and embeds a cleaned list under a `data` block. Parsing is best-effort and defensive — a malformed entry is skipped, never fatal.
- `pipeline_result` = the orchestrator's result dict (keys: `question`, `client`, `analyste`, `reviewer`, `stratege`, `redacteur`, `livrables_audit`, `served_by`).
- `build_report_md` may also receive `tool_outputs` so the report can render a few supporting charts (sentiment donut, mini timeline) — optional, defaults to none.

### Emitted Markdown structure (both flavours share this skeleton)

The generated `.md` contains six top-level sections, in order:

1. **Ton rôle** — one paragraph: "you are a front-end engineer; build ONE self-contained `.html` …".
2. **Direction artistique** — the `DESIGN_SYSTEM` block + layout-specific notes.
3. **Les données** — the payload inside a fenced ```json``` block.
4. **Ce qu'il faut construire** — section-by-section spec + the chart-per-metric table.
5. **Contraintes techniques** — single file, Chart.js CDN, responsive, FR labels, honest charts.
6. **Checklist d'acceptation** — the acceptance checklist.

## `DESIGN_SYSTEM` (shared)

Reuses the deck's dark "investigation" theme for brand consistency with the Canva decks:

- Background INK `#0B1020`; cards/panels `#1B2340`.
- Accents: VIOLET `#7C3AED`, CYAN `#22D3EE`, CORAL `#FF5C5C` — **coral reserved for negatives/alerts**.
- Text LIGHT `#E5E7EB`, MUTED `#94A3B8`.
- Georgia (serif) headers + a system sans stack for body.
- **Honest charts:** single-colour series; never rank-based colour coding that implies false categories (stated deck principle). Coral only for genuinely negative/alert quantities.
- Responsive: CSS grid of cards, `max-width` container, charts fluid.

## Data dashboard spec (`build_analyste_md`)

Layout = **KPI strip + responsive grid of chart cards**, each card one metric + a one-line caption.

Chart-per-metric guidance embedded in the prompt (drawn from whatever `tool_outputs` are present):

| Metric | Chart | Source keys |
|---|---|---|
| Volume vs reach over time | Chart.js **mixed line, dual y-axis** | timeline `series` / `reach` |
| Velocity callouts (7 h to peak, ×2/2.8 h, half-life) | big-number stat cards | timeline `velocity` |
| Sentiment mix | doughnut (neutral grey, negative coral, positive cyan) | `sentiment_share_pct` |
| Top amplified accounts | horizontal bar | `top_amplified_authors` |
| Narrative volumes | horizontal bar, one colour | `narratifs[].volume_pct` |
| Coordination synchrony | gauge / single-bar with the ×3.7-vs-uniform baseline annotated | coordination `synchrony` |

**Chart.js feature reminders** to include in the prompt (per user request "remind the future AI what key features they could use"):
- mixed datasets (`type: 'line'` + `'bar'`) and a secondary axis (`scales.y1`) for the volume-vs-reach dual curve;
- `doughnut` with `cutout` for sentiment;
- `indexAxis: 'y'` for horizontal bars;
- tooltips/`callbacks` for rich hover;
- **`chartjs-plugin-annotation`** (a second, optional CDN lib) to mark the ignition hour and peak on the timeline — explicitly offered as "add this if it helps."

## Report / action-plan spec (`build_report_md`)

Layout = **single-column briefing document**:

1. Hero — headline verdict + the question + client + reviewer trust badge (`reviewer.verdict`, grounding).
2. Diagnostic summary — `analyste.synthese` + `faits_cles` as a checklist; small **sentiment donut** + **mini timeline** if `tool_outputs` supplied (charts that aid the report, per user (b)).
3. **Grille 5 axes** — narratifs / dynamique / coordination / sentiment as cards.
4. **Plan de réponse** (the action plan) — `stratege`: posture, objectifs, audiences, then `axes_reponse` as cards each showing `action` + its `justification`, then risques + KPIs. Optional small horizontal-bar to rank axes.
5. **Livrables prêts à l'emploi** — `redacteur`: communiqué, fil social (numbered), FAQ (Q/R), éléments de langage — each in a **copy-to-clipboard** card.
6. Footer — `limites` + reviewer audit findings + `served_by`.

## Technical constraints (embedded in both prompts)

- Output = **one `.html` file**, all CSS/JS inline except CDN `<script>` tags.
- **Chart.js via CDN** is allowed (and `chartjs-plugin-annotation` optionally). Note: "these load fine when you open the file locally in a browser; if you need a strict-offline / Claude-Artifact version, swap Chart.js for inline SVG."
- Responsive; no horizontal body scroll; wide tables/charts scroll inside their own container.
- All labels in **French**; numbers formatted FR (thin-space thousands, comma decimals).
- Do not invent numbers — use only the embedded JSON.

## Changes to existing files

### `agent/analyste.py`
- `ask()` return dict gains `"tool_outputs": tool_outputs` (raw strings) so the emit path has the figures. (Additive; existing `n_tool_calls` kept.)
- `__main__`: add `--emit-viz` flag. When set, after `ask(...)`, call `viz_prompt.build_analyste_md(out["report"], out["tool_outputs"])` and `emit(..., "out/viz_analyste.md")`.

### `agent/orchestrateur.py`
- `__main__`: add `--emit-viz` to the recognised flags (alongside `--cache`, `--deep`) and strip it from positional args.
- After `run_pipeline(...)` returns `out`, if `--emit-viz`: load `tool_outputs` from `out/tool_outputs.json` (freshly written by the run, or cached), then emit **both** `viz_analyste.md` (from `out["analyste"]` + tool_outputs) and `viz_report.md` (from `out` + tool_outputs).
- Path constants reuse the existing `out/` dir resolution used by `DIAG_CACHE` / `TOOLOUT_CACHE`.

## Testing / verification

- Unit-free smoke: run `orchestrateur.py --cache --emit-viz` (no API) → both `.md` files exist, are non-empty, contain a fenced ```json block that `json.loads` round-trips, and contain the six numbered sections. A tiny `scratchpad` check script asserts this.
- `analyste.py "<q>" --emit-viz` requires an LLM run (quota); verify via `--cache` path on the orchestrator instead, which exercises the same `build_analyste_md`.
- Confirm no regression: `analyste.ask` still returns `n_tool_calls`; `verify_tools.py` untouched (still 60/60).
- Manual: open the produced prompt, sanity-check it reads well and the JSON is the run's real figures.

## Rollout note for PROJECT_NOTES.md

Add a bullet documenting the `--emit-viz` flag, the two `out/viz_*.md` artifacts, and the "paste into another AI → single-file HTML" workflow.
