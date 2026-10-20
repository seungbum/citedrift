"""E1: judge vs string matching on abstractive statements (low word overlap with the 2023 page).

Subset: test pairs whose statement 4-gram overlap with the 2023 text is below
CUT (fixed a priori). Reports the subset size and the AUC of MiniCheck, the
string-match baseline and the combined judge, with bootstrap CIs.

Usage: .venv/bin/python -I src/e1_subset.py <pairs> <minicheck_scores> <ngram_scores> <combo_scores> <out_json>
"""
import json, sys

import numpy as np
from sklearn.metrics import roc_auc_score

CUT = 0.3


def ci(y, p, n=1000, seed=0):
    rng = np.random.default_rng(seed)
    v = []
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        if y[i].min() != y[i].max():
            v.append(roc_auc_score(y[i], p[i]))
    return [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]


def main():
    pairs_p, mc_p, ng_p, co_p, out_p = sys.argv[1:6]
    P = {(r["split"], r["idx"]): r for r in map(json.loads, open(pairs_p))}
    load = lambda p: {(r["split"], r["idx"]): r["prob"] for r in map(json.loads, open(p))}
    M, G, C = load(mc_p), load(ng_p), load(co_p)
    ks = [k for k in P if k[0] == "test" and G[k] < CUT]
    y = np.array([P[k]["label_2023"] == "complete_support" for k in ks], int)
    res = {"cut": CUT, "n": len(ks), "n_test": sum(k[0] == "test" for k in P), "pos_rate": float(y.mean())}
    for name, S in (("minicheck", M), ("ngram", G), ("combo", C)):
        p = np.array([S[k] for k in ks])
        res[name] = {"auc": float(roc_auc_score(y, p)), "ci": ci(y, p)}
    json.dump(res, open(out_p, "w"), indent=1)
    print(res)


if __name__ == "__main__":
    main()
