"""
Deterministic tool layer for the "Analyste" agent (Phase 1).

Principle: the LLM never reads raw rows. These pandas/sklearn tools compute all
facts (numbers, @handles, sample tweets); the LLM only interprets and narrates.
Every tool returns a JSON-serialisable dict whose fields the LLM can cite.

Schema-driven: column ROLES come from config.yaml, so the same tools run on any
tweet corpus. Clustering (TF-IDF + k-means) runs locally — no API key needed.

CLI (for Phase-1 verification against analysis/out/key_figures.json):
    .venv/bin/python agent/tools.py profile
    .venv/bin/python agent/tools.py timeline --freq D
    .venv/bin/python agent/tools.py narratives --k 6
    .venv/bin/python agent/tools.py sample --contains blast --n 5
"""
from __future__ import annotations

import os
import re
import json
import argparse
from functools import cached_property

import numpy as np
import pandas as pd
import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_CONFIG = os.path.join(HERE, "config.yaml")


def _to_native(obj):
    """Recursively coerce numpy/pandas scalars to plain Python for json.dumps."""
    if isinstance(obj, dict):
        return {str(k): _to_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_native(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (pd.Timestamp,)):
        return str(obj)
    return obj


class Corpus:
    """Loads config + dataframe once, exposes the deterministic analysis tools."""

    def __init__(self, config_path: str = DEFAULT_CONFIG):
        with open(config_path) as f:
            self.cfg = yaml.safe_load(f)
        self.col = self.cfg["columns"]
        self.val = self.cfg["values"]
        self.stopwords = list(self.cfg.get("stopwords", []))
        self.df = self._load()

    # ---------------------------------------------------------------- load
    def _load(self) -> pd.DataFrame:
        ds = self.cfg["dataset"]
        path = ds["path"]
        if not os.path.isabs(path):
            path = os.path.join(ROOT, path)
        df = pd.read_excel(path, sheet_name=ds.get("sheet", 0))

        ts, eng = self.col["timestamp"], self.col["engagement"]
        df[ts] = pd.to_datetime(df[ts], errors="coerce")
        df = df.dropna(subset=[ts]).sort_values(ts).reset_index(drop=True)
        # missing engagement type => treat as an original post
        df[eng] = df[eng].fillna(self.val["engagement_original"])

        # amplified handle: parse the reposted-original URL
        rx = re.compile(self.cfg["repost_handle_regex"])
        def handle(u):
            m = rx.search(str(u))
            return m.group(1) if m else None
        df["_repost_handle"] = df[self.col["repost_url"]].map(handle)
        return df

    # ------------------------------------------------------------- helpers
    def _verified_mask(self) -> pd.Series:
        vals = [str(v).lower() for v in self.val.get("verified_true", ["true"])]
        return self.df[self.col["verified"]].astype(str).str.lower().isin(vals)

    @cached_property
    def _clean_text(self) -> pd.Series:
        return self.df[self.col["text_clean"]].fillna("").astype(str)

    # ================================================================ TOOLS
    def profile(self, top: int = 10) -> dict:
        """Corpus overview: volume, accounts, message nature, amplifiers, sentiment.

        Grounds the 'who / what / how big' before any narrative claim.
        """
        df, col = self.df, self.col
        eng = df[col["engagement"]].value_counts()
        retweet_share = float((df[col["engagement"]] ==
                               self.val["engagement_retweet"]).mean()) * 100

        per_author = df[col["author"]].value_counts()
        amplified = df["_repost_handle"].dropna().value_counts()

        out = {
            "n_messages": len(df),
            "date_min": str(df[col["timestamp"]].min()),
            "date_max": str(df[col["timestamp"]].max()),
            "span_days": int((df[col["timestamp"]].max() -
                              df[col["timestamp"]].min()).days),
            "n_authors": int(df[col["author"]].nunique()),
            "engagement_type_counts": eng.to_dict(),
            "retweet_share_pct": round(retweet_share, 1),
            "verified_share_pct": round(float(self._verified_mask().mean()) * 100, 1),
            "n_authors_1_msg": int((per_author == 1).sum()),
            "n_authors_ge_20_msg": int((per_author >= 20).sum()),
            "top_active_authors": per_author.head(top).to_dict(),
            "top_amplified_authors": amplified.head(top).to_dict(),
        }
        if col.get("sentiment") in df:
            sent = df[col["sentiment"]].value_counts()
            out["sentiment_counts"] = sent.to_dict()
            out["sentiment_share_pct"] = {
                k: round(v / len(df) * 100, 1) for k, v in sent.items()}
        return _to_native(out)

    def timeline(self, freq: str = "D", top: int = 5, amplified_onsets: int = 5) -> dict:
        """Temporal dynamic: volume series, peaks, patient-zero and narrative onsets.

        freq: pandas offset ('D' daily, 'h' hourly, 'W' weekly).
        Returns the series (compact), the top peak periods, the earliest message
        overall, and — per top amplified account — the first time it was relayed
        (ignition order of the cascade).
        """
        df, col = self.df, self.col
        ts = col["timestamp"]
        series = df.set_index(ts).resample(freq).size()
        series = series[series > 0]
        peaks = series.sort_values(ascending=False).head(top)

        first = df.iloc[0]
        patient_zero = {
            "date": str(first[ts]),
            "author": first[col["author"]],
            "engagement": first[col["engagement"]],
            "text": str(first[col["text_raw"]])[:280],
        }

        # ignition order: earliest relay of each of the most-amplified accounts
        top_amp = df["_repost_handle"].dropna().value_counts().head(amplified_onsets).index
        onsets = {}
        for h in top_amp:
            sub = df[df["_repost_handle"] == h]
            r0 = sub.iloc[0]
            onsets[h] = {
                "first_relay": str(r0[ts]),
                "total_relays": int(len(sub)),
            }
        onsets = dict(sorted(onsets.items(), key=lambda kv: kv[1]["first_relay"]))

        return _to_native({
            "freq": freq,
            "n_periods": int(len(series)),
            "peak_period": str(peaks.index[0]),
            "peak_volume": int(peaks.iloc[0]),
            "top_peaks": {str(k): int(v) for k, v in peaks.items()},
            "series": {str(k): int(v) for k, v in series.items()},
            "patient_zero": patient_zero,
            "amplified_onsets": onsets,
        })

    def narratives(self, k: int = 6, samples: int = 3, min_df: int = 5,
                   max_features: int = 5000, ngram: int = 2, dedupe: bool = True,
                   random_state: int = 42) -> dict:
        """Unsupervised narrative discovery: TF-IDF + k-means over cleaned text.

        dedupe=True (default) clusters DISTINCT messages (each viral text counts
        once) so themes aren't swamped by retweet volume, then weights every
        cluster by its real message count. dedupe=False clusters the raw corpus
        (row-per-message).

        Returns, per cluster: message count & share, distinctive terms (top
        centroid weights), sentiment mix, and real sample tweets nearest the
        centroid so the LLM can name + ground each narrative.
        """
        df, col = self.df, self.col
        texts = self._clean_text
        nonempty = texts.str.len() > 0
        sub = df[nonempty]
        doc_text = texts[nonempty]

        if dedupe:
            # one representative row per distinct cleaned text (highest reach),
            # plus the volume weight and all source rows (for sentiment).
            groups = sub.groupby(doc_text.values, sort=False)
            reach_col = col.get("reach")
            reps, weights, src_index = [], [], []
            for _, g in groups:
                if reach_col in g:
                    rep = g.loc[g[reach_col].idxmax()]
                else:
                    rep = g.iloc[0]
                reps.append(rep.name)          # df index of representative row
                weights.append(len(g))
                src_index.append(g.index)      # all rows sharing this text
            rep_index = pd.Index(reps)
            docs = df.loc[rep_index, col["text_clean"]].fillna("").astype(str)
            weights = np.array(weights)
        else:
            rep_index = sub.index
            docs = doc_text
            weights = np.ones(len(docs), dtype=int)
            src_index = [pd.Index([i]) for i in rep_index]

        vec = TfidfVectorizer(stop_words=self.stopwords, min_df=min_df,
                              max_df=0.5, ngram_range=(1, ngram),
                              max_features=max_features)
        X = vec.fit_transform(docs)
        terms = np.array(vec.get_feature_names_out())

        km = KMeans(n_clusters=k, random_state=random_state, n_init=10)
        labels = km.fit_predict(X)

        # cosine sim to own centroid (X is L2-normalised by TfidfVectorizer)
        centroids = km.cluster_centers_
        sims = np.asarray(X @ centroids.T)

        total_msgs = int(weights.sum())
        has_sent = col.get("sentiment") in df
        clusters = []
        for c in range(k):
            members = np.where(labels == c)[0]     # positions within docs
            volume = int(weights[members].sum())   # real messages in cluster
            top_term_ids = centroids[c].argsort()[::-1][:12]
            top_terms = list(terms[top_term_ids])

            # samples = representative rows nearest the centroid (already distinct)
            order = members[np.argsort(-sims[members, c])][:samples]
            samp = []
            for pos in order:
                row = df.loc[rep_index[pos]]
                samp.append({
                    "author": row[col["author"]],
                    "engagement": row[col["engagement"]],
                    "date": str(row[col["timestamp"]]),
                    "relays": int(weights[pos]),
                    "text": str(row[col["text_raw"]])[:280],
                })

            entry = {
                "cluster": c,
                "n_messages": volume,
                "n_distinct_texts": int(len(members)),
                "share_pct": round(volume / total_msgs * 100, 1),
                "top_terms": top_terms,
                "samples": samp,
            }
            if has_sent and len(members):
                rows = pd.Index(np.concatenate([src_index[p].values for p in members]))
                sent = df.loc[rows, col["sentiment"]].value_counts()
                entry["sentiment_counts"] = sent.to_dict()
            clusters.append(entry)

        clusters.sort(key=lambda c: c["n_messages"], reverse=True)
        return _to_native({
            "k": k,
            "dedupe": dedupe,
            "n_messages": total_msgs,
            "n_distinct_texts": int(len(docs)),
            "vocab_size": int(len(terms)),
            "clusters": clusters,
        })

    def sample(self, contains: str | None = None, author: str | None = None,
               amplified: str | None = None, engagement: str | None = None,
               sentiment: str | None = None, date_from: str | None = None,
               date_to: str | None = None, n: int = 5,
               sort: str = "reach") -> dict:
        """Return real tweets matching a filter — grounding evidence, verbatim.

        Any combination of: contains (substring in cleaned text), author,
        amplified (relays of this handle), engagement, sentiment, date range.
        sort: 'reach' | 'recent' | 'oldest'.
        """
        df, col = self.df, self.col
        m = pd.Series(True, index=df.index)
        if contains:
            m &= self._clean_text.str.contains(re.escape(contains.lower()), na=False)
        if author:
            m &= df[col["author"]].astype(str).str.lower() == author.lower()
        if amplified:
            m &= df["_repost_handle"].astype(str).str.lower() == amplified.lower()
        if engagement:
            m &= df[col["engagement"]].astype(str).str.upper() == engagement.upper()
        if sentiment and col.get("sentiment") in df:
            m &= df[col["sentiment"]].astype(str).str.lower() == sentiment.lower()
        if date_from:
            m &= df[col["timestamp"]] >= pd.to_datetime(date_from)
        if date_to:
            m &= df[col["timestamp"]] <= pd.to_datetime(date_to)

        sub = df[m]
        total = int(len(sub))
        if sort == "reach" and col.get("reach") in df:
            sub = sub.sort_values(col["reach"], ascending=False)
        elif sort == "oldest":
            sub = sub.sort_values(col["timestamp"])
        else:  # recent
            sub = sub.sort_values(col["timestamp"], ascending=False)

        rows = []
        for _, row in sub.head(n).iterrows():
            item = {
                "author": row[col["author"]],
                "date": str(row[col["timestamp"]]),
                "engagement": row[col["engagement"]],
                "text": str(row[col["text_raw"]])[:280],
            }
            if col.get("reach") in df:
                item["reach"] = row[col["reach"]]
            if col.get("sentiment") in df:
                item["sentiment"] = row[col["sentiment"]]
            if pd.notna(row["_repost_handle"]):
                item["reposts"] = row["_repost_handle"]
            rows.append(item)
        return _to_native({"n_matching": total, "returned": len(rows), "rows": rows})

    def coordination(self, min_dup: int = 5, top: int = 15) -> dict:
        """Coordination signals: verbatim copy-paste + synchronised bursts.

        Returns the most-duplicated identical texts (verbatim relays of the same
        message), same-minute bursts of an identical text (near-simultaneous
        posting), the verbatim-duplication rate, and the concentration of
        activity (share of single-message vs high-frequency accounts).
        """
        df, col = self.df, self.col
        clean = self._clean_text

        # 1. verbatim duplication: identical normalised texts posted many times
        dup = clean[clean.str.len() > 0].value_counts()
        dup = dup[dup >= min_dup]
        dup_share = float(dup[dup >= 2].sum()) / len(df) * 100  # msgs in any dup group
        top_dup = [{"count": int(v), "text": str(k)[:160]}
                   for k, v in dup.head(top).items()]

        # 2. synchronised bursts: same identical text within the same minute
        minute = df[col["timestamp"]].dt.floor("min")
        burst = (df.assign(_min=minute, _txt=clean)
                   .groupby(["_min", "_txt"]).size())
        burst = burst[burst >= 3].sort_values(ascending=False).head(top)
        top_burst = [{"minute": str(m), "count": int(n), "text": str(t)[:120]}
                     for (m, t), n in burst.items()]

        # 3. activity concentration
        per_author = df[col["author"]].value_counts()

        return _to_native({
            "n_distinct_duplicated_texts": int(len(dup)),
            "verbatim_duplication_rate_pct": round(dup_share, 1),
            "top_duplicated_messages": top_dup,
            "top_synchronized_bursts": top_burst,
            "n_authors_1_msg": int((per_author == 1).sum()),
            "n_authors_ge_20_msg": int((per_author >= 20).sum()),
        })

    def semantique(self, freq: str = "D") -> dict:
        """Sentiment dynamics: overall mix + evolution over time.

        Returns overall sentiment counts/shares, a per-period breakdown, the most
        negative period, and whether negativity tracks the volume peak (negative
        share on the peak-volume period vs overall).
        """
        df, col = self.df, self.col
        if col.get("sentiment") not in df:
            return {"error": "no sentiment column configured"}
        ts, sent = col["timestamp"], col["sentiment"]

        counts = df[sent].value_counts()
        shares = {k: round(v / len(df) * 100, 1) for k, v in counts.items()}

        piv = (df.assign(_p=df[ts].dt.to_period(freq).dt.start_time)
                 .pivot_table(index="_p", columns=sent, values=col["id"],
                              aggfunc="count").fillna(0).astype(int))
        vol = piv.sum(axis=1)
        neg = piv["negative"] if "negative" in piv else pd.Series(0, index=piv.index)
        neg_share = (neg / vol.replace(0, np.nan) * 100).round(1)

        peak_period = vol.idxmax()
        most_neg_share_period = neg_share.idxmax()

        daily = {str(p.date() if hasattr(p, "date") else p):
                 {c: int(piv.loc[p, c]) for c in piv.columns}
                 for p in piv.index}

        return _to_native({
            "freq": freq,
            "sentiment_counts": counts.to_dict(),
            "sentiment_share_pct": shares,
            "peak_volume_period": str(peak_period),
            "negative_share_on_peak_pct": float(neg_share.get(peak_period, float("nan"))),
            "negative_share_overall_pct": round(float(neg.sum() / len(df) * 100), 1),
            "most_negative_period": str(most_neg_share_period),
            "most_negative_period_share_pct": float(neg_share.max()),
            "per_period": daily,
        })


# ------------------------------------------------------------------- CLI
def _main():
    p = argparse.ArgumentParser(description="Analyste deterministic tools")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("profile")

    t = sub.add_parser("timeline")
    t.add_argument("--freq", default="D")
    t.add_argument("--top", type=int, default=5)

    n = sub.add_parser("narratives")
    n.add_argument("--k", type=int, default=6)
    n.add_argument("--samples", type=int, default=3)

    s = sub.add_parser("sample")
    s.add_argument("--contains")
    s.add_argument("--author")
    s.add_argument("--amplified")
    s.add_argument("--engagement")
    s.add_argument("--sentiment")
    s.add_argument("--n", type=int, default=5)
    s.add_argument("--sort", default="reach")

    co = sub.add_parser("coordination")
    co.add_argument("--min-dup", type=int, default=5)
    co.add_argument("--top", type=int, default=15)

    se = sub.add_parser("semantique")
    se.add_argument("--freq", default="D")

    args = p.parse_args()
    c = Corpus()
    if args.cmd == "profile":
        res = c.profile()
    elif args.cmd == "timeline":
        res = c.timeline(freq=args.freq, top=args.top)
        res["series"] = f"<{len(res['series'])} periods omitted>"  # keep CLI compact
    elif args.cmd == "narratives":
        res = c.narratives(k=args.k, samples=args.samples)
    elif args.cmd == "sample":
        res = c.sample(contains=args.contains, author=args.author,
                       amplified=args.amplified, engagement=args.engagement,
                       sentiment=args.sentiment, n=args.n, sort=args.sort)
    elif args.cmd == "coordination":
        res = c.coordination(min_dup=args.min_dup, top=args.top)
    elif args.cmd == "semantique":
        res = c.semantique(freq=args.freq)
        res["per_period"] = f"<{len(res['per_period'])} periods omitted>"
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _main()
