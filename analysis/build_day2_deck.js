// Day-2 full pitch deck (skeleton + finished diagnosis slides), pptxgenjs.
// Arc: Problem -> Agents -> Response. Same dark "investigation" theme as v3.
// Reuses the finished Propagation + Coordination slides; other slides are
// laid-out skeletons ready to fill. Numbers come from verified Corpus tools.
const pptxgen = require("pptxgenjs");
const path = require("path");

const HERE = __dirname, ROOT = path.dirname(HERE);
const FP = path.join(HERE, "figures_prop");
const FC = path.join(HERE, "figures_coord");

const INK = "0B1020", PANEL = "1B2340", PANEL2 = "141B33";
const VIOLET = "7C3AED", CYAN = "22D3EE", CORAL = "FF5C5C";
const WHITE = "FFFFFF", LIGHT = "E5E7EB", MUTED = "94A3B8";
const HEAD = "Georgia", BODY = "Calibri";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.author = "Datathon"; pres.title = "Ultia x CNC — Jour 2 (pitch)";
const PW = 13.333, PH = 7.5;
const sh = () => ({ type: "outer", color: "000000", blur: 10, offset: 3, angle: 135, opacity: 0.35 });

// ---------- shared helpers (identical to the finished slide scripts) ----------
function bg(s, topBar = VIOLET) {
  s.background = { color: INK };
  s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: PW, h: 0.14, fill: { color: topBar } });
}
function kicker(s, t, c = CYAN) { s.addText(t.toUpperCase(), { x: 0.6, y: 0.42, w: 12.1, h: 0.35, margin: 0, fontFace: BODY, fontSize: 13, bold: true, color: c, charSpacing: 3 }); }
function title(s, t, w = 12.1, fs = 26) { s.addText(t, { x: 0.6, y: 0.78, w, h: 1.05, margin: 0, fontFace: HEAD, fontSize: fs, bold: true, color: WHITE, lineSpacingMultiple: 0.98 }); }
function card(s, x, y, w, h, fill = PANEL) { s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { type: "none" }, shadow: sh() }); }
function chartCard(s, img, ar, x, y, w, h) {
  card(s, x, y, w, h, WHITE);
  const pad = 0.26; let iw = w - 2 * pad, ih = iw / ar;
  if (ih > h - 2 * pad) { ih = h - 2 * pad; iw = ih * ar; }
  s.addImage({ path: img, x: x + (w - iw) / 2, y: y + (h - ih) / 2, w: iw, h: ih });
}
function statRow(s, x, y, w, h, big, small, accent, bigFs = 22) {
  card(s, x, y, w, h);
  s.addShape(pres.shapes.RECTANGLE, { x, y: y + 0.14, w: 0.09, h: h - 0.28, fill: { color: accent } });
  s.addText(big, { x: x + 0.26, y: y + 0.06, w: w - 0.4, h: 0.5, margin: 0, fontFace: HEAD, fontSize: bigFs, bold: true, color: accent });
  s.addText(small, { x: x + 0.28, y: y + 0.55, w: w - 0.45, h: h - 0.6, margin: 0, fontFace: BODY, fontSize: 12, color: LIGHT, lineSpacingMultiple: 0.95 });
}
function footnote(s, t, w = 12.1) {
  s.addText(t, { x: 0.6, y: 7.02, w, h: 0.4, margin: 0, align: "left", fontFace: BODY, fontSize: 10.5, italic: true, color: MUTED });
}
// vertical stat card (label above a big figure), for grids
function axisCard(s, x, y, w, h, name, fig, tool, accent) {
  card(s, x, y, w, h);
  s.addShape(pres.shapes.RECTANGLE, { x, y, w, h: 0.09, fill: { color: accent } });
  s.addText(name, { x: x + 0.22, y: y + 0.22, w: w - 0.4, h: 0.35, margin: 0, fontFace: HEAD, fontSize: 15, bold: true, color: WHITE });
  s.addText(fig, { x: x + 0.22, y: y + 0.62, w: w - 0.4, h: h - 1.0, margin: 0, fontFace: BODY, fontSize: 12, color: LIGHT, lineSpacingMultiple: 1.05, valign: "top" });
  s.addText(tool.toUpperCase(), { x: x + 0.22, y: y + h - 0.42, w: w - 0.4, h: 0.3, margin: 0, fontFace: BODY, fontSize: 9.5, bold: true, color: accent, charSpacing: 2 });
}
// pipeline node
function node(s, x, y, w, h, num, name, role, accent) {
  card(s, x, y, w, h);
  s.addShape(pres.shapes.OVAL, { x: x + 0.24, y: y + 0.24, w: 0.5, h: 0.5, fill: { color: accent } });
  s.addText(String(num), { x: x + 0.24, y: y + 0.26, w: 0.5, h: 0.46, margin: 0, align: "center", fontFace: HEAD, fontSize: 18, bold: true, color: INK });
  s.addText(name, { x: x + 0.24, y: y + 0.9, w: w - 0.45, h: 0.4, margin: 0, fontFace: HEAD, fontSize: 16, bold: true, color: WHITE });
  s.addText(role, { x: x + 0.24, y: y + 1.34, w: w - 0.45, h: h - 1.5, margin: 0, fontFace: BODY, fontSize: 11.5, color: LIGHT, lineSpacingMultiple: 1.0, valign: "top" });
}
function arrow(s, x, y) {
  s.addText("→", { x, y, w: 0.55, h: 0.5, margin: 0, align: "center", fontFace: BODY, fontSize: 26, bold: true, color: CYAN });
}
function bullets(s, x, y, w, h, items, accent = CYAN, fs = 13.5) {
  s.addText(items.map((t, i) => ({ text: t, options: { bullet: { code: "2022", indent: 18 }, color: LIGHT, breakLine: true, paraSpaceAfter: 8 } })),
    { x, y, w, h, margin: 0, fontFace: BODY, fontSize: fs, color: LIGHT, lineSpacingMultiple: 1.05, valign: "top", bulletColor: accent });
}
// placeholder zone for content to be dropped in (screenshot / chart / demo)
function placeholder(s, x, y, w, h, label) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: PANEL2 }, line: { color: MUTED, width: 1, dashType: "dash" } });
  s.addText(label, { x: x + 0.3, y: y + h / 2 - 0.3, w: w - 0.6, h: 0.6, margin: 0, align: "center", fontFace: BODY, fontSize: 13, italic: true, color: MUTED });
}
function sectionDivider(s, n, kick, big, accent = VIOLET) {
  bg(s, accent);
  s.addText(n, { x: 0.6, y: 2.2, w: 3, h: 1.4, margin: 0, fontFace: HEAD, fontSize: 90, bold: true, color: PANEL });
  s.addText(kick.toUpperCase(), { x: 0.65, y: 3.35, w: 12, h: 0.4, margin: 0, fontFace: BODY, fontSize: 14, bold: true, color: accent, charSpacing: 3 });
  s.addText(big, { x: 0.6, y: 3.75, w: 11.5, h: 1.6, margin: 0, fontFace: HEAD, fontSize: 34, bold: true, color: WHITE, lineSpacingMultiple: 1.0 });
}

// ============================================================ 1 · COVER
let s = pres.addSlide(); bg(s);
s.addShape(pres.shapes.RECTANGLE, { x: 0, y: PH - 0.14, w: PW, h: 0.14, fill: { color: CYAN } });
s.addText("DATATHON NEXA · JOUR 2 · GÉRER UNE CRISE VIRALE AVEC DES AGENTS IA", { x: 0.9, y: 1.5, w: 11.5, h: 0.4, margin: 0, fontFace: BODY, fontSize: 14, bold: true, color: CYAN, charSpacing: 3 });
s.addText([
  { text: "Ultia ", options: { color: WHITE } },
  { text: "× ", options: { color: VIOLET } },
  { text: "CNC", options: { color: WHITE } },
], { x: 0.85, y: 2.2, w: 11.5, h: 1.2, margin: 0, fontFace: HEAD, fontSize: 62, bold: true });
s.addText("De la compréhension de la dynamique à la réponse — automatisée par une chaîne d'agents ancrés dans la donnée.",
  { x: 0.9, y: 3.7, w: 10.5, h: 1.0, margin: 0, fontFace: HEAD, fontSize: 22, italic: true, color: LIGHT, lineSpacingMultiple: 1.05 });
s.addText([
  { text: "Diagnostic ", options: { color: CYAN, bold: true } }, { text: "→ ", options: { color: MUTED } },
  { text: "Agents ", options: { color: VIOLET, bold: true } }, { text: "→ ", options: { color: MUTED } },
  { text: "Réponse", options: { color: CORAL, bold: true } },
], { x: 0.9, y: 5.4, w: 11, h: 0.5, margin: 0, fontFace: BODY, fontSize: 18 });
s.addText("Crise X mars–avril 2026 · corpus 35 396 messages · analyse neutre de la dynamique", { x: 0.9, y: 6.4, w: 11.5, h: 0.4, margin: 0, fontFace: BODY, fontSize: 13, color: MUTED });

// ============================================================ 2 · LA CRISE EN BREF
s = pres.addSlide(); bg(s);
kicker(s, "Le problème · une cascade d'amplification, pas un débat");
title(s, "En 4 jours, un sujet de politique culturelle devient un déferlement viral");
const crise = [
  ["35 396", "messages · 10 437 comptes (19 mars → 1er mai 2026)", CYAN],
  ["86 %", "de retweets (30 368) — seulement 1,9 % de messages originaux", VIOLET],
  ["7 303", "messages au pic du 27 mars — 4 jours de déflagration", CORAL],
  ["9,1 %", "de comptes vérifiés parmi les plus amplifiés", CYAN],
];
let cy = 1.95;
crise.forEach(([b, l, c]) => { statRow(s, 0.6, cy, 5.55, 1.12, b, l, c); cy += 1.26; });
card(s, 6.5, 1.95, 6.25, 4.78);
s.addShape(pres.shapes.RECTANGLE, { x: 6.5, y: 2.11, w: 0.09, h: 4.46, fill: { color: VIOLET } });
s.addText("Ce que montre la donnée", { x: 6.78, y: 2.15, w: 5.7, h: 0.45, margin: 0, fontFace: HEAD, fontSize: 18, bold: true, color: WHITE });
bullets(s, 6.78, 2.75, 5.75, 3.8, [
  "La structure est une cascade de relais : une poignée de sources, une masse de comptes qui repartagent à l'identique.",
  "Le volume double toutes les ~2,8 h pendant la montée — trop rapide pour une modération manuelle.",
  "Les cadres narratifs se déplacent dans le temps : l'affaire personnelle d'abord, « l'argent public » ensuite.",
  "Sentiment majoritairement neutre (66 %), mais la négativité épouse le pic de volume.",
], VIOLET, 13.5);
footnote(s, "Chiffres Jour 1 — key_figures.json (eda.py). Détail par axe dans les slides suivantes.");

// ============================================================ 3 · MISSION & GRILLE
s = pres.addSlide(); bg(s);
kicker(s, "Notre approche · une grille à 5 axes, chaque chiffre ancré dans un outil vérifié");
title(s, "Comprendre la dynamique — pour pouvoir y répondre, automatiquement");
const axes = [
  ["Acteurs", "Qui amplifie ? Sources vs relais, vérifiés, empreinte.", "profile", CYAN],
  ["Narratifs", "Quels cadres ? Argent public · camps · qui est financé.", "narratives", VIOLET],
  ["Propagation", "À quelle vitesse ? Allumage, doublement, demi-vie.", "timeline", CORAL],
  ["Coordination", "Est-ce orchestré ? Synchronies, copier-coller, clusters.", "coordination", CYAN],
  ["Sémantique", "Quel ton ? Mix de sentiment, négativité au pic.", "semantique", VIOLET],
];
const aw = 2.36, agap = 0.11; let ax = 0.6;
axes.forEach(([n, f, t, c]) => { axisCard(s, ax, 2.0, aw, 2.5, n, f, t, c); ax += aw + agap; });
card(s, 0.6, 4.75, 12.15, 1.7);
s.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 4.91, w: 0.09, h: 1.38, fill: { color: CYAN } });
s.addText("La thèse", { x: 0.88, y: 4.9, w: 3, h: 0.4, margin: 0, fontFace: HEAD, fontSize: 16, bold: true, color: WHITE });
s.addText([
  { text: "Une crise virale se gère en heures, pas en jours. ", options: { color: CYAN, bold: true } },
  { text: "On a outillé les 5 axes en fonctions déterministes et vérifiées (l'agent ne lit jamais les lignes brutes), puis enchaîné des agents qui diagnostiquent la crise et rédigent la réponse — chaque chiffre traçable jusqu'à un outil.", options: { color: LIGHT } },
], { x: 0.88, y: 5.36, w: 11.6, h: 1.0, margin: 0, fontFace: BODY, fontSize: 13.5, lineSpacingMultiple: 1.05 });

// ============================================================ 4 · DIAGNOSTIC · PROPAGATION (finished)
s = pres.addSlide(); bg(s);
kicker(s, "Diagnostic 1/2 · Propagation · la vitesse — le cœur de la dynamique");
title(s, "La physique du déferlement : 7 h pour exploser, ×2 toutes les 2,8 h", 12.2);
chartCard(s, path.join(FP, "velocity.png"), 9.0 / 4.7, 0.55, 1.95, 7.35, 5.0);
{
  const RX = 8.15, RW = 4.65;
  const stats = [
    ["7 h", "temps de montée : allumage 09 h → pic 16 h (26/03)", CYAN],
    ["× 2 / 2,8 h", "rythme de doublement du volume pendant la montée (+28 %/h)", VIOLET],
    ["7 h", "demi-vie : le volume retombe de moitié 7 h après le pic", CORAL],
  ];
  let ry = 1.95;
  stats.forEach(([b, l, c]) => { statRow(s, RX, ry, RW, 1.12, b, l, c); ry += 1.26; });
  card(s, RX, ry + 0.02, RW, 1.35);
  s.addShape(pres.shapes.RECTANGLE, { x: RX, y: ry + 0.16, w: 0.09, h: 1.03, fill: { color: CYAN } });
  s.addText("L'audience précède le volume", { x: RX + 0.26, y: ry + 0.13, w: RW - 0.45, h: 0.4, margin: 0, fontFace: HEAD, fontSize: 15, bold: true, color: WHITE });
  s.addText([
    { text: "Le reach culmine ", options: { color: LIGHT } },
    { text: "2 h avant", options: { color: CYAN, bold: true } },
    { text: " le volume : les grosses sources s'allument d'abord, la masse des relais suit.", options: { color: LIGHT } },
  ], { x: RX + 0.26, y: ry + 0.52, w: RW - 0.45, h: 0.8, margin: 0, fontFace: BODY, fontSize: 12.5, lineSpacingMultiple: 1.02 });
  s.addText("Volume (violet) et audience/reach (teal) par heure, 25–31 mars. Métriques calculées sur la série horaire (agent · outil timeline, velocity).",
    { x: 0.6, y: 7.0, w: 7.3, h: 0.35, margin: 0, align: "center", fontFace: BODY, fontSize: 11, italic: true, color: MUTED });
}

// ============================================================ 5 · DIAGNOSTIC · COORDINATION (finished)
s = pres.addSlide(); bg(s);
kicker(s, "Diagnostic 2/2 · Coordination · est-ce orchestré ? synchronie · concentration · comportement des comptes");
title(s, "Une amplification synchronisée par retweet — pas du copier-coller, ni des cellules isolées", 12.2, 23);
chartCard(s, path.join(FC, "bursts.png"), 9.0 / 4.7, 0.55, 1.95, 7.35, 5.0);
{
  const RX = 8.15, RW = 4.65;
  const stats = [
    ["× 3,7", "les retweets sont 3,7× plus groupés qu'un étalement uniforme sur la durée de vie des tweets (~25 h) : 30 % à moins de 60 s d'un autre (Δ = 60 s)", CYAN],
    ["0,6 %", "vrai copier-coller (même texte posté comme tweet original). Les « 82 % de duplication » = 100 % de retweets, identiques par nature — pas du copier-coller", VIOLET],
    ["1 535 · 14,7 %", "amplificateurs à faible empreinte : message unique, peu de posts / d'abonnés — PROXY (aucune date de création)", CORAL],
  ];
  let ry = 1.9;
  stats.forEach(([b, l, c]) => { statRow(s, RX, ry, RW, 1.22, b, l, c, 20); ry += 1.32; });
  card(s, RX, ry + 0.02, RW, 1.4);
  s.addShape(pres.shapes.RECTANGLE, { x: RX, y: ry + 0.16, w: 0.09, h: 1.08, fill: { color: CYAN } });
  s.addText("Concentration, pas des cellules", { x: RX + 0.26, y: ry + 0.11, w: RW - 0.45, h: 0.36, margin: 0, fontFace: HEAD, fontSize: 14, bold: true, color: WHITE });
  s.addText([
    { text: "Une poignée de tweets-sources concentrent le volume. À Δ=60 s, 2 824 comptes forment ", options: { color: LIGHT } },
    { text: "un seul grand composant", options: { color: CYAN, bold: true } },
    { text: " ; en exigeant des co-rafales répétées, il ne reste que des paires — amplification de masse, pas un anneau organisé.", options: { color: LIGHT } },
  ], { x: RX + 0.26, y: ry + 0.47, w: RW - 0.45, h: 0.9, margin: 0, fontFace: BODY, fontSize: 10.5, lineSpacingMultiple: 0.98 });
  s.addText("Rafales de retweets synchronisées / jour (même texte, ≥3 copies en < 60 s). Source : agent · coordination + coordination_network (vérifiés 60/60). Signaux compatibles avec une amplification coordonnée — le retweet rapide existe aussi de façon organique ; ni preuve d'automatisation ni d'intention.",
    { x: 0.6, y: 6.98, w: 7.3, h: 0.45, margin: 0, align: "center", fontFace: BODY, fontSize: 10, italic: true, color: MUTED });
}

// ============================================================ 6 · SECTION — LES AGENTS
s = pres.addSlide(); sectionDivider(s, "02", "De l'analyse à l'action", "Une chaîne d'agents qui diagnostique la crise — puis rédige la réponse", VIOLET);

// ============================================================ 7 · LE SYSTÈME D'AGENTS
s = pres.addSlide(); bg(s);
kicker(s, "Architecture · 4 agents orchestrés, une seule source de vérité");
title(s, "Analyste → Relecteur → Stratège → Rédacteur");
{
  const ny = 2.15, nh = 3.0, nw = 2.6, ngap = 0.577;
  const nodes = [
    [1, "Analyste", "Diagnostic ancré : appelle les outils vérifiés, couvre les 5 axes, sort un rapport structuré.", CYAN],
    [2, "Relecteur", "Audit + critique : vérifie que chaque @compte et chaque chiffre vient d'un outil. ≤ 1 reprise.", VIOLET],
    [3, "Stratège", "Plan de réponse : objectifs, audiences, axes, risques, KPIs — justifiés par un fait du diagnostic.", CORAL],
    [4, "Rédacteur", "Livrables : communiqué, fil social, FAQ, éléments de langage — sans chiffre hors diagnostic.", CYAN],
  ];
  let nx = 0.6;
  nodes.forEach(([num, name, role, c], i) => {
    node(s, nx, ny, nw, nh, num, name, role, c);
    if (i < nodes.length - 1) arrow(s, nx + nw + (ngap - 0.55) / 2, ny + nh / 2 - 0.25);
    nx += nw + ngap;
  });
  card(s, 0.6, 5.5, 12.15, 1.1);
  s.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 5.66, w: 0.09, h: 0.78, fill: { color: VIOLET } });
  s.addText([
    { text: "Contrat d'ancrage : ", options: { color: VIOLET, bold: true } },
    { text: "seul l'Analyste touche la donnée. Stratège et Rédacteur ne peuvent réutiliser que les faits du rapport — aucun nouveau chiffre ni @compte inventé. Multi-provider avec failover (Groq → Mistral) pour tenir le run malgré les quotas.", options: { color: LIGHT } },
  ], { x: 0.88, y: 5.62, w: 11.6, h: 0.9, margin: 0, fontFace: BODY, fontSize: 12.5, lineSpacingMultiple: 1.02 });
}

// ============================================================ 8 · ANCRAGE & GARDE-FOUS
s = pres.addSlide(); bg(s);
kicker(s, "Pourquoi lui faire confiance · la donnée pilote, pas le modèle");
title(s, "Chaque affirmation est traçable — ou elle ne sort pas");
statRow(s, 0.6, 2.0, 5.55, 1.35, "55 / 55", "contrôles de cohérence : la sortie de chaque outil est ré-assertée contre les chiffres canoniques (key_figures.json).", CYAN, 30);
statRow(s, 0.6, 3.5, 5.55, 1.35, "0 chiffre libre", "l'auditeur déterministe rejette tout @compte absent du corpus et tout nombre absent des sorties d'outils.", VIOLET, 24);
statRow(s, 0.6, 5.0, 5.55, 1.35, "Ton neutre", "garde-fou intégré : « signaux compatibles avec une amplification coordonnée », jamais « bots prouvés ».", CORAL, 24);
card(s, 6.5, 2.0, 6.25, 4.65);
s.addShape(pres.shapes.RECTANGLE, { x: 6.5, y: 2.16, w: 0.09, h: 4.33, fill: { color: CYAN } });
s.addText("Les 4 garde-fous", { x: 6.78, y: 2.2, w: 5.7, h: 0.45, margin: 0, fontFace: HEAD, fontSize: 18, bold: true, color: WHITE });
bullets(s, 6.78, 2.8, 5.75, 3.7, [
  "Outils déterministes : l'agent ne lit jamais les lignes brutes, seulement des résultats vérifiés.",
  "Chart = outil = vérif : les graphiques importent les mêmes fonctions que l'agent.",
  "Auditeur avant stratégie : une reprise automatique si un fait fabriqué est détecté.",
  "Limites explicites : « comptes récents » est un proxy assumé (aucune date de création dans la donnée).",
], CYAN, 13.5);
footnote(s, "Pile : outils Corpus (pandas/scikit-learn/networkx) · agents LangChain · verify_tools.py.");

// ============================================================ 9 · DÉMO LIVE
s = pres.addSlide(); bg(s);
kicker(s, "Démo · une question en langage naturel → un dossier de réponse complet");
title(s, "En direct : « Est-ce organique ou coordonné, et comment répondre ? »");
placeholder(s, 0.6, 2.0, 7.6, 4.7, "[ capture / enregistrement de la démo CLI — orchestrateur.py ]");
const steps = [
  ["1 · Analyste", "5+ appels d'outils → diagnostic 5 axes ancré", CYAN],
  ["2 · Relecteur", "audit : 0 chiffre non sourcé, ton neutre OK", VIOLET],
  ["3 · Stratège", "plan : objectifs, axes, KPIs", CORAL],
  ["4 · Rédacteur", "communiqué + fil + FAQ + éléments de langage", CYAN],
];
let sy = 2.0;
steps.forEach(([b, l, c]) => { statRow(s, 8.45, sy, 4.3, 1.05, b, l, c, 16); sy += 1.17; });
footnote(s, "Commande : .venv/bin/python agent/orchestrateur.py \"<question>\" — sorties mises en cache dans agent/out/.");

// ============================================================ 10 · SECTION — LA RÉPONSE
s = pres.addSlide(); sectionDivider(s, "03", "Ce que les agents produisent", "Une réponse de crise prête à publier, ancrée dans le diagnostic", CORAL);

// ============================================================ 11 · LIVRABLES
s = pres.addSlide(); bg(s);
kicker(s, "Livrables automatisés · générés par le Rédacteur, sans chiffre hors diagnostic");
title(s, "Un kit de réponse de crise, prêt à relire et publier");
const livr = [
  ["Communiqué", "Position officielle du CNC : reconnaît les faits, cadre la dynamique, pose la ligne — ton neutre.", CYAN],
  ["Fil social ≤ 280", "Fil X point par point pour reprendre la main dans le canal où la crise s'est jouée.", VIOLET],
  ["FAQ", "Questions récurrentes anticipées (argent public, bénéficiaires) avec réponses factuelles.", CORAL],
  ["Éléments de langage", "Messages-clés pour porte-parole et relais internes — cohérents avec le communiqué.", CYAN],
];
const lw = 2.96, lgap = 0.13; let lx = 0.6;
livr.forEach(([n, d, c]) => {
  card(s, lx, 2.05, lw, 3.1);
  s.addShape(pres.shapes.RECTANGLE, { x: lx, y: 2.05, w: lw, h: 0.09, fill: { color: c } });
  s.addText(n, { x: lx + 0.22, y: 2.3, w: lw - 0.4, h: 0.7, margin: 0, fontFace: HEAD, fontSize: 17, bold: true, color: WHITE });
  s.addText(d, { x: lx + 0.22, y: 3.05, w: lw - 0.42, h: 1.9, margin: 0, fontFace: BODY, fontSize: 12.5, color: LIGHT, lineSpacingMultiple: 1.05, valign: "top" });
  lx += lw + lgap;
});
card(s, 0.6, 5.4, 12.15, 1.05);
s.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 5.56, w: 0.09, h: 0.73, fill: { color: CORAL } });
s.addText([
  { text: "Garde-fou de sortie : ", options: { color: CORAL, bold: true } },
  { text: "le Rédacteur n'a pas accès au corpus — un audit final rejette tout @compte ou chiffre absent du diagnostic. La réponse reste factuelle par construction.", options: { color: LIGHT } },
], { x: 0.88, y: 5.52, w: 11.6, h: 0.85, margin: 0, fontFace: BODY, fontSize: 12.5, lineSpacingMultiple: 1.02 });

// ============================================================ 12 · IMPACT
s = pres.addSlide(); bg(s);
kicker(s, "Ce que ça change · pour une cellule de crise");
title(s, "De la veille manuelle à une réponse ancrée, en minutes");
const imp = [
  ["Heures → minutes", "diagnostic 5 axes + plan + livrables en un seul run orchestré", CYAN],
  ["Reproductible", "remappez les colonnes dans config.yaml → l'analyse tourne sur n'importe quel corpus de tweets", VIOLET],
  ["Traçable & neutre", "chaque chiffre remonte à un outil vérifié ; le ton reste factuel par garde-fou", CORAL],
];
let ix = 0.6;
imp.forEach(([b, l, c]) => { statRow(s, ix, 2.3, 3.97, 1.7, b, l, c, 22); ix += 4.09; });
card(s, 0.6, 4.4, 12.15, 2.1);
s.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 4.56, w: 0.09, h: 1.78, fill: { color: CYAN } });
s.addText("Limites assumées", { x: 0.88, y: 4.55, w: 5, h: 0.4, margin: 0, fontFace: HEAD, fontSize: 16, bold: true, color: WHITE });
bullets(s, 0.88, 5.05, 11.6, 1.4, [
  "« Comptes récents » non mesurable directement (pas de date de création) → proxy à faible empreinte, étiqueté comme tel.",
  "La coordination décrit des signaux, pas une intention prouvée. Décision humaine toujours dans la boucle.",
], CYAN, 13);

// ============================================================ 13 · CLÔTURE
s = pres.addSlide(); bg(s, CYAN);
s.addShape(pres.shapes.RECTANGLE, { x: 0, y: PH - 0.14, w: PW, h: 0.14, fill: { color: VIOLET } });
s.addText("MERCI", { x: 0.9, y: 2.3, w: 11.5, h: 1.0, margin: 0, fontFace: HEAD, fontSize: 56, bold: true, color: WHITE });
s.addText("Comprendre la dynamique, ancrer chaque chiffre, automatiser la réponse — dans le respect d'un ton neutre.",
  { x: 0.92, y: 3.6, w: 10.5, h: 1.0, margin: 0, fontFace: HEAD, fontSize: 20, italic: true, color: LIGHT, lineSpacingMultiple: 1.05 });
s.addText([
  { text: "Diagnostic ", options: { color: CYAN, bold: true } }, { text: "→ ", options: { color: MUTED } },
  { text: "Agents ", options: { color: VIOLET, bold: true } }, { text: "→ ", options: { color: MUTED } },
  { text: "Réponse", options: { color: CORAL, bold: true } },
], { x: 0.92, y: 5.0, w: 11, h: 0.5, margin: 0, fontFace: BODY, fontSize: 18 });
s.addText("Démo : agent/orchestrateur.py · outils vérifiés 55/55 · corpus Ultia × CNC", { x: 0.92, y: 6.2, w: 11.5, h: 0.4, margin: 0, fontFace: BODY, fontSize: 13, color: MUTED });

const out = path.join(ROOT, "Datathon_Ultia_CNC_Jour2.pptx");
pres.writeFile({ fileName: out }).then(() => console.log("Saved", out));
