# Datathon — Ultia × CNC

Analysis + AI-agent toolkit for the Nexa datathon "Gérer une crise virale avec des
agents IA" (the Ultia × CNC affair, mars–avril 2026). The corpus is a ~35 k-message X
(Twitter) dataset; this repo (1) analyses the crisis dynamic and (2) runs a schema-driven
"Analyste" agent over the corpus.

## Layout

```
Dataset/            source data (data.xlsx + column dictionary)
analysis/           EDA, chart builders, deck builders (Python + Node)
agent/              the Analyste agent, its deterministic tools, and orchestrator
  config.yaml       column-role mapping — adapts the agent to any tweet corpus
  tools.py          deterministic analysis tools (profile/timeline/narratives/sample)
  analyste.py       the LLM agent that calls the tools
  orchestrateur.py  end-to-end pipeline
PROJECT_NOTES.md    running notes, key findings, and context
```

## Prerequisites

- **Python 3.12**
- **Node.js 22** (only for the `pptxgenjs` deck builders in `analysis/*.js`)

## Setup

```bash
# 1. Python environment
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Node deps (only needed for the .js deck builders)
npm install

# 3. Configure API keys
cp .env.example .env
#   then edit .env: set LLM_PROVIDER (gemini | groq | mistral) and paste the
#   matching API key. Free keys: aistudio.google.com | console.groq.com | mistral.ai
```

> The system `python3` is PEP-668 "externally managed", so install into the venv and
> run everything as `.venv/bin/python`.

## Running

**Analysis / figures**

```bash
.venv/bin/python analysis/eda.py            # regenerates analysis/out/key_figures.json
node analysis/build_deck_v3.js              # builds the .pptx deck
```

**Deterministic agent tools** (no API key needed):

```bash
.venv/bin/python agent/tools.py profile
.venv/bin/python agent/tools.py timeline --freq D
.venv/bin/python agent/tools.py narratives --k 6
.venv/bin/python agent/tools.py sample --contains blast --n 5
.venv/bin/python agent/verify_tools.py      # sanity-check the tools
```

**The LLM agent** (needs a key in `.env`):

```bash
.venv/bin/python agent/analyste.py "Quels sont les principaux narratifs ?"
.venv/bin/python agent/orchestrateur.py "Comment le CNC doit-il réagir à la crise ?"
```

## Adapting to another dataset

The agent reads column **roles** from `agent/config.yaml`, never hard-coded column names.
Point `dataset.path` at a new file and remap the `columns:` block to run the same tools
on any tweet corpus.

## Notes

- `.env` holds secrets and is git-ignored — never commit real keys.
- `.venv/` and `node_modules/` are git-ignored; recreate them with the setup steps above.
