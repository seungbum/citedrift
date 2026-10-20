"""Sampling strata of the validation spot check, shared by every estimator that weights it.

The validation sample (data/inspection2) was drawn from these strata: content changes, uncertain pairs,
still-supported pairs and "away" links, plus a "demoted" stratum of pairs that an earlier, looser rule had
flagged as content changes (results/e2_drift_rule1.jsonl). Demoted pairs were sampled at a much higher
rate than the classes they now belong to, so they are kept as separate strata. Pairs on dead/error pages
(link lost without a redirect) are not sampled; estimators include all of them.
"""
import json


def old_flags(rule1_path):
    return {(r["split"], r["idx"]) for r in map(json.loads, open(rule1_path)) if r["class_human"] == "content_changed"}


def stratum(d, old):
    """d: one e2_drift.jsonl row (current outcome); old: keys flagged by the earlier rule."""
    if d["link_group"] == "lost":
        return "away" if d["link_state"] == "away" else "dead"
    c = d["class_human"]
    if c in ("still_supported", "uncertain"):
        return c + ("_demoted" if (d["split"], d["idx"]) in old else "")
    return c  # content_changed
