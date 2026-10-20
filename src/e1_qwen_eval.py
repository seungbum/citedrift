"""E1: Qwen2.5-7B (4-bit) verdicts vs the 2023 human labels, alone and as a cascade.

Qwen "supported" counts as supported (partial/not as unsupported). Cascade:
the combined judge decides, except in the uncertain band (LO, HI) where Qwen
decides; the band is fixed a priori, not tuned. Test metrics with bootstrap CIs.

Usage: .venv/bin/python -I src/e1_qwen_eval.py <pairs> <qwen_jsonl> <combo_scores> <e1_eval_combo_json> <out_json>
"""
import json, sys

import numpy as np
from sklearn.metrics import balanced_accuracy_score as BA, f1_score

LO, HI = 0.6, 0.85


def boot_ba(y, yhat, n=1000, seed=0):
    rng = np.random.default_rng(seed)
    v = []
    for _ in range(n):
        i = rng.integers(0, len(y), len(y))
        v.append(BA(y[i], yhat[i]))
    return [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))]


def main():
    pairs_p, q_p, c_p, ev_p, out_p = sys.argv[1:6]
    P = {(r["split"], r["idx"]): r for r in map(json.loads, open(pairs_p))}
    Q = {(r["split"], r["idx"]): r for r in map(json.loads, open(q_p))}
    C = {(r["split"], r["idx"]): r["prob"] for r in map(json.loads, open(c_p))}
    thr = json.load(open(ev_p))["complete"]["threshold_dev"]
    res = {"band": [LO, HI]}
    for sp in ("dev", "test"):
        ks = [k for k in P if k[0] == sp]
        y = np.array([P[k]["label_2023"] == "complete_support" for k in ks], int)
        q = np.array([Q[k]["verdict"] == "supported" for k in ks], int)
        c = np.array([C[k] for k in ks])
        band = (c > LO) & (c < HI)
        casc = np.where(band, q, (c >= thr).astype(int))
        res[sp] = {"qwen_bal_acc": BA(y, q), "qwen_bal_acc_ci": boot_ba(y, q),
                   "qwen_f1_unsupported": f1_score(1 - y, 1 - q),
                   "qwen_supported_rate": float(q.mean()),
                   "cascade_bal_acc": BA(y, casc), "cascade_bal_acc_ci": boot_ba(y, casc),
                   "cascade_share_qwen": float(band.mean())}
    secs = [r["seconds"] for r in Q.values()]
    toks = [r["n_input_tokens"] for r in Q.values()]
    res["median_seconds"] = float(np.median(secs))
    res["p90_seconds"] = float(np.percentile(secs, 90))
    res["median_input_tokens"] = float(np.median(toks))
    json.dump(res, open(out_p, "w"), indent=1)
    print(json.dumps(res["test"], indent=1), res["median_seconds"])


if __name__ == "__main__":
    main()
