"""
"Reviewer" — a 4th stage that CHECKS the Analyste before the Stratège/Rédacteur
build on it. Two independent layers (the user chose "audit + critique"):

  A. GROUNDING AUDITOR (deterministic, no LLM / no quota) — the project's whole
     credibility pitch enforced mechanically. Extracts every @handle and every
     substantive number from the report and verifies each against reality:
       • @handles must exist in the corpus (author ∪ amplified ∪ replied-to);
       • substantive figures must appear verbatim in a tool result from the run;
       • neutral-tone rule: no "bot/automatisé/prouvé/orchestré" hard claims.
     For the Rédacteur, it enforces the containment guardrail: livrables may not
     introduce a @handle or number absent from the diagnostic.

  B. LLM CRITIC (one structured call) — judges what the auditor can't: axis
     coverage, over-interpretation, weak evidence that should be cross-checked
     (breakdown/actor/engagement_quality), internal contradictions, tone.

`review()` returns findings + critique + a verdict; the orchestrator uses the
verdict to run ONE correction pass (re-invoke the Analyste with the findings).
"""
from __future__ import annotations

import re
import json

from pydantic import BaseModel, Field

from analyste import build_structured, DEFAULT_MODEL
from tools import Corpus

# @handle tokens (X handles: letters/digits/_ , 1–15 chars is X's real limit,
# but we stay permissive at 2–30 to still catch obvious fabrications).
_HANDLE_RX = re.compile(r"@([A-Za-z0-9_]{2,30})")
# number-like tokens, keeping French thousands (space/nbsp/narrow-nbsp) + comma decimals
_NUM_RX = re.compile(r"\d[\d\s  .,]*\d|\d")
# hard claims banned by the neutral-tone contract (coordination is a *signal*)
_TONE_RX = re.compile(
    r"\b(bots?|automatis\w+|robots?|prouv\w+|démontr\w+|orchestr\w+|manipulation)\b",
    re.IGNORECASE)
# a real diagnosis cites many figures; below this floor it is vacuous → hard error
MIN_GROUNDED_FACTS = 3


# --------------------------------------------------------------- text helpers
def _norm_num(tok: str) -> str | None:
    """Normalise a report number to its compact tool-JSON form: strip thousands
    separators, comma→dot, drop a trailing %. Returns None if not substantive."""
    t = tok.strip().rstrip("%").strip()
    t = t.replace(" ", "").replace(" ", "").replace(" ", "")
    t = t.replace(",", ".")
    if t.count(".") > 1:                       # was a thousands-dotted int
        t = t.replace(".", "")
    if not re.fullmatch(r"\d+(\.\d+)?", t):
        return None
    digits = t.replace(".", "")
    # substantive = has a decimal, or ≥3 significant digits (skip "3 axes", years)
    if "." not in t and (len(digits) < 3 or re.fullmatch(r"(19|20)\d\d", t)):
        return None
    return t


def _numbers(text: str) -> set[str]:
    out = set()
    for m in _NUM_RX.finditer(text):
        n = _norm_num(m.group(0))
        if n:
            out.add(n)
    return out


def _handles(text: str) -> set[str]:
    return {h.lower() for h in _HANDLE_RX.findall(text)}


def _numeric_values(text: str) -> set[float]:
    """Every number in a reference text (tool JSON OR French diagnostic prose),
    normalised to float — French-aware (comma decimals, space thousands) so a
    diagnostic '29,5 %' grounds a livrable '29,5 %'."""
    out = set()
    for m in _NUM_RX.finditer(text):
        t = re.sub(r"\s", "", m.group(0)).rstrip("%").replace(",", ".")
        if t.count(".") > 1:
            t = t.replace(".", "")
        try:
            out.add(round(float(t), 4))
        except ValueError:
            pass
    return out


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= 0.05 + 0.01 * abs(b)


def _ungrounded_numbers(text: str, reference: str) -> list[str]:
    """Report numbers that trace to NOTHING in `reference`, allowing benign
    derivations: a ratio written as a percent (×100 / ÷100) and a pairwise gap
    (a−b of two reference numbers, e.g. the spread between two segments)."""
    vals = _numeric_values(reference)
    gaps = {round(abs(a - b), 2) for a in vals for b in vals if a != b}
    bad = []
    for n in _numbers(_HANDLE_RX.sub(" ", text)):   # don't scrape digits out of @handles
        v = float(n)
        grounded = (any(_close(v, b) or _close(v, b * 100) or _close(v, b / 100)
                        for b in vals) or round(v, 2) in gaps)
        if not grounded:
            bad.append(n)
    return bad


def _report_text(d: dict) -> str:
    """Flatten every string field of a nested dict to one searchable blob."""
    parts = []
    def walk(x):
        if isinstance(x, str):
            parts.append(x)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)
    walk(d)
    return "\n".join(parts)


# ------------------------------------------------------------------ auditor
class Finding(BaseModel):
    severity: str          # "error" | "warning"
    type: str              # empty_diagnosis | unknown_handle | ungrounded_number | tone | livrable_leak
    where: str
    detail: str


class Corpus_handles:
    """Lazy cache of the set of real @handles in the corpus."""
    _cache: set | None = None

    @classmethod
    def get(cls, corpus: Corpus) -> set:
        if cls._cache is None:
            col = corpus.col
            s = set(corpus.df[col["author"]].astype(str).str.lower())
            s |= set(corpus.df["_repost_handle"].dropna().astype(str).str.lower())
            s |= set(corpus.df["_reply_handle"].dropna().astype(str).str.lower())
            cls._cache = {h.lstrip("@") for h in s}
        return cls._cache


def audit_report(report: dict, tool_outputs: list[str], corpus: Corpus) -> list[Finding]:
    """Deterministic grounding audit of the Analyste report."""
    findings: list[Finding] = []
    blob = "\n".join(tool_outputs)
    known = Corpus_handles.get(corpus)
    text = _report_text(report)

    for h in _handles(text):
        if h not in known:
            findings.append(Finding(
                severity="error", type="unknown_handle", where="rapport",
                detail=f"@{h} n'existe pas dans le corpus (auteur/amplifié/répondu)."))

    for n in _ungrounded_numbers(text, blob):
        findings.append(Finding(
            severity="warning", type="ungrounded_number", where="rapport",
            detail=f"le chiffre {n} n'apparaît dans aucun résultat d'outil de ce run "
                   "(ni comme ratio en %, ni comme écart entre deux chiffres sourcés)."))

    # SUBSTANCE gate: a diagnosis must actually CITE tool-grounded facts. A vacuous
    # report (no numbers, no @handles) passes the checks above trivially precisely
    # because there is nothing to falsify — so require a floor of grounded facts.
    present_handles = {h for h in _handles(text) if h in known}
    grounded_numbers = _numbers(_HANDLE_RX.sub(" ", text)) - set(_ungrounded_numbers(text, blob))
    n_substance = len(present_handles) + len(grounded_numbers)
    if n_substance < MIN_GROUNDED_FACTS:
        called = (f"malgré {len(tool_outputs)} appel(s) d'outil" if tool_outputs
                  else "— aucun outil n'a été appelé")
        findings.append(Finding(
            severity="error", type="empty_diagnosis", where="rapport",
            detail=(f"diagnostic non étayé : {n_substance} fait chiffré/@compte sourcé "
                    f"(minimum {MIN_GROUNDED_FACTS}) {called}. Un diagnostic doit citer des "
                    "chiffres issus des outils (profile + axes pertinents), pas des "
                    "recommandations ou généralités.")))

    # tone: scan the analyst's OWN prose fields (not narratifs/faits_cles, which
    # embed verbatim tweet quotes that may legitimately contain these words)
    for field in ("coordination", "synthese", "dynamique"):
        val = report.get(field)
        if isinstance(val, str):
            for m in _TONE_RX.finditer(val):
                findings.append(Finding(
                    severity="warning", type="tone", where=field,
                    detail=f"terme « {m.group(0)} » : rester sur « signal compatible avec », "
                           "pas d'affirmation d'automatisation/intention."))
    return findings


def audit_livrables(livrables: dict, diagnostic: dict) -> list[Finding]:
    """Containment guardrail: the Rédacteur may not introduce a @handle or a
    substantive number that is absent from the Analyste diagnostic."""
    findings: list[Finding] = []
    diag_text = _report_text(diagnostic)
    diag_handles = _handles(diag_text)
    liv_text = _report_text(livrables)
    for h in _handles(liv_text) - diag_handles:
        findings.append(Finding(
            severity="error", type="livrable_leak", where="rédacteur",
            detail=f"@{h} absent du diagnostic — le Rédacteur l'a introduit."))
    for n in _ungrounded_numbers(liv_text, diag_text):
        findings.append(Finding(
            severity="warning", type="livrable_leak", where="rédacteur",
            detail=f"chiffre {n} absent du diagnostic — à retirer ou requalifier."))
    return findings


# -------------------------------------------------------------------- critic
class RevueCritique(BaseModel):
    """Critique qualitative structurée du diagnostic de l'Analyste."""
    couverture_axes: list[str] = Field(
        description="Axes (Acteurs/Narratifs/Propagation/Coordination/Sémantique) "
                    "bien traités vs manquants ou faibles")
    surinterpretations: list[str] = Field(
        description="Affirmations qui vont au-delà de ce que les faits soutiennent")
    preuves_a_recouper: list[str] = Field(
        description="Faits à corroborer par un CROISEMENT (breakdown/actor/"
                    "engagement_quality/reply_network) avant d'être affirmés")
    incoherences: list[str] = Field(description="Contradictions internes du rapport")
    ton: list[str] = Field(description="Écarts de neutralité / sur-affirmations de ton")
    verdict: str = Field(description="'valide' ou 'revision_requise'")
    corrections_demandees: list[str] = Field(
        description="Corrections concrètes à demander à l'Analyste (si revision_requise)")


CRITIC_PROMPT = """Tu es le « Relecteur » d'une cellule d'analyse de crise. On te donne \
le DIAGNOSTIC de l'Analyste (produit via des outils déterministes sur un corpus de tweets) \
et les CONSTATS AUTOMATIQUES d'un audit de conformité. Ta mission : juger la QUALITÉ et la \
SOLIDITÉ du diagnostic, pas le refaire.

Critères :
- COUVERTURE : les axes pertinents pour la question sont-ils traités (Acteurs, Narratifs, \
Propagation, Coordination, Sémantique) ?
- SUR-INTERPRÉTATION : une affirmation dépasse-t-elle les faits cités ?
- RECOUPEMENT : un fait clé repose-t-il sur une seule source alors qu'un croisement \
(breakdown par sentiment/engagement, actor, engagement_quality, reply_network) le \
confirmerait ou l'infirmerait ? Liste ces croisements à faire.
- COHÉRENCE : contradictions internes ?
- TON : neutralité (coordination = « signal compatible avec », jamais « bots prouvés »).

Rends `verdict`='revision_requise' s'il y a un @handle inconnu, une sur-interprétation nette, \
un axe clé manquant, ou une incohérence ; sinon 'valide'. Sois concret et bref.

DIAGNOSTIC :
{diagnostic}

CONSTATS AUTOMATIQUES DE L'AUDIT :
{audit}"""


def run_critic(report: dict, findings: list[Finding],
               model: str = DEFAULT_MODEL) -> RevueCritique:
    llm = build_structured(RevueCritique)
    audit_str = "\n".join(f"- [{f.severity}/{f.type}] {f.where}: {f.detail}"
                          for f in findings) or "(aucun constat automatique)"
    prompt = CRITIC_PROMPT.format(
        diagnostic=json.dumps(report, ensure_ascii=False, indent=2), audit=audit_str)
    return llm.invoke(prompt)


# ------------------------------------------------------------------- review
def review(report: dict, tool_outputs: list[str], corpus: Corpus,
           model: str = DEFAULT_MODEL, run_llm_critic: bool = True) -> dict:
    """Full review of the Analyste report.

    `verdict` drives the orchestrator's (at most one) auto-correction pass and is
    set ONLY by deterministic HARD ERRORS (fabricated @handle, livrable leak) — a
    blind re-run reliably fixes those. The LLM critic is ADVISORY: its findings
    (over-interpretation, cross-checks to run) are surfaced for a human, not
    looped on, because a re-run doesn't reliably converge on subjective notes.
    """
    findings = audit_report(report, tool_outputs, corpus)
    critique = run_critic(report, findings, model) if run_llm_critic else None
    verdict = "revision_requise" if any(f.severity == "error" for f in findings) else "valide"
    return {
        "findings": [f.model_dump() for f in findings],
        "critique": critique.model_dump() if critique else None,
        "critique_verdict": critique.verdict if critique else None,
        "verdict": verdict,
    }


def corrections_message(review_out: dict) -> str:
    """Turn a review into an instruction block appended to the Analyste question."""
    lines = ["\n\n--- CORRECTIONS DEMANDÉES PAR LE RELECTEUR (corrige-les) ---"]
    for f in review_out["findings"]:
        lines.append(f"- [{f['type']}] {f['detail']}")
    crit = review_out.get("critique") or {}
    for c in crit.get("corrections_demandees", []):
        lines.append(f"- {c}")
    for c in crit.get("preuves_a_recouper", []):
        lines.append(f"- Recoupe ce fait avec l'outil adéquat (breakdown/actor/"
                     f"engagement_quality) : {c}")
    return "\n".join(lines)
