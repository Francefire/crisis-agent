"""Generate v3 visual assets: abstract network hero + donut charts, plus reuse of v2 bar/line charts."""
import os, json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
FIG = os.path.join(HERE, "figures_v3")
os.makedirs(FIG, exist_ok=True)
S = json.load(open(os.path.join(HERE, "out", "key_figures.json")))

INK = "#0B1020"; VIOLET = "#7C3AED"; CYAN = "#22D3EE"; CORAL = "#FF5C5C"
LIGHT = "#E5E7EB"; MUTED = "#94A3B8"; SLATE = "#3A4468"

# ---------- abstract "information storm" network image (for hero bands)
def hero(path, w=1400, h=1600, seed=7, npts=170):
    rng = np.random.default_rng(seed)
    fig, ax = plt.subplots(figsize=(w/100, h/100), dpi=100)
    fig.patch.set_facecolor(INK); ax.set_facecolor(INK)
    # radial concentration toward center for a "burst" feel
    ang = rng.uniform(0, 2*np.pi, npts)
    rad = rng.beta(1.6, 3.0, npts)
    cx, cy = 0.5, 0.55
    x = cx + rad*np.cos(ang)*0.6
    y = cy + rad*np.sin(ang)*0.6
    # connecting lines to nearest-ish neighbours
    for i in range(npts):
        d = (x-x[i])**2 + (y-y[i])**2
        for j in np.argsort(d)[1:3]:
            ax.plot([x[i], x[j]], [y[i], y[j]], color=CYAN, alpha=0.06, lw=0.7, zorder=1)
    sizes = rng.uniform(6, 130, npts) * (1.3 - rad)
    cols = rng.choice([VIOLET, CYAN, CORAL], size=npts, p=[0.5, 0.38, 0.12])
    # glow: draw large faint then small bright
    ax.scatter(x, y, s=sizes*6, c=cols, alpha=0.10, zorder=2, edgecolors="none")
    ax.scatter(x, y, s=sizes, c=cols, alpha=0.9, zorder=3, edgecolors="none")
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    ax.margins(0)
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    fig.savefig(path, dpi=100, facecolor=INK)
    plt.close(fig)

hero(os.path.join(FIG, "hero.png"))
hero(os.path.join(FIG, "hero_wide.png"), w=760, h=1600, seed=21, npts=120)

# ---------- sentiment donut
def donut(path, labels, values, colors, w=900, h=900):
    fig, ax = plt.subplots(figsize=(w/100, h/100), dpi=100)
    fig.patch.set_alpha(0)
    ax.pie(values, colors=colors, startangle=90,
           wedgeprops=dict(width=0.42, edgecolor=INK, linewidth=3))
    # biggest slice value in the hole for a clean focal number
    imax = int(np.argmax(values))
    ax.text(0, 0, f"{values[imax]}%\n{labels[imax]}", ha="center", va="center",
            color=colors[imax], fontsize=20, fontweight="bold")
    ax.set_aspect("equal")
    fig.savefig(path, dpi=100, transparent=True, bbox_inches="tight")
    plt.close(fig)

sent = S["sentiment_counts"]; n = S["n_rows"]
donut(os.path.join(FIG, "sentiment_donut.png"),
      ["Négatif", "Neutre", "Positif"],
      [round(sent["negative"]/n*100), round(sent["neutral"]/n*100), round(sent["positive"]/n*100)],
      [CORAL, SLATE, CYAN])

et = S["engagement_type_counts"]; tot = sum(et.values())
donut(os.path.join(FIG, "engagement_donut.png"),
      ["Retweets", "Réponses", "Quotes", "Originaux"],
      [round(et["RETWEET"]/tot*100), round(et["REPLY"]/tot*100),
       round(et["QUOTE"]/tot*100), round(et["ORIGINAL"]/tot*100)],
      [VIOLET, CYAN, SLATE, CORAL])

print("v3 assets:", sorted(os.listdir(FIG)))
