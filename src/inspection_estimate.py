"""Stratified estimate of content-level support loss, calibrated by the validation spot check.

Population: complete_support pairs on reachable pages (E2, human mode). Strata
match the validation sample: content_changed, uncertain, still_supported that
the looser rule had flagged ("demoted"), and the other still_supported. For
each stratum the share of inspected pairs that are no longer FULLY supported
today (partial or no; cannot_tell excluded) is applied to the stratum size.
95% CI by bootstrap over the inspected pairs within strata (2,000 draws, seed 0).
The inspector is an AI agent; this calibrates the tool against a second model,
not against people.

Usage: .venv/bin/python -I src/inspection_estimate.py <drift_jsonl> <rule1_drift_jsonl> <key2_csv> <labels2_csv> <out_json>
"""
import csv, json, sys

import numpy as np


def main():
    drift_p, rule1_p, key_p, lab_p, out_p = sys.argv[1:6]
    rows = [r for r in map(json.loads, open(drift_p))
            if r["label_2023"] == "complete_support" and r["link_group"] == "reachable"]
    old_cc = {(r["split"], r["idx"]) for r in map(json.loads, open(rule1_p)) if r["class_human"] == "content_changed"}

    def stratum(r):
        if r["class_human"] in ("content_changed", "uncertain"):
            return r["class_human"]
        return "demoted" if (r["split"], r["idx"]) in old_cc else "still_supported"

    size = {}
    for r in rows:
        size[stratum(r)] = size.get(stratum(r), 0) + 1
    key = {int(r["item"]): r for r in csv.DictReader(open(key_p))}
    lab = {int(r["item"]): r for r in csv.DictReader(open(lab_p))}
    obs = {}
    for i, k in key.items():
        if k["stratum"] in size and lab[i]["current_support"] != "cannot_tell":
            obs.setdefault(k["stratum"], []).append(lab[i]["current_support"] in ("partial", "no"))
    n_reach = len(rows)
    point = sum(size[s] * np.mean(obs[s]) for s in size) / n_reach
    rng = np.random.default_rng(0)
    boots = []
    for _ in range(2000):
        boots.append(sum(size[s] * np.mean(rng.choice(obs[s], len(obs[s]))) for s in size) / n_reach)
    # strict variant: only "no" counts as loss
    obs_no = {}
    for i, k in key.items():
        if k["stratum"] in size and lab[i]["current_support"] != "cannot_tell":
            obs_no.setdefault(k["stratum"], []).append(lab[i]["current_support"] == "no")
    point_no = sum(size[s] * np.mean(obs_no[s]) for s in size) / n_reach
    res = {"n_reachable": n_reach, "strata_sizes": size,
           "inspected": {s: len(v) for s, v in obs.items()},
           "not_full_share": {s: float(np.mean(v)) for s, v in obs.items()},
           "estimate_not_full": float(point), "ci": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))],
           "estimate_no_support": float(point_no)}
    json.dump(res, open(out_p, "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
