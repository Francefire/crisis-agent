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

from pydantic import BaseModel, Field

from analyste import build_model, build_agent, RapportAnalyste, DEFAULT_MODEL, HERE

OUT_DIR = os.path.join(HERE, "out")
os.makedirs(OUT_DIR, exist_ok=True)
DIAG_CACHE = os.path.join(OUT_DIR, "diagnostic.json")


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
def run_analyste(question: str, model: str = DEFAULT_MODEL) -> tuple[RapportAnalyste, int]:
    agent = build_agent(model)
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    report = result.get("structured_response")
    n_calls = sum(1 for m in result["messages"] if getattr(m, "type", "") == "tool")
    return report, n_calls


def run_stratege(report: RapportAnalyste, client: str,
                 model: str = DEFAULT_MODEL) -> PlanStrategie:
    llm = build_model(model).with_structured_output(PlanStrategie)
    prompt = STRATEGE_PROMPT.format(
        client=client,
        diagnostic=json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
    return llm.invoke(prompt)


def run_redacteur(report: RapportAnalyste, plan: PlanStrategie, client: str,
                  model: str = DEFAULT_MODEL) -> LivrablesRedaction:
    llm = build_model(model).with_structured_output(LivrablesRedaction)
    prompt = REDACTEUR_PROMPT.format(
        client=client,
        diagnostic=json.dumps(report.model_dump(), ensure_ascii=False, indent=2),
        plan=json.dumps(plan.model_dump(), ensure_ascii=False, indent=2))
    return llm.invoke(prompt)


def run_pipeline(question: str, client: str = "le CNC",
                 model: str = DEFAULT_MODEL, use_cache: bool = False) -> dict:
    # Stage 1 — Analyste (the expensive, multi-call stage). Cache its diagnosis so
    # a quota failure downstream (or iterating on Stratège/Rédacteur) needn't
    # re-run it. use_cache=True reuses the last saved diagnostic if present.
    if use_cache and os.path.exists(DIAG_CACHE):
        with open(DIAG_CACHE) as f:
            report = RapportAnalyste(**json.load(f))
        print(f"[1/3] Analyste  — diagnostic (cache : {DIAG_CACHE})", flush=True)
    else:
        print(f"[1/3] Analyste  — diagnostic (« {question} »)…", flush=True)
        report, n_calls = run_analyste(question, model)
        if report is None:
            sys.exit("L'Analyste n'a pas produit de rapport structuré.")
        with open(DIAG_CACHE, "w") as f:
            json.dump(report.model_dump(), f, ensure_ascii=False, indent=2)
        print(f"      {n_calls} appels d'outils — diagnostic mis en cache.", flush=True)

    print("[2/3] Stratège  — plan de réponse…", flush=True)
    plan = run_stratege(report, client, model)

    print("[3/3] Rédacteur — livrables…", flush=True)
    livrables = run_redacteur(report, plan, client, model)

    return {
        "question": question,
        "client": client,
        "analyste": report.model_dump(),
        "stratege": plan.model_dump(),
        "redacteur": livrables.model_dump(),
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
    # optional flag: --cache reuses the last saved diagnostic (skips the Analyste)
    args = [a for a in sys.argv[1:] if a != "--cache"]
    use_cache = "--cache" in sys.argv[1:]
    q = " ".join(args) or \
        "Comment le CNC doit-il réagir à cette crise virale ? Analyse la propagation, les narratifs et la coordination."
    out = run_pipeline(q, use_cache=use_cache)
    with open(os.path.join(OUT_DIR, "pipeline_result.json"), "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    _print_report(out)
