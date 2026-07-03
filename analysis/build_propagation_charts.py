"""Propagation deep-dive charts (Day-2): velocity dual-curve + narrative drift.

Numbers come straight from the verified Corpus tools (agent/tools.py), so the
charts match the agent's output and verify_tools (26/26). Transparent PNGs with
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
FIG = os.path.join(HERE, "figures_prop")
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
ts = c.col["timestamp"]
vel = c.timeline(freq="h", velocity=True)["velocity"]
onset = pd.to_datetime(vel["onset_period"]); peak = pd.to_datetime(vel["peak_period"])

# ============================================ 1. VELOCITY : volume vs audience
win = ("2026-03-25", "2026-03-31")
sub = c.df[(c.df[ts] >= win[0]) & (c.df[ts] <= win[1])]
vol = sub.set_index(ts).resample("h").size()
reach = sub.set_index(ts)[c.col["reach"]].fillna(0).resample("h").sum()

fig, ax = plt.subplots(figsize=(9.0, 4.7))
ax.fill_between(vol.index, vol.values, color=VIOLET, alpha=0.20)
ax.plot(vol.index, vol.values, color=VIOLET, linewidth=2.6, label="Messages / heure")
ax.set_ylabel("messages / heure", color=VIOLET)
ax.tick_params(axis="y", colors=VIOLET)

ax2 = ax.twinx()
ax2.plot(reach.index, reach.values / 1e6, color=TEAL, linewidth=2.2,
         linestyle=(0, (4, 2)), label="Audience (reach) / heure")
ax2.set_ylabel("audience (millions) / heure", color=TEAL)
ax2.tick_params(axis="y", colors=TEAL)
ax2.spines["top"].set_visible(False)

# onset + peak markers
ax.axvline(onset, color=MUTED, linewidth=1.0, linestyle=":")
ax.scatter([peak], [vol.max()], color=CORAL, zorder=6, s=80)
ax.annotate(f"pic {int(vol.max())} msg/h\n{peak:%d/%m %Hh}", (peak, vol.max()),
            xytext=(10, -2), textcoords="offset points", color=CORAL,
            fontweight="bold", fontsize=12, va="top")
ax.annotate(f"allumage\n{onset:%d/%m %Hh}", (onset, vol.max()*0.62),
            xytext=(-72, 0), textcoords="offset points", color=MUTED, fontsize=11)

for a in (ax, ax2):
    a.spines["top"].set_visible(False)
ax.grid(axis="y", color=GRID, linewidth=0.7)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
ax.margins(x=0.01)
fig.tight_layout()
fig.savefig(os.path.join(FIG, "velocity.png"), dpi=200, transparent=True)
plt.close(fig)

# ================================= 2. NARRATIVE DRIFT : normalized daily curves
nt = c.narrative_timelines(k=6, freq="D")
# keep the most substantial framings; drop a filler cluster if its terms are thin
clusters = [cl for cl in nt["clusters"] if cl["series"]][:5]
palette = [VIOLET, TEAL, CORAL, AMBER, SLATE]

fig, ax = plt.subplots(figsize=(9.0, 4.6))
for cl, colr in zip(clusters, palette):
    s = pd.Series({pd.to_datetime(k): v for k, v in cl["series"].items()}).sort_index()
    s = s[(s.index >= pd.to_datetime("2026-03-26")) & (s.index <= pd.to_datetime("2026-04-03"))]
    if s.empty or s.max() == 0:
        continue
    label = " · ".join(cl["top_terms"][:2])
    norm = s.values / s.max()
    ax.plot(s.index, norm, color=colr, linewidth=2.4, marker="o", markersize=4, label=label)
    pk = s.idxmax()
    ax.scatter([pk], [1.0], color=colr, s=55, zorder=5, edgecolor="white", linewidth=1.0)

ax.set_ylabel("volume (normalisé au pic)")
ax.set_ylim(0, 1.12)
ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
ax.grid(axis="y", color=GRID, linewidth=0.7)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
ax.margins(x=0.02)
ax.legend(loc="upper right", fontsize=11, frameon=False, ncol=1)
fig.tight_layout()
fig.savefig(os.path.join(FIG, "narrative_drift.png"), dpi=200, transparent=True)
plt.close(fig)

print("propagation charts ->", FIG, os.listdir(FIG))
print("velocity:", {k: vel[k] for k in
      ("time_to_peak_hours", "doubling_time_hours", "half_life_hours")})
print("lead_lag:", [(cl["top_terms"][:2], cl["peak_period"][:10]) for cl in clusters])
