"""Regenerate chart PNGs in the v2 palette (clean, large fonts, no titles)."""
import os, json
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIG = os.path.join(HERE, "figures_v2")
os.makedirs(FIG, exist_ok=True)
S = json.load(open(os.path.join(HERE, "out", "key_figures.json")))

VIOLET = "#7C3AED"
CYAN   = "#22D3EE"
CORAL  = "#FF5C5C"
INK    = "#0B1020"
MUTED  = "#64748B"
GRID   = "#E2E8F0"

plt.rcParams.update({
    "font.size": 15, "axes.edgecolor": "#CBD5E1", "axes.linewidth": 0.8,
    "text.color": INK, "axes.labelcolor": INK, "xtick.color": MUTED,
    "ytick.color": INK, "font.family": "DejaVu Sans",
})

df = pd.read_excel(os.path.join(ROOT, "Dataset", "data.xlsx"))
df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
df = df.dropna(subset=["Date"]).sort_values("Date")

# ---- timeline (area) on white card
daily = df.set_index("Date").resample("D").size()
fig, ax = plt.subplots(figsize=(8.6, 4.6))
ax.fill_between(daily.index, daily.values, color=VIOLET, alpha=0.22)
ax.plot(daily.index, daily.values, color=VIOLET, linewidth=2.6)
peak_day = daily.idxmax()
ax.scatter([peak_day], [daily.max()], color=CORAL, zorder=5, s=70)
ax.annotate(f"  {peak_day.date()}\n  {int(daily.max()):,} msgs".replace(",", " "),
            (peak_day, daily.max()), color=CORAL, fontweight="bold", fontsize=14,
            va="top")
for s in ["top", "right"]:
    ax.spines[s].set_visible(False)
ax.set_ylabel("messages / jour")
ax.grid(axis="y", color=GRID, linewidth=0.7)
ax.margins(x=0.01)
fig.tight_layout()
fig.savefig(os.path.join(FIG, "timeline.png"), dpi=200, transparent=True)
plt.close(fig)

# ---- amplified accounts (patient zero) horizontal bars
amp = list(S["top15_amplified_authors"].items())[:8][::-1]
names = ["@" + a for a, _ in amp]
vals = [c for _, c in amp]
fig, ax = plt.subplots(figsize=(8.4, 5.0))
bars = ax.barh(names, vals, color=VIOLET)
for b, v in zip(bars, vals):
    ax.text(v + max(vals)*0.01, b.get_y() + b.get_height()/2,
            f"{v:,}".replace(",", " "), va="center", fontsize=13, color=INK)
for s in ["top", "right"]:
    ax.spines[s].set_visible(False)
ax.set_xlabel("reprises (retweets)")
ax.margins(x=0.12)
ax.tick_params(axis="y", length=0)
fig.tight_layout()
fig.savefig(os.path.join(FIG, "amplified.png"), dpi=200, transparent=True)
plt.close(fig)

# ---- top terms horizontal bars
terms = list(S["top40_terms_docfreq"].items())[:14][::-1]
tnames = [t for t, _ in terms]
tvals = [c for _, c in terms]
fig, ax = plt.subplots(figsize=(5.6, 6.4))
ax.barh(tnames, tvals, color=VIOLET)
for s in ["top", "right"]:
    ax.spines[s].set_visible(False)
ax.set_xlabel("frequence documentaire")
ax.margins(x=0.02)
ax.tick_params(axis="y", length=0)
fig.tight_layout()
fig.savefig(os.path.join(FIG, "terms.png"), dpi=200, transparent=True)
plt.close(fig)

print("charts v2 written to", FIG, "->", os.listdir(FIG))
