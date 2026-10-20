"""Which URLs may use their browser re-check record, by the dev/test rule.

The dev/test browser re-check covered (a) refused pages: plain fetch timed out, failed, or answered
401/403/429/5xx, unless the answer came from the checker's own network filter (recheck_browser.targets), and
(b) two extra lists built from the plain fetch: HTTP 200 with under 200 characters of main text
(extra_short_text), and HTTP 202/405 or a short page (< 1,500 characters) whose text starts with a bot-wall
marker (extra_botwall). This script applies exactly that rule to a pairs file and writes the allowed URLs, so
that a split processed later (the held-out train split) uses browser records only where dev/test would have.

Usage: .venv/bin/python -I src/browser_allowlist.py <pairs_jsonl> <live_dir> <out_txt>
"""
import gzip, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from citedrift.markers import CHALLENGE_MARKERS, FILTER_MARKERS  # noqa: E402
from citedrift.textutil import main_text  # noqa: E402


def main():
    pairs_p, live_dir, out_p = sys.argv[1:4]
    urls = set(json.loads(l)["url"] for l in open(pairs_p))
    allow = []
    for r in map(json.loads, open(os.path.join(live_dir, "fetch_log.jsonl"))):
        u = r["url"]
        if u not in urls:
            continue
        html = ""
        if r.get("file"):
            with gzip.open(os.path.join(live_dir, "html", r["file"]), "rt", errors="replace") as h:
                html = h.read()
        if any(m in html[:30000] for m in FILTER_MARKERS):
            continue
        o, st = r.get("outcome"), r.get("status") or 0
        refused = o in ("timeout", "connection_error", "ssl_error", "error") or \
            (o == "http" and (st in (401, 403, 429) or st >= 500))
        mt = main_text(html) if o == "http" else ""
        head = mt[:500].lower()
        short200 = o == "http" and st == 200 and len(mt) < 200
        botwall = o == "http" and (st in (202, 405) or (len(mt) < 1500 and any(m in head for m in CHALLENGE_MARKERS)))
        if refused or short200 or botwall:
            allow.append(u)
    open(out_p, "w").write("\n".join(sorted(allow)) + "\n")
    print(len(allow), "URLs may use their browser record")


if __name__ == "__main__":
    main()
