"""Step 3: what link-only and string-matching checkers report for the citations CiteDrift flags.

Population: pairs whose 2023 human label is complete_support. For each
CiteDrift outcome we tabulate the urlhealth status of the URL and the verdict
of the string-matching baseline on the current page (statement 4-gram
overlap >= the dev-tuned threshold of that baseline on the 2023 text).
"Missed" = the baseline reports the citation as fine (urlhealth LIVE;
string match above threshold) although CiteDrift finds support lost. The string match sees the
same two views of today's page as CiteDrift (main text and DOM text, maximum).

Usage: .venv/bin/python -I src/baseline_compare.py <drift_jsonl> <urlhealth_jsonl> <e1_eval_ngram_json> \
          <pairs_jsonl> <url_features_jsonl> <out_json>
"""
import collections, gzip, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from baseline_ngram import ngram_score  # noqa: E402


def main():
    drift_p, uh_p, ng_p, pairs_p, feat_p, out_p = sys.argv[1:7]
    uh = {r["url"]: r["url_status"] for r in map(json.loads, open(uh_p))}
    ng_thr = json.load(open(ng_p))["complete"]["threshold_dev"]
    pairs = {(r["split"], r["idx"]): r for r in map(json.loads, open(pairs_p))}
    key = {r["url"]: r["key"] for r in map(json.loads, open(feat_p))}
    rows = [r for r in map(json.loads, open(drift_p)) if r["label_2023"] == "complete_support"]
    cache = {}
    tab = collections.defaultdict(collections.Counter)
    sm = collections.defaultdict(collections.Counter)
    for r in rows:
        tab[r["class_human"]][uh.get(r["url"], "NOT_RUN")] += 1
        if r["link_group"] == "reachable":
            if r["url"] not in cache:
                with gzip.open(os.path.join("data/cache/now_text", key[r["url"]] + ".json.gz"), "rt") as f:
                    cache.clear()
                    d = json.load(f)
                    cache[r["url"]] = (d["main_text"], d.get("dom_text", ""))
            st = pairs[(r["split"], r["idx"])]["statement"]
            s = max(ngram_score(st, cache[r["url"]][0]), ngram_score(st, cache[r["url"]][1]))  # same views as CiteDrift
            sm[r["class_human"]]["match" if s >= ng_thr else "no_match"] += 1
        else:
            sm[r["class_human"]]["no_page"] += 1
    lost = [r for r in rows if r["class_human"] in ("link_lost", "content_changed")]
    live_missed = sum(uh.get(r["url"]) == "LIVE" for r in lost)
    res = {"population": "complete_support pairs", "n": len(rows), "ngram_threshold": ng_thr,
           "urlhealth_by_class": {k: dict(v) for k, v in tab.items()},
           "stringmatch_by_class": {k: dict(v) for k, v in sm.items()},
           "lost_support_total": len(lost),
           "urlhealth_live_among_lost": live_missed,
           "urlhealth_live_among_link_lost": sum(uh.get(r["url"]) == "LIVE" for r in lost if r["class_human"] == "link_lost"),
           "n_link_lost": sum(r["class_human"] == "link_lost" for r in lost),
           "urlhealth_live_among_content_changed": sum(uh.get(r["url"]) == "LIVE" for r in lost if r["class_human"] == "content_changed"),
           "n_content_changed": sum(r["class_human"] == "content_changed" for r in lost),
           "stringmatch_match_among_content_changed": sm["content_changed"]["match"],
           "urlhealth_flagged_among_still": sum(uh.get(r["url"]) in ("DEAD", "LIKELY_HALLUCINATED") for r in rows
                                                if r["class_human"] == "still_supported"),
           "n_still": sum(r["class_human"] == "still_supported" for r in rows)}
    json.dump(res, open(out_p, "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
