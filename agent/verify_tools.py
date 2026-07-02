"""
Phase-1 verification: assert the deterministic tools reproduce the canonical
numbers in analysis/out/key_figures.json (the EDA is the source of truth).

Run:  .venv/bin/python agent/verify_tools.py
"""
import os
import json
import sys

from tools import Corpus, ROOT

KEY = os.path.join(ROOT, "analysis", "out", "key_figures.json")


def check(name, got, exp):
    ok = got == exp
    mark = "OK " if ok else "XX "
    print(f"  [{mark}] {name}: got={got!r} exp={exp!r}")
    return ok


def main():
    with open(KEY) as f:
        kf = json.load(f)
    c = Corpus()
    p = c.profile(top=15)
    tl = c.timeline(freq="D", top=5)
    co = c.coordination(min_dup=5, top=20)
    se = c.semantique(freq="D")

    results = []
    print("profile() vs key_figures.json")
    results.append(check("n_messages", p["n_messages"], kf["n_rows"]))
    results.append(check("date_min", p["date_min"], kf["date_min"]))
    results.append(check("date_max", p["date_max"], kf["date_max"]))
    results.append(check("n_authors", p["n_authors"], kf["n_authors"]))
    results.append(check("engagement_type_counts",
                         p["engagement_type_counts"], kf["engagement_type_counts"]))
    results.append(check("retweet_share_pct",
                         p["retweet_share_pct"], kf["retweet_share_pct"]))
    results.append(check("verified_share_pct",
                         p["verified_share_pct"], kf["verified_share_pct"]))
    results.append(check("sentiment_counts",
                         p["sentiment_counts"], kf["sentiment_counts"]))
    results.append(check("n_authors_1_msg",
                         p["n_authors_1_msg"], kf["n_authors_1_msg"]))
    results.append(check("n_authors_ge_20_msg",
                         p["n_authors_ge_20_msg"], kf["n_authors_ge_20_msg"]))
    results.append(check("top_amplified_authors",
                         p["top_amplified_authors"],
                         dict(list(kf["top15_amplified_authors"].items())[:15])))
    results.append(check("top_active_authors",
                         p["top_active_authors"],
                         dict(list(kf["top15_authors_by_volume"].items())[:15])))

    print("\ntimeline() vs key_figures.json")
    results.append(check("peak_day", tl["peak_period"][:10], kf["peak_day"]))
    results.append(check("peak_volume", tl["peak_volume"], kf["peak_day_volume"]))
    results.append(check("top5_peak_days",
                         {k[:10]: v for k, v in tl["top_peaks"].items()},
                         kf["top5_peak_days"]))

    print("\ncoordination() vs key_figures.json")
    got_dup = [d["count"] for d in co["top_duplicated_messages"][:10]]
    exp_dup = list(kf["top20_duplicated_messages"].values())[:10]
    results.append(check("top_duplicated_counts(10)", got_dup, exp_dup))
    got_burst = sorted([b["count"] for b in co["top_synchronized_bursts"][:10]], reverse=True)
    exp_burst = sorted(list(kf["top_synchronized_bursts"].values())[:10], reverse=True)
    results.append(check("top_burst_counts(10)", got_burst, exp_burst))
    results.append(check("coord.n_authors_1_msg",
                         co["n_authors_1_msg"], kf["n_authors_1_msg"]))
    results.append(check("coord.n_authors_ge_20_msg",
                         co["n_authors_ge_20_msg"], kf["n_authors_ge_20_msg"]))

    print("\nsemantique() vs key_figures.json")
    results.append(check("sentiment_counts", se["sentiment_counts"], kf["sentiment_counts"]))

    n_ok, n = sum(results), len(results)
    print(f"\n{n_ok}/{n} checks passed.")
    sys.exit(0 if n_ok == n else 1)


if __name__ == "__main__":
    main()
