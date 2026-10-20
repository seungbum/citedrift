"""E2: two-time drift classes for every statement-citation pair.

Inputs: pair index, per-URL features (after the browser re-check), judge
scores on the 2023 text (combined MiniCheck + 4-gram, threshold from dev) and
on the current page (main text and DOM text, same combination and threshold).

"Then" support comes from the 2023 human label (complete_support), or, in
tool mode, from the judge on the 2023 text. Classes:
  still_supported  then supported, page reachable, judge supports now (main or DOM text)
  link_lost        then supported, link state in the "lost" group
  content_changed  then supported, page reachable, judge no longer supports
  never_supported  not supported at citation time
  unverifiable     then supported, link could not be checked from our vantage point
In human mode (then = annotator label) a reachable pair that the judge does
not support now counts as content_changed only if BOTH the judge supported it
on the 2023 text AND the annotator's 2023 evidence is no longer in the current
DOM text (fuzzy). If the evidence is still there it stays still_supported
(the judge misses it); otherwise it is "uncertain". (Rule fixed on the first
blinded spot check, data/inspection/; validated on the second, data/inspection2/.)

Usage: .venv/bin/python -I src/e2_drift.py <pairs> <url_features> <scores_2023_combo> <minicheck_now> \
          <judge_params> <e1_eval_combo_json> <out_jsonl> <out_summary_json> <minicheck_2023_scores> <liu_dir>
In tool mode the annotator's evidence is not used; as in the live checker, the "then" evidence is the
sentence of the best-scoring 2023 chunk closest to the statement, and a content change needs it gone.
"""
import collections, gzip, json, os, sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from citedrift.linkstate import GROUP, classify  # noqa: E402
from citedrift.textutil import evidence_survival  # noqa: E402
from baseline_ngram import ngram_score  # noqa: E402
from e1_combo import combine  # noqa: E402
from citedrift.judge import chunk_document  # noqa: E402
from citedrift.pipeline import best_sentence  # noqa: E402
from rapidfuzz import fuzz  # noqa: E402

CACHE = "data/cache/now_text"
CLASSES = ["still_supported", "content_changed", "uncertain", "link_lost", "unverifiable", "never_supported"]


def load_now(key):
    with gzip.open(os.path.join(CACHE, key + ".json.gz"), "rt") as f:
        return json.load(f)


def wilson(k, n, z=1.96):
    if n == 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [float(c - h), float(c + h)]


def main():
    (pairs_p, feat_p, s23_p, now_p, par_p, e1_p, out_p, sum_p, mc23_p, liu) = sys.argv[1:11]
    mc23 = {(r["split"], r["idx"]): r["best_chunk"] for r in map(json.loads, open(mc23_p))}
    raw23 = {}
    for sp in sorted({json.loads(l)["split"] for l in open(pairs_p)}):
        with gzip.open(os.path.join(liu, "verifiability_judgments", f"verifiability_judgments_{sp}.jsonl.gz"), "rt") as f:
            for i, line in enumerate(f):
                raw23[(sp, i)] = json.loads(line)["source_raw_text"]
    params = json.load(open(par_p))
    thr = json.load(open(e1_p))["complete"]["threshold_dev"]
    feats = {r["url"]: r for r in map(json.loads, open(feat_p))}
    s23 = {(r["split"], r["idx"]): r["prob"] for r in map(json.loads, open(s23_p))}
    now = {(r["split"], r["idx"]): r for r in map(json.loads, open(now_p))}
    state_cache, rows = {}, []
    for p in map(json.loads, open(pairs_p)):
        k = (p["split"], p["idx"])
        f = feats[p["url"]]
        d = load_now(f["key"])
        if p["url"] not in state_cache:
            state_cache[p["url"]] = classify(f, d.get("main_text", "")[:500])
        state = state_cache[p["url"]]
        group = GROUP[state]
        then_human = p["label_2023"] == "complete_support"
        then_judge = s23[k] >= thr
        s_main = s_dom = None
        if k in now and group == "reachable":
            r = now[k]
            if "main_text" in r:
                s_main = float(combine(params, r["main_text"]["prob"], ngram_score(p["statement"], d["main_text"])))
            if "dom_text" in r:
                s_dom = float(combine(params, r["dom_text"]["prob"], ngram_score(p["statement"], d["dom_text"])))
        now_supported = max(x for x in (s_main, s_dom, -1) if x is not None) >= thr if group == "reachable" else None
        ev_dom = evidence_survival(p.get("evidence_2023"), d.get("dom_text", ""))[1] if group == "reachable" else None

        tool_ev = ""
        if group == "reachable" and not now_supported:
            chunks = chunk_document(raw23[k])
            tool_ev = best_sentence(chunks[mc23[k]], p["statement"])[0] if mc23[k] < len(chunks) else ""
        tool_ev_present = bool(tool_ev) and fuzz.partial_ratio(tool_ev.lower(), (d.get("dom_text") or "").lower()) >= 90
        ev_gone = ev_dom is not None and ev_dom < 1.0
        ev_present = ev_dom is not None and ev_dom >= 1.0

        def cls(then, human):
            if not then:
                return "never_supported"
            if group == "unverifiable":
                return "unverifiable"
            if group == "lost":
                return "link_lost"
            if now_supported:
                return "still_supported"
            if not human:  # tool mode, as in the live checker: the best 2023 passage must be gone too
                if not tool_ev:
                    return "uncertain"
                return "still_supported" if tool_ev_present else "content_changed"
            if then_judge and ev_gone:
                return "content_changed"  # both signals: judge supported the 2023 text, evidence no longer on the page
            if ev_present:
                return "still_supported"  # the annotator's evidence is still there; the judge misses it today
            return "uncertain"  # the two signals disagree or evidence is unavailable

        rows.append({"split": p["split"], "idx": p["idx"], "engine": p["engine"], "url": p["url"],
                     "label_2023": p["label_2023"], "link_state": state, "link_group": group,
                     "score_2023": s23[k], "score_now_main": s_main, "score_now_dom": s_dom,
                     "evidence_fuzzy_now_dom": ev_dom, "class_human": cls(then_human, True),
                     "class_tool": cls(then_judge, False), "judge_then_supported": bool(then_judge),
                     "judge_miss_evidence_present": bool(then_human and group == "reachable" and not now_supported
                                                         and ev_present)})
    with open(out_p, "w") as out:
        for r in rows:
            out.write(json.dumps(r) + "\n")

    summ = {"threshold": thr, "n_pairs": len(rows), "n_urls": len(state_cache),
            "link_states_urls": collections.Counter(state_cache.values()),
            "link_groups_urls": collections.Counter(GROUP[s] for s in state_cache.values())}
    for mode in ("human", "tool"):
        c = collections.Counter(r[f"class_{mode}"] for r in rows)
        base = [r for r in rows if r[f"class_{mode}"] != "never_supported"]
        checkable = [r for r in base if r["link_group"] != "unverifiable"]
        lost = sum(r[f"class_{mode}"] in ("link_lost", "content_changed") for r in checkable)
        changed = [r for r in base if r[f"class_{mode}"] == "content_changed"]
        corrob = sum((r["evidence_fuzzy_now_dom"] is not None and r["evidence_fuzzy_now_dom"] < 1.0) for r in changed)
        summ[mode] = {"classes": dict(c), "then_supported": len(base), "checkable": len(checkable),
                      "lost_any": lost, "lost_any_rate": lost / len(checkable) if checkable else None,
                      "lost_any_ci": wilson(lost, len(checkable)),
                      "content_changed_with_evidence_missing": corrob,
                      "uncertain": sum(r[f"class_{mode}"] == "uncertain" for r in checkable),
                      "lost_upper_rate": (lost + sum(r[f"class_{mode}"] == "uncertain" for r in checkable)) / len(checkable)
                      if checkable else None,
                      "by_engine": {}}
        for e in sorted({r["engine"] for r in rows if r["engine"]}):
            ch = [r for r in checkable if r["engine"] == e]
            le = sum(r[f"class_{mode}"] in ("link_lost", "content_changed") for r in ch)
            summ[mode]["by_engine"][e] = {
                "checkable": len(ch), "lost_any": le, "rate": le / len(ch) if ch else None,
                "ci": wilson(le, len(ch)),
                "classes": dict(collections.Counter(r[f"class_{mode}"] for r in rows if r["engine"] == e))}
    # judge-consistent subset: human said supported AND the judge agreed on the 2023 text
    jc = [r for r in rows if r["label_2023"] == "complete_support" and r["judge_then_supported"]
          and r["link_group"] == "reachable"]
    jl = sum(r["class_human"] == "content_changed" for r in jc)
    summ["judge_consistent_reachable"] = {"n": len(jc), "content_changed": jl,
                                          "rate": jl / len(jc) if jc else None, "ci": wilson(jl, len(jc))}
    # cluster bootstrap by URL (pairs that share a URL are not independent); 2,000 draws, seed 0
    rng = np.random.default_rng(0)
    chk = [r for r in rows if r["class_human"] not in ("never_supported", "unverifiable")]
    by_url = {}
    for r in chk:
        by_url.setdefault(r["url"], []).append(r)
    urls_ = list(by_url)
    cnt = {u: (len(v), sum(x["class_human"] == "link_lost" for x in v),
               sum(x["class_human"] == "content_changed" for x in v)) for u, v in by_url.items()}
    bl, bc, bt = [], [], []
    for _ in range(2000):
        pick = rng.choice(len(urls_), len(urls_))
        n_ = sum(cnt[urls_[i]][0] for i in pick)
        l_ = sum(cnt[urls_[i]][1] for i in pick)
        c_ = sum(cnt[urls_[i]][2] for i in pick)
        bl.append(l_ / n_), bc.append(c_ / n_), bt.append((l_ + c_) / n_)
    q = lambda v: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]
    summ["human"]["cluster_ci"] = {"link_lost": q(bl), "content_changed": q(bc), "lost_any": q(bt),
                                   "n_url_clusters": len(urls_)}
    tst = [r for r in chk if r["split"] == "test"]
    summ["human"]["test_only"] = {"checkable": len(tst),
                                  "link_lost": sum(r["class_human"] == "link_lost" for r in tst),
                                  "content_changed": sum(r["class_human"] == "content_changed" for r in tst)}
    summ["human"]["judge_miss_evidence_present"] = sum(r["judge_miss_evidence_present"] for r in rows)
    # evidence-only measure (no judge): reachable complete_support pairs whose evidence is fully gone
    ev = [r for r in rows if r["label_2023"] == "complete_support" and r["link_group"] == "reachable"
          and r["evidence_fuzzy_now_dom"] is not None]
    summ["evidence_only"] = {"n": len(ev), "fully_present": sum(r["evidence_fuzzy_now_dom"] >= 1 for r in ev),
                             "none_present": sum(r["evidence_fuzzy_now_dom"] == 0 for r in ev)}
    if "--human-only" in sys.argv:  # tool-mode scores are incomplete when only complete_support pairs were scored
        summ.pop("tool", None)
        for r in rows:
            r.pop("class_tool", None)
        with open(out_p, "w") as out:
            for r in rows:
                out.write(json.dumps(r) + "\n")
    json.dump(summ, open(sum_p, "w"), indent=1)
    print(json.dumps(summ["human"], indent=1)[:1500])


if __name__ == "__main__":
    main()
