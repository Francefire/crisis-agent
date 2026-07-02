# Datathon — Ultia × CNC

Analysis + AI-agent toolkit for the Nexa datathon *"Gérer une crise virale avec des
agents IA"* (the Ultia × CNC affair, mars–avril 2026). The corpus is a ~35 400-message
X (Twitter) dataset. This repo does two things:

1. **Analyses the dynamic of the crisis** — who spread it, how fast, with what message, and
   whether the spread was organic or coordinated.
2. **Runs an "Analyste" AI agent** that answers questions about the corpus by calling the
   same analysis code, so every claim it makes is backed by a real number.

---

## How the analysis works (the data-science part)

This section explains **what methods are used and why** — written to be presentable in a
school / student data-science context. Every method below is a standard, teachable
technique; nothing here is a black box.

The whole analysis is organised around a **5-axis grid**. A social-media crisis is too
big to describe in one number, so we split the question into five angles and pick the
right method for each:

| Axis | Question it answers | Main method |
|------|---------------------|-------------|
| **Acteurs** | Who is posting and who is being amplified? | Frequency counts + regex extraction |
| **Narratifs** | What are people actually saying? | TF-IDF + k-means clustering (unsupervised NLP) |
| **Propagation** | How fast and how far did it spread? | Time-series resampling + diffusion metrics |
| **Coordination** | Was it organic or organised? | Duplicate detection + burst detection |
| **Sémantique** | What is the emotional tone over time? | Sentiment distribution over time |

### Step 0 — Loading and cleaning the data

Before any analysis, the raw Excel file is loaded into a **pandas DataFrame** (a table in
memory). Three cleaning steps matter:

- **Parse dates.** The `Date` column is converted from text into real timestamps
  (`pd.to_datetime`). Rows with an unreadable date are dropped — you can't put a message on
  a timeline if you don't know when it happened.
- **Fill missing values.** A message with no "engagement type" is treated as an *original*
  post (the default), so we don't silently lose rows.
- **Extract the amplified author.** When someone retweets, the column `X Repost of` stores
  the *URL of the original tweet*. A **regular expression** (`twitter.com/([^/]+)/status`)
  pulls the original author's handle out of that URL. This is how we can tell *whose*
  content is being spread, not just who is doing the spreading.

> **Why it matters:** clean, typed data is the foundation. ~90% of the reliability of an
> analysis comes from getting this step right, even though it looks unglamorous.

### Axis 1 — Acteurs: who is loud, who is amplified

This is **descriptive statistics**: counting.

- `value_counts()` on the author column → the most *active* accounts (who posts most).
- `value_counts()` on the extracted repost-handle → the most *amplified* accounts (whose
  content is retweeted most). **These are two different things** — the person shouting
  loudest is rarely the person everyone is repeating. Separating them reveals the real
  "patient zero" sources versus the relay crowd.
- Share of **verified** accounts, and a **follower/following ratio** as a rough
  bot-plausibility proxy.

### Axis 2 — Narratifs: what are people saying (unsupervised NLP)

We can't read 35 000 tweets, and we don't have pre-made topic labels. So we use
**unsupervised machine learning** to let the themes emerge from the text itself. Two
classic techniques, chained together:

1. **TF-IDF vectorization** (`TfidfVectorizer`). Turns each tweet into a vector of numbers.
   TF-IDF = *Term Frequency × Inverse Document Frequency*. In plain words: a word scores
   high in a tweet if it appears **often in that tweet** but is **rare across the whole
   corpus**. This automatically down-weights filler words ("le", "et", "être" — we also
   pass an explicit French **stop-word** list) and up-weights the words that actually
   distinguish one message from another. We include **bigrams** (2-word phrases like
   "argent public") so that meaningful expressions survive, not just isolated words.

2. **K-means clustering** (`KMeans`). Groups the tweet-vectors into `k` clusters so that
   messages using similar vocabulary land together. Each resulting cluster ≈ one
   **narrative / framing** of the crisis. For every cluster we report:
   - its **distinctive terms** (the words closest to the cluster centre),
   - its **share of volume**,
   - **real example tweets** nearest the cluster centre (so a human can name the theme and
     verify it's not noise).

   > **A subtlety worth mentioning in a presentation:** we cluster **distinct messages**,
   > not raw rows. Because 86% of the corpus is retweets, clustering raw rows would just
   > rediscover "the most-copied tweet" over and over. So we deduplicate to unique texts,
   > cluster those, then *re-weight* each cluster by how many times its messages were
   > actually posted. This separates *what the distinct ideas are* from *how loud each one
   > got*.

3. **`narrative_timelines`** reuses the exact same TF-IDF + k-means labels, then plots each
   narrative's volume **over time** — revealing that framings don't all peak together
   (e.g. the "political camps" framing peaks days before the "public money / taxes"
   framing). This is the bridge between the Narratifs and Propagation axes.

### Axis 3 — Propagation: how fast and how far (time-series analysis)

This axis treats the crisis like an **epidemic curve**.

- **Resampling.** `resample("D")` / `resample("h")` buckets messages into equal time bins
  (per day, per hour) and counts them — the standard way to turn irregular event
  timestamps into a smooth time series you can plot and measure.
- **Peak detection.** Sort the series to find the biggest spikes (the day/hour the crisis
  exploded).
- **Diffusion / velocity metrics** — borrowed from epidemiology, computed on the hourly
  curve:
  - **Onset** — the first hour reaching 10% of the peak (when it "caught fire").
  - **Time-to-peak** — hours from onset to maximum.
  - **Growth rate per hour** and **doubling time** — how explosively it grew (like R₀ for a
    virus). Doubling time uses the compound-growth formula
    `ln(2) / ln(1 + growth_rate)`.
  - **Half-life** — how fast it died down after the peak.
- **Reach vs. volume lead/lag.** We compare *when audience (reach) peaks* against *when
  message-volume peaks*. If reach peaks **before** volume, it means big accounts fired
  first and the crowd relayed afterwards — a signature of top-down amplification.

### Axis 4 — Coordination: organic or organised?

The goal is to distinguish a genuine grassroots reaction from an orchestrated campaign.
Two heuristics, both simple and defensible:

- **Verbatim duplication.** Count how many times the *exact same normalised text* is
  posted. Natural conversation produces variety; hundreds of identical copies of one
  sentence is a coordination signal. We report a corpus-wide **verbatim-duplication rate**.
- **Synchronised bursts.** Group messages by *(same minute, same text)*. Many identical
  messages within the same 60-second window is hard to produce by chance and points to
  coordinated or automated posting.
- **Activity concentration.** How many accounts posted exactly once vs. many times — the
  shape of participation.

> These are **transparent rules**, not a mysterious "bot score". In a crisis analysis you
> want signals you can explain to a journalist or a regulator, and these qualify.

### Axis 5 — Sémantique: emotional tone over time

Each message carries a pre-computed **sentiment** label (positive / neutral / negative).
We compute the overall mix, then **pivot it against time** to see whether negativity
*tracks the volume spike* (it does — the negative share jumps on the peak day). This links
emotion to dynamics rather than reporting a single static percentage.

### What the analysis concludes

Running the above on this corpus produces a consistent story (full numbers in
`analysis/out/key_figures.json`): a **4-day amplification cascade**, ~86% retweets and only
~2% original posts, ignited by a small set of high-reach accounts, with verbatim copying
and synchronised bursts indicating coordination — not an organic debate. The methods above
are *how* we can say that with evidence instead of intuition.

---

## How the AI agent works (and why it's trustworthy)

A big risk with LLMs is that they **make up numbers**. This project's design prevents that
with a pattern worth explaining in a presentation:

```
        ┌─────────────────────────────────────────────┐
        │  Deterministic tools (pandas / scikit-learn) │  ← compute every number
        │  profile · timeline · narratives · sample …  │
        └─────────────────────────────────────────────┘
                          ▲   returns JSON facts
                          │
        ┌─────────────────┴───────────────────────────┐
        │  LLM "Analyste"                              │  ← only INTERPRETS & narrates,
        │  calls the tools, then writes the report     │     never touches raw data
        └──────────────────────────────────────────────┘
```

- **The LLM never reads the 35 000 raw rows.** It can only call the deterministic tools
  above, which return already-computed facts (numbers, @handles, real sample tweets). The
  model's job is to *choose which tool to call* and *narrate the result* — the arithmetic
  is done by pandas, which can't hallucinate. This is a **tool-use / RAG-style grounding**
  pattern.
- **Structured output.** The agent must fill a fixed schema (synthèse, faits-clés,
  narratifs, dynamique, limites), so the answer is always complete and comparable.
- **Orchestration.** `orchestrateur.py` chains three agents — **Analyste** (grounded
  diagnosis) → **Stratège** (response plan) → **Rédacteur** (communiqué, social posts,
  FAQ). Only the Analyste can see the data; the other two may reuse *only* the facts the
  Analyste already surfaced, so no new unverified numbers can sneak in.
- **Schema-driven & reusable.** Column *roles* live in `agent/config.yaml` (not hard-coded
  names), so the same tools run on any tweet corpus by remapping that file.

### A quick glossary (for the presentation)

- **DataFrame** — an in-memory table (rows × columns), from the pandas library.
- **Regex (regular expression)** — a text-pattern language, here used to pull a handle out
  of a URL.
- **TF-IDF** — a way to score how *characteristic* a word is of a document; the standard
  first step for turning text into numbers.
- **K-means** — an unsupervised algorithm that groups items into `k` clusters by
  similarity; here it discovers narratives without being told what to look for.
- **Resampling** — bucketing timestamped events into equal time bins to build a time
  series.
- **Doubling time / half-life** — epidemiology-style measures of how fast something grows
  and decays.
- **Grounding** — forcing the AI to base every statement on retrieved facts rather than its
  own memory.

---

## Layout

```
Dataset/            source data (data.xlsx + column dictionary)
analysis/           EDA, chart builders, deck builders (Python + Node)
  eda.py            the exploratory analysis that produces the figures + key numbers
agent/              the Analyste agent, its deterministic tools, and orchestrator
  config.yaml       column-role mapping — adapts the agent to any tweet corpus
  tools.py          deterministic analysis tools (profile/timeline/narratives/…)
  analyste.py       the LLM agent that calls the tools
  orchestrateur.py  end-to-end pipeline (Analyste → Stratège → Rédacteur)
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

# 3. Configure API keys (only needed for the LLM agent)
cp .env.example .env
#   then edit .env: set LLM_PROVIDER (gemini | groq | mistral) and paste the
#   matching API key. Free keys: aistudio.google.com | console.groq.com | mistral.ai
```

> The system `python3` is PEP-668 "externally managed", so install into the venv and
> run everything as `.venv/bin/python`.

## Running

**Analysis / figures** — regenerates every number and chart:

```bash
.venv/bin/python analysis/eda.py            # → analysis/out/key_figures.json + figures/
node analysis/build_deck_v3.js              # builds the .pptx deck
```

**Deterministic analysis tools** (no API key needed) — run any axis directly:

```bash
.venv/bin/python agent/tools.py profile
.venv/bin/python agent/tools.py timeline --freq h --velocity   # propagation + speed metrics
.venv/bin/python agent/tools.py narratives --k 6               # TF-IDF + k-means themes
.venv/bin/python agent/tools.py coordination                   # duplication + bursts
.venv/bin/python agent/tools.py semantique                     # sentiment over time
.venv/bin/python agent/tools.py sample --contains blast --n 5  # real example tweets
.venv/bin/python agent/verify_tools.py                         # sanity-check the tools
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
</content>
</invoke>
