// Day-2 Coordination deep-dive slide (pptxgenjs). Same dark theme as v3.
// Standalone file so it can be merged into the Day-2 deck later.
// All numbers come from the verified Corpus tools (agent/tools.py, verify 41/41).
const pptxgen = require("pptxgenjs");
const path = require("path");

const HERE = __dirname, ROOT = path.dirname(HERE);
const FC = path.join(HERE, "figures_coord");

const INK = "0B1020", PANEL = "1B2340";
const VIOLET = "7C3AED", CYAN = "22D3EE", CORAL = "FF5C5C";
const WHITE = "FFFFFF", LIGHT = "E5E7EB", MUTED = "94A3B8";
const HEAD = "Georgia", BODY = "Calibri";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.author = "Datathon"; pres.title = "Ultia x CNC — Coordination (Jour 2)";
const PW = 13.333, PH = 7.5;
const sh = () => ({ type: "outer", color: "000000", blur: 10, offset: 3, angle: 135, opacity: 0.35 });

function kicker(s, t, c = CYAN) { s.addText(t.toUpperCase(), { x: 0.6, y: 0.42, w: 12, h: 0.35, margin: 0, fontFace: BODY, fontSize: 13, bold: true, color: c, charSpacing: 3 }); }
function title(s, t, w = 12.1) { s.addText(t, { x: 0.6, y: 0.78, w, h: 1.05, margin: 0, fontFace: HEAD, fontSize: 25, bold: true, color: WHITE, lineSpacingMultiple: 0.98 }); }
function card(s, x, y, w, h, fill = PANEL) { s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { type: "none" }, shadow: sh() }); }
function chartCard(s, img, ar, x, y, w, h) {
  card(s, x, y, w, h, WHITE);
  const pad = 0.26; let iw = w - 2 * pad, ih = iw / ar;
  if (ih > h - 2 * pad) { ih = h - 2 * pad; iw = ih * ar; }
  s.addImage({ path: img, x: x + (w - iw) / 2, y: y + (h - ih) / 2, w: iw, h: ih });
}
function statRow(s, x, y, w, h, big, small, accent) {
  card(s, x, y, w, h);
  s.addShape(pres.shapes.RECTANGLE, { x, y: y + 0.14, w: 0.09, h: h - 0.28, fill: { color: accent } });
  s.addText(big, { x: x + 0.26, y: y + 0.05, w: w - 0.4, h: 0.46, margin: 0, fontFace: HEAD, fontSize: 20, bold: true, color: accent });
  s.addText(small, { x: x + 0.28, y: y + 0.5, w: w - 0.45, h: h - 0.56, margin: 0, fontFace: BODY, fontSize: 11.5, color: LIGHT, lineSpacingMultiple: 0.95 });
}

// ============================================================= SLIDE
let s = pres.addSlide(); s.background = { color: INK };
s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: PW, h: 0.14, fill: { color: VIOLET } });
kicker(s, "Coordination · est-ce orchestré ? synchronies · copier-coller · clusters");
title(s, "Un relais synchronisé et templaté — mais un maillage diffus, pas des cellules isolées", 12.2);

// hero chart : synchronised bursts per day
chartCard(s, path.join(FC, "bursts.png"), 9.0 / 4.7, 0.55, 1.95, 7.35, 5.0);

// right column : coordination stat callouts + network insight
const RX = 8.15, RW = 4.65;
const stats = [
  ["30 %", "des copies de textes identiques sont postées à moins de 60 s d'une autre copie — synchronie (Δ = 60 s)", CYAN],
  ["3 variantes · 710 msgs", "le communiqué « le CNC a pris connaissance… » relayé en 3 versions templatées (Jaccard 3-grammes ≥ 0,8) — copier-coller", VIOLET],
  ["1 535 comptes · 14,7 %", "amplificateurs à faible empreinte : message unique + peu de posts + peu d'abonnés — PROXY (aucune date de création)", CORAL],
];
let ry = 1.9;
stats.forEach(([b, l, c]) => { statRow(s, RX, ry, RW, 1.22, b, l, c); ry += 1.32; });

// network / clusters insight
card(s, RX, ry + 0.02, RW, 1.4);
s.addShape(pres.shapes.RECTANGLE, { x: RX, y: ry + 0.16, w: 0.09, h: 1.08, fill: { color: CYAN } });
s.addText("Clusters : un maillage, pas des cellules", { x: RX + 0.26, y: ry + 0.11, w: RW - 0.45, h: 0.36, margin: 0, fontFace: HEAD, fontSize: 14, bold: true, color: WHITE });
s.addText([
  { text: "À Δ=60 s, 2 824 comptes forment ", options: { color: LIGHT } },
  { text: "un seul grand composant", options: { color: CYAN, bold: true } },
  { text: " (597 communautés Louvain, la plus grande ≈138). En exigeant des co-rafales répétées, il ne reste que des paires : amplification de masse, pas un anneau restreint.", options: { color: LIGHT } },
], { x: RX + 0.26, y: ry + 0.47, w: RW - 0.45, h: 0.9, margin: 0, fontFace: BODY, fontSize: 10.5, lineSpacingMultiple: 0.98 });

s.addText("Rafales synchronisées / jour (même texte identique, ≥3 copies en moins de 60 s). Source : agent · outils coordination + coordination_network (vérifiés, 41/41). Signaux compatibles avec une amplification coordonnée — pas une preuve d'automatisation ni d'intention.",
  { x: 0.6, y: 7.0, w: 7.3, h: 0.4, margin: 0, align: "center", fontFace: BODY, fontSize: 10.5, italic: true, color: MUTED });

const out = path.join(ROOT, "Datathon_Ultia_CNC_Coordination.pptx");
pres.writeFile({ fileName: out }).then(() => console.log("Saved", out));
