"""
"Analyste" agent — Phase 2 (LLM wiring).

A single tool-using agent (LangChain `create_agent`) over the deterministic
Phase-1 tools. The LLM never reads raw rows: pandas/sklearn tools compute every
fact (numbers, @handles, sample tweets); the LLM only interprets, names and
narrates. Every figure or handle in the answer must come from a tool result —
otherwise the agent must say "preuve insuffisante".

LLM = Google Gemini (free tier). Swap provider by editing `build_model()`.
Clustering runs locally (free). Key is read from .env (never hard-coded).

Run:
    .venv/bin/python agent/analyste.py "Quels sont les principaux narratifs ?"
    .venv/bin/python agent/analyste.py            # -> default demo question
"""
from __future__ import annotations

import os
import sys
import json

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_core.tools import tool

from tools import Corpus, HERE, ROOT
from runlog import get_logger, ToolLogger
import llm
import models
# The LLM engine (provider/model selection, key rotation, rate limiting, fallback)
# lives in llm.py. `build_model`/`build_structured` are re-exported here so existing
# importers (reviewer, orchestrateur) keep working unchanged. This module is now the
# DOMAIN layer only: the Analyste's tools, output schema and system prompt.
from llm import build_model, build_structured

load_dotenv(os.path.join(ROOT, ".env"))
_LOG = get_logger()

# Display/back-compat strings for the PRIMARY provider (logging + imports); the real
# per-call choice happens in llm._leaf_models via models.resolve(). Provider is set
# by LLM_PROVIDER in .env (gemini|groq|mistral|deepseek); see providers.PROVIDERS.
PROVIDER = llm.PROVIDER
DEFAULT_MODEL = models.top(PROVIDER, "small")     # cheap stages tier
ANALYSTE_MODEL = models.top(PROVIDER, "big")      # Analyste tier

# One shared corpus instance (loads the 35k-row xlsx once).
CORPUS = Corpus()


# ----------------------------------------------------------------- tools
# Thin LangChain wrappers around the deterministic Corpus methods. Docstrings
# ARE the tool descriptions the LLM reads, so they must be precise.

@tool
def profile() -> dict:
    """Vue d'ensemble du corpus : volume de messages, nombre de comptes, part de
    retweets, part de comptes vérifiés, répartition des types d'engagement et du
    sentiment, comptes les plus actifs et comptes les plus amplifiés (retweetés).
    À appeler en premier pour cadrer l'échelle de la crise avant toute analyse."""
    return CORPUS.profile(top=10)


@tool
def timeline(freq: str = "h", velocity: bool = True, weight: str = "count",
             window: list | None = None) -> dict:
    """Dynamique temporelle de la crise (axe PROPAGATION). freq = 'h' (heure,
    recommandé pour la vitesse), 'D' (jour) ou 'W'. velocity=True ajoute un bloc
    `velocity` : heure d'allumage (onset), heure du pic, temps de montée
    (time_to_peak_hours), taux de croissance horaire, temps de doublement
    (doubling_time_hours) et demi-vie post-pic (half_life_hours) — pour chiffrer
    « à quelle vitesse ». weight='count'|'reach'|'impressions' choisit ce que
    mesure la courbe. Le bloc `reach` compare la courbe d'audience à la courbe de
    volume (reach_vs_volume_lead_periods < 0 = l'audience culmine AVANT le volume,
    signe que les grosses sources s'allument avant la masse des relais). window =
    ['AAAA-MM-JJ','AAAA-MM-JJ'] pour zoomer sur une fenêtre. Renvoie aussi
    top_peaks, patient_zero et amplified_onsets (ordre d'allumage des comptes)."""
    res = CORPUS.timeline(freq=freq, top=6, velocity=velocity, weight=weight,
                          window=tuple(window) if window else None)
    res.pop("series", None)  # garder la réponse compacte
    if "reach" in res:
        res["reach"].pop("reach_series", None)
    return res


@tool
def narrative_timelines(k: int = 6, freq: str = "D",
                        window: list | None = None) -> dict:
    """Propagation PAR NARRATIF (croisement Narratifs × Propagation). Reprend le
    clustering TF-IDF + k-means de `narratives`, puis donne pour chaque cluster sa
    courbe de volume dans le temps, son pic (peak_period) et sa part. `lead_lag`
    ordonne les cadrages par heure de pic : révèle si les narratifs culminent
    ensemble ou si l'un précède/suit l'autre (dérive narrative). freq/window comme
    `timeline`. Utile pour montrer que le cadrage évolue au fil de la crise."""
    res = CORPUS.narrative_timelines(k=k, freq=freq,
                                     window=tuple(window) if window else None)
    for cl in res.get("clusters", []):      # garder compact : le pic suffit, pas la série
        cl.pop("series", None)
    return res


@tool
def narratives(k: int = 6, dedupe: bool = True) -> dict:
    """Découverte non supervisée des narratifs par TF-IDF + k-means sur le texte
    nettoyé. k = nombre de clusters (essayer 6–10). dedupe=True regroupe les
    messages DISTINCTS puis pondère chaque cluster par son volume réel de
    messages. Chaque cluster renvoie : n_messages, n_distinct_texts, part (%),
    top_terms, répartition de sentiment et des tweets réels (samples) proches du
    centre — à utiliser pour nommer et illustrer chaque narratif. Augmenter k
    pour subdiviser un cluster dominant trop large."""
    return CORPUS.narratives(k=k, dedupe=dedupe, samples=3)


@tool
def sample(contains: str | None = None, author: str | None = None,
           amplified: str | None = None, engagement: str | None = None,
           sentiment: str | None = None, n: int = 5, sort: str = "reach") -> dict:
    """Renvoie des tweets RÉELS (verbatim) correspondant à un filtre, pour étayer
    une affirmation par des preuves. Filtres combinables : contains (sous-chaîne
    dans le texte), author (@compte auteur), amplified (relais d'un @compte),
    engagement (RETWEET/REPLY/QUOTE/ORIGINAL), sentiment (negative/neutral/
    positive). n = nombre de tweets, sort = 'reach' | 'recent' | 'oldest'.
    Toujours citer les @handles et chiffres tels que renvoyés ici."""
    return CORPUS.sample(contains=contains, author=author, amplified=amplified,
                         engagement=engagement, sentiment=sentiment, n=n, sort=sort)


@tool
def coordination(min_dup: int = 5, top: int = 15, delta_seconds: int = 60) -> dict:
    """Signaux de coordination / amplification.

    ⚠ DISTINCTION CLÉ — retweet vs copier-coller :
    - `verbatim_duplication_rate_pct` (clé héritée, ~82 %) et `top_duplicated_messages`
      comptent les RETWEETS, dont le texte est identique PAR NATURE (amplification
      native, pas du copier-coller) — `retweet_share_of_duplicated_pct` ≈ 100 % le
      prouve. NE présente JAMAIS ce taux comme du « copier-coller ».
    - `copy_paste_rate_pct` = VRAI copier-coller = même texte posté comme tweet
      ORIGINAL/QUOTE (retweets et réponses exclus) ; ici ≈ 0,6 % → quasi nul. C'est CE
      chiffre qu'il faut citer pour « copier-coller ». Voir `copy_paste_definition`.
    Autres clés de base : `top_synchronized_bursts`, concentration de l'activité.
    - `synchrony` : fenêtre Δ=delta_seconds. `coordination_score_pct` = part des copies
      (de retweets) postées à moins de Δ d'une autre ; compare-la à
      `expected_within_delta_uniform_pct` (attendu si l'amplification était étalée sur la
      durée de vie du tweet) via `synchrony_lift_vs_uniform` (×) — un lift > 1 = plus
      groupé que le hasard. C'est le signal de synchronie à citer. Répond à « synchronies ».
    - `near_duplicates` : variantes quasi-identiques regroupées par Jaccard 3-grammes
      ≥ 0,8. ⚠ calculées sur les textes les plus dupliqués (donc des retweets) : décrivent
      COMMENT un message s'est propagé via quelques comptes-sources, PAS des comptes qui
      copient-collent.
    - `account_behaviour` : PROXIES de comptes (aucune date de création dans les
      données) — ratio abonnements/abonnés, `low_footprint_amplifiers` (comptes à
      message unique, peu de posts, peu d'abonnés), part de vérifiés parmi les
      duplicateurs. Répond (par proxy) à « comptes récents/suspects ».
    Ton neutre : ce sont des signaux COMPATIBLES avec une amplification coordonnée,
    jamais une preuve d'automatisation ou d'intention."""
    res = CORPUS.coordination(min_dup=min_dup, top=top, delta_seconds=delta_seconds)
    syn = res.get("synchrony", {})
    syn.pop("burst_size_over_time", None)              # série journalière → sur le slide, pas dans le LLM
    syn["top_synchronized_texts"] = syn.get("top_synchronized_texts", [])[:6]
    nd = res.get("near_duplicates", {})
    nd["top_near_dup_groups"] = nd.get("top_near_dup_groups", [])[:6]
    return res


@tool
def coordination_network(min_dup: int = 5, delta_seconds: int = 60,
                         min_edge_weight: int = 1, top_clusters: int = 10) -> dict:
    """Réseau de co-activité (axe « clusters » de la coordination). Deux comptes
    sont reliés chaque fois qu'ils postent un même texte identique dans la même
    fenêtre de delta_seconds ; le poids de l'arête = nombre de rafales partagées.
    On garde les arêtes de poids ≥ min_edge_weight (1 par défaut ; augmenter pour
    ne garder que les comptes qui co-rafalent de façon répétée), puis une détection
    de communautés de Louvain (pondérée) partitionne le graphe. Renvoie n_nodes /
    n_edges / n_components / largest_component_size et `top_clusters` (taille, part
    de vérifiés, part de comptes à message unique, textes dominants partagés,
    exemples de comptes). Un grand composant unique = relais massif diffus plutôt
    que cellules isolées. Signal compatible avec une coordination, pas une preuve."""
    res = CORPUS.coordination_network(min_dup=min_dup, delta_seconds=delta_seconds,
                                      min_edge_weight=min_edge_weight,
                                      top_clusters=top_clusters)
    res["top_clusters"] = res.get("top_clusters", [])[:5]   # compact pour le LLM
    for cl in res["top_clusters"]:
        cl["sample_accounts"] = cl.get("sample_accounts", [])[:3]
        cl["dominant_shared_texts"] = cl.get("dominant_shared_texts", [])[:1]
    return res


@tool
def semantique(freq: str = "D") -> dict:
    """Dynamique du sentiment. freq = 'D'/'h'/'W'. Renvoie la répartition globale
    (négatif/neutre/positif), l'évolution par période, la part de négatif le jour
    du pic de volume vs la moyenne, et la période la plus négative. Utile pour
    savoir si la négativité suit ou précède le pic d'activité."""
    return CORPUS.semantique(freq=freq)


@tool
def breakdown(by: str, metrics: list | None = None) -> dict:
    """CROISEMENT de métriques par une dimension — l'outil pour comparer des
    segments et RECOUPER une affirmation. `by` = 'sentiment' | 'engagement' |
    'verified' | 'day' | 'hour'. `metrics` (sous-ensemble) : 'volume',
    'share_pct', 'dup_rate' (taux de copier-coller verbatim DANS le segment),
    'synchrony_score' (part des copies postées à <60 s d'une autre DANS le
    segment), 'verified_share', 'low_footprint_share' (proxy comptes jetables),
    'mean_reach', 'mean_organic_engagement'. Renvoie chaque segment PLUS un bloc
    `gaps` (min/max/écart + quel segment détient chaque extrême) : pour étayer
    « les X sont plus copiés que les Y » par l'écart chiffré, pas une intuition.
    Ex. « les réponses positives sont-elles autant copiées/bot que les négatives ? »
    → breakdown(by='sentiment', metrics=['dup_rate','synchrony_score','low_footprint_share'])."""
    return CORPUS.breakdown(by=by, metrics=metrics)


@tool
def actor(handle: str, samples: int = 5) -> dict:
    """Dossier MULTI-SOURCE sur UN compte (axe ACTEURS approfondi) — recoupe
    « ce compte est-il un moteur ? » sous plusieurs angles indépendants : son
    activité propre (messages, mix engagement/sentiment, proxies abonnés/
    abonnements/posts/vérifié, qui il cite/relaie) ET ce qui se passe autour de
    lui (nombre de fois où son contenu est retweeté + nb de relayeurs distincts,
    réponses reçues + leur négativité). Utile pour corroborer un nom des
    top-listes de `profile`. Cite les @handles et chiffres tels quels."""
    return CORPUS.actor(handle=handle, samples=samples)


@tool
def engagement_quality() -> dict:
    """Signal d'authenticité INDÉPENDANT : engagement organique (likes+commentaires
    +partages) rapporté au reach. RECOUPE les signaux de copier-coller/synchronie
    depuis une source séparée. Renvoie le ratio organique/reach global et par type
    d'engagement, le contraste messages dupliqués vs uniques, et les anomalies
    « fort reach / engagement organique quasi-nul » (amplifié mais peu engagé
    organiquement — compatible avec une amplification mécanique). Note : les
    RETWEET portent le reach mais 0 engagement organique (attribué à l'original) —
    à interpréter avec prudence, ton neutre."""
    return CORPUS.engagement_quality()


@tool
def reply_network(top: int = 15) -> dict:
    """Structure conversationnelle depuis « X Reply to » (INDÉPENDANTE du graphe
    de retweets) : qui est le plus RÉPONDU/pris à partie et à quel point ces
    réponses sont négatives. Complète la vue « amplification » par une vue « qui
    est attaqué ». Renvoie n_replies, part de réponses, cibles principales avec
    part de négatif. Cite les @handles tels quels."""
    return CORPUS.reply_network(top=top)


_TOOLS_RAW = [profile, timeline, narrative_timelines, narratives, sample,
              coordination, coordination_network, semantique,
              breakdown, actor, engagement_quality, reply_network]

# ---- deterministic tool-call BUDGET -----------------------------------------
# Prompts are advisory; this is enforcement. A thorough reasoning model (e.g.
# deepseek-chat) otherwise over-explores — calling `sample`/`actor` 20+ times —
# and blows the recursion limit. Once a tool is over its per-tool budget, or the
# run is over its total budget, the wrapper returns a STOP signal instead of more
# data, forcing the agent to write the report. Env-overridable.
import functools
from collections import Counter

TOOL_BUDGET_TOTAL = int(os.environ.get("LLM_TOOL_BUDGET_TOTAL", "16"))
TOOL_BUDGET_PER = int(os.environ.get("LLM_TOOL_BUDGET_PER", "3"))
_TOOL_CALLS: Counter = Counter()

_STOP_MSG = {"budget_exhausted": True,
             "message": ("Budget d'exploration atteint : n'appelle plus d'outils. "
                         "RÉDIGE MAINTENANT le rapport structuré à partir des "
                         "données déjà collectées.")}


def reset_tool_budget() -> None:
    """Call at the start of each Analyste run so the budget is per-run."""
    _TOOL_CALLS.clear()


def _budgeted(t):
    """Wrap a tool so calls past the per-tool / total budget return a stop signal."""
    orig = t.func

    @functools.wraps(orig)
    def wrapper(*args, **kwargs):
        _TOOL_CALLS[t.name] += 1
        _TOOL_CALLS["__total__"] += 1
        if _TOOL_CALLS[t.name] > TOOL_BUDGET_PER or _TOOL_CALLS["__total__"] > TOOL_BUDGET_TOTAL:
            _LOG.info("budget → %s bloqué (%d× ce tool, %d au total)",
                      t.name, _TOOL_CALLS[t.name], _TOOL_CALLS["__total__"])
            return _STOP_MSG
        return orig(*args, **kwargs)

    t.func = wrapper
    return t


TOOLS = [_budgeted(t) for t in _TOOLS_RAW]


# -------------------------------------------------------------- schema out
class Narratif(BaseModel):
    nom: str = Field(description="Nom court et neutre du narratif")
    resume: str = Field(description="Ce que dit ce narratif, ton descriptif")
    volume_pct: float | None = Field(
        default=None, description="Part du volume (%) issue du cluster")
    exemple: str = Field(description="Un tweet réel (verbatim) illustrant le narratif")


class RapportAnalyste(BaseModel):
    """Sortie structurée de l'Analyste. Tous les chiffres/@handles proviennent
    d'un résultat d'outil ; sinon 'preuve insuffisante'."""
    synthese: str = Field(description="Synthèse neutre en 2–3 phrases")
    faits_cles: list[str] = Field(description="Faits chiffrés et sourcés (fait, pas opinion)")
    narratifs: list[Narratif] = Field(default_factory=list)
    dynamique: str = Field(description="Comment la crise s'est propagée dans le temps")
    coordination: str | None = Field(
        default=None,
        description="Indices de coordination/amplification — DISTINGUE l'amplification "
                    "par retweet (duplication verbatim ~82 % = retweets, PAS du copier-coller) "
                    "du vrai copier-coller (copy_paste_rate_pct ≈ 0,6 %) ; cite la synchronie et "
                    "son lift vs hasard (synchrony_lift_vs_uniform), les proxies de comptes, les "
                    "clusters de co-activité — ton neutre : signaux compatibles avec une "
                    "coordination, pas une preuve — si pertinent")
    sentiment: str | None = Field(
        default=None,
        description="Lecture du sentiment et de son évolution — si pertinent")
    limites: str = Field(description="Limites méthodologiques / preuves manquantes")


SYSTEM_PROMPT = """Tu es « l'Analyste », un agent d'analyse de crise informationnelle \
sur les réseaux sociaux. Tu étudies un corpus de tweets déjà chargé, via des OUTILS \
déterministes (pandas/NLP). Tu n'as PAS accès aux lignes brutes : tu dois appeler les \
outils pour obtenir tout fait.

Corpus : affaire Ultia × CNC (mars–avril 2026), en français. Les faits sont RÉELS — \
ne juge pas leur véracité ; analyse la DYNAMIQUE (qui amplifie, comment, à quelle vitesse).

Grille d'analyse en 5 axes, chacun servi par un outil : ACTEURS (`profile` : comptes \
actifs/amplifiés), NARRATIFS (`narratives`), PROPAGATION (`timeline` + `narrative_timelines`), \
COORDINATION (`coordination` + `coordination_network`), SÉMANTIQUE \
(`semantique` : sentiment dans le temps). Choisis les axes/outils pertinents pour la question.

IMPORTANT — TON RÔLE EST LE DIAGNOSTIC, PAS LE CONSEIL : même si la question porte sur la \
RÉPONSE ou la GESTION à adopter (« comment le CNC devrait-il réagir/gérer la crise ? »), tu ne \
donnes JAMAIS de recommandations ni de conseils de communication (c'est le rôle du Stratège en \
aval). Tu commences TOUJOURS par `profile`, puis tu appelles les axes pertinents, et tu \
n'écris QUE des faits chiffrés et sourcés issus des outils (volumes, %, @comptes, vitesses, \
scores de coordination…). Une réponse faite de généralités (« être transparent », « réagir \
vite ») sans chiffres d'outils est un ÉCHEC et sera rejetée par le relecteur.

COORDINATION (« est-ce orchestré ? synchronies, copier-coller, comptes récents, clusters ») : \
appelle `coordination`. ⚠ DISTINGUE amplification par retweet et copier-coller : le taux de \
« duplication verbatim » (~82 %) compte les RETWEETS, dont le texte est identique PAR NATURE \
(`retweet_share_of_duplicated_pct` ≈ 100 %) — NE le présente JAMAIS comme du « copier-coller » \
ni comme des « copies exactes ». Pour le copier-coller, cite `copy_paste_rate_pct` (vrai texte \
identique posté en ORIGINAL/QUOTE ≈ 0,6 % → quasi nul). Pour la synchronie, cite le \
`coordination_score_pct` (part des retweets postés à <60 s d'un autre) ET son rapport au hasard \
`synchrony_lift_vs_uniform` (× vs un étalement uniforme sur la durée de vie des tweets ; >1 = \
plus groupé que le hasard). Ajoute le bloc `account_behaviour` (proxies de comptes). Pour l'axe \
« clusters », appelle `coordination_network` (communautés de comptes co-rafalant le même texte). RÈGLE DE TON \
STRICTE : parle de « signaux compatibles avec une amplification coordonnée », jamais de « bots \
prouvés » ni d'intention démontrée. Rappelle dans `limites` qu'AUCUNE date de création de compte \
n'existe : « comptes récents » est un PROXY (message unique + peu de posts + peu d'abonnés).

PROPAGATION (le cœur de l'analyse — « qui amplifie, comment, à quelle vitesse ») : pour \
chiffrer la VITESSE, appelle `timeline` en freq='h' avec velocity=True et cite le temps de \
montée, le temps de doublement et la demi-vie ; regarde `reach_vs_volume_lead_periods` pour \
dire si l'audience (grosses sources) culmine avant ou après la masse des relais. Pour montrer \
que le CADRAGE ÉVOLUE, appelle `narrative_timelines` et lis `lead_lag` (quel narratif pique \
en premier, lequel suit).

CROISEMENT / RECOUPEMENT (renforce la crédibilité — un fait confirmé par deux sources \
indépendantes vaut mieux qu'un seul chiffre) : pour COMPARER des segments (ex. « les \
réponses positives sont-elles autant copiées/bot que les négatives/neutres ? »), appelle \
`breakdown(by='sentiment', metrics=[...])` et cite le bloc `gaps` (l'écart chiffré), jamais \
une intuition. Pour approfondir UN compte cité dans une top-liste, appelle `actor(handle)` \
(active/amplifie/répond + réactions reçues). Pour CORROBORER la coordination par une source \
séparée, appelle `engagement_quality` (fort reach + engagement organique quasi-nul = \
compatible avec une amplification mécanique) — si deux signaux indépendants concordent, \
dis-le ; s'ils divergent, signale-le. Pour la vue « qui est pris à partie », `reply_network`.

RÈGLES ABSOLUES :
1. Chaque chiffre et chaque @compte que tu écris DOIT provenir d'un résultat d'outil de \
ce tour. N'invente jamais un chiffre ni un @compte. « preuve insuffisante » se réserve à \
UN fait précis manquant — ne l'utilise JAMAIS pour remplir une section entière.
2. Tu DOIS remplir toutes les sections du rapport à partir des résultats d'outils que tu \
as obtenus : `synthese`, `faits_cles`, `dynamique` et `limites` se rédigent toujours à \
partir des données déjà collectées (jamais « preuve insuffisante »). Si une section a \
besoin de données que tu n'as pas encore, appelle l'outil correspondant AVANT de conclure.
3. Distingue trois niveaux : le FAIT (ce qui s'est passé), le NARRATIF (la manière dont \
c'est cadré/raconté) et la DYNAMIQUE (comment ça se propage).
4. Ton neutre, analytique, factuel. Pas de prise de position politique.
5. Illustre chaque narratif par un tweet réel et REPRÉSENTATIF. Si l'exemple le plus \
proche du centre (`narratives.samples`) est trop court ou peu parlant, appelle `sample` \
avec un terme distinctif du cluster (`contains=...`, sort='reach') pour un meilleur verbatim.
6. `limites` = limites MÉTHODOLOGIQUES réelles (ex. un cluster dominant très large agrège \
plusieurs cadrages ; l'analyse porte sur le texte nettoyé ; sentiment pré-calculé), pas un \
aveu d'ignorance.

MÉTHODE : commence par `profile` pour cadrer, puis appelle les outils d'axe pertinents — \
`timeline` (vitesse/chronologie de la propagation), `narrative_timelines` (dérive du cadrage \
dans le temps), `narratives` (narratifs), `coordination` (dès qu'il s'agit d'amplification \
organisée/bots/copier-coller), `semantique` (tonalité et son évolution) — puis `sample` pour \
étayer par des verbatims. Si un cluster domine (>50 %), \
relance `narratives` avec un k plus grand. Ne remplis `coordination` et `sentiment` du \
rapport que si tu as appelé l'outil correspondant. Chaque outil d'axe ne doit être appelé \
qu'UNE fois (au plus deux si tu affines un paramètre) : après avoir couvert les axes \
pertinents et étayé par 2–3 `sample`, RÉDIGE le rapport — n'enchaîne pas les appels à l'infini.

Réponds en français."""

# LangGraph caps the ReAct loop at `recursion_limit` super-steps (default 25 ≈ 12
# tool rounds). A thorough Analyste (profile + 5 axes + several `sample`) legitimately
# needs more, so we raise it — but keep it BOUNDED so a genuinely looping model fails
# fast instead of burning tokens. Env-overridable.
ANALYSTE_RECURSION_LIMIT = int(os.environ.get("LLM_RECURSION_LIMIT", "50"))


def build_agent(tier: str = "big"):
    """The tool-using Analyste agent: the LLM engine's generic `build_agent` bound
    to THIS domain's tools, system prompt and output schema. It fails over across
    every configured (provider, model, key) — see llm.build_agent for the policy.
    Defaults to the "big" tier (the Analyste is the tool-using reasoning stage)."""
    return llm.build_agent(TOOLS, SYSTEM_PROMPT, RapportAnalyste, tier=tier)


def ask(question: str, tier: str = "big") -> dict:
    reset_tool_budget()
    agent = build_agent(tier)
    result = agent.invoke(
        {"messages": [{"role": "user", "content": question}]},
        config={"callbacks": [ToolLogger()],
                "recursion_limit": ANALYSTE_RECURSION_LIMIT})
    report = result.get("structured_response")
    tool_calls = [m for m in result["messages"] if getattr(m, "type", "") == "tool"]
    return {
        "report": report.model_dump() if report else None,
        "n_tool_calls": len(tool_calls),
    }


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or \
        "Quels sont les principaux narratifs de la crise et comment se sont-ils propagés ?"
    print(f">>> Question : {q}\n")
    out = ask(q)
    print(f"[{out['n_tool_calls']} appels d'outils]\n")
    print(json.dumps(out["report"], indent=2, ensure_ascii=False))
