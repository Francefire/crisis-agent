"""Coordination deep-dive charts (Day-2): synchronised-burst timeline + cluster sizes.

Numbers come straight from the verified Corpus tools (agent/tools.py), so the
charts match the agent's output and verify_tools (41/41). Transparent PNGs with
dark labels, to sit on white cards in the dark deck.
"""
import os, sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIG = os.path.join(HERE, "figures_coord")
os.makedirs(FIG, exist_ok=True)
sys.path.insert(0, os.path.join(ROOT, "agent"))
from tools import Corpus  # noqa: E402

VIOLET = "#7C3AED"; TEAL = "#0E7490"; CORAL = "#DC2626"
AMBER = "#D97706"; SLATE = "#475569"; INK = "#0B1020"
MUTED = "#64748B"; GRID = "#E2E8F0"

plt.rcParams.update({
    "font.size": 15, "axes.edgecolor": "#CBD5E1", "axes.linewidth": 0.8,
    "text.color": INK, "axes.labelcolor": INK, "xtick.color": MUTED,
    "ytick.color": INK, "font.family": "DejaVu Sans",
})

c = Corpus()
co = c.coordination()
net = c.coordination_network()

# ============================================ 1. SYNCHRONISED BURSTS OVER TIME
# n_bursts_ge3 = number of Δ=60s windows with >=3 copies of an identical text
series = co["synchrony"]["burst_size_over_time"]
s = pd.Series({pd.to_datetime(k): v["n_bursts_ge3"] for k, v in series.items()}).sort_index()
s = s[(s.index >= pd.to_datetime("2026-03-25")) & (s.index <= pd.to_datetime("2026-04-03"))]

fig, ax = plt.subplots(figsize=(9.0, 4.7))
peak_day = s.idxmax()
colors = [CORAL if d == peak_day else VIOLET for d in s.index]
ax.bar(s.index, s.values, width=0.72, color=colors, alpha=0.92)
ax.annotate(f"{int(s.max())} rafales\n{peak_day:%d/%m}", (peak_day, s.max()),
            xytext=(0, 6), textcoords="offset points", color=CORAL,
            fontweight="bold", fontsize=12, ha="center", va="bottom")
ax.set_ylabel("rafales synchronisées / jour\n(même texte, ≥3 copies en < 60 s)")
ax.set_ylim(0, s.max() * 1.16)
ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
ax.grid(axis="y", color=GRID, linewidth=0.7)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
ax.margins(x=0.02)
fig.tight_layout()
fig.savefig(os.path.join(FIG, "bursts.png"), dpi=200, transparent=True)
plt.close(fig)

# ============================================ 2. LARGEST COORDINATED CLUSTERS
clusters = net["top_clusters"][:8]
sizes = [cl["size"] for cl in clusters]
labels = [f"cluster {i+1}" for i in range(len(clusters))]
ver = [cl["verified_share_pct"] for cl in clusters]

fig, ax = plt.subplots(figsize=(9.0, 4.6))
ypos = np.arange(len(sizes))[::-1]
ax.barh(ypos, sizes, color=VIOLET, alpha=0.9, height=0.66)
for y, sz, v in zip(ypos, sizes, ver):
    ax.text(sz + max(sizes) * 0.01, y, f"{sz} comptes · {v:.0f}% vérifiés",
            va="center", ha="left", fontsize=11, color=INK)
ax.set_yticks(ypos); ax.set_yticklabels(labels, fontsize=11)
ax.set_xlabel("taille du cluster (comptes co-rafalant le même texte, Δ=60 s)")
ax.set_xlim(0, max(sizes) * 1.32)
ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
ax.grid(axis="x", color=GRID, linewidth=0.7)
fig.tight_layout()
fig.savefig(os.path.join(FIG, "clusters.png"), dpi=200, transparent=True)
plt.close(fig)

print("coordination charts ->", FIG, os.listdir(FIG))
print("coordination_score_pct:", co["synchrony"]["coordination_score_pct"])
print("peak bursts day:", str(peak_day.date()), int(s.max()))
print("near_dup top group:", co["near_duplicates"]["top_near_dup_groups"][0]["n_variants"],
      "variants /", co["near_duplicates"]["top_near_dup_groups"][0]["total_count"], "msgs")
print("low_footprint:", co["account_behaviour"]["low_footprint_amplifiers"],
      co["account_behaviour"]["low_footprint_amplifiers_pct"], "%")
print("network:", {k: net[k] for k in ("n_nodes", "largest_component_size", "n_communities")})
