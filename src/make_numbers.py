"""Write paper/numbers.tex: every number in the paper as a LaTeX macro, computed from results/.

No number in the paper text is typed by hand; sections use these macros.
A missing input file yields \\pending{...} macros, which `make check` rejects.

Usage: .venv/bin/python -I src/make_numbers.py <results_dir> <out_tex>
"""
import json, os, statistics, sys


FIG_ITEM = "dev-880"  # pair shown in Figure 1 (src/figure_screenshot.py)


def main():
    R, out_p = sys.argv[1:3]
    M = {}

    def load(name):
        p = os.path.join(R, name)
        return json.load(open(p)) if os.path.exists(p) else None

    def n(x):
        return f"{x:,}"

    def pc(x, d=1):
        return f"{100 * x:.{d}f}\\%"

    def f3(x):
        return f"{x:.2f}"

    def ci(v, d=1):
        return f"{100 * v[0]:.{d}f}--{100 * v[1]:.{d}f}\\%"

    def ci2(v):
        return f"{v[0]:.2f}--{v[1]:.2f}"

    s = load("e2_summary.json")
    h = s["human"]
    M["nPairs"], M["nUrls"] = n(s["n_pairs"]), n(s["n_urls"])
    M["nThenSupported"], M["nCheckable"] = n(h["then_supported"]), n(h["checkable"])
    M["nUnverPairs"] = n(h["classes"]["unverifiable"])
    M["lostRate"], M["lostCI"], M["lostN"] = pc(h["lost_any_rate"]), ci(h["lost_any_ci"]), n(h["lost_any"])
    M["linkLostN"], M["changedN"] = n(h["classes"]["link_lost"]), n(h["classes"]["content_changed"])
    M["linkLostRate"] = pc(h["classes"]["link_lost"] / h["checkable"])
    M["changedRate"] = pc(h["classes"]["content_changed"] / h["checkable"])
    M["uncertainN"], M["lostUpperRate"] = n(h["uncertain"]), pc(h["lost_upper_rate"])
    import math
    k_, n_ = h["classes"]["link_lost"], h["checkable"]
    p_ = k_ / n_
    z = 1.96
    c_ = (p_ + z * z / (2 * n_)) / (1 + z * z / n_)
    w_ = z * math.sqrt(p_ * (1 - p_) / n_ + z * z / (4 * n_ * n_)) / (1 + z * z / n_)
    M["linkLostCI"] = ci([c_ - w_, c_ + w_])
    M["uncertainRate"] = pc(h["uncertain"] / h["checkable"])
    M["judgeMissEv"] = n(h["judge_miss_evidence_present"])
    names = {"bing_chat": "Bing", "neeva": "Neeva", "perplexity": "Ppl", "you": "You"}
    for e, v in h["by_engine"].items():
        M[f"lost{names[e]}"] = pc(v["rate"])
        M[f"lost{names[e]}CI"] = ci(v["ci"])
        M[f"checkable{names[e]}"] = n(v["checkable"])
        M[f"link{names[e]}"] = pc(v["classes"].get("link_lost", 0) / v["checkable"])
        M[f"changed{names[e]}"] = pc(v["classes"].get("content_changed", 0) / v["checkable"])
    jc = s["judge_consistent_reachable"]
    M["jcN"], M["jcChanged"], M["jcRate"] = n(jc["n"]), n(jc["content_changed"]), pc(jc["rate"])
    ev = s["evidence_only"]
    M["evN"], M["evPresent"], M["evNone"] = n(ev["n"]), pc(ev["fully_present"] / ev["n"]), pc(ev["none_present"] / ev["n"])
    t = s["tool"]
    M["toolCheckable"], M["toolLostRate"], M["toolLostCI"] = n(t["checkable"]), pc(t["lost_any_rate"]), ci(t["lost_any_ci"])
    g = s["link_groups_urls"]
    M["urlReachable"], M["urlLost"], M["urlUnver"] = n(g["reachable"]), n(g["lost"]), n(g["unverifiable"])
    M["urlReachablePct"] = pc(g["reachable"] / s["n_urls"])
    M["urlLostPct"], M["urlUnverPct"] = pc(g["lost"] / s["n_urls"]), pc(g["unverifiable"] / s["n_urls"])

    c = load("calibration.json")
    M["calBlocked"] = n(c["v1_groups"]["blocked"])
    reach = c["v1_blocked_now"].get("ok", 0) + c["v1_blocked_now"].get("moved", 0)
    M["calBlockedReachable"] = n(reach)
    M["calBlockedTried"] = n(c["v1_blocked_tried_in_browser"])
    M["calBlockedStill"] = n(c["v1_blocked_now"].get("blocked", 0))
    M["calFiltered"] = n(c["network_filtered"])
    M["calRedirect"] = n(sum(c["v1_redirect_now"].values()))
    M["calRedirectMoved"] = n(c["v1_redirect_now"].get("moved", 0))
    M["calPlainAlive"] = pc(c["v1_groups"]["reachable"] / c["n_urls"])
    M["wbN"], M["wbCapture"] = n(c["wayback_requery"]["n"]), n(c["wayback_requery"]["has_capture"])  # records of any status
    b1 = {json.loads(l)["url"] for l in open("data/live_browser/browser_log_try1.jsonl")}
    b2 = {json.loads(l)["url"] for l in open("data/live_browser/browser_log.jsonl")}
    M["browserN"], M["browserTwice"] = n(len(b2)), n(len(b1 & b2))
    allow = set()
    for f_ in ("results/train/browser_allow.txt",):
        if os.path.exists(f_):
            allow |= {l.strip() for l in open(f_) if l.strip()}
    trurls = {json.loads(l)["url"] for l in open("data/pairs_train.jsonl")} if os.path.exists("data/pairs_train.jsonl") else set()
    M["browserUnused"] = n(len((b2 & trurls) - allow))
    M["wbFiltered"] = n(c["wayback_requery"]["answered_by_network_filter"])
    M["wbReachable"] = n(c["wayback_requery"]["reachable_now"])

    for key, f in (("Mc", "e1_eval_source_raw_text.json"), ("Ng", "e1_eval_ngram.json"), ("Co", "e1_eval_combo.json")):
        e = load(f)["complete"]
        M[f"eOne{key}Auc"], M[f"eOne{key}AucCI"] = f3(e["test"]["auc"]), ci2(e["test_ci"]["auc"])
        M[f"eOne{key}Ba"], M[f"eOne{key}BaCI"] = f3(e["test"]["bal_acc"]), ci2(e["test_ci"]["bal_acc"])
        M[f"eOne{key}Fone"] = f3(e["test"]["f1_unsupported"])
    M["eOneThr"] = f3(load("e1_eval_combo.json")["complete"]["threshold_dev"])
    q = load("e1_eval_qwen.json")
    M["eOneQwBa"], M["eOneQwBaCI"] = f3(q["test"]["qwen_bal_acc"]), ci2(q["test"]["qwen_bal_acc_ci"])
    M["eOneQwFone"], M["eOneQwSupRate"] = f3(q["test"]["qwen_f1_unsupported"]), pc(q["test"]["qwen_supported_rate"], 0)
    M["eOneCascBa"] = f3(q["test"]["cascade_bal_acc"])
    M["qwenMedianS"] = f"{q['median_seconds']:.1f}"
    sub = load("e1_subset.json")
    M["subN"], M["subShare"] = n(sub["n"]), pc(sub["n"] / sub["n_test"], 0)
    M["subMcAuc"], M["subNgAuc"], M["subCoAuc"] = f3(sub["minicheck"]["auc"]), f3(sub["ngram"]["auc"]), f3(sub["combo"]["auc"])
    M["nTest"] = n(load("e1_eval_combo.json")["n"]["test"])
    M["nDev"] = n(load("e1_eval_combo.json")["n"]["dev"])

    bc = load("baseline_compare.json")
    M["uhLiveLost"], M["uhLiveLostPct"] = n(bc["urlhealth_live_among_lost"]), pc(bc["urlhealth_live_among_lost"] / bc["lost_support_total"])
    M["uhLiveLinkLost"], M["uhLiveChanged"] = n(bc["urlhealth_live_among_link_lost"]), n(bc["urlhealth_live_among_content_changed"])
    M["uhLiveLinkLostPct"] = pc(bc["urlhealth_live_among_link_lost"] / bc["n_link_lost"], 0)
    M["uhHalluLinkLost"] = n(bc["urlhealth_by_class"]["link_lost"].get("LIKELY_HALLUCINATED", 0))
    M["uhHalluStill"] = n(bc["urlhealth_by_class"]["still_supported"].get("LIKELY_HALLUCINATED", 0))
    sm = bc["stringmatch_by_class"]
    M["smNoMatchStill"] = n(sm["still_supported"]["no_match"])
    M["smNoMatchStillPct"] = pc(sm["still_supported"]["no_match"] / (sm["still_supported"]["no_match"] + sm["still_supported"]["match"]))
    M["smCatchChanged"] = n(sm["content_changed"]["no_match"])
    M["nStill"] = n(bc["n_still"])

    ins1 = load("inspection_summary.json")  # design sample (rule chosen on it)
    if ins1:
        M["insOneChangedPrec"] = ins1["macros"]["insChangedPrec"]
        M["insOneN"] = str(ins1["n_labels"])
    ins = load("inspection2_summary.json")  # validation sample (reported)
    if ins:
        for k, v in ins["macros"].items():
            M[k] = v
        M["insTwoN"] = str(ins["n_labels"])
    else:
        for k in ("insChangedN", "insChangedPrec", "insStillN", "insStillAgree", "insAwayN", "insAwayDifferent",
                  "insDemotedN", "insDemotedFull", "insUncertainN", "insUncertainNotFull"):
            M[k] = "\\pending{inspection}"

    est = load("inspection2_estimate.json")
    if est:
        M["estNotFull"], M["estCI"] = pc(est["estimate_not_full"], 0), ci(est["ci"], 0)
        M["estNo"] = pc(est["estimate_no_support"], 0)
        M["estStillNotFull"] = pc(est["not_full_share"]["still_supported"], 0)
    e3 = load("e3_latency.json")
    if e3:
        runs = e3["runs"]
        M["eThreeN"] = n(len(runs))
        M["eThreeMedianS"] = f"{statistics.median(r['total_s'] for r in runs):.0f}"
        M["eThreePairs"] = f"{statistics.median(r['n_pairs'] for r in runs):.0f}"
        M["eThreeUrls"] = f"{statistics.median(r['n_urls'] for r in runs):.0f}"
        tot = sum(r["total_s"] for r in runs)
        M["eThreeNetShare"] = pc(sum(r["fetch_s"] + r["archive_s"] for r in runs) / tot, 0)
        M["eThreeJudgeS"] = f"{statistics.median(r['judge_and_rest_s'] for r in runs):.1f}"
        M["eThreeGpuGB"] = f"{e3['peak_gpu_gb']:.1f}"
        st = [c for r in runs for c in r["archive_status"]]
        nothen = [c for c in st if c not in ("ok", "provided", "not_requested")]
        M["eThreeArchFail"] = f"{len(nothen)} of the {len(st)}"  # per pair: lookup errors + refused capture fetches
        M["eThreeArchLookup"] = n(sum(c.startswith("lookup_failed") for c in nothen))
        M["eThreeArchFetch"] = n(sum(c.startswith("fetch_failed") for c in nothen))
    else:
        for k in ("eThreeN", "eThreeMedianS", "eThreePairs", "eThreeUrls", "eThreeNetShare", "eThreeJudgeS", "eThreeGpuGB",
                  "eThreeArchFail"):
            M[k] = "\\pending{E3}"
    e3x = load("e3_latency_explain.json")
    M["eThreeExplainGpuGB"] = f"{e3x['peak_gpu_gb']:.1f}" if e3x else "\\pending{E3 explain}"
    now = [json.loads(l) for l in open(os.path.join(R, "e2_scores_now.jsonl"))]
    secs = [r["main_text"]["seconds"] for r in now if "main_text" in r]
    M["judgeMedianMs"] = f"{1000 * statistics.median(secs):.0f}"
    both = [r["main_text"]["seconds"] + r["dom_text"]["seconds"] for r in now if "main_text" in r and "dom_text" in r]
    M["judgeBothMs"] = f"{1000 * statistics.median(both):.0f}"
    cc = h["cluster_ci"]
    M["linkLostClusterCI"], M["changedClusterCI"], M["lostClusterCI"] = ci(cc["link_lost"]), ci(cc["content_changed"]), ci(cc["lost_any"])
    to = h["test_only"]
    M["testLinkLostRate"], M["testChangedRate"] = pc(to["link_lost"] / to["checkable"]), pc(to["content_changed"] / to["checkable"])
    bs = load("baseline_spotcheck.json")
    if bs:
        M["bsN"], M["bsSampled"], M["bsDead"] = n(bs["population_pairs"]), n(bs["within_sample_n"]), n(bs["dead_pairs"])
        for key_, nm in (("citedrift", "Cd"), ("urlhealth", "Uh"), ("stringmatch", "Sm")):
            w = bs["weighted"][key_]
            M[f"bs{nm}P"], M[f"bs{nm}R"], M[f"bs{nm}F"] = f3(w["precision"]), f3(w["recall"]), f3(w["f1"])
            c_ = bs["weighted_ci"][key_]["precision"]
            M[f"bs{nm}PCI"] = ci2(c_)
    e4 = load("e4_checkmode.json")
    if e4:
        M["eFourN"], M["eFourPairs"] = n(e4["n_answers"]), n(e4["n_matched_pairs"])
        M["eFourTotal"] = n(e4["n_matched_pairs"] + e4["n_unmatched"])
        M["eFourAgree"] = pc(e4["outcome_agreement"] / e4["n_matched_pairs"], 0)
        M["eFourLinkAgree"] = pc(e4["link_state_agreement"] / e4["n_matched_pairs"], 0)
        nn = e4["confusion"].get("never_supported->never_supported", 0)
        M["eFourAgreeExNever"] = pc((e4["outcome_agreement"] - nn) / (e4["n_matched_pairs"] - nn), 0)
        M["eFourUnmatched"] = n(e4["n_unmatched"])
    else:
        for k_ in ("eFourN", "eFourPairs", "eFourAgree", "eFourLinkAgree"):
            M[k_] = "\\pending{E4}"
    ctl = load("inspection_control_estimate.json")
    if ctl:
        for k_, v_ in ctl["macros"].items():
            M[k_] = v_

    ex = {x["id"]: x for x in json.load(open(os.path.join(os.path.dirname(R.rstrip("/")) or ".", "app", "static", "explorer.json")))["items"]}
    fig = ex[FIG_ITEM]
    M["figItem"], M["figPthen"], M["figPnow"] = FIG_ITEM, f3(fig["p23"]), f3(fig["pn"])

    tr = os.path.join(R, "train")
    if os.path.exists(os.path.join(tr, "e2_summary.json")):
        th = json.load(open(os.path.join(tr, "e2_summary.json")))["human"]
        M["trCheckable"] = n(th["checkable"])
        M["trLinkLostRate"] = pc(th["classes"]["link_lost"] / th["checkable"])
        M["trChangedRate"] = pc(th["classes"]["content_changed"] / th["checkable"])
        te = json.load(open(os.path.join(tr, "e1_eval.json")))
        M["trAuc"], M["trPairs"] = f3(te["auc"]), n(te["n"])
    if os.path.exists("data/pairs_train.jsonl"):
        import datetime
        devu = {json.loads(l)["url"] for l in open("data/pairs_devtest.jsonl")}
        tru = {json.loads(l)["url"] for l in open("data/pairs_train.jsonl")} - devu
        ts = lambda x: datetime.datetime.strptime(x, "%Y-%m-%dT%H:%M:%SZ")
        t_dev = min(ts(r["fetched_at"]) for r in map(json.loads, open("data/live/fetch_log.jsonl")) if r["url"] in devu)
        t_tr = min(ts(r["fetched_at"]) for r in map(json.loads, open("data/live/fetch_log.jsonl")) if r["url"] in tru)
        M["trFetchGapH"] = f"{(t_tr - t_dev).total_seconds() / 3600:.0f}"
    ac = load("author_check.json")
    if ac and ac["votes"]:
        M["authorItems"] = n(ac["items_checked"])
        M["authorAgree"] = f"{ac['agree']} of {ac['votes']} ({100 * ac['agree_rate']:.0f}\\%)"
    else:
        M["authorItems"], M["authorAgree"] = "\\pending{n}", "\\pending{n}"
    trs = load("inspection_train_summary.json")
    if trs:
        k_, n_ = trs["agreement"]["content_changed_not_full"]
        M["trChangedPrec"] = f"{k_} of {n_} ({100 * k_ / n_:.0f}\\%)"
        M["trChangedSampled"] = n(len([1 for _ in open("data/inspection_train/key.csv")]) and
                                  sum(1 for r in __import__("csv").DictReader(open("data/inspection_train/key.csv"))
                                      if r["stratum"] == "content_changed"))
    else:
        M["trChangedPrec"] = "\\pending{train spot check}"
    with open(out_p, "w") as f:
        f.write("% Generated by src/make_numbers.py from results/. Do not edit by hand.\n")
        for k, v in sorted(M.items()):
            f.write(f"\\newcommand{{\\{k}}}{{{v}\\xspace}}\n")
    print(len(M), "macros")


if __name__ == "__main__":
    main()
