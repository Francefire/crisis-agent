"""
Datathon Ultia x CNC — Exploratory Data Analysis.
Builds the timeline + the 5 analysis axes (Acteurs, Narratifs, Propagation,
Coordination, Semantique) and dumps figures + a key-figures summary.

Run:  ../.venv/bin/python eda.py   (from analysis/)  or  .venv/bin/python analysis/eda.py
"""
import os
import re
import json
from collections import Counter

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FIG = os.path.join(HERE, "figures")
OUT = os.path.join(HERE, "out")
os.makedirs(FIG, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

summary = {}


def save(fig, name):
    path = os.path.join(FIG, name)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    print("  saved", name)


# ---------------------------------------------------------------- load
print("Loading corpus...")
df = pd.read_excel(os.path.join(ROOT, "Dataset", "data.xlsx"))
df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
df = df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
df["Engagement Type"] = df["Engagement Type"].fillna("ORIGINAL")
summary["n_rows"] = len(df)
summary["date_min"] = str(df["Date"].min())
summary["date_max"] = str(df["Date"].max())
summary["n_authors"] = int(df["Author"].nunique())
print(f"  {len(df)} rows, {df['Author'].nunique()} unique authors")

# ============================================================= TIMELINE
print("\n[TIMELINE]")
daily = df.set_index("Date").resample("D").size()
fig, ax = plt.subplots(figsize=(12, 4))
ax.plot(daily.index, daily.values, color="#5b2be0")
ax.fill_between(daily.index, daily.values, alpha=0.2, color="#5b2be0")
ax.set_title("Volume de messages par jour — crise Ultia x CNC")
ax.set_ylabel("messages / jour")
save(fig, "01_timeline_daily.png")

peaks = daily.sort_values(ascending=False).head(5)
summary["top5_peak_days"] = {str(d.date()): int(v) for d, v in peaks.items()}
summary["peak_day"] = str(peaks.index[0].date())
summary["peak_day_volume"] = int(peaks.iloc[0])

# hourly view around the peak day
peak_day = peaks.index[0]
mask = (df["Date"] >= peak_day.normalize()) & (df["Date"] < peak_day.normalize() + pd.Timedelta(days=2))
hourly = df.loc[mask].set_index("Date").resample("h").size()
fig, ax = plt.subplots(figsize=(12, 4))
ax.plot(hourly.index, hourly.values, color="#e0662b")
ax.set_title(f"Volume horaire autour du pic ({peak_day.date()})")
ax.set_ylabel("messages / heure")
save(fig, "02_timeline_hourly_peak.png")

# ============================================================= ACTEURS
print("\n[ACTEURS]")
top_authors = df["Author"].value_counts().head(15)
summary["top15_authors_by_volume"] = top_authors.to_dict()

# amplifiers: whose content gets retweeted most.
# "X Repost of" holds the original tweet URL -> extract the handle from it.
def handle_from_url(u):
    m = re.search(r"twitter\.com/([^/]+)/status", str(u))
    return m.group(1) if m else None

df["repost_handle"] = df["X Repost of"].map(handle_from_url)
amplified = df["repost_handle"].dropna().value_counts().head(15)
summary["top15_amplified_authors"] = amplified.to_dict()

fig, axes = plt.subplots(1, 2, figsize=(15, 6))
top_authors[::-1].plot.barh(ax=axes[0], color="#5b2be0")
axes[0].set_title("Top 15 comptes les plus actifs (nb messages)")
amplified[::-1].plot.barh(ax=axes[1], color="#2bbfa0")
axes[1].set_title("Top 15 comptes les plus retweetes (patient zero / relais)")
save(fig, "03_acteurs_top.png")

verified_share = df["X Verified"].astype(str).str.lower().isin(["true", "1", "1.0"]).mean()
summary["verified_share_pct"] = round(float(verified_share) * 100, 1)

# ============================================================= PROPAGATION
print("\n[PROPAGATION]")
et = df["Engagement Type"].value_counts()
summary["engagement_type_counts"] = et.to_dict()
summary["retweet_share_pct"] = round(float((df["Engagement Type"] == "RETWEET").mean()) * 100, 1)

fig, ax = plt.subplots(figsize=(7, 5))
et.plot.bar(ax=ax, color=["#5b2be0", "#e0662b", "#2bbfa0", "#888"])
ax.set_title("Nature des messages (Engagement Type)")
ax.set_ylabel("nb messages")
save(fig, "04_propagation_engagement_type.png")

# reach / impressions over time
reach_daily = df.set_index("Date")["Reach"].resample("D").sum()
fig, ax = plt.subplots(figsize=(12, 4))
ax.plot(reach_daily.index, reach_daily.values, color="#e0662b")
ax.set_title("Reach cumule par jour (portee de la crise)")
ax.set_ylabel("reach / jour")
save(fig, "05_propagation_reach.png")

# ============================================================= SEMANTIQUE
print("\n[SEMANTIQUE]")
sent = df["Sentiment"].value_counts()
summary["sentiment_counts"] = sent.to_dict()
sent_daily = df.pivot_table(index=df["Date"].dt.date, columns="Sentiment",
                            values="postID", aggfunc="count").fillna(0)
fig, ax = plt.subplots(figsize=(12, 4))
for col, color in [("negative", "#d13b3b"), ("neutral", "#888"), ("positive", "#2bbfa0")]:
    if col in sent_daily:
        ax.plot(sent_daily.index, sent_daily[col], label=col, color=color)
ax.legend()
ax.set_title("Sentiment par jour")
ax.set_ylabel("messages / jour")
save(fig, "06_semantique_sentiment.png")

# ============================================================= NARRATIFS
print("\n[NARRATIFS]")
STOP = set("""le la les un une des de du et a à en au aux ce cette ces que qui quoi
dont ou où pour par sur avec sans dans est sont ete été être c est s il elle ils
elles on nous vous je tu son sa ses mon ma mes ton ta tes leur leurs se ne pas ni
plus moins mais donc or car si comme tout tous toute toutes meme même aussi bien
fait faire cela ça y d l m n t qu jai jaine rt via https http co t.co amp lol""".split())


def tokens(text):
    return [w for w in re.findall(r"[a-zàâçéèêëîïôûùüÿñæœ]{3,}", str(text).lower())
            if w not in STOP]


counter = Counter()
for txt in df["message_normalizer"].fillna(""):
    counter.update(set(tokens(txt)))  # per-doc set => document frequency
top_terms = counter.most_common(40)
summary["top40_terms_docfreq"] = {w: c for w, c in top_terms}

fig, ax = plt.subplots(figsize=(9, 10))
words = [w for w, _ in top_terms][::-1]
counts = [c for _, c in top_terms][::-1]
ax.barh(words, counts, color="#5b2be0")
ax.set_title("Top 40 termes (frequence documentaire)")
save(fig, "07_narratifs_top_terms.png")

# ============================================================= COORDINATION
print("\n[COORDINATION]")
# 1. duplicate / copy-paste texts (excluding pure retweets is hard; use normalized text)
dup = df["message_normalizer"].fillna("").value_counts()
dup = dup[dup >= 5].head(20)
summary["top20_duplicated_messages"] = {str(k)[:120]: int(v) for k, v in dup.items()}

# 2. account-age / behaviour proxies: very high posts, follower/following ratio
df["foll_ratio"] = df["X Followers"] / (df["X Following"].replace(0, np.nan) + 1)
susp = (df.groupby("Author")
          .agg(msgs=("postID", "count"),
               followers=("X Followers", "max"),
               following=("X Following", "max"),
               posts=("X Posts", "max"))
          .sort_values("msgs", ascending=False))
summary["n_authors_1_msg"] = int((susp["msgs"] == 1).sum())
summary["n_authors_ge_20_msg"] = int((susp["msgs"] >= 20).sum())

# 3. burst detection: messages within same minute sharing text (coordination signal)
df["minute"] = df["Date"].dt.floor("min")
burst = (df.groupby(["minute", "message_normalizer"]).size()
           .sort_values(ascending=False).head(15))
summary["top_synchronized_bursts"] = {
    f"{m} | {str(t)[:60]}": int(n) for (m, t), n in burst.items()}

fig, ax = plt.subplots(figsize=(10, 5))
susp["msgs"].clip(upper=50).plot.hist(bins=50, ax=ax, color="#e0662b")
ax.set_title("Distribution du nb de messages par compte (clip a 50)")
ax.set_xlabel("messages par compte")
save(fig, "08_coordination_msgs_per_account.png")

# ---------------------------------------------------------------- dump
with open(os.path.join(OUT, "key_figures.json"), "w") as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)

print("\n==================== KEY FIGURES ====================")
print(json.dumps(summary, indent=2, ensure_ascii=False)[:4000])
print("\nDone. Figures in analysis/figures/, summary in analysis/out/key_figures.json")
