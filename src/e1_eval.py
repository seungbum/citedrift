"""E1: agreement of the local judge (on 2023 page text) with the 2023 human labels.

Binary target "supported" = complete_support (primary) or complete+partial
(secondary). The decision threshold is chosen on dev (max balanced accuracy)
and applied unchanged to test. Reports AUC, balanced accuracy, accuracy and
the F1 of the "not supported" class, each with a 95% bootstrap CI on test
(1,000 resamples of pairs, seed 0), plus the fixed 0.5 threshold.

Usage: .venv/bin/python -I src/e1_eval.py <pairs_jsonl> <scores_jsonl> <out_json>
"""
import json, sys

import numpy as np
from sklearn.metrics import balanced_accuracy_score, f1_score, roc_auc_score

TARGETS = {"complete": {"complete_support"}, "complete_or_partial": {"complete_support", "partial_support"}}


def metrics(y, p, thr):
    yhat = (p >= thr).astype(int)
    return {"auc": roc_auc_score(y, p), "bal_acc": balanced_accuracy_score(y, yhat),
            "acc": float((yhat == y).mean()), "f1_unsupported": f1_score(1 - y, 1 - yhat)}


def best_threshold(y, p):
    grid = np.unique(np.round(p, 4))
    return float(max(grid, key=lambda t: balanced_accuracy_score(y, (p >= t).astype(int))))


def boot(y, p, thr, n=1000, seed=0):
    rng = np.random.default_rng(seed)
    out = {k: [] for k in ("auc", "bal_acc", "acc", "f1_unsupported")}
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        if y[i].min() == y[i].max():
            continue
        for k, v in metrics(y[i], p[i], thr).items():
            out[k].append(v)
    return {k: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] for k, v in out.items()}


def main():
    pairs_path, scores_path, out_path = sys.argv[1:4]
    pairs = {(r["split"], r["idx"]): r for r in map(json.loads, open(pairs_path))}
    scores = {(r["split"], r["idx"]): r["prob"] for r in map(json.loads, open(scores_path))}
    res = {"scores": scores_path, "n": {}}
    for name, pos in TARGETS.items():
        d = {}
        for sp in ("dev", "test"):
            ks = [k for k in pairs if k[0] == sp and k in scores]
            d[sp] = (np.array([pairs[k]["label_2023"] in pos for k in ks], int),
                     np.array([scores[k] for k in ks]), [pairs[k]["engine"] for k in ks])
            res["n"][sp] = len(ks)
        thr = best_threshold(d["dev"][0], d["dev"][1])
        yt, pt, et = d["test"]
        r = {"threshold_dev": thr, "test": metrics(yt, pt, thr), "test_ci": boot(yt, pt, thr),
             "test_thr0.5": metrics(yt, pt, 0.5), "dev": metrics(*d["dev"][:2], thr),
             "test_pos_rate": float(yt.mean()), "by_engine_test": {}}
        for e in sorted(set(et)):
            m = np.array([x == e for x in et])
            if yt[m].min() != yt[m].max():
                r["by_engine_test"][e] = dict(n=int(m.sum()), **metrics(yt[m], pt[m], thr))
        res[name] = r
    json.dump(res, open(out_path, "w"), indent=1)
    for name in TARGETS:
        r = res[name]
        print(name, "thr=%.3f" % r["threshold_dev"],
              {k: round(v, 3) for k, v in r["test"].items()},
              {k: [round(x, 3) for x in v] for k, v in r["test_ci"].items()})


if __name__ == "__main__":
    main()
