"""Apply the dev-fitted combined judge (results/judge_combo_params.json) to new pairs, e.g. the held-out train split.

Usage: .venv/bin/python -I src/apply_combo.py <minicheck_scores> <ngram_scores> <params_json> <out_scores>
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from e1_combo import combine  # noqa: E402


def main():
    mc_p, ng_p, par_p, out_p = sys.argv[1:5]
    params = json.load(open(par_p))
    G = {(r["split"], r["idx"]): r["prob"] for r in map(json.loads, open(ng_p))}
    with open(out_p, "w") as out:
        for r in map(json.loads, open(mc_p)):
            k = (r["split"], r["idx"])
            out.write(json.dumps({"split": k[0], "idx": k[1], "prob": float(combine(params, r["prob"], G[k]))}) + "\n")


if __name__ == "__main__":
    main()
