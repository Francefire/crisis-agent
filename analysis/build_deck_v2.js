// Datathon Ultia x CNC — Jour 1 deck v2 (pptxgenjs). Dark "investigation" theme.
const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");

const HERE = __dirname;
const ROOT = path.dirname(HERE);
const FIG = path.join(HERE, "figures_v2");
const S = JSON.parse(fs.readFileSync(path.join(HERE, "out", "key_figures.json"), "utf8"));

// palette (no # per pptxgenjs)
const INK = "0B1020", PANEL = "1B2340", PANEL2 = "141B33";
const VIOLET = "7C3AED", CYAN = "22D3EE", CORAL = "FF5C5C";
const WHITE = "FFFFFF", LIGHT = "E5E7EB", MUTED = "94A3B8";
const HEAD = "Georgia", BODY = "Calibri";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
pres.author = "Datathon"; pres.title = "Affaire Ultia x CNC — Jour 1";
const PW = 13.333, PH = 7.5;

const shadow = () => ({ type: "outer", color: "000000", blur: 10, offset: 3, angle: 135, opacity: 0.35 });
const nf = (n) => n.toLocaleString("fr-FR").replace(/ | /g, " ");

function kicker(slide, txt, color = CYAN) {
  slide.addText(txt.toUpperCase(), { x: 0.6, y: 0.42, w: 11, h: 0.35, margin: 0,
    fontFace: BODY, fontSize: 13, bold: true, color, charSpacing: 3 });
}
function title(slide, txt, color = WHITE, w = 12.1) {
  slide.addText(txt, { x: 0.6, y: 0.78, w, h: 1.15, margin: 0,
    fontFace: HEAD, fontSize: 30, bold: true, color, lineSpacingMultiple: 0.98 });
}
function pageDot(slide, n) {
  slide.addText(`${n} / 5`, { x: PW - 1.4, y: PH - 0.5, w: 1.0, h: 0.3, margin: 0,
    align: "right", fontFace: BODY, fontSize: 10, color: MUTED });
}
// image contained inside a white card
function chartCard(slide, img, ar, x, y, w, h) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08,
    fill: { color: WHITE }, line: { type: "none" }, shadow: shadow() });
  const pad = 0.28;
  let iw = w - 2 * pad, ih = iw / ar;
  if (ih > h - 2 * pad) { ih = h - 2 * pad; iw = ih * ar; }
  slide.addImage({ path: path.join(FIG, img), x: x + (w - iw) / 2, y: y + (h - ih) / 2, w: iw, h: ih });
}
function statCard(slide, x, y, w, h, big, small, accent) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08,
    fill: { color: PANEL }, line: { type: "none" }, shadow: shadow() });
  slide.addShape(pres.shapes.RECTANGLE, { x, y: y + 0.18, w: 0.09, h: h - 0.36, fill: { color: accent } });
  slide.addText(big, { x: x + 0.28, y: y + 0.14, w: w - 0.4, h: 0.62, margin: 0,
    fontFace: HEAD, fontSize: 30, bold: true, color: accent });
  slide.addText(small, { x: x + 0.28, y: y + 0.74, w: w - 0.45, h: h - 0.8, margin: 0,
    fontFace: BODY, fontSize: 12.5, color: LIGHT, lineSpacingMultiple: 0.98 });
}

const et = S.engagement_type_counts, sent = S.sentiment_counts, n = S.n_rows;
const pctNeg = Math.round(sent.negative / n * 100);
const pctNeu = Math.round(sent.neutral / n * 100);
const pctPos = Math.round(sent.positive / n * 100);
const amp = Object.entries(S.top15_amplified_authors);
const maxdup = Math.max(...Object.values(S.top20_duplicated_messages));

// ============================================================= SLIDE 1
let s = pres.addSlide(); s.background = { color: INK };
// accent motif: two thin bars
s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: PW, h: 0.14, fill: { color: VIOLET } });
s.addShape(pres.shapes.RECTANGLE, { x: 0, y: PH - 0.14, w: PW, h: 0.14, fill: { color: CYAN } });
s.addText("DATATHON · 2 JOURS · JOUR 1", { x: 0.9, y: 1.15, w: 11, h: 0.4, margin: 0,
  fontFace: BODY, fontSize: 15, bold: true, color: CYAN, charSpacing: 4 });
s.addText("Affaire Ultia × CNC", { x: 0.9, y: 1.9, w: 11.5, h: 1.1, margin: 0,
  fontFace: HEAD, fontSize: 52, bold: true, color: WHITE });
s.addText("Anatomie d'un déferlement viral", { x: 0.9, y: 3.0, w: 11.5, h: 0.9, margin: 0,
  fontFace: HEAD, fontSize: 34, italic: true, color: VIOLET });
s.addText([
  { text: "Un fait réel, transformé en tempête sur X en quatre jours.  ", options: { color: LIGHT } },
  { text: "Fait → Narratif → ", options: { color: MUTED } },
  { text: "Dynamique", options: { color: CYAN, bold: true } },
  { text: " : nous analysons la dynamique.", options: { color: MUTED } },
], { x: 0.9, y: 4.15, w: 11.2, h: 0.6, margin: 0, fontFace: BODY, fontSize: 17 });
// stat strip
const strip = [[nf(n), "messages"], [nf(S.n_authors), "comptes"],
  [S.date_min.slice(0, 10) + " → " + S.date_max.slice(0, 10), "période"]];
let sx = 0.9;
strip.forEach(([b, l], i) => {
  const w = i === 2 ? 4.6 : 2.7;
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: sx, y: 5.35, w, h: 1.3, rectRadius: 0.08,
    fill: { color: PANEL }, line: { type: "none" } });
  s.addText(b, { x: sx + 0.25, y: 5.5, w: w - 0.4, h: 0.65, margin: 0,
    fontFace: HEAD, fontSize: i === 2 ? 20 : 30, bold: true, color: WHITE });
  s.addText(l.toUpperCase(), { x: sx + 0.25, y: 6.12, w: w - 0.4, h: 0.4, margin: 0,
    fontFace: BODY, fontSize: 12, color: MUTED, charSpacing: 2 });
  sx += w + 0.35;
});

// ============================================================= SLIDE 2
s = pres.addSlide(); s.background = { color: INK };
kicker(s, "01 · Propagation");
title(s, "Une déflagration de 4 jours, portée par le retweet");
chartCard(s, "timeline.png", 1.872, 0.6, 2.0, 7.7, 4.9);
statCard(s, 8.75, 2.0, 4.0, 1.5, S.retweet_share_pct.toFixed(0) + " %",
  "des messages sont des retweets — amplification, pas débat.", VIOLET);
statCard(s, 8.75, 3.62, 4.0, 1.5, nf(S.peak_day_volume),
  "messages le " + S.peak_day + " (jour de pic).", CORAL);
statCard(s, 8.75, 5.24, 4.0, 1.5, nf(et.ORIGINAL),
  "messages originaux seulement (1,9 % du corpus).", CYAN);
pageDot(s, 2);

// ============================================================= SLIDE 3
s = pres.addSlide(); s.background = { color: INK };
kicker(s, "02 · Acteurs");
title(s, "Deux couches : des sources amplifiées, une masse de relais");
chartCard(s, "amplified.png", 1.68, 0.6, 2.0, 7.4, 4.9);
s.addText("Comptes dont les messages sont le plus retweetés (patient zéro / relais).",
  { x: 0.6, y: 7.02, w: 7.4, h: 0.35, margin: 0, align: "center", fontFace: BODY, fontSize: 12, italic: true, color: MUTED });
const layers = [
  ["Les sources", "Personnalités politiques, médias & comptes militants (Bellamy, Maréchal, Bastié, ojim_france…) + le CNC lui-même.", VIOLET],
  ["Les relais", "Une piétaille de comptes qui retweetent en boucle (~100 messages chacun) pour propulser le narratif.", CYAN],
  ["Le vernis", S.verified_share_pct + " % de comptes certifiés seulement : l'amplification vient surtout de comptes non vérifiés.", CORAL],
];
let ly = 2.0;
layers.forEach(([t, d, c]) => {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 8.35, y: ly, w: 4.4, h: 1.5, rectRadius: 0.08,
    fill: { color: PANEL }, line: { type: "none" }, shadow: shadow() });
  s.addShape(pres.shapes.RECTANGLE, { x: 8.35, y: ly + 0.18, w: 0.09, h: 1.14, fill: { color: c } });
  s.addText(t, { x: 8.63, y: ly + 0.16, w: 4.0, h: 0.4, margin: 0, fontFace: HEAD, fontSize: 18, bold: true, color: c });
  s.addText(d, { x: 8.63, y: ly + 0.6, w: 3.95, h: 0.85, margin: 0, fontFace: BODY, fontSize: 12, color: LIGHT, lineSpacingMultiple: 0.98 });
  ly += 1.62;
});
pageDot(s, 3);

// ============================================================= SLIDE 4
s = pres.addSlide(); s.background = { color: INK };
kicker(s, "03 · Narratifs & Sémantique");
title(s, "Trois cadrages qui s'affrontent, un ton majoritairement négatif");
chartCard(s, "terms.png", 0.875, 0.6, 2.0, 4.7, 4.9);
const frames = [
  ["L'argent public", "cnc · fonds · subventions · millions · euros · aides", CORAL],
  ["Les camps politiques", "gauche · extrême · droite · français", VIOLET],
  ["Qui finance-t-on ?", "talent · streameuse · créateurs · cinéma · film", CYAN],
];
let fy = 2.0;
frames.forEach(([t, w, c]) => {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 5.7, y: fy, w: 7.05, h: 1.12, rectRadius: 0.08,
    fill: { color: PANEL }, line: { type: "none" }, shadow: shadow() });
  s.addShape(pres.shapes.RECTANGLE, { x: 5.7, y: fy + 0.15, w: 0.09, h: 0.82, fill: { color: c } });
  s.addText(t, { x: 5.98, y: fy + 0.13, w: 6.6, h: 0.4, margin: 0, fontFace: HEAD, fontSize: 17, bold: true, color: c });
  s.addText(w, { x: 5.98, y: fy + 0.56, w: 6.6, h: 0.45, margin: 0, fontFace: BODY, fontSize: 13, color: LIGHT });
  fy += 1.26;
});
// sentiment bar (stacked) with labels
const sy = fy + 0.05, sbx = 5.7, sbw = 7.05;
const segs = [[pctNeg, CORAL, "négatif"], [pctNeu, "3A4468", "neutre"], [pctPos, CYAN, "positif"]];
let cx = sbx;
segs.forEach(([p, c]) => { const w = sbw * p / 100;
  s.addShape(pres.shapes.RECTANGLE, { x: cx, y: sy, w, h: 0.5, fill: { color: c } }); cx += w; });
s.addText([
  { text: `Sentiment  `, options: { color: MUTED } },
  { text: `${pctNeg}% négatif`, options: { color: CORAL, bold: true } },
  { text: `  ·  ${pctNeu}% neutre  ·  `, options: { color: LIGHT } },
  { text: `${pctPos}% positif`, options: { color: CYAN, bold: true } },
], { x: sbx, y: sy + 0.55, w: sbw, h: 0.35, margin: 0, fontFace: BODY, fontSize: 13 });
pageDot(s, 4);

// ============================================================= SLIDE 5
s = pres.addSlide(); s.background = { color: INK };
s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: PW, h: 0.14, fill: { color: CORAL } });
kicker(s, "04 · Coordination & Riposte", CORAL);
title(s, "Des signaux de coordination → un agent IA pour outiller la riposte");
// left: coordination
s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.6, y: 2.05, w: 5.9, h: 4.5, rectRadius: 0.08,
  fill: { color: PANEL }, line: { type: "none" }, shadow: shadow() });
s.addText("Ce que révèle la coordination", { x: 0.9, y: 2.3, w: 5.3, h: 0.5, margin: 0,
  fontFace: HEAD, fontSize: 19, bold: true, color: CYAN });
s.addText([
  { text: `Messages copiés-collés jusqu'à ${nf(maxdup)} fois à l'identique`, options: { bullet: { indent: 18 }, breakLine: true, paraSpaceAfter: 12 } },
  { text: "Rafales synchronisées à la même minute", options: { bullet: { indent: 18 }, breakLine: true, paraSpaceAfter: 12 } },
  { text: `${nf(S.n_authors_1_msg)} comptes ne postent qu'un seul message (masse de relais)`, options: { bullet: { indent: 18 }, breakLine: true, paraSpaceAfter: 12 } },
  { text: `${S.verified_share_pct} % de comptes certifiés seulement`, options: { bullet: { indent: 18 } } },
], { x: 0.9, y: 2.95, w: 5.3, h: 3.4, margin: 0, fontFace: BODY, fontSize: 15, color: LIGHT });
// right: agent
s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 6.85, y: 2.05, w: 5.9, h: 4.5, rectRadius: 0.08,
  fill: { color: VIOLET }, line: { type: "none" }, shadow: shadow() });
s.addText("Prochaine étape : l'agent « Analyste »", { x: 7.15, y: 2.3, w: 5.3, h: 0.5, margin: 0,
  fontFace: HEAD, fontSize: 19, bold: true, color: WHITE });
s.addText("Modèle + outil d'accès au corpus + mémoire", { x: 7.15, y: 2.82, w: 5.3, h: 0.4, margin: 0,
  fontFace: BODY, fontSize: 14, bold: true, color: "E9D5FF" });
s.addText([
  { text: "Interroge le corpus (volume, comptes, narratifs)", options: { bullet: { indent: 18 }, breakLine: true, paraSpaceAfter: 12 } },
  { text: "Résume le narratif dominant d'un échantillon", options: { bullet: { indent: 18 }, breakLine: true, paraSpaceAfter: 12 } },
  { text: "Détecte les signaux de coordination", options: { bullet: { indent: 18 }, breakLine: true, paraSpaceAfter: 12 } },
  { text: "Réutilisable pour d'autres crises informationnelles", options: { bullet: { indent: 18 } } },
], { x: 7.15, y: 3.35, w: 5.3, h: 3.0, margin: 0, fontFace: BODY, fontSize: 15, color: WHITE });
pageDot(s, 5);

const out = path.join(ROOT, "Datathon_Ultia_CNC_Jour1_v2.pptx");
pres.writeFile({ fileName: out }).then(() => console.log("Saved", out));
