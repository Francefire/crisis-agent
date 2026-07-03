"""
Orchestration : Analyste → Stratège → Rédacteur.

A 3-agent crisis-response pipeline over the same corpus:

  1. ANALYSTE  — tool-grounded diagnosis (5-axis). Every fact from a pandas/NLP
                 tool; never invents a number or @handle. (see analyste.py)
  2. STRATÈGE  — turns the diagnosis into a response PLAN (objectives, audiences,
                 actions, risks, KPIs). Reasons ONLY over the Analyste's facts.
  3. RÉDACTEUR — drafts the concrete deliverables (communiqué, fil social, FAQ,
                 éléments de langage) executing the plan.

Grounding contract: the Stratège and Rédacteur may only rely on facts present in
the Analyste's report. They must not introduce new figures or @handles.

LLM = Gemini (free tier), key in .env. Stratège/Rédacteur are structured LLM
calls (no corpus access) — the Analyste is the only agent that touches the data.

Run:
    .venv/bin/python agent/orchestrateur.py "Comment le CNC doit-il réagir à la crise ?"
    .venv/bin/python agent/orchestrateur.py           # -> default question
"""
from __future__ import annotations

import os
import sys
import json
from dataclasses import dataclass
from typing import Callable

from pydantic import BaseModel, Field

from analyste import (build_structured, run_diagnostic, RapportAnalyste,
                       DEFAULT_MODEL, ANALYSTE_MODEL, HERE, CORPUS)
from reviewer import review, audit_livrables, corrections_message
from runlog import get_logger, served_summary, reset_served

LOG = get_logger()

OUT_DIR = os.path.join(HERE, "out")
os.makedirs(OUT_DIR, exist_ok=True)
DIAG_CACHE = os.path.join(OUT_DIR, "diagnostic.json")
TOOLOUT_CACHE = os.path.join(OUT_DIR, "tool_outputs.json")


# ============================================================ STRATÈGE schema
class AxeReponse(BaseModel):
    axe: str = Field(description="Intitulé court de l'axe de réponse")
    action: str = Field(description="Action de communication concrète et actionnable")
    justification: str = Field(
        description="Le fait précis du diagnostic qui motive cette action")


class PlanStrategie(BaseModel):
    """Plan de réponse de crise, dérivé du diagnostic de l'Analyste."""
    diagnostic_synthese: str = Field(
        description="Reformulation neutre du cœur de la crise, en 1–2 phrases")
    objectifs: list[str] = Field(description="Objectifs de communication prioritaires")
    audiences: list[str] = Field(description="Publics clés à adresser")
    axes_reponse: list[AxeReponse] = Field(
        description="Actions de réponse, chacune justifiée par un fait du diagnostic")
    risques: list[str] = Field(description="Risques et écueils à éviter (ce qu'il NE faut PAS faire)")
    kpis: list[str] = Field(description="Indicateurs de désescalade à suivre")
    posture: str = Field(description="Posture/ton recommandé (ex. transparence factuelle)")


# ============================================================ RÉDACTEUR schema
class QAItem(BaseModel):
    question: str
    reponse: str


class LivrablesRedaction(BaseModel):
    """Livrables de communication prêts à publier, exécutant le plan."""
    communique: str = Field(description="Communiqué officiel factuel (~120–180 mots)")
    fil_social: list[str] = Field(
        description="Fil de 3–5 messages courts (≤280 caractères chacun)")
    faq: list[QAItem] = Field(description="2–3 questions anticipées + réponses factuelles")
    elements_langage: list[str] = Field(description="Messages clés / éléments de langage")


# ==================================================================== prompts
STRATEGE_PROMPT = """Tu es le « Stratège » d'une cellule de gestion de crise \
informationnelle. On te fournit le DIAGNOSTIC factuel produit par l'Analyste (issu \
d'outils sur le corpus). Ta mission : transformer ce diagnostic en un PLAN DE RÉPONSE \
pour {client}.

RÈGLES :
- Raisonne UNIQUEMENT à partir des faits du diagnostic. N'invente aucun chiffre ni @compte \
absent du diagnostic.
- Chaque action doit être justifiée par un fait précis du diagnostic (dynamique, narratif, \
coordination, sentiment).
- Ton neutre et professionnel ; pas de prise de position politique. Objectif = désescalade \
et rétablissement des faits, pas polémique.
- Adapte la réponse à la nature de la propagation (ex. si fortement coordonnée/virale, \
privilégie rapidité, transparence et sourcing ; ne nourris pas le troll).

DIAGNOSTIC :
{diagnostic}"""

REDACTEUR_PROMPT = """Tu es le « Rédacteur » de la cellule de crise. On te fournit le \
DIAGNOSTIC de l'Analyste et le PLAN du Stratège. Rédige les livrables de communication \
concrets pour {client}, prêts à publier.

RÈGLES :
- Exécute le plan ; couvre les narratifs identifiés par des faits, sans les amplifier.
- N'invente aucun chiffre ni @compte : n'utilise que ceux présents dans le diagnostic \
(et seulement si tu es sûr de leur sens). En cas de doute, reste qualitatif.
- Ton factuel, calme, transparent, non défensif ; français correct. Pas d'attaque \
personnelle, pas de politique.
- `communique` : posture institutionnelle. `fil_social` : messages courts et clairs \
(≤280 caractères). `faq` : réponses aux critiques dominantes. `elements_langage` : \
formules réutilisables.

DIAGNOSTIC :
{diagnostic}

PLAN :
{plan}"""


# ================================================================= pipeline
def run_analyste(question: str, deep: bool = False) -> tuple[RapportAnalyste, int, list[str]]:
    # deep on DeepSeek → thinking tool-agent; elsewhere a no-op (see analyste.run_diagnostic)
    report, tool_outputs = run_diagnostic(question, deep=deep)
    return report, len(tool_outputs), tool_outputs


# ======================================================= declarative stages
# Everything AFTER the Analyste + Reviewer is a "generation" stage: a structured
# LLM call that reasons ONLY over prior results (no corpus access). Each is declared
# as DATA — schema + prompt + which prior results feed its prompt — so adding an
# agent to the pipeline (e.g. a fact-checker, an English rédacteur, a Q&A prepper)
# is ONE `Stage` entry in `STAGES`, with no change to the run loop. The runner fills
# the prompt from the accumulating `ctx`, validates the output against the schema,
# and stores it back in `ctx` under `key` for downstream stages to read.

def _dump(d: dict) -> str:
    return json.dumps(d, ensure_ascii=False, indent=2)


@dataclass
class Stage:
    key: str                              # ctx slot + output field (e.g. "stratege")
    name: str                             # display label (e.g. "Stratège")
    schema: type                          # pydantic output schema
    prompt: str                           # template with {..} slots
    inputs: Callable[[dict], dict]        # ctx -> prompt .format() kwargs
    note: str = ""                        # extra text after the label in the step line
    tier: str = "small"                   # LLM tier (cheap by default)


# The downstream pipeline, in order. Each `inputs` reads from `ctx`, which holds the
# client plus every prior stage's result dict (incl. "analyste" = the diagnostic).
STAGES: list[Stage] = [
    Stage(
        key="stratege", name="Stratège", schema=PlanStrategie, prompt=STRATEGE_PROMPT,
        note=" — plan de réponse",
        inputs=lambda ctx: {"client": ctx["client"],
                            "diagnostic": _dump(ctx["analyste"])},
    ),
    Stage(
        key="redacteur", name="Rédacteur", schema=LivrablesRedaction, prompt=REDACTEUR_PROMPT,
        note=" — livrables",
        inputs=lambda ctx: {"client": ctx["client"],
                            "diagnostic": _dump(ctx["analyste"]),
                            "plan": _dump(ctx["stratege"])},
    ),
]


def run_stage(stage: Stage, ctx: dict):
    """Execute one declarative stage: build a structured LLM at its tier, fill its
    prompt from `ctx`, invoke, and return the validated pydantic object."""
    llm = build_structured(stage.schema, tier=stage.tier)
    return llm.invoke(stage.prompt.format(**stage.inputs(ctx)))


def run_pipeline(question: str, client: str = "le CNC", model: str = DEFAULT_MODEL,
                 use_cache: bool = False, review_llm: bool = True,
                 deep: bool = False) -> dict:
    n_steps = 2 + len(STAGES)      # Analyste + Reviewer + each declarative stage

    # Stage 1 — Analyste (the expensive, multi-call stage). Cache its diagnosis +
    # tool outputs so a quota failure downstream (or iterating) needn't re-run it.
    if use_cache and os.path.exists(DIAG_CACHE):
        with open(DIAG_CACHE) as f:
            report = RapportAnalyste(**json.load(f))
        tool_outputs = json.load(open(TOOLOUT_CACHE)) if os.path.exists(TOOLOUT_CACHE) else []
        print(f"[1/{n_steps}] Analyste  — diagnostic (cache : {DIAG_CACHE})", flush=True)
    else:
        reset_served()
        LOG.info("=== PIPELINE « %s » | analyste=%s cheap=%s ===",
                 question, ANALYSTE_MODEL, DEFAULT_MODEL)
        print(f"[1/{n_steps}] Analyste  — diagnostic (« {question} ») [modèle : {ANALYSTE_MODEL}"
              f"{', approfondi' if deep else ''}]…", flush=True)
        report, n_calls, tool_outputs = run_analyste(question, deep=deep)
        if report is None:
            sys.exit("L'Analyste n'a pas produit de rapport structuré.")
        print(f"      {n_calls} appels d'outils.", flush=True)

    # Stage 2 — Reviewer (audit déterministe + critique LLM), avec UNE reprise.
    print(f"[2/{n_steps}] Relecteur — audit + critique…", flush=True)
    rev = review(report.model_dump(), tool_outputs, CORPUS, model, run_llm_critic=review_llm)
    n_err = sum(1 for f in rev["findings"] if f["severity"] == "error")
    print(f"      audit={rev['verdict']} — {len(rev['findings'])} constats "
          f"({n_err} erreur(s)) ; critique (avis)={rev.get('critique_verdict')}.", flush=True)
    if rev["verdict"] == "revision_requise" and not use_cache:
        print("      → reprise de l'Analyste avec les corrections…", flush=True)
        LOG.info("reviewer → reprise (%d constat(s))", len(rev["findings"]))
        report, n_calls, tool_outputs = run_analyste(question + corrections_message(rev), deep=deep)
        rev2 = review(report.model_dump(), tool_outputs, CORPUS, model, run_llm_critic=review_llm)
        rev = {**rev2, "revision": 1, "review_avant_reprise": rev}
        print(f"      après reprise : verdict={rev['verdict']} "
              f"({len(rev['findings'])} constats).", flush=True)

    with open(DIAG_CACHE, "w") as f:
        json.dump(report.model_dump(), f, ensure_ascii=False, indent=2)
    with open(TOOLOUT_CACHE, "w") as f:
        json.dump(tool_outputs, f, ensure_ascii=False)

    # Stages 3.. — declarative generation stages (Stratège, Rédacteur, …). `ctx`
    # accumulates each result so later stages can read earlier ones by key.
    ctx: dict = {"client": client, "analyste": report.model_dump()}
    for i, stage in enumerate(STAGES, start=3):
        print(f"[{i}/{n_steps}] {stage.name}{stage.note}…", flush=True)
        ctx[stage.key] = run_stage(stage, ctx).model_dump()

    # Rédacteur guardrail: livrables may not introduce a @handle/number absent from
    # the diagnostic. Runs whenever the Rédacteur stage is present.
    liv_audit: list = []
    if "redacteur" in ctx:
        liv_audit = [f.model_dump()
                     for f in audit_livrables(ctx["redacteur"], ctx["analyste"])]
        if liv_audit:
            print(f"      audit livrables : {len(liv_audit)} fuite(s) hors diagnostic.",
                  flush=True)

    served = served_summary()
    LOG.info("=== SERVED BY: %s ===", served or "(cache — aucun appel LLM)")
    print(f"      servi par : {served or '(cache)'}  |  journal : {get_logger().handlers[0].baseFilename}",
          flush=True)

    return {
        "question": question,
        "client": client,
        "analyste": ctx["analyste"],
        "reviewer": rev,
        **{s.key: ctx[s.key] for s in STAGES},
        "livrables_audit": liv_audit,
        "served_by": served,
    }


def _print_report(out: dict) -> None:
    r, p, d = out["analyste"], out["stratege"], out["redacteur"]
    L = "─" * 72
    print(f"\n{L}\nDIAGNOSTIC (Analyste)\n{L}")
    print("Synthèse :", r["synthese"])
    print("\nFaits clés :")
    for f in r["faits_cles"]:
        print("  •", f)
    if r.get("narratifs"):
        print("\nNarratifs :")
        for n in r["narratifs"]:
            vp = f" ({n['volume_pct']}%)" if n.get("volume_pct") is not None else ""
            print(f"  • {n['nom']}{vp} — {n['resume']}")
    for k in ("dynamique", "coordination", "sentiment"):
        if r.get(k):
            print(f"\n{k.capitalize()} : {r[k]}")

    rev = out.get("reviewer")
    if rev:
        print(f"\n{L}\nRELECTURE (Reviewer) — verdict : {rev['verdict']}\n{L}")
        if rev.get("revision"):
            print("(après 1 reprise de l'Analyste)")
        if rev["findings"]:
            print("Constats d'audit :")
            for f in rev["findings"]:
                print(f"  • [{f['severity']}/{f['type']}] {f['where']} — {f['detail']}")
        else:
            print("Audit : aucun @handle inconnu ni chiffre non sourcé détecté.")
        crit = rev.get("critique")
        if crit:
            print(f"Critique LLM (avis, non bloquant) — verdict : {rev.get('critique_verdict')}")
            if crit.get("surinterpretations"):
                print("  Sur-interprétations :", "; ".join(crit["surinterpretations"]))
            if crit.get("preuves_a_recouper"):
                print("  À recouper :", "; ".join(crit["preuves_a_recouper"]))
        if out.get("livrables_audit"):
            print("Fuites livrables (hors diagnostic) :")
            for f in out["livrables_audit"]:
                print(f"  • [{f['type']}] {f['detail']}")

    print(f"\n{L}\nPLAN (Stratège)\n{L}")
    print("Posture :", p["posture"])
    print("Objectifs :", "; ".join(p["objectifs"]))
    print("Audiences :", "; ".join(p["audiences"]))
    print("\nAxes de réponse :")
    for a in p["axes_reponse"]:
        print(f"  • [{a['axe']}] {a['action']}\n      ↳ justifié par : {a['justification']}")
    print("\nRisques :", "; ".join(p["risques"]))
    print("KPIs :", "; ".join(p["kpis"]))

    print(f"\n{L}\nLIVRABLES (Rédacteur)\n{L}")
    print("COMMUNIQUÉ :\n" + d["communique"])
    print("\nFIL SOCIAL :")
    for i, t in enumerate(d["fil_social"], 1):
        print(f"  {i}. {t}")
    print("\nFAQ :")
    for qa in d["faq"]:
        print(f"  Q: {qa['question']}\n  R: {qa['reponse']}")
    print("\nÉLÉMENTS DE LANGAGE :")
    for e in d["elements_langage"]:
        print("  •", e)


if __name__ == "__main__":
    # optional flags: --cache reuses the last saved diagnostic (skips the Analyste);
    # --deep / --thinking widens the Analyste's tool selection + reasoning.
    flags = {"--cache", "--deep", "--thinking"}
    args = [a for a in sys.argv[1:] if a not in flags]
    use_cache = "--cache" in sys.argv[1:]
    deep = "--deep" in sys.argv[1:] or "--thinking" in sys.argv[1:]
    q = " ".join(args) or \
        "Comment le CNC doit-il réagir à cette crise virale ? Analyse la propagation, les narratifs et la coordination."
    out = run_pipeline(q, use_cache=use_cache, deep=deep)
    with open(os.path.join(OUT_DIR, "pipeline_result.json"), "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    _print_report(out)
