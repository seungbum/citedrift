"""Fit the combined judge on dev: logistic regression on [logit(MiniCheck prob), 4-gram overlap].

Target is complete_support. Coefficients are fitted on dev only and saved;
scores for all pairs are written in the judge format so that e1_eval.py picks
the threshold on dev and reports test.

Usage: .venv/bin/python -I src/e1_combo.py <pairs_jsonl> <minicheck_scores> <ngram_scores> <out_scores> <out_params_json>
"""
import json, sys

import numpy as np
from sklearn.linear_model import LogisticRegression


def logit(p):
    p = np.clip(np.asarray(p, float), 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def combine(params, minicheck_prob, ngram):
    z = params["intercept"] + params["w_minicheck_logit"] * logit(minicheck_prob) + params["w_ngram"] * np.asarray(ngram)
    return 1 / (1 + np.exp(-z))


def main():
    pairs_path, mc_path, ng_path, out_path, par_path = sys.argv[1:6]
    P = {(r["split"], r["idx"]): r for r in map(json.loads, open(pairs_path))}
    M = {(r["split"], r["idx"]): r["prob"] for r in map(json.loads, open(mc_path))}
    G = {(r["split"], r["idx"]): r["prob"] for r in map(json.loads, open(ng_path))}
    dev = [k for k in P if k[0] == "dev"]
    X = np.c_[logit([M[k] for k in dev]), [G[k] for k in dev]]
    y = np.array([P[k]["label_2023"] == "complete_support" for k in dev], int)
    lr = LogisticRegression().fit(X, y)
    params = {"intercept": float(lr.intercept_[0]), "w_minicheck_logit": float(lr.coef_[0, 0]),
              "w_ngram": float(lr.coef_[0, 1]), "fitted_on": "dev", "target": "complete_support"}
    json.dump(params, open(par_path, "w"), indent=1)
    with open(out_path, "w") as out:
        for k in P:
            out.write(json.dumps({"split": k[0], "idx": k[1],
                                  "prob": float(combine(params, M[k], G[k]))}) + "\n")
    print(params)


if __name__ == "__main__":
    main()
