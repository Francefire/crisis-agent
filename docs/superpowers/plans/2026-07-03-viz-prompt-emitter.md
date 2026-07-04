# Viz-prompt Emitter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `--emit-viz` flag to `analyste.py` and `orchestrateur.py` that writes (and prints) a paste-ready Markdown prompt instructing a downstream AI to build a single-file HTML visualizer — a data dashboard from the Analyste, and a report/action-plan from the full pipeline.

**Architecture:** One new pure-formatting module `agent/viz_prompt.py` (no LLM, no corpus) exposes `build_analyste_md`, `build_report_md`, `emit`. The two CLIs import it and wire the flag. `orchestrateur --emit-viz` emits **both** files (it already runs the Analyste and caches `tool_outputs.json`); `analyste --emit-viz` emits only the data one.

**Tech Stack:** Python 3 (stdlib only for the new module), the repo's existing `.venv/bin/python` runner. No pytest in this repo — verification is assertion-based smoke scripts run in the scratchpad, mirroring `verify_tools.py` style.

## Global Constraints

- **Always run Python as `.venv/bin/python`** (system pip is PEP-668 locked). Bare `python`/`pip` fail.
- **Re-read `analyste.py` and `orchestrateur.py` immediately before editing** — another session has uncommitted changes to both (CLAUDE.md concurrency rule). Keep edits minimal and additive.
- **The new module is stdlib-only** — `json`, `os` only. No new dependencies.
- **All user-facing strings in the emitted Markdown are French** (matches the corpus/deck language).
- **Design theme (verbatim hex):** INK `#0B1020`, PANEL `#1B2340`, VIOLET `#7C3AED`, CYAN `#22D3EE`, CORAL `#FF5C5C` (coral reserved for negatives/alerts), text LIGHT `#E5E7EB`, MUTED `#94A3B8`.
- **Commits:** the repo has unrelated WIP in `analyste.py`/`orchestrateur.py` from another session. Every commit step MUST stage **only this feature's own paths** (never `git add -A`). Commit at your discretion / when the user asks.
- **Do not touch** `tools.py`, agent prompts, or `verify_tools.py` — `verify_tools.py` must still pass 60/60 afterward.

## File Structure

- **Create** `agent/viz_prompt.py` — the emitter. Responsibility: turn already-computed data (report dict, tool_outputs strings, pipeline dict) into a Markdown prompt string, and write+print it. Pure, LLM-free, independently testable via cached JSON.
- **Modify** `agent/analyste.py` — `ask()` returns `tool_outputs`; `__main__` gains `--emit-viz`.
- **Modify** `agent/orchestrateur.py` — `__main__` recognises `--emit-viz` and emits both files.
- **Modify** `PROJECT_NOTES.md` — document the flag + artifacts.

---

### Task 1: `viz_prompt.py` — shared scaffolding, `emit`, and the data dashboard builder

**Files:**
- Create: `agent/viz_prompt.py`
- Test: `/tmp/claude-1000/-home-moto-Documents-datathon/65414dc8-d079-47b7-8e81-8967ee5c25f6/scratchpad/smoke_viz1.py`

**Interfaces:**
- Consumes: nothing (stdlib only).
- Produces:
  - `DESIGN_SYSTEM: str`
  - `_parse_tool_outputs(tool_outputs: list[str] | None) -> list[dict]`
  - `_fence(obj) -> str`
  - `build_analyste_md(report: dict, tool_outputs: list[str] | None) -> str`
  - `emit(md: str, path: str) -> None`

- [ ] **Step 1: Write the failing smoke test**

Create `scratchpad/smoke_viz1.py`:

```python
import sys, json
sys.path.insert(0, "/home/moto/Documents/datathon/agent")
import viz_prompt as v

report = json.load(open("/home/moto/Documents/datathon/agent/out/diagnostic.json"))
tool_outputs = json.load(open("/home/moto/Documents/datathon/agent/out/tool_outputs.json"))

md = v.build_analyste_md(report, tool_outputs)
assert md.startswith("# "), "must start with an H1"
for h in ["## 1. Ton rôle", "## 2. Direction artistique", "## 3. Les données",
          "## 4.", "## 5. Contraintes techniques", "## 6. Checklist"]:
    assert h in md, f"missing section: {h}"
assert "#0B1020" in md and "#FF5C5C" in md, "design hex missing"
assert "Chart.js" in md, "chart lib reminder missing"
# the fenced JSON must round-trip
block = md.split("```json", 1)[1].split("```", 1)[0]
data = json.loads(block)
assert "rapport" in data and "mesures" in data
assert isinstance(data["mesures"], list) and len(data["mesures"]) >= 1
# parser skips junk without raising
assert v._parse_tool_outputs(["not json", None, '{"a":1}']) == [{"a": 1}]
print("smoke_viz1 OK")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python "/tmp/claude-1000/-home-moto-Documents-datathon/65414dc8-d079-47b7-8e81-8967ee5c25f6/scratchpad/smoke_viz1.py"`
Expected: FAIL with `ModuleNotFoundError: No module named 'viz_prompt'`.

- [ ] **Step 3: Write `agent/viz_prompt.py` (this task's portion)**

```python
"""viz_prompt.py — emit a paste-ready Markdown prompt that instructs a downstream
AI to build a single-file HTML visualizer of the crisis analysis.

Pure formatting: no LLM calls, no corpus access. Two flavours:
  build_analyste_md  → data / numbers dashboard   (Analyste report + tool_outputs)
  build_report_md    → report / action-plan        (full orchestrator pipeline)
"""
from __future__ import annotations

import json
import os

DESIGN_SYSTEM = """\
**Thème « investigation » (cohérent avec les decks du projet) :**
- Fond INK `#0B1020` ; cartes/panneaux `#1B2340`.
- Accents : VIOLET `#7C3AED`, CYAN `#22D3EE`, CORAIL `#FF5C5C` — **le corail est réservé aux valeurs négatives / alertes**.
- Texte clair `#E5E7EB`, texte atténué `#94A3B8`.
- Titres en Georgia (serif) ; corps en sans-serif système (`system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`).
- **Graphiques honnêtes** : une seule couleur par série ; jamais de code couleur par rang qui suggère de fausses catégories. Le corail uniquement pour du réellement négatif.
- Responsive : grille CSS de cartes, conteneur `max-width`, graphiques fluides.
- Nombres au format français : espace fine pour les milliers, virgule décimale."""

_CONSTRAINTS = """\
- Produis **un seul fichier `.html`** : tout le CSS et le JS en ligne, sauf les balises `<script>` CDN.
- **Chart.js autorisé** via CDN (`https://cdn.jsdelivr.net/npm/chart.js`). Optionnel : `chartjs-plugin-annotation` (`https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation`) pour marquer l'heure d'ignition et le pic.
- Ces CDN se chargent très bien quand tu ouvres le fichier localement dans un navigateur. Si tu as besoin d'une version strictement hors-ligne / compatible « Claude Artifact », remplace Chart.js par du SVG en ligne.
- Responsive ; pas de défilement horizontal du corps ; un tableau/graphique large défile dans son propre conteneur.
- **Tous les libellés en français.**
- **N'invente aucun chiffre** : utilise uniquement le JSON fourni ci-dessus."""

_CHARTJS_FEATURES = """\
Fonctionnalités Chart.js utiles ici :
- **datasets mixtes** (`type:'line'` + `type:'bar'`) et **axe secondaire** (`scales.y1`) pour la double courbe volume vs portée ;
- **`doughnut`** avec `cutout` pour le sentiment ;
- **`indexAxis:'y'`** pour les barres horizontales (comptes amplifiés, volumes de narratifs) ;
- **tooltips** personnalisés (`plugins.tooltip.callbacks`) pour un survol riche ;
- **`chartjs-plugin-annotation`** (2ᵉ CDN, optionnel) pour tracer une ligne/zone sur l'ignition et le pic."""


def _parse_tool_outputs(tool_outputs):
    """Best-effort parse of raw tool-result strings → list of dicts. Skips
    non-JSON / budget-signal entries; never raises on a bad element."""
    out = []
    for s in tool_outputs or []:
        try:
            obj = json.loads(s)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _fence(obj) -> str:
    return "```json\n" + json.dumps(obj, ensure_ascii=False, indent=2) + "\n```"


def build_analyste_md(report, tool_outputs) -> str:
    data = {"rapport": report, "mesures": _parse_tool_outputs(tool_outputs)}
    return f"""# Visualiseur HTML — tableau de bord de crise (données & chiffres)

## 1. Ton rôle
Tu es ingénieur front-end. À partir des données ci-dessous, construis **un seul fichier `.html`** autonome : un **tableau de bord** dense et lisible façon « salle de crise » qui donne à voir l'ampleur et la dynamique de la crise en chiffres.

## 2. Direction artistique
{DESIGN_SYSTEM}

## 3. Les données
Le rapport de l'agent Analyste (`rapport`) et les mesures brutes des outils (`mesures`, où vivent les chiffres) :

{_fence(data)}

## 4. Ce qu'il faut construire
Disposition = **bandeau de KPI** (grands nombres) puis **grille responsive de cartes**, chaque carte = un graphique + une légende d'une ligne.

Guide graphique par métrique (utilise ce qui est présent dans `mesures`) :

| Métrique | Graphique | Où la trouver |
|---|---|---|
| Volume vs portée dans le temps | Chart.js **ligne mixte, double axe Y** | `timeline` : `series` / `reach` |
| Vélocité (montée, doublement, demi-vie) | cartes « grand chiffre » | `timeline` : `velocity` |
| Répartition du sentiment | **doughnut** (neutre gris, négatif corail, positif cyan) | `sentiment_share_pct` |
| Comptes les plus amplifiés | **barres horizontales** | `top_amplified_authors` |
| Volume par narratif | barres horizontales, une couleur | `rapport.narratifs[].volume_pct` |
| Synchronie de coordination | jauge / barre unique avec le ratio ×… vs hasard | `coordination` : `synchrony` |

{_CHARTJS_FEATURES}

## 5. Contraintes techniques
{_CONSTRAINTS}

## 6. Checklist d'acceptation
- [ ] Un seul fichier `.html`, s'ouvre sans erreur console.
- [ ] Bandeau KPI avec au moins 4 grands chiffres (messages, part de retweets, jour de pic, sentiment négatif).
- [ ] Au moins 4 graphiques rendus depuis les données fournies.
- [ ] Thème sombre respecté ; corail réservé au négatif.
- [ ] Libellés en français, nombres au format FR.
- [ ] Aucun chiffre absent du JSON fourni.
"""


def emit(md, path) -> None:
    """Write the Markdown to `path` and echo it to stdout (user chose 'Both')."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    size = os.path.getsize(path)
    print(f"\n[viz] écrit {path} ({size / 1024:.1f} Ko)", flush=True)
```

- [ ] **Step 4: Run the smoke test to verify it passes**

Run: `.venv/bin/python "/tmp/claude-1000/-home-moto-Documents-datathon/65414dc8-d079-47b7-8e81-8967ee5c25f6/scratchpad/smoke_viz1.py"`
Expected: prints `smoke_viz1 OK`.

- [ ] **Step 5: Commit (feature paths only)**

```bash
cd /home/moto/Documents/datathon
git add agent/viz_prompt.py
git commit -m "feat(agent): viz_prompt emitter — data dashboard builder

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `viz_prompt.py` — the report / action-plan builder

**Files:**
- Modify: `agent/viz_prompt.py`
- Test: `/tmp/claude-1000/-home-moto-Documents-datathon/65414dc8-d079-47b7-8e81-8967ee5c25f6/scratchpad/smoke_viz2.py`

**Interfaces:**
- Consumes: `DESIGN_SYSTEM`, `_parse_tool_outputs`, `_fence`, `_CONSTRAINTS`, `_CHARTJS_FEATURES` from Task 1.
- Produces: `build_report_md(pipeline_result: dict, tool_outputs: list[str] | None = None) -> str`

- [ ] **Step 1: Write the failing smoke test**

Create `scratchpad/smoke_viz2.py`:

```python
import sys, json
sys.path.insert(0, "/home/moto/Documents/datathon/agent")
import viz_prompt as v

pr = json.load(open("/home/moto/Documents/datathon/agent/out/pipeline_result.json"))
tool_outputs = json.load(open("/home/moto/Documents/datathon/agent/out/tool_outputs.json"))

md = v.build_report_md(pr, tool_outputs)
assert md.startswith("# "), "must start with an H1"
for h in ["## 1. Ton rôle", "## 2. Direction artistique", "## 3. Les données",
          "## 4.", "## 5. Contraintes techniques", "## 6. Checklist"]:
    assert h in md, f"missing section: {h}"
assert "Plan de réponse" in md and "Livrables" in md, "report sections missing"
assert "copier" in md, "copy-to-clipboard instruction missing"
block = md.split("```json", 1)[1].split("```", 1)[0]
data = json.loads(block)
for k in ["question", "client", "analyste", "stratege", "redacteur", "reviewer"]:
    assert k in data, f"payload missing {k}"
# tool_outputs optional → must not raise when omitted
md2 = v.build_report_md(pr)
assert md2.startswith("# ")
print("smoke_viz2 OK")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python "/tmp/claude-1000/-home-moto-Documents-datathon/65414dc8-d079-47b7-8e81-8967ee5c25f6/scratchpad/smoke_viz2.py"`
Expected: FAIL with `AttributeError: module 'viz_prompt' has no attribute 'build_report_md'`.

- [ ] **Step 3: Append `build_report_md` to `agent/viz_prompt.py`**

Insert immediately after `build_analyste_md` (before `emit`):

```python
def build_report_md(pipeline_result, tool_outputs=None) -> str:
    rev = pipeline_result.get("reviewer") or {}
    data = {
        "question": pipeline_result.get("question"),
        "client": pipeline_result.get("client"),
        "analyste": pipeline_result.get("analyste"),
        "stratege": pipeline_result.get("stratege"),
        "redacteur": pipeline_result.get("redacteur"),
        "reviewer": {
            "verdict": rev.get("verdict"),
            "critique_verdict": rev.get("critique_verdict"),
        },
        "served_by": pipeline_result.get("served_by"),
        "mesures": _parse_tool_outputs(tool_outputs) if tool_outputs else [],
    }
    return f"""# Visualiseur HTML — note de réponse & plan d'action

## 1. Ton rôle
Tu es ingénieur front-end. À partir des données ci-dessous, construis **un seul fichier `.html`** autonome : une **note de synthèse** qui se lit comme un briefing d'aide à la décision — diagnostic, plan de réponse, puis livrables prêts à l'emploi.

## 2. Direction artistique
{DESIGN_SYSTEM}

## 3. Les données
Résultat complet du pipeline (Analyste → Stratège → Rédacteur) + verdict du Relecteur :

{_fence(data)}

## 4. Ce qu'il faut construire
Disposition = **document en une colonne**, sections dans cet ordre :
1. **En-tête** — verdict d'ouverture + la question + le client + un **badge de confiance** (`reviewer.verdict`).
2. **Diagnostic** — `analyste.synthese` + `analyste.faits_cles` en liste ; si `mesures` est fourni, un petit **doughnut de sentiment** et une **mini courbe temporelle**.
3. **Grille 5 axes** — cartes : narratifs / dynamique / coordination / sentiment.
4. **Plan de réponse** — `stratege` : posture, objectifs, audiences, puis `axes_reponse` en cartes montrant chaque `action` + sa `justification`, puis risques + KPIs. Option : petite barre horizontale pour hiérarchiser les axes.
5. **Livrables prêts à l'emploi** — `redacteur` : communiqué, fil social (numéroté), FAQ (Q/R), éléments de langage — chacun dans une carte avec **bouton « copier »**.
6. **Pied de page** — `analyste.limites` + verdict du relecteur + `served_by`.

Graphiques (légers, seulement s'ils aident la lecture) : doughnut de sentiment, mini courbe temporelle depuis `mesures`.
{_CHARTJS_FEATURES}

## 5. Contraintes techniques
{_CONSTRAINTS}

## 6. Checklist d'acceptation
- [ ] Un seul fichier `.html`, s'ouvre sans erreur console.
- [ ] Les 6 sections présentes et dans l'ordre.
- [ ] Chaque livrable a un bouton « copier » fonctionnel.
- [ ] Badge de confiance affichant le verdict du relecteur.
- [ ] Thème sombre respecté ; libellés FR ; nombres au format FR.
- [ ] Aucun @compte / chiffre absent du JSON fourni.
"""
```

- [ ] **Step 4: Run the smoke test to verify it passes**

Run: `.venv/bin/python "/tmp/claude-1000/-home-moto-Documents-datathon/65414dc8-d079-47b7-8e81-8967ee5c25f6/scratchpad/smoke_viz2.py"`
Expected: prints `smoke_viz2 OK`.

- [ ] **Step 5: Commit (feature paths only)**

```bash
cd /home/moto/Documents/datathon
git add agent/viz_prompt.py
git commit -m "feat(agent): viz_prompt — report/action-plan builder

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Wire `--emit-viz` into `analyste.py`

**Files:**
- Modify: `agent/analyste.py` (`ask()` return dict ~line 532-537; `__main__` ~line 540-555)

**Interfaces:**
- Consumes: `viz_prompt.build_analyste_md`, `viz_prompt.emit`; `HERE` (already imported from `tools`).
- Produces: `ask()` return dict gains key `"tool_outputs": list[str]`.

- [ ] **Step 1: Re-read the file region before editing**

Run: `sed -n '532,555p' /home/moto/Documents/datathon/agent/analyste.py`
Confirm `ask()` and `__main__` still match the code below; if the other session moved them, adapt the anchors.

- [ ] **Step 2: Make `ask()` return `tool_outputs`**

Change (in `agent/analyste.py`):

```python
def ask(question: str, tier: str = "big", deep: bool = False) -> dict:
    report, tool_outputs = run_diagnostic(question, deep=deep)
    return {
        "report": report.model_dump() if report else None,
        "n_tool_calls": len(tool_outputs),
    }
```

to:

```python
def ask(question: str, tier: str = "big", deep: bool = False) -> dict:
    report, tool_outputs = run_diagnostic(question, deep=deep)
    return {
        "report": report.model_dump() if report else None,
        "n_tool_calls": len(tool_outputs),
        "tool_outputs": tool_outputs,
    }
```

- [ ] **Step 3: Add the `--emit-viz` flag to `__main__`**

After the existing `p.add_argument("--deep", ...)` block and before `args = p.parse_args()`, add:

```python
    p.add_argument("--emit-viz", action="store_true", dest="emit_viz",
                   help="écrit + affiche out/viz_analyste.md : un prompt prêt à coller "
                        "pour qu'une IA construise un tableau de bord HTML des chiffres")
```

Then, at the end of the `__main__` block, after `print(json.dumps(out["report"], indent=2, ensure_ascii=False))`, add:

```python
    if args.emit_viz:
        from viz_prompt import build_analyste_md, emit
        emit(build_analyste_md(out["report"], out["tool_outputs"]),
             os.path.join(HERE, "out", "viz_analyste.md"))
```

- [ ] **Step 4: Verify import + arg parse (no API call)**

Run:
```bash
cd /home/moto/Documents/datathon && .venv/bin/python -c "
import agent.analyste" 2>/dev/null; \
.venv/bin/python agent/analyste.py --help | grep -q "emit-viz" && echo "FLAG OK"
```
Expected: prints `FLAG OK` (the `--emit-viz` flag appears in help; no LLM call made).

- [ ] **Step 5: Verify the emit path end-to-end from cached data (no API)**

Run:
```bash
cd /home/moto/Documents/datathon && .venv/bin/python -c "
import sys; sys.path.insert(0,'agent'); import json, os
import viz_prompt as v
rep=json.load(open('agent/out/diagnostic.json')); to=json.load(open('agent/out/tool_outputs.json'))
v.emit(v.build_analyste_md(rep,to), 'agent/out/viz_analyste.md')
print('exists', os.path.exists('agent/out/viz_analyste.md'))
"
```
Expected: prints the Markdown, then `[viz] écrit agent/out/viz_analyste.md (...)` and `exists True`.

- [ ] **Step 6: Confirm no regression to the tool checks**

Run: `.venv/bin/python agent/verify_tools.py 2>&1 | tail -1`
Expected: `60/60` (unchanged — this task didn't touch `tools.py`).

- [ ] **Step 7: Commit (feature paths only)**

```bash
cd /home/moto/Documents/datathon
git add agent/analyste.py
git commit -m "feat(agent): analyste --emit-viz flag (data dashboard prompt)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Wire `--emit-viz` into `orchestrateur.py` (emit both files)

**Files:**
- Modify: `agent/orchestrateur.py` (`__main__` ~line 44-55)

**Interfaces:**
- Consumes: `viz_prompt.build_analyste_md`, `viz_prompt.build_report_md`, `viz_prompt.emit`; existing `OUT_DIR`, `TOOLOUT_CACHE`.
- Produces: writes `out/viz_analyste.md` and `out/viz_report.md`.

- [ ] **Step 1: Re-read the file region before editing**

Run: `sed -n '44,56p' /home/moto/Documents/datathon/agent/orchestrateur.py`
Confirm the `flags = {...}` set, `args = [...]`, `use_cache`, `deep`, `run_pipeline`, and the `pipeline_result.json` dump still match the anchors below.

- [ ] **Step 2: Add `--emit-viz` to the recognised flags**

Change:

```python
    flags = {"--cache", "--deep", "--thinking"}
    args = [a for a in sys.argv[1:] if a not in flags]
    use_cache = "--cache" in sys.argv[1:]
    deep = "--deep" in sys.argv[1:] or "--thinking" in sys.argv[1:]
```

to:

```python
    flags = {"--cache", "--deep", "--thinking", "--emit-viz"}
    args = [a for a in sys.argv[1:] if a not in flags]
    use_cache = "--cache" in sys.argv[1:]
    deep = "--deep" in sys.argv[1:] or "--thinking" in sys.argv[1:]
    emit_viz = "--emit-viz" in sys.argv[1:]
```

- [ ] **Step 3: Emit both files after the pipeline result is written**

After:

```python
    out = run_pipeline(q, use_cache=use_cache, deep=deep)
    with open(os.path.join(OUT_DIR, "pipeline_result.json"), "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
```

add:

```python
    if emit_viz:
        from viz_prompt import build_analyste_md, build_report_md, emit
        tool_outputs = (json.load(open(TOOLOUT_CACHE))
                        if os.path.exists(TOOLOUT_CACHE) else [])
        emit(build_analyste_md(out["analyste"], tool_outputs),
             os.path.join(OUT_DIR, "viz_analyste.md"))
        emit(build_report_md(out, tool_outputs),
             os.path.join(OUT_DIR, "viz_report.md"))
```

- [ ] **Step 4: Verify end-to-end from cache (no API call)**

Run:
```bash
cd /home/moto/Documents/datathon && .venv/bin/python agent/orchestrateur.py --cache --emit-viz "test" > /tmp/orch_emit.log 2>&1; \
ls -la agent/out/viz_analyste.md agent/out/viz_report.md && \
.venv/bin/python -c "
import json
for f in ['agent/out/viz_analyste.md','agent/out/viz_report.md']:
    md=open(f).read()
    block=md.split('\`\`\`json',1)[1].split('\`\`\`',1)[0]
    json.loads(block)
    assert md.count('## 6. Checklist')==1
    print(f, 'OK', len(md), 'chars')
"
```
Expected: both files listed, each prints `OK <n> chars` (JSON round-trips, six sections present). `--cache` means no LLM call.

- [ ] **Step 5: Commit (feature paths only)**

```bash
cd /home/moto/Documents/datathon
git add agent/orchestrateur.py
git commit -m "feat(agent): orchestrateur --emit-viz — emits data + report prompts

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Document the flag in `PROJECT_NOTES.md`

**Files:**
- Modify: `PROJECT_NOTES.md`

**Interfaces:**
- Consumes: nothing. Produces: nothing (docs only).

- [ ] **Step 1: Re-read the tail of the notes**

Run: `tail -5 /home/moto/Documents/datathon/PROJECT_NOTES.md`
Confirm the last bullet is the "Phase 3c ideas" line (or adapt placement if the other session appended more).

- [ ] **Step 2: Append the feature bullet**

Add a new bullet under the Analyste agent section (end of file is fine):

```markdown
- **HTML-visualizer prompt emitter DONE (2026-07-03)** — new `agent/viz_prompt.py` (pure, stdlib-only, no LLM): `build_analyste_md(report, tool_outputs)` → a **data dashboard** prompt, `build_report_md(pipeline_result, tool_outputs)` → a **report/action-plan** prompt; `emit()` writes the `.md` AND prints it. Wired as `--emit-viz`: `analyste.py "<q>" --emit-viz` → `out/viz_analyste.md`; `orchestrateur.py "<q>" [--cache] --emit-viz` → **both** `out/viz_analyste.md` + `out/viz_report.md` (cache path = zero API calls). Each `.md` = role brief + dark "investigation" design direction + the run's real data as fenced JSON (dashboard embeds `tool_outputs`, where the numbers live) + a section-by-section build spec + Chart.js (CDN, `chartjs-plugin-annotation` optional) feature reminders + acceptance checklist. Workflow: run with the flag → paste the `.md` into another AI → get a single-file HTML you open locally. `ask()` now also returns `tool_outputs`. Doesn't touch `tools.py`; `verify_tools.py` still 60/60.
```

- [ ] **Step 3: Commit (feature paths only)**

```bash
cd /home/moto/Documents/datathon
git add PROJECT_NOTES.md
git commit -m "docs: note the --emit-viz HTML-visualizer prompt emitter

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- New module `viz_prompt.py` with `build_analyste_md`/`build_report_md`/`emit` → Tasks 1–2. ✓
- `--emit-viz` on `analyste.py` (data) → Task 3. ✓
- `--emit-viz` on `orchestrateur.py` emitting both, cache-compatible → Task 4. ✓
- `ask()` returns `tool_outputs` → Task 3, Step 2. ✓
- Shared `DESIGN_SYSTEM` theme with verbatim hex → Task 1. ✓
- Dashboard embeds `tool_outputs`; report embeds pipeline + optional tool_outputs → Tasks 1–2. ✓
- Chart.js CDN + optional annotation plugin + feature reminders → Task 1 (`_CHARTJS_FEATURES`, `_CONSTRAINTS`). ✓
- Report layout: 6 sections incl. plan + copy-ready livrables + reviewer badge → Task 2. ✓
- Write-file-AND-print output form → `emit` (Task 1). ✓
- PROJECT_NOTES rollout note → Task 5. ✓
- Verification without API via cached JSON; `verify_tools.py` stays 60/60 → Tasks 3–4. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases" — all code and commands are concrete. ✓

**Type consistency:** `build_analyste_md(report, tool_outputs)`, `build_report_md(pipeline_result, tool_outputs=None)`, `emit(md, path)`, `_parse_tool_outputs`, `_fence` — names/signatures identical across Tasks 1–4. `ask()` return key `tool_outputs` consumed by Task 3 emit call. ✓
