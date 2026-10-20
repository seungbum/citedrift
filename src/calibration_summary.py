"""Step 1 calibration: how the link-state picture changes from a plain HTTP fetch to the calibrated states.

Compares, per distinct URL, the first-pass state (drift_basic.py, plain fetch,
URL-path redirect rule) with the calibrated state (citedrift.linkstate:
browser re-check, network-filter detection, content-based redirect rule,
bot-wall text markers). Also summarises the Wayback re-query of URLs that
urlhealth labelled LIKELY_HALLUCINATED.

Usage: .venv/bin/python -I src/calibration_summary.py <drift_basic_jsonl> <url_features_jsonl> \
          <browser_log_jsonl> <wayback_gaps_jsonl> <out_json>
"""
import collections, gzip, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from citedrift.linkstate import GROUP, classify  # noqa: E402

V1_GROUP = {"alive": "reachable", "blocked_or_paywalled": "blocked", "dead_http": "lost", "soft404_or_empty": "lost",
            "redirect_home": "redirect", "redirect_other_page": "redirect", "redirect_other_site": "redirect",
            "unreachable": "unreachable", "robots_disallowed": "skipped", "not_fetched": "skipped"}


def main():
    v1_p, feat_p, br_p, wb_p, out_p = sys.argv[1:6]
    v1 = {}
    for r in map(json.loads, open(v1_p)):
        v1[r["url"]] = r["link_state"]
    feats = [json.loads(l) for l in open(feat_p)]
    v2 = {}
    for f in feats:
        with gzip.open(os.path.join("data/cache/now_text", f["key"] + ".json.gz"), "rt") as h:
            v2[f["url"]] = classify(f, json.load(h).get("main_text", "")[:500])
    n = len(v2)
    trans = collections.Counter((V1_GROUP[v1[u]], v2[u]) for u in v2)
    br = [json.loads(l) for l in open(br_p)]
    wb = [json.loads(l) for l in open(wb_p)]
    filt = {f["url"] for f in feats if f["network_filtered_http"]}
    res = {
        "n_urls": n,
        "v1_states": collections.Counter(v1[u] for u in v2),
        "v1_groups": collections.Counter(V1_GROUP[v1[u]] for u in v2),
        "v2_states": collections.Counter(v2.values()),
        "v2_groups": collections.Counter(GROUP[s] for s in v2.values()),
        "transitions": {f"{a}->{b}": c for (a, b), c in sorted(trans.items())},
        "network_filtered": sum(f["network_filtered_http"] for f in feats),
        "browser_rechecked": len(br),
        "browser_outcomes": collections.Counter(
            "error" if r["outcome"] == "browser_error" else ("bot_wall" if r.get("challenge") else f"http_{r.get('status')}")
            for r in br),
        "v1_blocked_now": collections.Counter(v2[u] for u in v2 if V1_GROUP[v1[u]] == "blocked"),
        "v1_blocked_tried_in_browser": sum(V1_GROUP[v1[u]] == "blocked" and u in {r["url"] for r in br} for u in v2),
        "v1_redirect_now": collections.Counter(v2[u] for u in v2 if V1_GROUP[v1[u]] == "redirect"),
        "wayback_requery": {
            "n": len(wb),
            "has_capture": sum(bool(x["avail_found"]) or bool(x["cdx_rows"]) for x in wb),
            "availability_429": sum(x["avail_status"] == 429 for x in wb),
            "no_capture_found": sum(not (x["avail_found"] or x["cdx_rows"]) for x in wb),
            "answered_by_network_filter": sum(x["url"] in filt for x in wb),
            "reachable_now": sum(GROUP[v2[x["url"]]] == "reachable" for x in wb),
        },
    }
    json.dump(res, open(out_p, "w"), indent=1)
    print(json.dumps({k: res[k] for k in ("v1_groups", "v2_groups", "v1_blocked_now", "v1_redirect_now",
                                         "wayback_requery", "browser_outcomes")}, indent=1))


if __name__ == "__main__":
    main()
