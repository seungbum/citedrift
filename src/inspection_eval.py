"""Step 1(c): compare the blinded spot-check labels with CiteDrift's outcomes.

Reads the key (item -> stratum) and the inspector's labels. Reports, per
stratum, how often the inspector agrees with the tool:
  content_changed  current page no longer FULLY supports the statement (partial or no)
  still_supported  current page fully supports the statement
  away             the URL now leads to a different document
cannot_tell answers are excluded from the denominators and counted separately.
The inspector was an independent AI agent (not a person) that saw only the
packets; see AI_USAGE_LOG.md.

With a drift file, a pair counts for its stratum only if its CURRENT outcome still belongs to that
stratum (e.g. a sampled content change that a later rule moved to "could not check" is dropped).

Usage: .venv/bin/python -I src/inspection_eval.py <key_csv> <labels_csv> <out_json> [current_drift_jsonl]
"""
import collections, csv, json, sys


def main():
    key_p, lab_p, out_p = sys.argv[1:4]
    key = {int(r["item"]): r for r in csv.DictReader(open(key_p))}
    cur = None
    if len(sys.argv) > 4:
        cur = {(r["split"], r["idx"]): r for r in map(json.loads, open(sys.argv[4]))}

    def still_in(k):
        if cur is None or k["stratum"] == "demoted":
            return True
        d = cur[(k["split"], int(k["idx"]))]
        return d["link_state"] == "away" if k["stratum"] == "away" else d["class_human"] == k["stratum"]
    lab = {int(r["item"]): r for r in csv.DictReader(open(lab_p))}
    res = {"n_key": len(key), "n_labels": len(lab), "inspector": "independent AI agent (blind to outcomes)"}
    strata = collections.defaultdict(list)
    for i, k in key.items():
        if i in lab and still_in(k):
            strata[k["stratum"]].append(lab[i])
    for s, rows in strata.items():
        res[s] = {"n": len(rows),
                  "current_support": dict(collections.Counter(r["current_support"] for r in rows)),
                  "evidence_now": dict(collections.Counter(r["evidence_now"] for r in rows)),
                  "same_document": dict(collections.Counter(r["same_document"] for r in rows))}

    def share(rows, field, ok, excl="cannot_tell"):
        v = [r[field] for r in rows if r[field] != excl]
        return sum(x in ok for x in v), len(v)

    cc = share(strata["content_changed"], "current_support", {"partial", "no"})
    ss = share(strata["still_supported"], "current_support", {"full"})
    aw = share(strata["away"], "same_document", {"different"})
    dm = share(strata.get("demoted", []), "current_support", {"full"})
    un = share(strata.get("uncertain", []), "current_support", {"partial", "no"})
    cc_ev = share(strata["content_changed"], "evidence_now", {"changed", "absent"})
    res["agreement"] = {"content_changed_not_full": cc, "content_changed_evidence_changed_or_absent": cc_ev,
                        "still_supported_full": ss, "away_different": aw,
                        "demoted_full": dm, "uncertain_not_full": un}
    fmt = lambda a: f"{a[0]} of {a[1]} ({100 * a[0] / a[1]:.0f}\\%)" if a[1] else "--"
    res["macros"] = {"insChangedN": str(len(strata["content_changed"])), "insChangedPrec": fmt(cc),
                     "insStillN": str(len(strata["still_supported"])), "insStillAgree": fmt(ss),
                     "insAwayN": str(len(strata["away"])), "insAwayDifferent": fmt(aw),
                     "insChangedEv": fmt(cc_ev), "insDemotedN": str(len(strata.get("demoted", []))),
                     "insDemotedFull": fmt(dm), "insUncertainN": str(len(strata.get("uncertain", []))),
                     "insUncertainNotFull": fmt(un)}
    json.dump(res, open(out_p, "w"), indent=1)
    print(json.dumps(res["agreement"]), res["macros"])


if __name__ == "__main__":
    main()
