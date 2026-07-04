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
    # ensure_ascii=False keeps accents readable but leaves U+2028/U+2029 (Line/
    # Paragraph Separator, present in some tweet samples) raw — editors flag those
    # as "unusual line terminators". Re-escape them to their JSON form (still valid,
    # round-trips identically) so the fenced block has no stray line breaks.
    body = json.dumps(obj, ensure_ascii=False, indent=2)
    body = body.replace(chr(0x2028), "\\u2028").replace(chr(0x2029), "\\u2029")
    return "```json\n" + body + "\n```"


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


def emit(md, path) -> None:
    """Write the Markdown to `path` and echo it to stdout (user chose 'Both')."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)
    print(md)
    size = os.path.getsize(path)
    print(f"\n[viz] écrit {path} ({size / 1024:.1f} Ko)", flush=True)
