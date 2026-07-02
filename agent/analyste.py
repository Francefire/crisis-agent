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
from langchain.agents import create_agent

from tools import Corpus, HERE, ROOT

load_dotenv(os.path.join(ROOT, ".env"))

# ---- provider selection (set LLM_PROVIDER in .env: gemini | groq | mistral) ----
# Gemini free tier caps at ~20 req/day/model on restricted projects; a full
# Analyste→Stratège→Rédacteur run is ~7 calls, so Groq (thousands/day) or Mistral
# are better for the pipeline. Swapping = one env var; no code change.
PROVIDER = os.environ.get("LLM_PROVIDER", "gemini").lower()
_PROVIDER_DEFAULT_MODEL = {
    "gemini": "gemini-2.5-flash-lite",   # largest Gemini free daily quota
    "groq": "llama-3.3-70b-versatile",   # strong tool-calling, generous free tier
    "mistral": "mistral-small-latest",
}
_PROVIDER_KEY_ENV = {
    "gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY", "mistral": "MISTRAL_API_KEY",
}
DEFAULT_MODEL = os.environ.get("LLM_MODEL") or \
    _PROVIDER_DEFAULT_MODEL.get(PROVIDER, "gemini-2.5-flash-lite")

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
def timeline(freq: str = "D") -> dict:
    """Dynamique temporelle de la crise. freq = 'D' (jour), 'h' (heure) ou 'W'
    (semaine). Renvoie les pics de volume (top_peaks), le message le plus ancien
    (patient_zero) et l'ordre d'allumage des comptes les plus amplifiés
    (amplified_onsets = date du premier relais de chacun). Utile pour dater le
    déclenchement et décrire la propagation."""
    res = CORPUS.timeline(freq=freq, top=6)
    res.pop("series", None)  # garder la réponse compacte : pics + onsets suffisent
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
def coordination(min_dup: int = 5, top: int = 15) -> dict:
    """Signaux de coordination / amplification artificielle. Renvoie les messages
    identiques les plus dupliqués verbatim (top_duplicated_messages + leur
    nombre), les rafales synchronisées (top_synchronized_bursts = même texte
    posté par plusieurs comptes dans la même minute), le taux de duplication
    verbatim (part des messages qui sont des copies exactes) et la concentration
    de l'activité (comptes à 1 seul message vs comptes très actifs). Utile pour
    juger si la propagation est organique ou coordonnée."""
    return CORPUS.coordination(min_dup=min_dup, top=top)


@tool
def semantique(freq: str = "D") -> dict:
    """Dynamique du sentiment. freq = 'D'/'h'/'W'. Renvoie la répartition globale
    (négatif/neutre/positif), l'évolution par période, la part de négatif le jour
    du pic de volume vs la moyenne, et la période la plus négative. Utile pour
    savoir si la négativité suit ou précède le pic d'activité."""
    return CORPUS.semantique(freq=freq)


TOOLS = [profile, timeline, narratives, sample, coordination, semantique]


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
        description="Indices de coordination/amplification (duplication verbatim, "
                    "rafales synchronisées) — si la question s'y prête")
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
actifs/amplifiés), NARRATIFS (`narratives`), PROPAGATION (`timeline`), COORDINATION \
(`coordination` : duplication verbatim, rafales synchronisées), SÉMANTIQUE (`semantique` : \
sentiment dans le temps). Choisis les axes/outils pertinents pour la question posée.

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
`timeline` (propagation/chronologie), `narratives` (narratifs), `coordination` (dès qu'il \
s'agit d'amplification organisée/bots/copier-coller), `semantique` (tonalité et son \
évolution) — puis `sample` pour étayer par des verbatims. Si un cluster domine (>50 %), \
relance `narratives` avec un k plus grand. Ne remplis `coordination` et `sentiment` du \
rapport que si tu as appelé l'outil correspondant.

Réponds en français."""


def build_model(model: str = DEFAULT_MODEL, temperature: float = 0):
    """Return a LangChain chat model for the active provider (LLM_PROVIDER)."""
    key_env = _PROVIDER_KEY_ENV.get(PROVIDER)
    key = os.environ.get(key_env) if key_env else None
    if not key:
        sys.exit(f"ERREUR : {key_env} absent de .env "
                 f"(provider={PROVIDER} ; voir .env.example).")
    if PROVIDER == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model, google_api_key=key,
                                      temperature=temperature)
    if PROVIDER == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(model=model, api_key=key, temperature=temperature)
    if PROVIDER == "mistral":
        from langchain_mistralai import ChatMistralAI
        return ChatMistralAI(model=model, api_key=key, temperature=temperature)
    sys.exit(f"ERREUR : provider inconnu '{PROVIDER}' (gemini|groq|mistral).")


def build_agent(model: str = DEFAULT_MODEL):
    return create_agent(
        build_model(model),
        tools=TOOLS,
        system_prompt=SYSTEM_PROMPT,
        response_format=RapportAnalyste,
    )


def ask(question: str, model: str = DEFAULT_MODEL) -> dict:
    agent = build_agent(model)
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
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
