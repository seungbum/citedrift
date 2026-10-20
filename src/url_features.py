"""Per-URL features for link-state calibration.

For every cited URL (dev+test) combines the plain HTTP fetch with the one-time
browser re-check, picks the best available current HTML, and records:
current main text / DOM text lengths, title, the share of the 2023 text's
word 5-grams that still occur in the current DOM text ("containment"), and
title similarity to the 2023 <title>. Current texts are cached locally
(data/cache/now_text/, not redistributed) for the judge and the UI.

Usage: .venv/bin/python -I src/url_features.py <liu_dir> <pairs_jsonl> <live_dir> <browser_dir> <out_jsonl> [--browser-allow FILE]
  --browser-allow  use a browser re-check record only for the URLs listed (src/browser_allowlist.py; the
                   dev/test re-check rule), ignoring visits made under any broader rule
"""
import gzip, hashlib, json, os, sys

from rapidfuzz import fuzz

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from citedrift.textutil import containment, dom_text, html_title, main_text  # noqa: E402
from citedrift.markers import FILTER_MARKERS  # noqa: E402

CACHE = "data/cache/now_text"


def read_gz(path):
    with gzip.open(path, "rt", errors="replace") as h:
        return h.read()


def main():
    liu, pairs_path, live_dir, br_dir, out_path = sys.argv[1:6]
    os.makedirs(CACHE, exist_ok=True)
    old = {}  # url -> (2023 text, 2023 title); longest text if a URL appears in several pairs
    for sp in sorted({json.loads(l)["split"] for l in open(pairs_path)}):
        with gzip.open(os.path.join(liu, "verifiability_judgments",
                                    f"verifiability_judgments_{sp}.jsonl.gz"), "rt") as f:
            for line in f:
                j = json.loads(line)
                u = j["source_url"]
                if u not in old or len(j["source_text"]) > len(old[u][0]):
                    old[u] = (j["source_text"], j.get("source_title") or "")
    live = {r["url"]: r for r in map(json.loads, open(os.path.join(live_dir, "fetch_log.jsonl")))}
    br = {}
    bpath = os.path.join(br_dir, "browser_log.jsonl")
    if os.path.exists(bpath):
        br = {r["url"]: r for r in map(json.loads, open(bpath))}
    urls = list(dict.fromkeys(json.loads(l)["url"] for l in open(pairs_path)))
    if "--browser-allow" in sys.argv:
        allow = {l.strip() for l in open(sys.argv[sys.argv.index("--browser-allow") + 1]) if l.strip()}
        br = {u: b for u, b in br.items() if u in allow}
    with open(out_path, "w") as out:
        for u in urls:
            r, b = live.get(u), br.get(u)
            html, src = "", None
            if r and r.get("file"):
                html, src = read_gz(os.path.join(live_dir, "html", r["file"])), "http"
            filtered = any(m in html[:30000] for m in FILTER_MARKERS)
            use_browser = b is not None and b.get("outcome") == "browser" and b.get("file")
            if use_browser:
                html, src = read_gz(os.path.join(br_dir, "html", b["file"])), "browser"
            mt, dt = main_text(html), dom_text(html)
            key = hashlib.sha1(u.encode()).hexdigest()
            with gzip.open(os.path.join(CACHE, key + ".json.gz"), "wt") as f:
                json.dump({"url": u, "source": src, "main_text": mt, "dom_text": dt, "title": html_title(html)}, f)
            t23, title23 = old[u]
            # a page served by the checker's own network filter says nothing about the site: keep no title
            now_title = "" if filtered and not use_browser else html_title(html)
            out.write(json.dumps({
                "url": u, "key": key, "http_outcome": r.get("outcome") if r else None,
                "http_status": r.get("status") if r else None,
                "http_final_url": r.get("final_url") if r else None,
                "network_filtered_http": filtered,
                "browser_outcome": b.get("outcome") if b else None,
                "browser_status": b.get("status") if b else None,
                "browser_final_url": b.get("final_url") if b else None,
                "browser_challenge": b.get("challenge") if b else None,
                "browser_statuses": b.get("statuses") if b else None,
                "browser_error": (b.get("error") or "")[:120] if b else None,
                "text_source": src, "len_main_now": len(mt), "len_dom_now": len(dt),
                "len_2023": len(t23), "title_2023": title23[:200], "title_now": now_title[:200],
                "title_sim": fuzz.token_set_ratio(title23.lower(), now_title.lower()) if title23 and now_title else None,
                "containment_dom": containment(t23, dt), "containment_main": containment(t23, mt),
            }) + "\n")


if __name__ == "__main__":
    main()
