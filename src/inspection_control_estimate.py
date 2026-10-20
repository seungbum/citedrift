"""Drift beyond labeller disagreement: paired comparison of the agent's labels on today's page vs the 2023 text.

For each distinct pair of the validation sample we have two blind labels from AI agents:
on today's page (data/inspection2) and on the 2023 page text (data/inspection2_control).
loss = "not fully supported" (partial or no); pairs with cannot_tell in either are dropped.
Per stratum we report then/now loss shares and the paired excess (now-loss minus then-loss),
and a stratum-size-weighted estimate of the excess over the reachable supported citations,
with a bootstrap CI over pairs within strata (2,000 draws, seed 0).

Usage: .venv/bin/python -I src/inspection_control_estimate.py <key2> <labels2> <ctl_key> <ctl_labels> \
          <drift_jsonl> <rule1_drift_jsonl> <out_json>
"""
import csv, json, sys

import numpy as np

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from strata import old_flags, stratum as strat  # noqa: E402


def main():
    k2, l2, kc, lc, drift_p, rule1_p, out_p = sys.argv[1:8]
    lab2 = {int(r["item"]): r["current_support"] for r in csv.DictReader(open(l2))}
    labc = {int(r["item"]): r["current_support"] for r in csv.DictReader(open(lc))}
    now, key_stratum = {}, {}
    for r in csv.DictReader(open(k2)):
        k = (r["split"], int(r["idx"]))
        if k not in now:
            now[k], key_stratum[k] = lab2[int(r["item"])], r["stratum"]
    then = {(r["split"], int(r["idx"])): labc[int(r["item"])] for r in csv.DictReader(open(kc))}
    rows = [r for r in map(json.loads, open(drift_p))
            if r["label_2023"] == "complete_support" and r["link_group"] == "reachable"]
    old_cc = old_flags(rule1_p)
    stratum = lambda r: strat(r, old_cc)

    size = {}
    for r in rows:
        size[stratum(r)] = size.get(stratum(r), 0) + 1
    # pairs of the "away" stratum are not on reachable pages; others are re-assigned to population strata
    drift = {(r["split"], r["idx"]): r for r in map(json.loads, open(drift_p))}
    obs = {}
    for k in now:
        if now[k] == "cannot_tell" or then.get(k, "cannot_tell") == "cannot_tell":
            continue
        d = drift[k]
        if d["link_group"] != "reachable":
            continue
        s = stratum(d)
        obs.setdefault(s, []).append((then[k] in ("partial", "no"), now[k] in ("partial", "no")))
    res = {"strata_sizes": size, "per_stratum": {}}
    for s, v in obs.items():
        a = np.array(v, float)
        res["per_stratum"][s] = {"n": len(v), "then_loss": float(a[:, 0].mean()), "now_loss": float(a[:, 1].mean()),
                                 "excess": float((a[:, 1] - a[:, 0]).mean())}
    tot = sum(size.values())
    est = lambda o: sum(size[s] * np.mean([b - a for a, b in o[s]]) for s in size if s in o) / tot
    point = est(obs)
    rng = np.random.default_rng(0)
    boots = [est({s: [v[i] for i in rng.integers(0, len(v), len(v))] for s, v in obs.items()}) for _ in range(2000)]
    res["excess_estimate"] = float(point)
    res["excess_ci"] = [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))]
    ps = res["per_stratum"]
    pc = lambda x: f"{100 * x:.0f}\\%"
    res["macros"] = {"ctlExcess": pc(point), "ctlExcessCI": f"{100 * res['excess_ci'][0]:.0f}--{100 * res['excess_ci'][1]:.0f}\\%",
                     "ctlStillThen": pc(ps["still_supported"]["then_loss"]),
                     "ctlStillN": str(ps["still_supported"]["n"]),
                     "ctlStillNow": pc(ps["still_supported"]["now_loss"]),
                     "ctlChangedThen": pc(ps["content_changed"]["then_loss"]),
                     "ctlChangedN": str(ps["content_changed"]["n"]),
                     "ctlChangedNow": pc(ps["content_changed"]["now_loss"]),
                     "ctlChangedExcess": pc(ps["content_changed"]["excess"]),
                     "ctlStillExcess": pc(ps["still_supported"]["excess"])}
    json.dump(res, open(out_p, "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
