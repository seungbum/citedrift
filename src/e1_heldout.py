"""E1 on a held-out split: combined judge (dev-fitted weights and threshold) vs the 2023 human labels.

Usage: .venv/bin/python -I src/e1_heldout.py <pairs_jsonl> <combo_scores_jsonl> <e1_eval_combo_json> <out_json>
"""
import json, sys

import numpy as np
from sklearn.metrics import balanced_accuracy_score, roc_auc_score


def main():
    pairs_p, sc_p, ev_p, out_p = sys.argv[1:5]
    P = {(r["split"], r["idx"]): r for r in map(json.loads, open(pairs_p))}
    C = {(r["split"], r["idx"]): r["prob"] for r in map(json.loads, open(sc_p))}
    thr = json.load(open(ev_p))["complete"]["threshold_dev"]
    ks = [k for k in C if k in P]
    y = np.array([P[k]["label_2023"] == "complete_support" for k in ks], int)
    p = np.array([C[k] for k in ks])
    res = {"n": len(ks), "auc": float(roc_auc_score(y, p)), "bal_acc": float(balanced_accuracy_score(y, p >= thr))}
    json.dump(res, open(out_p, "w"), indent=1)
    print(res)


if __name__ == "__main__":
    main()
