// Day-2 Propagation deep-dive slide (pptxgenjs). Same dark theme as v3.
// Standalone file so it can be merged into the Day-2 deck later.
const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");

const HERE = __dirname, ROOT = path.dirname(HERE);
const FP = path.join(HERE, "figures_prop");

const INK = "0B1020", PANEL = "1B2340";
const VIOLET = "7C3AED", CYAN = "22D3EE", CORAL = "FF5C5C";
const WHITE = "FFFFFF", LIGHT = "E5E7EB", MUTED = "94A3B8";
const HEAD = "Georgia", BODY = "Calibri";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.author = "Datathon"; pres.title = "Ultia x CNC — Propagation (Jour 2)";
const PW = 13.333, PH = 7.5;
const sh = () => ({ type: "outer", color: "000000", blur: 10, offset: 3, angle: 135, opacity: 0.35 });

function kicker(s, t, c = CYAN) { s.addText(t.toUpperCase(), { x: 0.6, y: 0.42, w: 12, h: 0.35, margin: 0, fontFace: BODY, fontSize: 13, bold: true, color: c, charSpacing: 3 }); }
function title(s, t, w = 12.1) { s.addText(t, { x: 0.6, y: 0.78, w, h: 1.05, margin: 0, fontFace: HEAD, fontSize: 26, bold: true, color: WHITE, lineSpacingMultiple: 0.98 }); }
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
  s.addText(big, { x: x + 0.26, y: y + 0.06, w: w - 0.4, h: 0.5, margin: 0, fontFace: HEAD, fontSize: 22, bold: true, color: accent });
  s.addText(small, { x: x + 0.28, y: y + 0.55, w: w - 0.45, h: h - 0.6, margin: 0, fontFace: BODY, fontSize: 12, color: LIGHT, lineSpacingMultiple: 0.95 });
}

// ============================================================= SLIDE
let s = pres.addSlide(); s.background = { color: INK };
s.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: PW, h: 0.14, fill: { color: VIOLET } });
kicker(s, "Propagation · la vitesse — le cœur de la dynamique");
title(s, "La physique du déferlement : 7 h pour exploser, ×2 toutes les 2,8 h", 12.2);

// hero chart : volume vs audience over the ignition window
chartCard(s, path.join(FP, "velocity.png"), 9.0 / 4.7, 0.55, 1.95, 7.35, 5.0);

// right column : velocity callouts + reach insight
const RX = 8.15, RW = 4.65;
const stats = [
  ["7 h", "temps de montée : allumage 09 h → pic 16 h (26/03)", CYAN],
  ["× 2 / 2,8 h", "rythme de doublement du volume pendant la montée (+28 %/h)", VIOLET],
  ["7 h", "demi-vie : le volume retombe de moitié 7 h après le pic", CORAL],
];
let ry = 1.95;
stats.forEach(([b, l, c]) => { statRow(s, RX, ry, RW, 1.12, b, l, c); ry += 1.26; });

// reach-leads-volume insight
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

const out = path.join(ROOT, "Datathon_Ultia_CNC_Propagation.pptx");
pres.writeFile({ fileName: out }).then(() => console.log("Saved", out));
