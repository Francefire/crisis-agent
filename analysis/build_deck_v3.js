// Datathon Ultia x CNC — Jour 1 deck v3 (pptxgenjs). Image-rich dark theme.
const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");

const HERE = __dirname, ROOT = path.dirname(HERE);
const F2 = path.join(HERE, "figures_v2"), F3 = path.join(HERE, "figures_v3");
const S = JSON.parse(fs.readFileSync(path.join(HERE, "out", "key_figures.json"), "utf8"));

const INK = "0B1020", PANEL = "1B2340";
const VIOLET = "7C3AED", CYAN = "22D3EE", CORAL = "FF5C5C";
const WHITE = "FFFFFF", LIGHT = "E5E7EB", MUTED = "94A3B8";
const HEAD = "Georgia", BODY = "Calibri";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.author = "Datathon"; pres.title = "Affaire Ultia x CNC — Jour 1";
const PW = 13.333, PH = 7.5;
const sh = () => ({ type: "outer", color: "000000", blur: 10, offset: 3, angle: 135, opacity: 0.35 });
const nf = (n) => n.toLocaleString("fr-FR").replace(/,/g, " ");

const et = S.engagement_type_counts, sent = S.sentiment_counts, n = S.n_rows;
const pctNeg = Math.round(sent.negative / n * 100), pctNeu = Math.round(sent.neutral / n * 100), pctPos = Math.round(sent.positive / n * 100);
const amp = Object.entries(S.top15_amplified_authors);
const maxdup = Math.max(...Object.values(S.top20_duplicated_messages));

function kicker(s, t, c = CYAN) { s.addText(t.toUpperCase(), { x: 0.6, y: 0.42, w: 11, h: 0.35, margin: 0, fontFace: BODY, fontSize: 13, bold: true, color: c, charSpacing: 3 }); }
function title(s, t, w = 12.1) { s.addText(t, { x: 0.6, y: 0.78, w, h: 1.15, margin: 0, fontFace: HEAD, fontSize: 29, bold: true, color: WHITE, lineSpacingMultiple: 0.98 }); }
function dot(s, i) { s.addText(`${i} / 5`, { x: PW - 1.4, y: PH - 0.5, w: 1.0, h: 0.3, margin: 0, align: "right", fontFace: BODY, fontSize: 10, color: MUTED }); }
function card(s, x, y, w, h, fill = PANEL) { s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { type: "none" }, shadow: sh() }); }
function chartCard(s, img, ar, x, y, w, h) {
  card(s, x, y, w, h, WHITE);
  const pad = 0.26; let iw = w - 2 * pad, ih = iw / ar;
  if (ih > h - 2 * pad) { ih = h - 2 * pad; iw = ih * ar; }
  s.addImage({ path: img, x: x + (w - iw) / 2, y: y + (h - ih) / 2, w: iw, h: ih });
}
function imgContain(s, img, ar, x, y, w, h) {
  let iw = w, ih = iw / ar; if (ih > h) { ih = h; iw = ih * ar; }
  s.addImage({ path: img, x: x + (w - iw) / 2, y: y + (h - ih) / 2, w: iw, h: ih });
}
function stat(s, x, y, w, h, big, small, accent) {
  card(s, x, y, w, h);
  s.addShape(pres.shapes.RECTANGLE, { x, y: y + 0.16, w: 0.09, h: h - 0.32, fill: { color: accent } });
  s.addText(big, { x: x + 0.26, y: y + 0.12, w: w - 0.4, h: 0.6, margin: 0, fontFace: HEAD, fontSize: 26, bold: true, color: accent });
  s.addText(small, { x: x + 0.26, y: y + 0.68, w: w - 0.42, h: h - 0.75, margin: 0, fontFace: BODY, fontSize: 12, color: LIGHT, lineSpacingMultiple: 0.98 });
}

// ============================================================= SLIDE 1
let s = pres.addSlide(); s.background = { color: INK };
s.addImage({ path: path.join(F3, "hero_wide.png"), x: 8.55, y: 0, w: 4.783, h: 7.5, sizing: { type: "cover", w: 4.783, h: 7.5 } });
s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: PW, h: 0.14, fill: { color: VIOLET } });
s.addShape(pres.shapes.RECTANGLE, { x: 0, y: PH - 0.14, w: PW, h: 0.14, fill: { color: CYAN } });
s.addText("DATATHON · 2 JOURS · JOUR 1", { x: 0.9, y: 1.1, w: 7.4, h: 0.4, margin: 0, fontFace: BODY, fontSize: 15, bold: true, color: CYAN, charSpacing: 4 });
s.addText("Affaire Ultia × CNC", { x: 0.9, y: 1.75, w: 7.5, h: 1.1, margin: 0, fontFace: HEAD, fontSize: 50, bold: true, color: WHITE });
s.addText("Anatomie d'un déferlement viral", { x: 0.9, y: 2.9, w: 7.5, h: 0.8, margin: 0, fontFace: HEAD, fontSize: 30, italic: true, color: VIOLET });
s.addText([
  { text: "Un fait réel, transformé en tempête sur X en quatre jours.  ", options: { color: LIGHT } },
  { text: "Fait → Narratif → ", options: { color: MUTED } },
  { text: "Dynamique", options: { color: CYAN, bold: true } },
  { text: ".", options: { color: MUTED } },
], { x: 0.9, y: 3.95, w: 7.3, h: 0.7, margin: 0, fontFace: BODY, fontSize: 16 });
const strip = [[nf(n), "MESSAGES", 2.15], [nf(S.n_authors), "COMPTES", 2.15], ["19 mars → 1 mai", "PÉRIODE", 2.45]];
let sx = 0.9;
strip.forEach(([b, l, w]) => {
  card(s, sx, 5.3, w, 1.35);
  s.addText(b, { x: sx + 0.22, y: 5.46, w: w - 0.35, h: 0.62, margin: 0, fontFace: HEAD, fontSize: l === "PÉRIODE" ? 19 : 27, bold: true, color: WHITE });
  s.addText(l, { x: sx + 0.22, y: 6.08, w: w - 0.35, h: 0.4, margin: 0, fontFace: BODY, fontSize: 12, color: MUTED, charSpacing: 2 });
  sx += w + 0.3;
});

// ============================================================= SLIDE 2
s = pres.addSlide(); s.background = { color: INK };
kicker(s, "01 · Propagation"); title(s, "Une déflagration de 4 jours, portée par le retweet");
chartCard(s, path.join(F2, "timeline.png"), 1.872, 0.6, 1.95, 6.95, 5.0);
// engagement donut card
card(s, 7.75, 1.95, 5.05, 2.55, WHITE);
s.addText("Nature des messages", { x: 7.95, y: 2.05, w: 3.0, h: 0.4, margin: 0, fontFace: HEAD, fontSize: 14, bold: true, color: INK });
imgContain(s, path.join(F3, "engagement_donut.png"), 1.0, 10.6, 2.15, 2.35, 2.05);
s.addText([
  { text: "86 % retweets", options: { color: "5B2BE0", bold: true, breakLine: true } },
  { text: "13 % réponses / quotes", options: { color: "0E7490", breakLine: true } },
  { text: "1,9 % originaux", options: { color: "B91C1C" } },
], { x: 7.95, y: 2.55, w: 2.55, h: 1.8, margin: 0, fontFace: BODY, fontSize: 13, lineSpacingMultiple: 1.1 });
stat(s, 7.75, 4.65, 2.42, 2.25, nf(S.peak_day_volume), "messages au pic, le " + S.peak_day + ".", CORAL);
stat(s, 10.38, 4.65, 2.42, 2.25, nf(et.ORIGINAL), "messages originaux (1,9 % du corpus).", CYAN);
dot(s, 2);

// ============================================================= SLIDE 3
s = pres.addSlide(); s.background = { color: INK };
kicker(s, "02 · Acteurs"); title(s, "Deux couches : des sources amplifiées, une masse de relais");
chartCard(s, path.join(F2, "amplified.png"), 1.68, 0.6, 1.95, 7.4, 4.95);
s.addText("Comptes dont les messages sont le plus retweetés (patient zéro / relais).", { x: 0.6, y: 7.02, w: 7.4, h: 0.35, margin: 0, align: "center", fontFace: BODY, fontSize: 12, italic: true, color: MUTED });
const layers = [
  ["Les sources", "Personnalités politiques, médias & comptes militants (Bellamy, Maréchal, Bastié, ojim_france…) + le CNC lui-même.", VIOLET],
  ["Les relais", "Une piétaille de comptes qui retweetent en boucle (~100 messages chacun) pour propulser le narratif.", CYAN],
  ["Le vernis", S.verified_share_pct + " % de comptes certifiés seulement : l'amplification vient surtout de comptes non vérifiés.", CORAL],
];
let ly = 1.95;
layers.forEach(([t, d, c]) => {
  card(s, 8.35, ly, 4.4, 1.5);
  s.addShape(pres.shapes.RECTANGLE, { x: 8.35, y: ly + 0.18, w: 0.09, h: 1.14, fill: { color: c } });
  s.addText(t, { x: 8.63, y: ly + 0.16, w: 4.0, h: 0.4, margin: 0, fontFace: HEAD, fontSize: 18, bold: true, color: c });
  s.addText(d, { x: 8.63, y: ly + 0.6, w: 3.95, h: 0.85, margin: 0, fontFace: BODY, fontSize: 12, color: LIGHT, lineSpacingMultiple: 0.98 });
  ly += 1.62;
});
dot(s, 3);

// ============================================================= SLIDE 4
s = pres.addSlide(); s.background = { color: INK };
kicker(s, "03 · Narratifs & Sémantique"); title(s, "Trois cadrages, un ton majoritairement négatif");
chartCard(s, path.join(F2, "terms.png"), 0.875, 0.5, 1.9, 4.55, 5.2);
const frames = [
  ["L'argent public", "cnc · fonds · subventions · millions · euros · aides", CORAL],
  ["Les camps politiques", "gauche · extrême · droite · français", VIOLET],
  ["Qui finance-t-on ?", "talent · streameuse · créateurs · cinéma · film", CYAN],
];
let fy = 1.7;
frames.forEach(([t, w, c]) => {
  card(s, 5.25, fy, 7.55, 1.0);
  s.addShape(pres.shapes.RECTANGLE, { x: 5.25, y: fy + 0.13, w: 0.09, h: 0.74, fill: { color: c } });
  s.addText(t, { x: 5.52, y: fy + 0.1, w: 7.1, h: 0.38, margin: 0, fontFace: HEAD, fontSize: 16, bold: true, color: c });
  s.addText(w, { x: 5.52, y: fy + 0.5, w: 7.1, h: 0.4, margin: 0, fontFace: BODY, fontSize: 13, color: LIGHT });
  fy += 1.13;
});
// sentiment donut card
card(s, 5.25, fy + 0.02, 7.55, 1.85);
imgContain(s, path.join(F3, "sentiment_donut.png"), 1.0, 5.4, fy + 0.05, 1.8, 1.8);
s.addText([
  { text: "Répartition des sentiments\n", options: { color: WHITE, bold: true } },
  { text: `${pctNeg} % négatif`, options: { color: CORAL, bold: true } },
  { text: `  ·  ${pctNeu} % neutre  ·  `, options: { color: LIGHT } },
  { text: `${pctPos} % positif`, options: { color: CYAN, bold: true } },
  { text: "\nLa négativité culmine avec le pic de volume.", options: { color: MUTED } },
], { x: 7.4, y: fy + 0.1, w: 5.2, h: 1.7, margin: 0, valign: "middle", fontFace: BODY, fontSize: 14, lineSpacingMultiple: 1.15 });
dot(s, 4);

// ============================================================= SLIDE 5
s = pres.addSlide(); s.background = { color: INK };
s.addImage({ path: path.join(F3, "hero_wide.png"), x: 9.7, y: 0, w: 3.633, h: 7.5, sizing: { type: "cover", w: 3.633, h: 7.5 } });
s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: PW, h: 0.14, fill: { color: CORAL } });
kicker(s, "04 · Coordination & Riposte", CORAL);
title(s, "Signaux de coordination → un agent IA pour la riposte", 9.0);
card(s, 0.6, 2.05, 4.35, 4.5);
s.addText("Ce que révèle la coordination", { x: 0.85, y: 2.28, w: 3.9, h: 0.5, margin: 0, fontFace: HEAD, fontSize: 17, bold: true, color: CYAN });
s.addText([
  { text: `Messages copiés-collés jusqu'à ${nf(maxdup)} fois à l'identique`, options: { bullet: { indent: 16 }, breakLine: true, paraSpaceAfter: 10 } },
  { text: "Rafales synchronisées à la même minute", options: { bullet: { indent: 16 }, breakLine: true, paraSpaceAfter: 10 } },
  { text: `${nf(S.n_authors_1_msg)} comptes ne postent qu'un seul message`, options: { bullet: { indent: 16 }, breakLine: true, paraSpaceAfter: 10 } },
  { text: `${S.verified_share_pct} % de comptes certifiés seulement`, options: { bullet: { indent: 16 } } },
], { x: 0.85, y: 2.9, w: 3.85, h: 3.5, margin: 0, fontFace: BODY, fontSize: 14, color: LIGHT });
card(s, 5.1, 2.05, 4.35, 4.5, VIOLET);
s.addText("Prochaine étape : l'agent « Analyste »", { x: 5.35, y: 2.28, w: 3.9, h: 0.5, margin: 0, fontFace: HEAD, fontSize: 17, bold: true, color: WHITE });
s.addText("Modèle + accès au corpus + mémoire", { x: 5.35, y: 2.78, w: 3.9, h: 0.35, margin: 0, fontFace: BODY, fontSize: 13, bold: true, color: "E9D5FF" });
s.addText([
  { text: "Interroge le corpus (volume, comptes, narratifs)", options: { bullet: { indent: 16 }, breakLine: true, paraSpaceAfter: 10 } },
  { text: "Résume le narratif dominant d'un échantillon", options: { bullet: { indent: 16 }, breakLine: true, paraSpaceAfter: 10 } },
  { text: "Détecte les signaux de coordination", options: { bullet: { indent: 16 }, breakLine: true, paraSpaceAfter: 10 } },
  { text: "Réutilisable pour d'autres crises informationnelles", options: { bullet: { indent: 16 } } },
], { x: 5.35, y: 3.25, w: 3.85, h: 3.1, margin: 0, fontFace: BODY, fontSize: 14, color: WHITE });
dot(s, 5);

const out = path.join(ROOT, "Datathon_Ultia_CNC_Jour1_v3.pptx");
pres.writeFile({ fileName: out }).then(() => console.log("Saved", out));
