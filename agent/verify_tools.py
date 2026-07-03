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

    # ---- enriched propagation: self-consistency vs independent pandas recompute
    import pandas as pd
    ts = c.col["timestamp"]
    hourly = c.df.set_index(ts).resample("h").size()
    reach_grid = c.df.set_index(ts)[c.col["reach"]].fillna(0).resample("h").sum()

    tlv = c.timeline(freq="h", velocity=True)
    print("\ntimeline(velocity=True) self-consistency")
    results.append(check("velocity.peak_volume==hourly max",
                         tlv["velocity"]["peak_volume"], int(hourly.max())))
    # onset is the first hour reaching >=10% of the hourly peak
    thr = 0.10 * int(hourly.max())
    exp_onset = str(hourly[hourly >= thr].index[0])
    results.append(check("velocity.onset_period", tlv["velocity"]["onset_period"], exp_onset))
    results.append(check("reach.peak_reach==reach grid max",
                         tlv["reach"]["peak_reach"], int(reach_grid.max())))
    exp_lead = int(reach_grid.values.argmax() - hourly.values.argmax())
    results.append(check("reach.lead_periods", tlv["reach"]["reach_vs_volume_lead_periods"], exp_lead))

    ntl = c.narrative_timelines(k=6, freq="D")
    print("\nnarrative_timelines() self-consistency")
    results.append(check("sum(cluster n_messages)==total",
                         sum(cl["n_messages"] for cl in ntl["clusters"]), ntl["n_messages"]))
    exp_labeled = int((c._clean_text.str.len() > 0).sum())
    results.append(check("total==nonempty clean-text rows", ntl["n_messages"], exp_labeled))

    # ---- enriched coordination: synchrony / near-dup / account behaviour
    print("\ncoordination() enriched blocks self-consistency")
    clean = c._clean_text
    dupc = clean[clean.str.len() > 0].value_counts()
    dupc = dupc[dupc >= 5]

    syn = co["synchrony"]
    results.append(check("synchrony.delta_seconds", syn["delta_seconds"], 60))
    results.append(check("synchrony.copies_considered==sum(dup counts)",
                         syn["copies_considered"], int(dupc.sum())))
    exp_score = round(syn["copies_within_delta"] / syn["copies_considered"] * 100, 1)
    results.append(check("synchrony.coordination_score consistent",
                         syn["coordination_score_pct"], exp_score))
    results.append(check("synchrony.within<=considered",
                         syn["copies_within_delta"] <= syn["copies_considered"], True))
    # max Δ-burst over time equals the top same-window burst size (=7 on 26 mars)
    max_burst = max(v["max_burst"] for v in syn["burst_size_over_time"].values())
    results.append(check("synchrony.max_burst==top_synchronized_bursts max",
                         max_burst, max(b["count"] for b in co["top_synchronized_bursts"])))
    # synchrony baseline (lift vs uniform-spread null)
    results.append(check("synchrony.lift==score/uniform_expected",
                         syn["synchrony_lift_vs_uniform"],
                         round(syn["coordination_score_pct"]
                               / syn["expected_within_delta_uniform_pct"], 1)))
    results.append(check("synchrony.observed>uniform_null (burstier than lifespan)",
                         syn["coordination_score_pct"] > syn["expected_within_delta_uniform_pct"],
                         True))

    # ---- engagement-aware duplication split (copy-paste vs retweet amplification)
    eng = c.df[c.col["engagement"]].astype(str).str.upper()
    rt_val = str(c.val["engagement_retweet"]).upper()
    dup_rows = clean.isin(set(dupc.index))
    exp_rt_share = round(float((eng[dup_rows] == rt_val).mean()) * 100, 1)
    results.append(check("coord.retweet_share_of_duplicated_pct",
                         co["retweet_share_of_duplicated_pct"], exp_rt_share))
    authored_idx = c.df.index[~eng.isin([rt_val, "REPLY"])]
    results.append(check("coord.copy_paste_rate_pct==seg_dup_rate(ORIGINAL+QUOTE)",
                         co["copy_paste_rate_pct"], c._seg_dup_rate(authored_idx, min_dup=2)))
    results.append(check("coord.copy_paste_rate << verbatim_rate (real copy-paste is tiny)",
                         co["copy_paste_rate_pct"] < co["verbatim_duplication_rate_pct"], True))

    nd = co["near_duplicates"]
    results.append(check("near_dup.candidate_texts==min(len(dup),500)",
                         nd["candidate_texts"], min(int(len(dupc)), 500)))
    results.append(check("near_dup.every group has >=2 variants",
                         nd["n_texts_merged"] >= 2 * nd["n_near_dup_groups"], True))
    results.append(check("near_dup.messages<=corpus",
                         nd["messages_in_near_dup_groups"] <= len(c.df), True))

    ab = co["account_behaviour"]
    results.append(check("account.n_accounts==n_authors", ab["n_accounts"], kf["n_authors"]))
    results.append(check("account.single_message_share_pct",
                         ab["single_message_share_pct"],
                         round(kf["n_authors_1_msg"] / kf["n_authors"] * 100, 1)))
    results.append(check("account.verified_share_among_duplicators in [0,100]",
                         0 <= ab["verified_share_among_duplicators_pct"] <= 100, True))

    # ---- coordination_network() invariants
    net = c.coordination_network()
    print("\ncoordination_network() self-consistency")
    results.append(check("net.accounts_in_clusters<=n_nodes",
                         net["n_accounts_in_clusters"] <= net["n_nodes"], True))
    results.append(check("net.largest_component<=n_nodes",
                         net["largest_component_size"] <= net["n_nodes"], True))
    results.append(check("net.every cluster size>=2",
                         all(cl["size"] >= 2 for cl in net["top_clusters"]), True))
    results.append(check("net.sum(top cluster sizes)<=accounts_in_clusters",
                         sum(cl["size"] for cl in net["top_clusters"])
                         <= net["n_accounts_in_clusters"], True))

    # ---- breakdown() self-consistency
    print("\nbreakdown() self-consistency")
    bd = c.breakdown(by="sentiment")
    results.append(check("breakdown.n_segments==sentiment classes",
                         bd["n_segments"], len(kf["sentiment_counts"])))
    results.append(check("breakdown.sum(volume)==n_messages",
                         sum(s["volume"] for s in bd["segments"].values()), kf["n_rows"]))
    results.append(check("breakdown.per-segment volume==sentiment_counts",
                         {k: v["volume"] for k, v in bd["segments"].items()},
                         {k: kf["sentiment_counts"][k] for k in bd["segments"]}))
    gap = bd["gaps"]["dup_rate"]
    results.append(check("breakdown.gap.spread==max-min",
                         gap["spread"], round(gap["max"] - gap["min"], 2)))
    bdv = c.breakdown(by="verified")
    results.append(check("breakdown(verified).sum(volume)==n_messages",
                         sum(s["volume"] for s in bdv["segments"].values()), kf["n_rows"]))

    # ---- actor() self-consistency vs profile()
    print("\nactor() self-consistency")
    top_amp_handle = list(p["top_amplified_authors"])[0]
    act = c.actor(top_amp_handle)
    results.append(check("actor.n_times_reposted==profile amplified count",
                         act["n_times_content_reposted"],
                         p["top_amplified_authors"][top_amp_handle]))
    top_auth = list(p["top_active_authors"])[0]
    aa = c.actor(top_auth)
    results.append(check("actor.n_messages_authored==profile active count",
                         aa["n_messages_authored"], p["top_active_authors"][top_auth]))
    results.append(check("actor.engagement_mix sums to n_authored",
                         sum(aa["profile"]["engagement_mix"].values()),
                         aa["n_messages_authored"]))

    # ---- engagement_quality() self-consistency
    print("\nengagement_quality() self-consistency")
    eq = c.engagement_quality()
    results.append(check("eq.retweet organic/reach==0 (engagement on original)",
                         eq["organic_per_reach_by_engagement"]["RETWEET"], 0.0))
    results.append(check("eq.overall ratio in [0,1]",
                         0 <= eq["organic_per_reach_overall"] <= 1, True))
    results.append(check("eq.unique >= duplicated organic/reach",
                         eq["organic_per_reach_unique"] >= eq["organic_per_reach_duplicated"], True))

    # ---- reply_network() self-consistency
    print("\nreply_network() self-consistency")
    rn = c.reply_network()
    reply_eng = kf["engagement_type_counts"].get("REPLY", 0)
    results.append(check("reply.n_replies<=REPLY engagement count",
                         rn["n_replies"] <= reply_eng, True))
    results.append(check("reply.sum(top targets)<=n_replies",
                         sum(t["n_replies_received"] for t in rn["top_reply_targets"])
                         <= rn["n_replies"], True))
    results.append(check("reply.share_pct consistent",
                         rn["reply_share_pct"], round(rn["n_replies"] / kf["n_rows"] * 100, 1)))

    n_ok, n = sum(results), len(results)
    print(f"\n{n_ok}/{n} checks passed.")
    sys.exit(0 if n_ok == n else 1)


if __name__ == "__main__":
    main()
