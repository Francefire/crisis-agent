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
from itertools import combinations
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


# ----------------------------------------------------- coordination helpers
def _char_ngrams(text: str, n: int = 3) -> frozenset:
    """Set of character n-grams of a normalised text (for near-dup Jaccard)."""
    t = " ".join(str(text).split())
    if len(t) < n:
        return frozenset({t}) if t else frozenset()
    return frozenset(t[i:i + n] for i in range(len(t) - n + 1))


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


class _UnionFind:
    """Minimal union-find for clustering near-duplicate texts / accounts."""
    def __init__(self, items):
        self.parent = {x: x for x in items}

    def find(self, x):
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:      # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb

    def groups(self) -> dict:
        out = {}
        for x in self.parent:
            out.setdefault(self.find(x), []).append(x)
        return out


def _sync_stats(seconds: np.ndarray, delta: float) -> tuple:
    """For sorted unix-second timestamps of one text: (n, n_within_delta,
    median_inter_arrival). A copy is 'synchronised' if its nearest neighbour
    (previous or next copy) is within `delta` seconds."""
    n = len(seconds)
    if n < 2:
        return n, 0, None
    gaps = np.diff(seconds)
    prev_gap = np.concatenate(([np.inf], gaps))
    next_gap = np.concatenate((gaps, [np.inf]))
    nearest = np.minimum(prev_gap, next_gap)
    n_within = int((nearest <= delta).sum())
    return n, n_within, float(np.median(gaps))


def _sync_windows(seconds: np.ndarray, delta: float):
    """Greedily group sorted timestamps into windows where each member is within
    `delta` seconds of the window's first member. Yields index-arrays per window."""
    if len(seconds) == 0:
        return
    start = seconds[0]
    cur = [0]
    for i in range(1, len(seconds)):
        if seconds[i] - start <= delta:
            cur.append(i)
        else:
            yield cur
            start = seconds[i]
            cur = [i]
    yield cur


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
        # replied-to handle: same URL shape as repost_url (…/statuses/…)
        if self.col.get("reply_to") in df:
            df["_reply_handle"] = df[self.col["reply_to"]].map(handle)
        else:
            df["_reply_handle"] = None
        return df

    # ------------------------------------------------------------- helpers
    def _verified_mask(self) -> pd.Series:
        vals = [str(v).lower() for v in self.val.get("verified_true", ["true"])]
        return self.df[self.col["verified"]].astype(str).str.lower().isin(vals)

    @cached_property
    def _clean_text(self) -> pd.Series:
        return self.df[self.col["text_clean"]].fillna("").astype(str)

    def _num(self, role: str) -> pd.Series:
        """A configured numeric column coerced to float (missing → 0)."""
        c = self.col.get(role)
        if c not in self.df:
            return pd.Series(0.0, index=self.df.index)
        return pd.to_numeric(self.df[c], errors="coerce").fillna(0.0)

    @cached_property
    def _low_footprint_set(self) -> set:
        """Accounts matching the 'throwaway amplifier' proxy: single message,
        lifetime posts ≤ P25, followers ≤ median. Shared by coordination + breakdown."""
        df, col = self.df, self.col
        per_author = df[col["author"]].value_counts()
        acct = df.groupby(col["author"]).agg(
            followers=(col["followers"], "max"), posts=(col["posts"], "max"))
        followers = pd.to_numeric(acct["followers"], errors="coerce")
        posts = pd.to_numeric(acct["posts"], errors="coerce")
        single = per_author[per_author == 1].index
        mask = (acct.index.isin(single) & (posts <= posts.quantile(0.25)) &
                (followers <= followers.median()))
        return set(acct.index[mask])

    def _seg_dup_rate(self, idx: pd.Index, min_dup: int = 2) -> float:
        """Verbatim-duplication rate WITHIN a subset: share of its messages whose
        normalised text also occurs (≥min_dup times) inside the same subset."""
        if len(idx) == 0:
            return 0.0
        clean = self._clean_text.loc[idx]
        vc = clean[clean.str.len() > 0].value_counts()
        return round(float(vc[vc >= min_dup].sum()) / len(idx) * 100, 1)

    def _seg_sync_score(self, idx: pd.Index, delta: int, min_dup: int = 2) -> float:
        """Synchrony score WITHIN a subset: of its duplicated-text copies, the
        share posted within `delta` seconds of another copy in the same subset."""
        if len(idx) == 0:
            return 0.0
        ts = self.col["timestamp"]
        clean = self._clean_text.loc[idx]
        sec = self.df.loc[idx, ts].values.astype("datetime64[s]").astype("int64")
        d = pd.DataFrame({"_t": clean.values, "_s": sec})
        d = d[d["_t"].str.len() > 0]
        vc = d["_t"].value_counts()
        dup_set = set(vc[vc >= min_dup].index)
        d = d[d["_t"].isin(dup_set)]
        total = synced = 0
        for _, g in d.groupby("_t"):
            n, nw, _ = _sync_stats(np.sort(g["_s"].values), delta)
            total += n
            synced += nw
        return round(synced / total * 100, 1) if total else 0.0

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

    def _window(self, df: pd.DataFrame, window) -> pd.DataFrame:
        """Filter df to a (start, end) date window (ISO strings; either may be None)."""
        if not window:
            return df
        ts = self.col["timestamp"]
        lo, hi = window
        if lo:
            df = df[df[ts] >= pd.to_datetime(lo)]
        if hi:
            df = df[df[ts] <= pd.to_datetime(hi)]
        return df

    def _velocity(self, s: pd.Series, onset_frac: float = 0.10) -> dict:
        """Velocity metrics on a CONTINUOUS (zero-filled) time series.

        onset = first period reaching onset_frac × peak; from there we measure
        time-to-peak, per-period growth rate, doubling time, and (post-peak)
        half-life. All durations in hours (period length inferred from the grid).
        """
        s = s.sort_index()
        vals = s.values.astype(float)
        if len(s) < 2 or vals.max() <= 0:
            return {"error": "series too short for velocity"}
        period_hours = (s.index[1] - s.index[0]).total_seconds() / 3600.0
        peak_pos = int(vals.argmax())
        peak_val = float(vals[peak_pos])
        thr = onset_frac * peak_val
        onset_pos = int(np.argmax(vals >= thr))      # first period ≥ threshold
        onset_val = float(vals[onset_pos])
        n_ramp = peak_pos - onset_pos
        growth = ((peak_val / onset_val) ** (1.0 / n_ramp) - 1.0) \
            if n_ramp > 0 and onset_val > 0 else None
        if growth is not None and growth > 0:
            doubling_h = round(np.log(2) / np.log(1 + growth) * period_hours, 2)
        else:
            doubling_h = None
        post = vals[peak_pos:]
        below = np.where(post <= 0.5 * peak_val)[0]
        half_life_h = round(int(below[0]) * period_hours, 2) if len(below) else None
        return {
            "freq_used": "h",
            "onset_frac": onset_frac,
            "onset_period": str(s.index[onset_pos]),
            "onset_volume": int(onset_val),
            "peak_period": str(s.index[peak_pos]),
            "peak_volume": int(peak_val),
            "time_to_peak_hours": round(n_ramp * period_hours, 2),
            "growth_rate_per_hour_pct": round(growth * 100, 2) if growth is not None else None,
            "doubling_time_hours": doubling_h,
            "half_life_hours": half_life_h,
            "core_hours_above_50pct": int((vals >= 0.5 * peak_val).sum()),
        }

    def timeline(self, freq: str = "D", top: int = 5, amplified_onsets: int = 5,
                 window=None, weight: str = "count", velocity: bool = False) -> dict:
        """Temporal dynamic: volume series, peaks, patient-zero and narrative onsets.

        freq: pandas offset ('D' daily, 'h' hourly, 'W' weekly).
        window: optional (start, end) ISO dates to zoom in before resampling.
        weight: 'count' (messages) | 'reach' | 'impressions' — what `series` sums.
        velocity: if True, attach a `velocity` block (time-to-peak, growth,
        doubling time, half-life) computed on an HOURLY volume series.

        Returns the series (compact), the top peak periods, the earliest message
        in the window, per-top-amplified-account first-relay time (ignition
        order), and — when a reach column is configured — a `reach` block
        (audience curve + whether audience peaks before/after raw volume).
        """
        df, col = self.df, self.col
        ts = col["timestamp"]
        df = self._window(df, window)

        # volume (count) series drives peaks/velocity; identical to legacy default
        count_series = df.set_index(ts).resample(freq).size()
        count_series = count_series[count_series > 0]

        if weight in ("reach", "impressions") and col.get(weight) in df:
            wcol = col[weight]
            series = df.set_index(ts)[wcol].fillna(0).resample(freq).sum()
            series = series[series > 0]
        else:
            weight, series = "count", count_series
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

        out = {
            "freq": freq,
            "weight": weight,
            "window": list(window) if window else None,
            "n_periods": int(len(series)),
            "peak_period": str(peaks.index[0]),
            "peak_volume": int(peaks.iloc[0]),
            "top_peaks": {str(k): int(v) for k, v in peaks.items()},
            "series": {str(k): int(v) for k, v in series.items()},
            "patient_zero": patient_zero,
            "amplified_onsets": onsets,
        }

        # reach block: audience curve vs raw-volume curve (lead/lag), always on
        # a shared continuous grid so the two peaks are directly comparable.
        reach_col = col.get("reach")
        if reach_col in df:
            grid_vol = df.set_index(ts).resample(freq).size()
            grid_reach = df.set_index(ts)[reach_col].fillna(0).resample(freq).sum()
            if grid_reach.max() > 0:
                r_series = grid_reach[grid_reach > 0]
                lead = int(int(grid_reach.values.argmax()) - int(grid_vol.values.argmax()))
                out["reach"] = {
                    "peak_reach_period": str(grid_reach.idxmax()),
                    "peak_reach": int(grid_reach.max()),
                    # >0 audience peaks AFTER volume ; <0 audience leads volume
                    "reach_vs_volume_lead_periods": lead,
                    "reach_series": {str(k): int(v) for k, v in r_series.items()},
                }

        if velocity:
            hourly = df.set_index(ts).resample("h").size()
            out["velocity"] = self._velocity(hourly)

        return _to_native(out)

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

    def narrative_timelines(self, k: int = 6, freq: str = "D", window=None,
                            dedupe: bool = True, min_df: int = 5,
                            max_features: int = 5000, ngram: int = 2,
                            random_state: int = 42) -> dict:
        """Per-narrative propagation: WHEN does each framing peak, and who leads?

        Reuses the same TF-IDF + k-means as `narratives()` to label every
        message, then resamples message volume per cluster over time. Reveals
        whether framings peak together or lead/lag one another (`lead_lag` =
        clusters ordered by peak time). freq/window as in `timeline()`.
        """
        df, col = self.df, self.col
        ts = col["timestamp"]
        dfw = self._window(df, window)

        texts = self._clean_text.loc[dfw.index]
        nonempty = texts.str.len() > 0
        sub = dfw[nonempty]
        doc_text = texts[nonempty]

        if dedupe:
            groups = sub.groupby(doc_text.values, sort=False)
            reach_col = col.get("reach")
            reps, src_index = [], []
            for _, g in groups:
                rep = g.loc[g[reach_col].idxmax()] if reach_col in g else g.iloc[0]
                reps.append(rep.name)
                src_index.append(g.index)
            docs = df.loc[pd.Index(reps), col["text_clean"]].fillna("").astype(str)
        else:
            src_index = [pd.Index([i]) for i in sub.index]
            docs = doc_text

        vec = TfidfVectorizer(stop_words=self.stopwords, min_df=min_df,
                              max_df=0.5, ngram_range=(1, ngram),
                              max_features=max_features)
        X = vec.fit_transform(docs)
        terms = np.array(vec.get_feature_names_out())
        km = KMeans(n_clusters=k, random_state=random_state, n_init=10)
        labels = km.fit_predict(X)
        centroids = km.cluster_centers_

        # label every source row with its cluster
        row_label = pd.Series(index=sub.index, dtype=float)
        for pos, idxs in enumerate(src_index):
            row_label.loc[idxs] = labels[pos]
        lab = row_label.dropna().astype(int)
        total = int(len(lab))

        clusters = []
        for c in range(k):
            idx_c = lab.index[lab.values == c]
            top_terms = list(terms[centroids[c].argsort()[::-1][:8]])
            s = df.loc[idx_c].set_index(ts).resample(freq).size()
            s = s[s > 0]
            clusters.append({
                "cluster": int(c),
                "top_terms": top_terms,
                "n_messages": int(len(idx_c)),
                "share_pct": round(len(idx_c) / total * 100, 1) if total else 0.0,
                "peak_period": str(s.idxmax()) if len(s) else None,
                "peak_volume": int(s.max()) if len(s) else 0,
                "series": {str(k_): int(v_) for k_, v_ in s.items()},
            })
        clusters.sort(key=lambda x: x["n_messages"], reverse=True)

        lead_lag = [{"cluster": c["cluster"], "top_terms": c["top_terms"][:4],
                     "peak_period": c["peak_period"]}
                    for c in sorted((c for c in clusters if c["peak_period"]),
                                    key=lambda x: x["peak_period"])]

        return _to_native({
            "k": k,
            "freq": freq,
            "window": list(window) if window else None,
            "n_messages": total,
            "clusters": clusters,
            "lead_lag": lead_lag,
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

    def coordination(self, min_dup: int = 5, top: int = 15,
                     delta_seconds: int = 60, sim_threshold: float = 0.8,
                     ngram: int = 3, max_near_dup_texts: int = 500) -> dict:
        """Coordination signals: verbatim copy-paste + synchronised bursts,
        enriched with sub-minute synchrony, near-duplicate detection, and
        account-behaviour proxies.

        Baseline keys (unchanged): the most-duplicated identical texts, the
        same-minute bursts, the verbatim-duplication rate and activity
        concentration (single-message vs high-frequency accounts).

        Enriched blocks (additive):
        - `synchrony` (A): using a Δ=`delta_seconds` window, inter-arrival stats
          of identical texts, a coordination score (share of copies landing
          within Δ of another copy), the most-synchronised texts, and the daily
          burst-size-over-time series.
        - `near_duplicates` (B): templated variants beyond exact match, grouped
          by char-`ngram` Jaccard ≥ `sim_threshold`.
        - `account_behaviour` (D): following/followers patterns, low-footprint
          "throwaway" amplifiers, and the verified share among duplicators —
          PROXIES only (no account-creation date exists in the data).

        Neutral framing: these are signals *compatible with* coordinated
        amplification, not proof of automation or intent.
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

        # 4. engagement-aware split — the rate above counts RETWEETS, whose text
        #    is identical BY CONSTRUCTION (native amplification, not copying).
        #    True copy-paste = identical text authored as ORIGINAL/QUOTE.
        eng = df[col["engagement"]].astype(str).str.upper()
        rt_val = str(self.val["engagement_retweet"]).upper()
        dup_rows = clean.isin(set(dup.index))
        n_dup_rows = int(dup_rows.sum())
        rt_share_of_dup = (round(float((eng[dup_rows] == rt_val).mean()) * 100, 1)
                           if n_dup_rows else 0.0)
        authored_idx = df.index[~eng.isin([rt_val, "REPLY"])]   # ORIGINAL + QUOTE
        copy_paste_rate = self._seg_dup_rate(authored_idx, min_dup=2)

        out = {
            "n_distinct_duplicated_texts": int(len(dup)),
            "verbatim_duplication_rate_pct": round(dup_share, 1),
            # ↑ legacy key: retweet-dominated, keep for continuity. Read the two
            #   keys below instead for an honest copy-paste vs amplification split.
            "retweet_share_of_duplicated_pct": rt_share_of_dup,
            "copy_paste_rate_pct": copy_paste_rate,
            "copy_paste_definition": ("identical normalised text posted ≥2× as an "
                "ORIGINAL or QUOTE tweet (excludes RETWEETs, whose text is identical "
                "by construction, and REPLYs). This is the true 'copier-coller' rate."),
            "top_duplicated_messages": top_dup,
            "top_synchronized_bursts": top_burst,
            "n_authors_1_msg": int((per_author == 1).sum()),
            "n_authors_ge_20_msg": int((per_author >= 20).sum()),
        }
        out["synchrony"] = self._synchrony(dup, clean, delta_seconds, top)
        out["near_duplicates"] = self._near_duplicates(
            dup, sim_threshold, ngram, max_near_dup_texts, top)
        out["account_behaviour"] = self._account_behaviour(dup, clean)
        return _to_native(out)

    # ----------------------------------------------------- coordination: A
    def _synchrony(self, dup: pd.Series, clean: pd.Series,
                   delta: int, top: int) -> dict:
        """Δ-window synchrony over the duplicated texts (count ≥ min_dup)."""
        ts = self.col["timestamp"]
        # resolution-safe unix seconds (pandas 3.0 datetimes may be µs, not ns)
        sec_all = self.df[ts].values.astype("datetime64[s]").astype("int64")
        dup_set = set(dup.index)
        mask = clean.isin(dup_set)
        sub = pd.DataFrame({"_txt": clean[mask], "_sec": sec_all[mask.values]})

        total = synced = 0
        null_exp = 0.0   # expected copies-within-Δ if each text's copies were
                         # spread UNIFORMLY over its own lifespan (a baseline: a
                         # viral tweet's retweets naturally cluster somewhat)
        per_text = []
        # daily burst-size-over-time (largest Δ-window per day + #windows ≥3)
        day = self.df[ts].dt.floor("D")
        day_max, day_bursts = {}, {}
        for txt, grp in sub.groupby("_txt"):
            s = np.sort(grp["_sec"].values)
            n, n_within, med = _sync_stats(s, delta)
            total += n
            synced += n_within
            if n >= 2:
                span = float(s[-1] - s[0])   # lifespan of this text, seconds
                # P(a point has a neighbour within Δ) under uniform placement of
                # n points on [0, span] ≈ 1 - (1 - 2Δ/span)^(n-1)
                null_exp += (1.0 - max(0.0, 1.0 - 2 * delta / span) ** (n - 1)) * n \
                    if span > 0 else float(n)
            per_text.append((txt, n, n_within, med))
            for win in _sync_windows(s, delta):
                if len(win) >= 2:
                    d = str(pd.Timestamp(int(s[win[0]]), unit="s").floor("D").date())
                    day_max[d] = max(day_max.get(d, 0), len(win))
                    if len(win) >= 3:
                        day_bursts[d] = day_bursts.get(d, 0) + 1

        per_text.sort(key=lambda r: (r[2] / r[1] if r[1] else 0, r[1]), reverse=True)
        top_sync = [{
            "text": str(t)[:120], "copies": int(n),
            "within_delta_pct": round(nw / n * 100, 1) if n else 0.0,
            "median_inter_arrival_seconds": round(med, 1) if med is not None else None,
        } for t, n, nw, med in per_text[:top]]

        series = {d: {"max_burst": day_max[d], "n_bursts_ge3": day_bursts.get(d, 0)}
                  for d in sorted(day_max)}
        obs_pct = synced / total * 100 if total else 0.0
        null_pct = null_exp / total * 100 if total else 0.0
        return {
            "delta_seconds": delta,
            "coordination_score_pct": round(obs_pct, 1),
            "copies_considered": int(total),
            "copies_within_delta": int(synced),
            # baseline: what the score would be if copies were spread uniformly
            # over each text's lifespan. lift = observed / expected. >1 means the
            # retweeting is burstier than the tweets' own lifespan would predict
            # (a signal *compatible with* coordinated amplification — not proof,
            # since organic retweeting is also bursty).
            "expected_within_delta_uniform_pct": round(null_pct, 1),
            "synchrony_lift_vs_uniform": round(obs_pct / null_pct, 1) if null_pct else None,
            "top_synchronized_texts": top_sync,
            "burst_size_over_time": series,
        }

    # ----------------------------------------------------- coordination: B
    def _near_duplicates(self, dup: pd.Series, sim: float, ngram: int,
                         max_texts: int, top: int) -> dict:
        """Cluster the most-duplicated distinct texts by char-ngram Jaccard,
        merging templated variants that differ only slightly."""
        texts = list(dup.head(max_texts).index)
        counts = {t: int(dup[t]) for t in texts}
        grams = {t: _char_ngrams(t, ngram) for t in texts}
        uf = _UnionFind(texts)
        for i in range(len(texts)):
            gi = grams[texts[i]]
            for j in range(i + 1, len(texts)):
                if _jaccard(gi, grams[texts[j]]) >= sim:
                    uf.union(texts[i], texts[j])

        groups = []
        for members in uf.groups().values():
            if len(members) < 2:                     # only merged (multi-variant)
                continue
            members.sort(key=lambda t: counts[t], reverse=True)
            groups.append({
                "n_variants": len(members),
                "total_count": sum(counts[m] for m in members),
                "representative": str(members[0])[:160],
                "variant_examples": [str(m)[:120] for m in members[1:4]],
            })
        groups.sort(key=lambda g: g["total_count"], reverse=True)
        return {
            "sim_threshold": sim,
            "ngram": ngram,
            "candidate_texts": len(texts),
            "n_near_dup_groups": len(groups),
            "n_texts_merged": sum(g["n_variants"] for g in groups),
            "messages_in_near_dup_groups": sum(g["total_count"] for g in groups),
            "top_near_dup_groups": groups[:top],
        }

    # ----------------------------------------------------- coordination: D
    def _account_behaviour(self, dup: pd.Series, clean: pd.Series) -> dict:
        """Account-behaviour PROXIES (no creation date exists in the data)."""
        df, col = self.df, self.col
        author = col["author"]
        per_author = df[author].value_counts()
        n_authors = int(per_author.size)

        # one row per account (account-level attributes are constant per author)
        acct = df.groupby(author).agg(
            followers=(col["followers"], "max"),
            following=(col["following"], "max"),
            posts=(col["posts"], "max"),
        )
        followers = pd.to_numeric(acct["followers"], errors="coerce")
        following = pd.to_numeric(acct["following"], errors="coerce")
        posts = pd.to_numeric(acct["posts"], errors="coerce")

        single_msg = per_author[per_author == 1].index
        posts_p25 = float(posts.quantile(0.25))
        followers_med = float(followers.median())
        # low-footprint amplifier proxy: single-message account, low lifetime
        # post count (≤ P25) and below-median followers → "throwaway" pattern
        low_footprint = acct.index.isin(single_msg) & \
            (posts <= posts_p25) & (followers <= followers_med)
        n_low_footprint = int(low_footprint.sum())

        # verified & behaviour among accounts that posted a duplicated text
        dup_set = set(dup.index)
        dup_authors = df.loc[clean.isin(dup_set), author].unique()
        vmask = self._verified_mask()
        dup_msg_mask = clean.isin(dup_set)
        verified_share_dup = float(vmask[dup_msg_mask].mean()) * 100

        return {
            "n_accounts": n_authors,
            "single_message_share_pct": round(len(single_msg) / n_authors * 100, 1),
            "median_followers": round(followers_med, 1),
            "median_following": round(float(following.median()), 1),
            "median_posts": round(float(posts.median()), 1),
            "following_over_followers_share_pct": round(
                float((following > followers).mean()) * 100, 1),
            "low_footprint_amplifiers": n_low_footprint,
            "low_footprint_amplifiers_pct": round(n_low_footprint / n_authors * 100, 1),
            "low_footprint_definition": (
                "compte à message unique, X Posts ≤ P25 et abonnés ≤ médiane "
                "— PROXY (aucune date de création disponible)"),
            "n_accounts_posting_duplicated_text": int(len(dup_authors)),
            "verified_share_among_duplicators_pct": round(verified_share_dup, 1),
        }

    # ----------------------------------------------------- coordination: C
    def coordination_network(self, min_dup: int = 5, delta_seconds: int = 60,
                             min_edge_weight: int = 1, top_clusters: int = 10,
                             sample_accounts: int = 8) -> dict:
        """Co-activity network of accounts that post the SAME text near-simultaneously.

        An edge links two accounts each time they post an identical (verbatim,
        count ≥ `min_dup`) text within the same `delta_seconds` window; the edge
        weight is how many such synchronised windows they share. Edges with
        weight ≥ `min_edge_weight` are kept (default 1 = co-appeared in ≥1
        synchronised burst; raise it to keep only accounts that co-burst
        repeatedly), then weighted Louvain community detection (networkx)
        partitions the graph into coordinated clusters.

        Reports graph size, connected components and the largest clusters with
        their verified / single-message share and dominant shared texts. This is
        a signal *compatible with* coordinated amplification — not proof of
        automation or intent. Requires networkx.
        """
        import networkx as nx
        from networkx.algorithms.community import louvain_communities

        df, col = self.df, self.col
        author, ts = col["author"], col["timestamp"]
        clean = self._clean_text

        dup = clean[clean.str.len() > 0].value_counts()
        dup = dup[dup >= min_dup]
        dup_set = set(dup.index)

        sec = df[ts].values.astype("datetime64[s]").astype("int64")
        mask = clean.isin(dup_set).values
        sub = pd.DataFrame({"_txt": clean.values[mask],
                            "_acct": df[author].values[mask],
                            "_sec": sec[mask]})

        # edge weight = # of synchronised windows two accounts co-appear in
        edges: dict = {}
        for _, grp in sub.groupby("_txt"):
            g = grp.sort_values("_sec")
            secs = g["_sec"].values
            accts = g["_acct"].values
            for win in _sync_windows(secs, delta_seconds):
                members = sorted(set(accts[win]))
                if len(members) < 2:
                    continue
                for a, b in combinations(members, 2):
                    edges[(a, b)] = edges.get((a, b), 0) + 1

        G = nx.Graph()
        for (a, b), w in edges.items():
            if w >= min_edge_weight:
                G.add_edge(a, b, weight=w)

        if G.number_of_nodes() == 0:
            return _to_native({
                "delta_seconds": delta_seconds, "min_edge_weight": min_edge_weight,
                "n_nodes": 0, "n_edges": 0, "n_components": 0, "clusters": [],
                "note": "no account pair co-posted an identical text within Δ at "
                        "least min_edge_weight times",
            })

        components = list(nx.connected_components(G))
        communities = louvain_communities(G, weight="weight", seed=42)

        vmask = self._verified_mask()
        acct_verified = df.groupby(author).apply(
            lambda d: bool(vmask.loc[d.index].any()), include_groups=False)
        per_author = df[author].value_counts()
        # map each account to the duplicated texts it posted (for dominant text)
        acct_txt = sub.groupby("_acct")["_txt"].apply(list)

        clusters = []
        for comm in sorted(communities, key=len, reverse=True):
            if len(comm) < 2:
                continue
            members = list(comm)
            sub_edges = G.subgraph(members).number_of_edges()
            txt_counter: dict = {}
            for m in members:
                for t in acct_txt.get(m, []):
                    txt_counter[t] = txt_counter.get(t, 0) + 1
            dom = sorted(txt_counter.items(), key=lambda kv: kv[1], reverse=True)
            n_verified = sum(bool(acct_verified.get(m, False)) for m in members)
            n_single = sum(int(per_author.get(m, 0) == 1) for m in members)
            clusters.append({
                "size": len(members),
                "internal_edges": int(sub_edges),
                "verified_share_pct": round(n_verified / len(members) * 100, 1),
                "single_message_share_pct": round(n_single / len(members) * 100, 1),
                "dominant_shared_texts": [{"count": int(c), "text": str(t)[:120]}
                                          for t, c in dom[:3]],
                "sample_accounts": [str(m) for m in members[:sample_accounts]],
            })
        clusters.sort(key=lambda c: c["size"], reverse=True)

        comp_sizes = sorted((len(c) for c in components), reverse=True)
        return _to_native({
            "delta_seconds": delta_seconds,
            "min_edge_weight": min_edge_weight,
            "n_nodes": G.number_of_nodes(),
            "n_edges": G.number_of_edges(),
            "n_components": len(components),
            "largest_component_size": comp_sizes[0] if comp_sizes else 0,
            "n_communities": len([c for c in communities if len(c) >= 2]),
            "n_accounts_in_clusters": sum(c["size"] for c in clusters),
            "top_clusters": clusters[:top_clusters],
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

    # ---------------------------------------------------------------- breakdown
    _BREAKDOWN_METRICS = ("volume", "share_pct", "dup_rate", "synchrony_score",
                          "verified_share", "low_footprint_share", "mean_reach",
                          "mean_organic_engagement")

    def _segments(self, by: str, min_seg: int = 1):
        """Yield (segment_label, row_index) for a grouping dimension `by`:
        sentiment | engagement | verified | day | hour."""
        df, col = self.df, self.col
        if by == "verified":
            v = self._verified_mask()
            grouper = v.map({True: "verified", False: "non_verifie"})
        elif by in ("day", "hour"):
            grouper = df[col["timestamp"]].dt.floor("D" if by == "day" else "h").astype(str)
        else:
            key = col.get(by, by)
            if key not in df:
                raise ValueError(f"dimension inconnue : {by}")
            grouper = df[key].astype(str)
        for label, idx in df.groupby(grouper).groups.items():
            if len(idx) >= min_seg:
                yield str(label), idx

    def breakdown(self, by: str, metrics: list | None = None, min_dup: int = 2,
                  delta_seconds: int = 60, min_seg: int = 30, top_segments: int = 30) -> dict:
        """Cross-tabulate metrics by a dimension — the composability primitive.

        `by`: sentiment | engagement | verified | day | hour.
        `metrics` (subset of _BREAKDOWN_METRICS): volume, share_pct, dup_rate
        (verbatim-copy rate WITHIN the segment), synchrony_score (share of the
        segment's copies posted <Δ from another), verified_share,
        low_footprint_share (throwaway-amplifier proxy), mean_reach,
        mean_organic_engagement (likes+comments+shares per message).

        Returns per-segment metrics PLUS a `gaps` block (min/max/spread and which
        segment holds each extreme) so a claim like "positives are copied more
        than negatives" is grounded in the spread, not inference.
        """
        valid_by = ("sentiment", "engagement", "verified", "day", "hour")
        if by not in valid_by:
            return {"error": f"dimension inconnue : '{by}'",
                    "valid_dimensions": list(valid_by)}
        metrics = metrics or list(self._BREAKDOWN_METRICS)
        good = [m for m in metrics if m in self._BREAKDOWN_METRICS]
        ignored = [m for m in metrics if m not in self._BREAKDOWN_METRICS]
        if not good:                       # nothing usable → tell the LLM the menu
            return {"error": f"métriques inconnues : {ignored}",
                    "valid_metrics": list(self._BREAKDOWN_METRICS)}
        metrics = good
        n_total = len(self.df)
        low_set = self._low_footprint_set
        organic = self._num("likes") + self._num("comments") + self._num("shares")
        reach = self._num("reach")
        author = self.col["author"]

        segs = {}
        for label, idx in self._segments(by, min_seg):
            m = {}
            if "volume" in metrics:
                m["volume"] = int(len(idx))
            if "share_pct" in metrics:
                m["share_pct"] = round(len(idx) / n_total * 100, 1)
            if "dup_rate" in metrics:
                m["dup_rate"] = self._seg_dup_rate(idx, min_dup)
            if "synchrony_score" in metrics:
                m["synchrony_score"] = self._seg_sync_score(idx, delta_seconds, max(min_dup, 2))
            if "verified_share" in metrics:
                m["verified_share"] = round(float(self._verified_mask().loc[idx].mean()) * 100, 1)
            if "low_footprint_share" in metrics:
                in_low = self.df.loc[idx, author].isin(low_set)
                m["low_footprint_share"] = round(float(in_low.mean()) * 100, 1)
            if "mean_reach" in metrics:
                m["mean_reach"] = round(float(reach.loc[idx].mean()), 1)
            if "mean_organic_engagement" in metrics:
                m["mean_organic_engagement"] = round(float(organic.loc[idx].mean()), 2)
            segs[label] = m

        # keep the largest segments if a high-cardinality dimension (day/hour)
        if len(segs) > top_segments:
            order = sorted(segs, key=lambda k: segs[k].get("volume", 0), reverse=True)
            segs = {k: segs[k] for k in order[:top_segments]}

        gaps = {}
        for met in metrics:
            if met in ("volume", "share_pct"):
                continue
            vals = {k: v[met] for k, v in segs.items() if met in v}
            if len(vals) >= 2:
                hi, lo = max(vals, key=vals.get), min(vals, key=vals.get)
                gaps[met] = {"max_segment": hi, "max": vals[hi],
                             "min_segment": lo, "min": vals[lo],
                             "spread": round(vals[hi] - vals[lo], 2)}
        out = {"by": by, "n_segments": len(segs), "segments": segs, "gaps": gaps}
        if ignored:
            out["ignored_metrics"] = ignored
        return _to_native(out)

    # ------------------------------------------------------------------- actor
    def actor(self, handle: str, samples: int = 5) -> dict:
        """Multi-source dossier on ONE account — triangulates 'is this a driver?'.

        Combines the account's own activity (posts, engagement/sentiment mix,
        follower/following/posts/verified proxies, who it replies to, who it
        amplifies) with what happens AROUND it (times its content was reposted +
        distinct relayers, replies it received + their negativity). Useful to
        corroborate a top-list name across independent angles.
        """
        df, col = self.df, self.col
        h = str(handle).lstrip("@")
        low = h.lower()
        as_author = df[df[col["author"]].astype(str).str.lower() == low]
        amplified = df[df["_repost_handle"].astype(str).str.lower() == low]
        replies_recv = df[df["_reply_handle"].astype(str).str.lower() == low]

        out = {"handle": h,
               "in_corpus_as_author": bool(len(as_author)),
               "n_messages_authored": int(len(as_author)),
               "n_times_content_reposted": int(len(amplified)),
               "n_distinct_relayers": int(amplified[col["author"]].nunique()),
               "n_replies_received": int(len(replies_recv))}
        if len(replies_recv) and col.get("sentiment") in df:
            neg = (replies_recv[col["sentiment"]].astype(str).str.lower() == "negative").mean()
            out["replies_received_negative_share_pct"] = round(float(neg) * 100, 1)

        if len(as_author):
            a = as_author
            def nummax(role):
                return float(pd.to_numeric(a[col[role]], errors="coerce").max())
            out["profile"] = {
                "first_seen": str(a[col["timestamp"]].min()),
                "last_seen": str(a[col["timestamp"]].max()),
                "followers": nummax("followers"), "following": nummax("following"),
                "posts": nummax("posts"),
                "verified": bool(self._verified_mask().loc[a.index].any()),
                "total_reach": int(pd.to_numeric(a[col["reach"]], errors="coerce").fillna(0).sum()),
                "engagement_mix": a[col["engagement"]].value_counts().to_dict(),
            }
            if col.get("sentiment") in df:
                out["profile"]["sentiment_mix"] = a[col["sentiment"]].value_counts().to_dict()
            replies_to = a["_reply_handle"].dropna().value_counts().head(5)
            amplifies = a["_repost_handle"].dropna().value_counts().head(5)
            out["profile"]["top_replies_to"] = replies_to.to_dict()
            out["profile"]["top_amplifies"] = amplifies.to_dict()
            top = a.sort_values(col["reach"], ascending=False).head(samples)
            out["profile"]["top_messages"] = [{
                "date": str(r[col["timestamp"]]), "engagement": r[col["engagement"]],
                "reach": int(pd.to_numeric(pd.Series([r[col["reach"]]]), errors="coerce").fillna(0)[0]),
                "text": str(r[col["text_raw"]])[:200]} for _, r in top.iterrows()]
        return _to_native(out)

    # ------------------------------------------------------- engagement_quality
    def engagement_quality(self, min_reach: int = 1, min_dup: int = 5,
                           top: int = 15) -> dict:
        """Independent authenticity signal: organic engagement vs reach.

        Cross-checks the copy/synchrony coordination signals from a SEPARATE
        source. Reports the organic-engagement-per-reach ratio overall and by
        engagement type, contrasts duplicated vs unique texts, and lists
        high-reach / near-zero-organic-engagement anomalies (amplified but not
        organically engaged — compatible with mechanical amplification).
        """
        df, col = self.df, self.col
        likes, comments, shares = self._num("likes"), self._num("comments"), self._num("shares")
        organic = likes + comments + shares
        reach = self._num("reach")
        m = reach >= min_reach

        def ratio(mask):
            r = reach[mask]
            return round(float((organic[mask].sum()) / r.sum()), 5) if r.sum() else None

        clean = self._clean_text
        vc = clean[clean.str.len() > 0].value_counts()
        dup_set = set(vc[vc >= min_dup].index)
        is_dup = clean.isin(dup_set)

        by_eng = {str(k): ratio(m & (df[col["engagement"]] == k))
                  for k in df[col["engagement"]].unique()}

        # anomalies: among high-reach msgs (≥P90 reach), the lowest organic/reach
        thr = float(reach[m].quantile(0.90)) if m.any() else 0.0
        hi = df[m & (reach >= thr)].copy()
        hi["_ratio"] = (organic[hi.index] / reach[hi.index]).values
        hi = hi.sort_values("_ratio").head(top)
        anomalies = [{
            "author": r[col["author"]], "engagement": r[col["engagement"]],
            "reach": int(reach[i]), "organic_engagement": int(organic[i]),
            "organic_per_reach": round(float(hi.loc[i, "_ratio"]), 6),
            "text": str(r[col["text_raw"]])[:160]} for i, r in hi.iterrows()]

        return _to_native({
            "min_reach": min_reach,
            "organic_per_reach_overall": ratio(m),
            "organic_per_reach_by_engagement": by_eng,
            "organic_per_reach_duplicated": ratio(m & is_dup),
            "organic_per_reach_unique": ratio(m & ~is_dup),
            "median_reach": round(float(reach[m].median()), 1) if m.any() else 0.0,
            "high_reach_threshold_p90": round(thr, 1),
            "n_high_reach_zero_organic": int((m & (reach >= thr) & (organic == 0)).sum()),
            "top_amplified_low_engagement": anomalies,
        })

    # ------------------------------------------------------------ reply_network
    def reply_network(self, top: int = 15) -> dict:
        """Conversation structure from `X Reply to` (independent of the repost
        graph): who is being replied-to/targeted, and how negative those replies
        are. Complements the amplification view with a 'who is attacked' view.
        """
        df, col = self.df, self.col
        rmask = df["_reply_handle"].notna()
        n_replies = int(rmask.sum())
        has_sent = col.get("sentiment") in df
        targets = df.loc[rmask, "_reply_handle"].value_counts().head(top)
        rows = []
        for h, n in targets.items():
            sub = df[df["_reply_handle"] == h]
            item = {"handle": str(h), "n_replies_received": int(n)}
            if has_sent:
                neg = (sub[col["sentiment"]].astype(str).str.lower() == "negative").mean()
                item["negative_share_pct"] = round(float(neg) * 100, 1)
            rows.append(item)
        return _to_native({
            "n_replies": n_replies,
            "reply_share_pct": round(n_replies / len(df) * 100, 1),
            "n_distinct_reply_targets": int(df.loc[rmask, "_reply_handle"].nunique()),
            "top_reply_targets": rows,
        })


# ------------------------------------------------------------------- CLI
def _main():
    p = argparse.ArgumentParser(description="Analyste deterministic tools")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("profile")

    t = sub.add_parser("timeline")
    t.add_argument("--freq", default="D")
    t.add_argument("--top", type=int, default=5)
    t.add_argument("--window", nargs=2, metavar=("FROM", "TO"), default=None)
    t.add_argument("--weight", default="count", choices=["count", "reach", "impressions"])
    t.add_argument("--velocity", action="store_true")

    n = sub.add_parser("narratives")
    n.add_argument("--k", type=int, default=6)
    n.add_argument("--samples", type=int, default=3)

    nt = sub.add_parser("narrative-timelines")
    nt.add_argument("--k", type=int, default=6)
    nt.add_argument("--freq", default="D")
    nt.add_argument("--window", nargs=2, metavar=("FROM", "TO"), default=None)

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
    co.add_argument("--delta-seconds", type=int, default=60)
    co.add_argument("--sim-threshold", type=float, default=0.8)

    cn = sub.add_parser("coordination-network")
    cn.add_argument("--min-dup", type=int, default=5)
    cn.add_argument("--delta-seconds", type=int, default=60)
    cn.add_argument("--min-edge-weight", type=int, default=1)
    cn.add_argument("--top-clusters", type=int, default=10)

    se = sub.add_parser("semantique")
    se.add_argument("--freq", default="D")

    bd = sub.add_parser("breakdown")
    bd.add_argument("--by", required=True,
                    choices=["sentiment", "engagement", "verified", "day", "hour"])
    bd.add_argument("--metrics", nargs="*", default=None)

    ac = sub.add_parser("actor")
    ac.add_argument("handle")
    ac.add_argument("--samples", type=int, default=5)

    sub.add_parser("engagement-quality")

    sub.add_parser("reply-network")

    args = p.parse_args()
    c = Corpus()
    if args.cmd == "profile":
        res = c.profile()
    elif args.cmd == "timeline":
        res = c.timeline(freq=args.freq, top=args.top, window=args.window,
                         weight=args.weight, velocity=args.velocity)
        res["series"] = f"<{len(res['series'])} periods omitted>"  # keep CLI compact
        if "reach" in res:
            res["reach"]["reach_series"] = \
                f"<{len(res['reach']['reach_series'])} periods omitted>"
    elif args.cmd == "narratives":
        res = c.narratives(k=args.k, samples=args.samples)
    elif args.cmd == "narrative-timelines":
        res = c.narrative_timelines(k=args.k, freq=args.freq, window=args.window)
        for cl in res["clusters"]:
            cl["series"] = f"<{len(cl['series'])} periods omitted>"
    elif args.cmd == "sample":
        res = c.sample(contains=args.contains, author=args.author,
                       amplified=args.amplified, engagement=args.engagement,
                       sentiment=args.sentiment, n=args.n, sort=args.sort)
    elif args.cmd == "coordination":
        res = c.coordination(min_dup=args.min_dup, top=args.top,
                             delta_seconds=args.delta_seconds,
                             sim_threshold=args.sim_threshold)
        res["synchrony"]["burst_size_over_time"] = \
            f"<{len(res['synchrony']['burst_size_over_time'])} days omitted>"
    elif args.cmd == "coordination-network":
        res = c.coordination_network(min_dup=args.min_dup,
                                     delta_seconds=args.delta_seconds,
                                     min_edge_weight=args.min_edge_weight,
                                     top_clusters=args.top_clusters)
    elif args.cmd == "semantique":
        res = c.semantique(freq=args.freq)
        res["per_period"] = f"<{len(res['per_period'])} periods omitted>"
    elif args.cmd == "breakdown":
        res = c.breakdown(by=args.by, metrics=args.metrics)
    elif args.cmd == "actor":
        res = c.actor(args.handle, samples=args.samples)
    elif args.cmd == "engagement-quality":
        res = c.engagement_quality()
    elif args.cmd == "reply-network":
        res = c.reply_network()
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    _main()
