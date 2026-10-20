"""Provenance of the "moved" redirect thresholds (5-gram containment >= 0.3 or title similarity >= 90).

The thresholds were set by looking at two reference groups before the evaluation: pages that kept their URL
(same document by construction) and redirects to a site root (a different document by construction). This
script recomputes the containment and title-similarity distributions of both groups from url_features.jsonl.

Usage: .venv/bin/python -I src/threshold_provenance.py <url_features_jsonl> <out_json>
"""
import json, sys, urllib.parse

import numpy as np


def main():
    feats = [json.loads(l) for l in open(sys.argv[1])]
    same, root = [], []
    for f in feats:
        fin = f["browser_final_url"] or f["http_final_url"]
        st = f["browser_status"] or f["http_status"]
        if not fin or st != 200 or f["containment_dom"] is None:
            continue
        a, b = urllib.parse.urlsplit(f["url"]), urllib.parse.urlsplit(fin)
        if a.netloc.removeprefix("www.") == b.netloc.removeprefix("www.") and a.path.rstrip("/") == b.path.rstrip("/"):
            same.append(f)
        elif not b.path.strip("/"):
            root.append(f)
    q = lambda v: [round(float(x), 3) for x in np.percentile(v, [10, 25, 50, 75, 90])] if v else None
    res = {}
    for name, g in (("same_url", same), ("redirect_to_site_root", root)):
        c = [f["containment_dom"] for f in g]
        t = [f["title_sim"] for f in g if f["title_sim"] is not None]
        res[name] = {"n": len(g), "containment_p10_25_50_75_90": q(c), "title_sim_p10_25_50_75_90": q(t),
                     "share_containment_ge_0.3": float(np.mean([x >= 0.3 for x in c])) if c else None,
                     "share_title_ge_90": float(np.mean([x >= 90 for x in t])) if t else None}
    json.dump(res, open(sys.argv[2], "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
