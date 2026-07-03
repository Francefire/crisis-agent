# Coordination — méthodes pandas & corrélations de données

> **But de ce document :** expliquer, en lignes simples, *comment* l'axe
> **Coordination** est calculé — quelles colonnes, quelles opérations pandas,
> quelles formules transforment 35 396 tweets bruts en signaux de coordination.
> Tout le code vit dans `agent/tools.py` (méthodes `coordination()` et
> `coordination_network()` + helpers). Les graphiques
> (`analysis/build_coordination_charts.py`) importent les mêmes fonctions →
> **chart == outil == vérif** (les chiffres ne sont jamais recalculés à la main).

**Cadrage honnête (à répéter à l'oral) :** ce sont des *signaux compatibles avec
une amplification coordonnée*, **pas** une preuve de bots ou d'intention.

---

## 1. TL;DR — les 5 briques

| # | Brique | Question du brief | Sortie clé (chiffre réel) |
|---|--------|-------------------|---------------------------|
| 0 | Duplication verbatim | Copier-coller brut | `verbatim_duplication_rate_pct` = **82,4 %** (dont 100 % = RETWEET) ; vrai copier-coller = **0,6 %** |
| A | Synchronie (`_synchrony`) | Synchronies | `coordination_score_pct` = **30,1 %**, lift ×**3,7** vs hasard |
| B | Quasi-doublons (`_near_duplicates`) | Copier-coller templaté | **2** groupes, top = 3 variantes / **710** msgs |
| D | Comportement compte (`_account_behaviour`) | Comptes récents/suspects | **1 535** comptes « throwaway » (**14,7 %**) — *proxy* |
| C | Réseau (`coordination_network`) | Clusters | **4 275** nœuds, **597** communautés, plus gros cluster = **138** comptes |

---

## 2. Données & colonnes utilisées

Les outils lisent des **rôles** de colonnes depuis `agent/config.yaml` (jamais les
noms en dur), donc l'agent tourne sur n'importe quel corpus X. Rôle → colonne réelle :

| Rôle (code) | Colonne réelle | À quoi ça sert pour la coordination |
|-------------|----------------|-------------------------------------|
| `timestamp` | `Date` | Fenêtres de synchronie Δ, séries temporelles |
| `author` | `Author` | Identité stable du compte (nœud du réseau) |
| `text_clean` | `message_normalizer` | Texte normalisé → dédup, quasi-doublons (`_clean_text`) |
| `engagement` | `Engagement Type` | Split RETWEET / QUOTE / ORIGINAL (retweet ≠ copier-coller) |
| `verified` | `X Verified` | Part de comptes vérifiés dans les groupes |
| `followers` | `X Followers` | Proxy « empreinte faible » |
| `following` | `X Following` | Ratio following/followers |
| `posts` | `X Posts` | Nombre de posts à vie → proxy compte jetable |
| `repost_url` | `X Repost of` | → `_repost_handle` (compte amplifié, via regex) |

⚠️ **Limite n°1 :** *aucune colonne de date de création de compte n'existe*. Le
« comptes récents » du brief ne peut pas être mesuré directement — il est
**proxifié** (voir brique D) et étiqueté comme tel.

---

## 3. Fiches par signal

### Brique 0 — Duplication verbatim (baseline)
- **Objectif :** combien de messages sont des textes identiques répétés.
- **Colonnes :** `message_normalizer`, `Engagement Type`.
- **Ops pandas :** `clean.value_counts()` → garder `count ≥ min_dup` ; masque
  `clean.isin(dup_set)`.
- **Formules :**
  - `verbatim_duplication_rate_pct = Σ(copies des textes en doublon) / N_messages × 100` → **82,4 %**
  - `retweet_share_of_duplicated_pct = moyenne(engagement == RETWEET | lignes en doublon)` → **100 %**
  - `copy_paste_rate_pct` = même taux mais **hors RETWEET & REPLY** (ORIGINAL+QUOTE seulement) → **0,6 %**
- **Pourquoi les deux :** le 82,4 % est gonflé par les retweets (texte identique
  *par construction* = amplification native, pas copier-coller). Le vrai
  « copier-coller » authentique est **0,6 %**.

### Brique A — Synchronie / rafales (`_synchrony`)
- **Objectif :** les copies d'un même texte tombent-elles quasi simultanément ?
- **Colonnes :** `Date`, `message_normalizer`.
- **Ops pandas / numpy :**
  - Timestamps → secondes unix : `.values.astype("datetime64[s]").astype("int64")`.
  - `groupby("_txt")` sur chaque texte dupliqué ; `np.sort` des secondes.
  - Voisin le plus proche : `np.diff(seconds)` → une copie est « synchronisée »
    si son voisin (précédent OU suivant) est **≤ Δ = 60 s** (`_sync_stats`).
  - Rafales journalières : `Date.dt.floor("D")` + fenêtres glissantes `_sync_windows`
    (fenêtre = membres à ≤ Δ du 1er membre) → `burst_size_over_time`
    (`max_burst`, `n_bursts_ge3` par jour — c'est ce que trace le graphe « rafales »).
- **Formules :**
  - `coordination_score_pct = copies_within_delta / copies_considered × 100` → **30,1 %**
  - **Modèle nul** (baseline « et si c'était du hasard ? ») : si les *n* copies
    d'un texte étaient réparties uniformément sur sa durée de vie `span`,
    `P(un point a un voisin ≤ Δ) ≈ 1 − (1 − 2Δ/span)^(n−1)` → attendu **8,1 %**.
  - `synchrony_lift_vs_uniform = observé / attendu = 30,1 / 8,1 ≈ ×3,7`.
    Lift > 1 = les copies sont **plus groupées** que le hasard ne le prédirait.

### Brique B — Quasi-doublons templatés (`_near_duplicates`)
- **Objectif :** attraper les variantes (mot/emoji changé) que le match exact rate.
- **Colonnes :** `message_normalizer` (les textes déjà dédupliqués, `count ≥ min_dup`).
- **Ops :** sur chaque texte → **ensemble de char-3-grammes** (`_char_ngrams`) ;
  comparaison de toutes les paires par **Jaccard** ; fusion des paires
  `≥ sim_threshold = 0,8` via **union-find** (`_UnionFind`) → groupes de variantes.
- **Formule :** `Jaccard(A,B) = |A ∩ B| / |A ∪ B|` (grammes en commun / grammes totaux).
- **Sortie :** **2** groupes ; top groupe = **3** variantes cumulant **710** messages.

### Brique D — Comportement des comptes (`_account_behaviour`) — *PROXIES*
- **Objectif :** approcher les « comptes récents / suspects » sans date de création.
- **Colonnes :** `Author`, `X Followers`, `X Following`, `X Posts`, `X Verified`.
- **Ops pandas :** `groupby(author).agg(max)` (les attributs de compte sont
  constants par auteur) ; seuils par `quantile(0.25)` et `median()`.
- **Proxy « throwaway amplifier » (empreinte faible)** — les 3 conditions :
  1. compte à **message unique** (`per_author == 1`)
  2. **X Posts ≤ P25** (peu d'activité à vie)
  3. **abonnés ≤ médiane**
  → **1 535** comptes (**14,7 %**). *Proxy assumé, pas une preuve.*
- **Autres formules :**
  - `single_message_share_pct` = part de comptes à 1 seul message → **54,5 %**
  - `following_over_followers_share_pct = moyenne(following > followers) × 100`
  - `verified_share_among_duplicators_pct` = part de vérifiés parmi ceux qui
    postent un texte dupliqué → **7,3 %** (bas ⇒ peu de comptes « officiels »).

### Brique C — Réseau de co-activité (`coordination_network`)
- **Objectif :** les « clusters » — quels comptes co-postent le même texte en même temps.
- **Colonnes :** `Author`, `Date`, `message_normalizer`, `X Verified`.
- **Ops (construction du graphe) :**
  1. Restreindre aux textes dupliqués (`count ≥ min_dup`).
  2. Par texte, fenêtres synchrones `_sync_windows` (Δ = 60 s).
  3. **Arête** entre 2 comptes = ils apparaissent dans la même fenêtre
     (`itertools.combinations`) ; **poids** = nombre de rafales partagées.
  4. Graphe `networkx` (arêtes `weight ≥ min_edge_weight`).
- **Analyse :**
  - `nx.connected_components` → composantes (**561**, la plus grande = **2 824**).
  - **Louvain pondéré** (`louvain_communities`, `seed=42`) → **597** communautés
    ≥ 2 comptes = clusters coordonnés.
  - Par cluster : taille, arêtes internes, part vérifiés / message unique, textes
    dominants partagés. Plus gros cluster = **138** comptes (8 % vérifiés) —
    c'est ce que trace le graphe « clusters ».
- **Graphe :** **4 275** nœuds, **6 041** arêtes. Corpus très retweet → composantes
  en étoile ; Louvain sert justement à découper ces gros amas en clusters lisibles.

---

## 4. Bloc formules (à réciter)

| Nom | Formule | Sens |
|-----|---------|------|
| Score de coordination | `copies ≤ Δ d'une autre / total copies × 100` | % de copies « en rafale » |
| Modèle nul uniforme | `1 − (1 − 2Δ/span)^(n−1)` | ce que donnerait le hasard sur la durée de vie du tweet |
| Lift de synchronie | `observé / attendu` | ×3,7 = 3,7× plus groupé que le hasard |
| Jaccard (3-grammes) | `|A ∩ B| / |A ∪ B|` | similarité texte pour quasi-doublons |
| Empreinte faible | `msg unique ∧ posts ≤ P25 ∧ abonnés ≤ médiane` | proxy compte jetable |

---

## 5. Traçabilité (pourquoi c'est solide)

- `analysis/build_coordination_charts.py` **importe `Corpus`** et lit
  `co["synchrony"]["burst_size_over_time"]` / `net["top_clusters"]` — donc les
  PNG (`figures_coord/bursts.png`, `clusters.png`) affichent exactement les
  chiffres des outils.
- `verify_tools.py` : **41/41** contrôles d'auto-cohérence passent.
- Le LLM ne lit **jamais** les lignes brutes ; il ne consomme que ces sorties
  déterministes → chiffres reproductibles.

> **Rappel de ton :** toujours « signaux compatibles avec une amplification
> coordonnée », jamais « bots prouvés ».
