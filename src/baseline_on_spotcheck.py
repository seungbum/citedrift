"""Baselines vs CiteDrift, estimated over all checkable citations with the validation spot check as reference.

Population: complete_support pairs whose link could be checked (link group reachable or lost).
Reference "support lost": for pairs on dead / error / empty pages, lost by definition (the cited page is gone);
for all other pairs, the AI agent's current_support label (partial or no), available for a stratified random
sample (data/inspection2; cannot_tell dropped; each distinct pair once).
Strata follow the sample design (src/strata.py): still_supported and uncertain, each split into pairs an earlier
looser rule had flagged ("_demoted", sampled at a far higher rate) and the rest; content_changed; and link_lost
via redirect ("away"), all by the pair's current CiteDrift outcome. Sampled pairs get weight N_stratum / n_sampled.
The reference for sampled pairs is the agent's 2026 label, which includes agent-vs-annotator disagreement
(see inspection_control_estimate.py); it therefore lowers every method's recall.
Dead/error-page pairs are all included with weight 1 (no sample needed).
Flags:
  CiteDrift     outcome content_changed or link_lost
  urlhealth     URL status other than LIVE
  string match  statement 4-gram overlap with today's page (max of main and DOM text) below the
                dev-tuned threshold, or the link is lost (dead, error page, or redirected to another document)
Also reports the unweighted within-sample figures. Bootstrap CIs resample pairs within sampled strata.

Usage: .venv/bin/python -I src/baseline_on_spotcheck.py <key_csv> <labels_csv> <drift_jsonl> <urlhealth_jsonl> \
          <e1_eval_ngram_json> <pairs_jsonl> <url_features_jsonl> <out_json> <rule1_drift_jsonl>
"""
import csv, gzip, json, os, sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from baseline_ngram import ngram_score  # noqa: E402
from strata import old_flags, stratum as strat  # noqa: E402

METHODS = ("citedrift", "urlhealth", "stringmatch")


def prf(rows):
    out = {}
    for m in METHODS:
        tp = sum(w for w, t, f in ((r["w"], r["truth"], r[m]) for r in rows) if f and t)
        fl = sum(r["w"] for r in rows if r[m])
        lost = sum(r["w"] for r in rows if r["truth"])
        p = tp / fl if fl else 0.0
        rc = tp / lost if lost else 0.0
        out[m] = {"precision": p, "recall": rc, "f1": 2 * p * rc / (p + rc) if p + rc else 0.0}
    return out


def main():
    key_p, lab_p, drift_p, uh_p, ng_p, pairs_p, feat_p, out_p, rule1_p = sys.argv[1:10]
    old = old_flags(rule1_p)
    stratum = lambda d: strat(d, old)
    lab = {int(r["item"]): r for r in csv.DictReader(open(lab_p))}
    D = {(r["split"], r["idx"]): r for r in map(json.loads, open(drift_p))}
    P = {(r["split"], r["idx"]): r for r in map(json.loads, open(pairs_p))}
    uh = {r["url"]: r["url_status"] for r in map(json.loads, open(uh_p))}
    thr = json.load(open(ng_p))["complete"]["threshold_dev"]
    fk = {r["url"]: r["key"] for r in map(json.loads, open(feat_p))}
    cache = {}

    def flags(k):
        d = D[k]
        if d["url"] not in cache:
            with gzip.open(os.path.join("data/cache/now_text", fk[d["url"]] + ".json.gz"), "rt") as f:
                t = json.load(f)
            cache[d["url"]] = (t.get("main_text", ""), t.get("dom_text", ""))
        mt, dt = cache[d["url"]]
        sm = max(ngram_score(P[k]["statement"], mt), ngram_score(P[k]["statement"], dt))
        return {"citedrift": d["class_human"] in ("content_changed", "link_lost"),
                "urlhealth": uh.get(d["url"], "NOT_RUN") != "LIVE",
                "stringmatch": d["link_group"] != "reachable" or sm < thr}

    pop = [k for k, d in D.items() if d["label_2023"] == "complete_support" and d["link_group"] in ("reachable", "lost")]
    size = {}
    for k in pop:
        size[stratum(D[k])] = size.get(stratum(D[k]), 0) + 1
    seen, sample = set(), {}
    for r in sorted(csv.DictReader(open(key_p)), key=lambda r: int(r["item"])):
        k = (r["split"], int(r["idx"]))
        if k in seen:
            continue
        seen.add(k)
        lb = lab[int(r["item"])]["current_support"]
        if lb == "cannot_tell" or k not in set(pop):
            continue
        s = stratum(D[k])
        if s == "dead":
            continue  # dead pages are covered in full below
        sample.setdefault(s, []).append(dict(flags(k), truth=lb in ("partial", "no"), key=k))
    dead = [dict(flags(k), truth=True, w=1.0) for k in pop if stratum(D[k]) == "dead"]

    def weighted(smp):
        rows = list(dead)
        for s, v in smp.items():
            for r in v:
                rows.append(dict(r, w=size[s] / len(v)))
        return rows

    res = {"population_pairs": len(pop), "strata_sizes": size, "sampled": {s: len(v) for s, v in sample.items()},
           "dead_pairs": len(dead), "weighted": prf(weighted(sample)),
           "within_sample": prf([dict(r, w=1.0) for v in sample.values() for r in v]),
           "within_sample_n": sum(len(v) for v in sample.values()),
           "within_sample_lost": sum(r["truth"] for v in sample.values() for r in v)}
    rng = np.random.default_rng(0)
    boots = {m: {"precision": [], "recall": [], "f1": []} for m in METHODS}
    for _ in range(1000):
        smp = {s: [v[i] for i in rng.integers(0, len(v), len(v))] for s, v in sample.items()}
        for m, d in prf(weighted(smp)).items():
            for q in ("precision", "recall", "f1"):
                boots[m][q].append(d[q])
    res["weighted_ci"] = {m: {q: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] for q, v in d.items()}
                          for m, d in boots.items()}
    res["p_f1_citedrift_gt_stringmatch"] = float(np.mean([a > b for a, b in zip(boots["citedrift"]["f1"],
                                                                              boots["stringmatch"]["f1"])]))
    json.dump(res, open(out_p, "w"), indent=1)
    print(json.dumps({k: res[k] for k in ("population_pairs", "strata_sizes", "sampled", "dead_pairs", "weighted")}, indent=1))


if __name__ == "__main__":
    main()
